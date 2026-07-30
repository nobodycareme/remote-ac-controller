#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门禁五 — srun-c vendored-C 算法真实验证（native PC-side orchestrator）。

本脚本证明：vendored 的 srun-c 实现（lib/srun-c）就是 AUTHORITATIVE 上游实现，
且其算法被固件真正调用。与旧版只跑 Python 参考不同，本版要求：

  1. SHA256 字节一致：lib/srun-c 中 7 个上游一致文件必须与固定提交
     1881da8fa98e52041fb92f38888b3d5eb4789f7a（克隆于 F:/PIO/srun-c-src）逐字节一致；
     第 8 个文件（esp8266 HTTP 适配器）是唯一允许的偏离：证书固定代替 setInsecure。

  2. 符号存在：规范 srun v2 符号必须存在于 vendored 源码。

  3. 上游 HEAD 校验：git rev-parse HEAD 必须 == 1881da8...（门禁五.7）。

  4. 真实 C 向量比对（门禁五.1-五.6）：ESP8266 测试固件
     (src/srun_c_vector_test.cpp + lib/srun-c/src/esp8266_mock_adapter.cpp，
     环境 nodemcuv2_srun_c_vector) 实际调用 vendored C 实现（srun_login），
     由 mock 适配器返回固定 challenge token（无网络、无凭据），从捕获的门户
     请求 URL 中提取 HMAC-MD5 / {SRBX1} info / SHA-1 chksum。本脚本用相同的
     固定输入（testuser/testpass/a1b2c3d4e5f6/10.1.2.3/ac_id=8/srun_bx1）计算
     Python 参考，并与设备实测值逐字节比较。只有完全一致才输出
     SRUN_VENDOR_C_VECTOR_PASS。

  5. 旧实现排除：rejected 源码仅存在于 archive/，不在 src/ 或 lib/ 构建树。

证据：写入 logs/srun_vendor_integrity.log 与
docs/03_协议与接口/_srun_c_vector_evidence.json（commit / 源文件 SHA256 /
C 值 / Python 值 / 比对结果）。

退出码 0 当且仅当所有门禁通过。
"""
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys

ROOT = r"F:\PIO\Projects\Remote_AC_Controller"
VEN = os.path.join(ROOT, "lib", "srun-c")
UP = r"F:\PIO\srun-c-src"
OUT = os.path.join(ROOT, "logs", "srun_vendor_integrity.log")
EVIDENCE = os.path.join(ROOT, "docs", "03_协议与接口", "_srun_c_vector_evidence.json")
PINNED_HEAD = "1881da8fa98e52041fb92f38888b3d5eb4789f7a"

# (vendored file, upstream file) — byte-identity expected
IDENTICAL_PAIRS = [
    ("include/srun.h", "srun.h"),
    ("include/compat.h", "platform/compat.h"),
    ("src/srun.c", "srun.c"),
    ("src/md.c", "platform/md.c"),
    ("src/arduinojson.cpp", "platform/arduinojson.cpp"),
    ("LICENSE", "LICENSE"),
    ("README_UPSTREAM.md", "README.md"),
]
ADAPTER_PAIR = ("src/esp8266_http_adapter_secure.cpp", "platform/esp8266_arduino_http.cpp")

REQUIRED_SYMBOLS = [
    "hmac_md5_digest",
    "x_encode",
    "{SRBX1}",
    "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA",
    'CHALL_N "200"',
    'CHALL_TYPE "1"',
    "%%7BMD5%%7D",
]

SRUN_B64 = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"

# 固定输入：必须与 mock 适配器返回的 token 及 srun_c_vector_test.cpp 完全一致。
FIXED = {
    "username": "testuser",
    "password": "testpass",
    "token": "a1b2c3d4e5f6",     # mock kChallengeJson challenge
    "ip": "10.1.2.3",
    "ac_id": 8,
    "enc_ver": "srun_bx1",
    "chall_n": "200",
    "chall_type": "1",
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- Python reference re-implementation of canonical srun v2 encoding ----
def s_encode(msg, append_len):
    msg_len = len(msg)
    buf_len = ((msg_len + 3) // 4) * 4
    buf = bytes(msg) + b"\x00" * (buf_len - msg_len)
    dst = [0] * (buf_len // 4)
    for i in range(0, msg_len, 4):
        dst[i // 4] = (buf[i + 3] << 24) | (buf[i + 2] << 16) | (buf[i + 1] << 8) | buf[i]
    if append_len:
        dst.append(msg_len)
    return dst


def s_decode(msg):
    ret_len = len(msg) * 4
    out = bytearray(ret_len)
    for i in range(ret_len):
        out[i] = (msg[i // 4] >> (i % 4 * 8)) & 0xFF
    return bytes(out)


def x_encode(src, key):
    if len(src) == 0:
        return b""
    key = key[:16]
    n = (len(src) + 3) // 4 + 1
    encoded_msg = s_encode(src, True)
    encoded_key = s_encode(key, False)
    while len(encoded_key) < 4:
        encoded_key.append(0)
    d = 0
    for _ in range(6 + 52 // n):
        d = (d + 0x9E3779B9) & 0xFFFFFFFF
        z = encoded_msg[n - 1]
        for p in range(n):
            y = encoded_msg[(p + 1) % n]
            encoded_msg[p] = (encoded_msg[p] + ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4 ^ d ^ y)
                              + (encoded_key[(p ^ d >> 2) & 3] ^ z))) & 0xFFFFFFFF
            z = encoded_msg[p]
    return s_decode(encoded_msg)


def b64_encode(src):
    out = []
    for i in range(0, len(src), 3):
        b0 = src[i]
        b1 = src[i + 1] if i + 1 < len(src) else 0
        b2 = src[i + 2] if i + 2 < len(src) else 0
        n = (b0 << 16) | (b1 << 8) | b2
        for j in range(4):
            out.append(SRUN_B64[(n >> (18 - j * 6)) & 0x3F])
    mod = len(src) % 3
    if mod == 1:
        out[-2] = out[-1] = "="
    elif mod == 2:
        out[-1] = "="
    return "".join(out)


def reference_vector():
    """Compute the Python reference values that MUST match the device C output."""
    username = FIXED["username"]
    password = FIXED["password"]
    token = FIXED["token"]
    ip = FIXED["ip"]
    ac_id = FIXED["ac_id"]
    enc_ver = FIXED["enc_ver"]

    # 关键：srun.c 调用 hmac_md5_digest(password, token) => key=password, data=token。
    hmac_hex = hmac.new(password.encode(), token.encode(), hashlib.md5).hexdigest()

    info = json.dumps({"username": username, "password": password, "ip": ip,
                       "acid": ac_id, "enc_ver": enc_ver}, separators=(",", ":"))
    xenc = x_encode(info.encode(), token.encode())
    b64info = "{SRBX1}" + b64_encode(xenc)

    sha_msg = (token + username + token + hmac_hex + token + str(ac_id) + token + ip
               + token + FIXED["chall_n"] + token + FIXED["chall_type"] + token + b64info)
    chksum = hashlib.sha1(sha_msg.encode()).hexdigest()
    return {"hmac": hmac_hex, "info_b64": b64info, "chksum": chksum}


def check_identical():
    print("=== 1) SHA256 byte-identity vs pinned upstream commit %s ===" % PINNED_HEAD[:12])
    ok = True
    manifest = {}
    for vrel, urel in IDENTICAL_PAIRS:
        vp = os.path.join(VEN, vrel)
        up = os.path.join(UP, urel)
        if not os.path.exists(vp):
            print("  FAIL missing vendored: %s" % vrel)
            ok = False
            continue
        vh = sha256_of(vp)
        manifest[vrel] = vh
        if not os.path.exists(up):
            print("  WARN upstream missing %s; vendored sha256=%s" % (urel, vh[:16]))
            continue
        uh = sha256_of(up)
        same = vh == uh
        ok = ok and same
        print("  %s %-32s %s..." % ("PASS" if same else "FAIL", vrel, vh[:16]))
        if not same:
            print("        upstream %s..." % uh[:16])
    av, au = ADAPTER_PAIR
    avp, aup = os.path.join(VEN, av), os.path.join(UP, au)
    if os.path.exists(avp) and os.path.exists(aup):
        diff = sha256_of(avp) != sha256_of(aup)
        print("  %s adapter %s differs from upstream %s" %
              ("PASS(deviation expected)" if diff else "UNEXPECTED", av, au))
        ok = ok and diff
    man_dir = os.path.join(ROOT, "docs", "03_协议与接口")
    os.makedirs(man_dir, exist_ok=True)
    with open(os.path.join(man_dir, "_srun_sha256_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("  manifest written: docs/03_协议与接口/_srun_sha256_manifest.json (%d files)" % len(manifest))
    return ok


def check_symbols():
    print("=== 2) Required canonical srun v2 symbols present in vendored sources ===")
    blob = ""
    for rel in ("src/srun.c", "src/md.c", "include/compat.h", "include/srun.h"):
        p = os.path.join(VEN, rel)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                blob += f.read()
    ok = True
    for sym in REQUIRED_SYMBOLS:
        present = sym in blob
        ok = ok and present
        print("  %s symbol: %s" % ("PASS" if present else "FAIL", sym))
    return ok


def check_git_head():
    print("=== 3) Upstream repo HEAD == %s (门禁五.7) ===" % PINNED_HEAD[:12])
    try:
        head = subprocess.check_output(
            ["git", "-C", UP, "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()
    except Exception as e:
        print("  FAIL git rev-parse failed: %s" % e)
        return False, None
    ok = (head == PINNED_HEAD)
    print("  %s upstream HEAD = %s" % ("PASS" if ok else "FAIL", head))
    if not ok:
        print("  EXPECTED %s" % PINNED_HEAD)
    return ok, head


def parse_c_vector_from_log(log_path):
    """Parse SRUN_C_HMAC_MD5 / SRUN_C_INFO_B64 / SRUN_C_CHKSUM from a captured
    device serial log produced by the nodemcuv2_srun_c_vector firmware."""
    vals = {}
    if not os.path.exists(log_path):
        return vals
    pat = re.compile(r"SRUN_C_(HMAC_MD5|INFO_B64|CHKSUM)=(\S+)")
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pat.search(line)
            if m:
                vals[m.group(1).lower()] = m.group(2).strip()
    return vals


def compare_c_vector():
    print("=== 4) Vendored-C actual output vs Python reference (byte-for-byte) ===")
    ref = reference_vector()
    log_path = os.path.join(ROOT, "logs", "srun_c_vector_serial.log")
    if len(sys.argv) > 1:
        log_path = sys.argv[1]
    cvals = parse_c_vector_from_log(log_path)
    print("  device log : %s" % log_path)
    print("  C HMAC_MD5  = %s" % cvals.get("hmac_md5", "<MISSING>"))
    print("  C INFO_B64  = %s" % cvals.get("info_b64", "<MISSING>"))
    print("  C CHKSUM    = %s" % cvals.get("chksum", "<MISSING>"))
    print("  PY HMAC_MD5 = %s" % ref["hmac"])
    print("  PY INFO_B64 = %s" % ref["info_b64"])
    print("  PY CHKSUM   = %s" % ref["chksum"])
    if not cvals:
        print("  FAIL no device C values captured (run nodemcuv2_srun_c_vector build + flash)")
        return False, ref, cvals
    ok = (cvals.get("hmac_md5") == ref["hmac"] and
          cvals.get("info_b64") == ref["info_b64"] and
          cvals.get("chksum") == ref["chksum"])
    print("  %s vendored C output matches Python reference" % ("PASS" if ok else "FAIL"))
    return ok, ref, cvals


def check_old_excluded():
    print("=== 5) Old self-made implementation excluded from build tree ===")
    forbidden = ["network/campus_auth.cpp", "network/campus_auth.h"]
    bad = []
    for base in ("src", "lib"):
        d = os.path.join(ROOT, base)
        for root, _dirs, files in os.walk(d):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), ROOT).replace("\\", "/")
                for fb in forbidden:
                    if rel.endswith(fb):
                        bad.append(rel)
    in_build = [b for b in bad if "archive/" not in b]
    ok = (len(in_build) == 0)
    if in_build:
        for b in in_build:
            print("  FAIL old impl present in build tree: %s" % b)
    else:
        print("  PASS no old campus_auth.{h,cpp} in src/ or lib/")
    arch_cpp = os.path.join(ROOT, "archive", "rejected_auth_implementation", "campus_auth.cpp")
    arch_h = os.path.join(ROOT, "archive", "rejected_auth_implementation", "campus_auth.h")
    arch_ok = os.path.exists(arch_cpp) and os.path.exists(arch_h)
    print("  archive copy present (moved, excluded from builds): %s" % arch_ok)
    return ok and arch_ok


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    import io
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    g1 = check_identical()
    g2 = check_symbols()
    g3, head = check_git_head()
    g4, ref, cvals = compare_c_vector()
    g5 = check_old_excluded()

    buf = sys.stdout.getvalue()
    sys.stdout = old_stdout
    print(buf)

    # Persist evidence (commit / source SHA256 / C vs Python / match).
    manifest = {}
    for vrel, _ in IDENTICAL_PAIRS:
        vp = os.path.join(VEN, vrel)
        if os.path.exists(vp):
            manifest[vrel] = sha256_of(vp)
    evidence = {
        "pinned_upstream_head": PINNED_HEAD,
        "upstream_head_actual": head,
        "upstream_head_match": g3,
        "source_sha256": manifest,
        "c_values": cvals,
        "python_reference": ref,
        "c_vector_match": g4,
        "sha_identity_pass": g1,
        "symbols_pass": g2,
        "old_excluded": g5,
    }
    os.makedirs(os.path.dirname(EVIDENCE), exist_ok=True)
    with open(EVIDENCE, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print("  evidence written: %s" % EVIDENCE)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(buf)
        f.write("\n=== EVIDENCE ===\n")
        f.write(json.dumps(evidence, indent=2) + "\n")

    all_ok = g1 and g2 and g3 and g4 and g5
    print("=== RESULT ===")
    print(("SRUN_VENDOR_SHA_PASS" if g1 else "SRUN_VENDOR_SHA_FAIL"))
    print(("SRUN_SYMBOLS_PASS" if g2 else "SRUN_SYMBOLS_FAIL"))
    print(("SRUN_UPSTREAM_HEAD_PASS" if g3 else "SRUN_UPSTREAM_HEAD_FAIL"))
    # 门禁五.6: 只有真实 C 结果完全一致才输出 SRUN_VENDOR_C_VECTOR_PASS
    print(("SRUN_VENDOR_C_VECTOR_PASS" if g4 else "SRUN_VENDOR_C_VECTOR_FAIL"))
    print(("OLD_AUTH_IMPLEMENTATION_EXCLUDED" if g5 else "OLD_AUTH_IMPLEMENTATION_STILL_PRESENT"))
    print("OVERALL: %s" % ("ALL_GATES_PASS" if all_ok else "GATE_FAIL"))
    print("log: %s" % OUT)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
