#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性红外状态注册表生成器（2026-07-28 全量集成轮）。

输入（全部私有，不入Git）：
  Private/Firmware/IR/CAPTURE_002.bin                 —— 原固定基线（418B，SHA固定）
  Private/Firmware/IR/Learned/<stateId>/canonical.bin —— 10个用户选定canonical
  Private/Firmware/IR/Learned/<stateId>/canonical.json
  Private/Firmware/IR/Learned/<stateId>/state.json

输出（gitignored）：
  src/private_ir_codes/generated/ir_library_generated.inc  —— 11条 PrivateIrCode PROGMEM 表

规则：
  - 全部结构校验（存在/长度/SHA256/帧头/AFN=22H/校验和/帧尾/与sourceCapture逐字节一致）失败即退出非零；
  - 不打印完整帧字节；
  - 生成后 roundtrip：解析生成的 .inc，逐字节/长度/SHA256 反向验证；
  - 输出确定性（固定顺序、无时间戳差异字段进入数组内容）。
"""
import hashlib, json, os, re, sys

ROOT = r"C:\example\remote-ac"
IR_DIR = os.path.join(ROOT, "Private", "Firmware", "IR")
LEARNED = os.path.join(IR_DIR, "Learned")
OUT = os.path.join(ROOT, "Firmware", "Remote_AC_Controller",
                   "src", "private_ir_codes", "generated", "ir_library_generated.inc")

FIXED_ID = "hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1"
FIXED_SHA = "e9ab43feca71acde248df5729d0cb0d228bdbcfb69f8513d43ea4b942cb6ac7e"
FIXED_LEN = 418

STATES = [
    "hisense_power_off_v1",
    "hisense_cool_24_turbo_swingV_v1",
    "hisense_cool_20_turbo_swingV_v1",
    "hisense_cool_25_auto_v1",
    "hisense_cool_26_auto_v1",
    "hisense_dry_24_turbo_swingVH_v1",
    "hisense_dry_24_auto_swingVH_v1",
    "hisense_dry_24_silent_swingVH_v1",
    "hisense_heat_26_auto_swingVH_v1",
    "hisense_heat_28_auto_swingVH_v1",
]

FRAME_HEADER, FRAME_TAIL, AFN = 0x68, 0x16, 0x22
IR_MIN, IR_MAX = 7, 832

# 显式元数据表（确定性来源）。state.json 中 mode/fan 存在中文/英文混用、
# power 字段格式不一（"on"/"off"/缺失），不可作为元数据事实来源；
# 帧字节仍以 canonical.bin 为唯一事实来源，此表仅提供检索/展示元数据。
STATE_META = {
    "hisense_power_off_v1":              ("关机",                             "off",  0,  "auto",  False, False, False),
    "hisense_cool_24_turbo_swingV_v1":   ("制冷24℃ 超强风 上下扫风",          "cool", 24, "turbo", True,  False, True),
    "hisense_cool_20_turbo_swingV_v1":   ("制冷20℃ 超强风 上下扫风",          "cool", 20, "turbo", True,  False, True),
    "hisense_cool_25_auto_v1":           ("制冷25℃ 自动风",                   "cool", 25, "auto",  False, False, True),
    "hisense_cool_26_auto_v1":           ("制冷26℃ 自动风",                   "cool", 26, "auto",  False, False, True),
    "hisense_dry_24_turbo_swingVH_v1":   ("除湿24℃ 超强风 双向扫风",          "dry",  24, "turbo", True,  True,  True),
    "hisense_dry_24_auto_swingVH_v1":    ("除湿24℃ 自动风 双向扫风",          "dry",  24, "auto",  True,  True,  True),
    "hisense_dry_24_silent_swingVH_v1":  ("除湿24℃ 静音风 双向扫风",          "dry",  24, "quiet", True,  True,  True),
    "hisense_heat_26_auto_swingVH_v1":   ("制热26℃ 自动风 双向扫风",          "heat", 26, "auto",  True,  True,  True),
    "hisense_heat_28_auto_swingVH_v1":   ("制热28℃ 自动风 双向扫风",          "heat", 28, "auto",  True,  True,  True),
}


def fail(msg):
    print("GEN_FAIL: %s" % msg)
    sys.exit(1)


def validate_frame(b, name):
    n = len(b)
    if not (IR_MIN <= n <= IR_MAX):
        fail("%s length out of range: %d" % (name, n))
    if b[0] != FRAME_HEADER:
        fail("%s bad header" % name)
    declared = b[1] | (b[2] << 8)
    if declared != n:
        fail("%s declared length %d != actual %d" % (name, declared, n))
    if b[4] != AFN:
        fail("%s AFN != 0x22" % name)
    if b[-1] != FRAME_TAIL:
        fail("%s bad tail" % name)
    cs = sum(b[3:n - 2]) & 0xFF
    if b[-2] != cs:
        fail("%s bad checksum" % name)


def load_entries():
    entries = []
    # 1) fixed baseline CAPTURE_002
    p = os.path.join(IR_DIR, "CAPTURE_002.bin")
    if not os.path.exists(p):
        fail("CAPTURE_002.bin missing")
    data = open(p, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    if len(data) != FIXED_LEN or sha != FIXED_SHA:
        fail("CAPTURE_002 baseline mismatch len=%d sha=%s" % (len(data), sha))
    validate_frame(data, "CAPTURE_002")
    entries.append({
        "codeId": FIXED_ID, "data": data, "sha": sha,
        "desc": "海信制冷24℃ 静音 上下扫风开启 左右扫风开启",
        "mode": "cool", "temp": 24, "fan": "quiet",
        "swingV": True, "swingH": True, "powerOn": True,
    })
    # 2) 10 learned canonical states
    for sid in STATES:
        d = os.path.join(LEARNED, sid)
        for fn in ("canonical.bin", "canonical.json", "state.json"):
            if not os.path.exists(os.path.join(d, fn)):
                fail("%s missing %s" % (sid, fn))
        cj = json.load(open(os.path.join(d, "canonical.json"), encoding="utf-8"))
        st = json.load(open(os.path.join(d, "state.json"), encoding="utf-8"))
        data = open(os.path.join(d, "canonical.bin"), "rb").read()
        sha = hashlib.sha256(data).hexdigest()
        if len(data) != cj.get("length"):
            fail("%s length != canonical.json" % sid)
        if sha != cj.get("sha256"):
            fail("%s sha256 != canonical.json" % sid)
        src = cj.get("sourceCapture")
        if not src or not re.match(r"^capture_\d{3}$", src):
            fail("%s invalid sourceCapture" % sid)
        srcb = open(os.path.join(d, src + ".bin"), "rb").read()
        if srcb != data:
            fail("%s canonical not byte-exact with %s" % (sid, src))
        validate_frame(data, sid)
        if sid not in STATE_META:
            fail("%s missing STATE_META entry" % sid)
        desc, mode, temp, fan, swing_v, swing_h, power_on = STATE_META[sid]
        entries.append({
            "codeId": sid, "data": data, "sha": sha,
            "desc": desc, "mode": mode, "temp": temp, "fan": fan,
            "swingV": swing_v, "swingH": swing_h, "powerOn": power_on,
        })
    return entries


def emit(entries):
    ids = [e["codeId"] for e in entries]
    if len(ids) != len(set(ids)):
        fail("duplicate stateId")
    lines = []
    a = lines.append
    a("// AUTO-GENERATED by tools/gen_ir_state_registry.py — DO NOT EDIT, DO NOT COMMIT.")
    a("// Gitignored private IR frames (complete 22H frames, PROGMEM).")
    a("#define PRIVATE_IR_LIBRARY_GENERATED 1")
    a("")
    for i, e in enumerate(entries):
        a("static const uint8_t kPrivateIrFrame%03d[] PROGMEM = {" % i)
        data = e["data"]
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            a("  " + " ".join("0x%02X," % b for b in chunk))
        a("};")
        a("")
    a("static const PrivateIrCode kPrivateIrCodes[] = {")
    for i, e in enumerate(entries):
        a("  {")
        a('    "%s",' % e["codeId"])
        a("    kPrivateIrFrame%03d," % i)
        a("    %d," % len(e["data"]))
        a('    "%s",' % e["sha"])
        a('    "%s",' % e["desc"])
        a('    "%s",' % e["mode"])
        a("    %d," % e["temp"])
        a('    "%s",' % e["fan"])
        a("    %s," % ("true" if e["swingV"] else "false"))
        a("    %s," % ("true" if e["swingH"] else "false"))
        a("    %s," % ("true" if e["powerOn"] else "false"))
        a("    true,  // enabled")
        a("  },")
    a("};")
    a("static const uint8_t kPrivateIrCodeCount = static_cast<uint8_t>(sizeof(kPrivateIrCodes) / sizeof(kPrivateIrCodes[0]));")
    a("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def roundtrip(entries):
    """Parse generated .inc, recover every frame, verify byte-exact + SHA."""
    text = open(OUT, encoding="utf-8").read()
    frames = {}
    for m in re.finditer(r"kPrivateIrFrame(\d{3})\[\] PROGMEM = \{(.*?)\};", text, re.S):
        idx = int(m.group(1))
        vals = re.findall(r"0x([0-9A-F]{2})", m.group(2))
        frames[idx] = bytes(int(v, 16) for v in vals)
    if len(frames) != len(entries):
        fail("roundtrip frame count %d != %d" % (len(frames), len(entries)))
    for i, e in enumerate(entries):
        rec = frames[i]
        if len(rec) != len(e["data"]):
            fail("roundtrip %s length mismatch" % e["codeId"])
        if rec != e["data"]:
            fail("roundtrip %s bytes mismatch" % e["codeId"])
        if hashlib.sha256(rec).hexdigest() != e["sha"]:
            fail("roundtrip %s sha mismatch" % e["codeId"])
    return True


def main():
    entries = load_entries()
    emit(entries)
    roundtrip(entries)
    summary = [{
        "stateId": e["codeId"], "length": len(e["data"]), "sha256": e["sha"],
        "mode": e["mode"], "temperature": e["temp"], "fan": e["fan"],
        "swingV": e["swingV"], "swingH": e["swingH"], "powerOn": e["powerOn"],
        "enabled": True,
    } for e in entries]
    print("IR_STATE_COUNT=%d" % len(entries))
    for s in summary:
        print("IR_STATE id=%s len=%d sha=%s..%s enabled=true" % (
            s["stateId"], s["length"], s["sha256"][:8], s["sha256"][-8:]))
    print("CAPTURE_002_BYTE_EXACT_PRESERVED=True")
    print("ALL_CANONICAL_BYTE_EXACT_PRESERVED=True")
    print("IR_RESOURCE_GENERATION_PASS=True")
    ev = os.environ.get("IR_GEN_EVIDENCE_JSON")
    if ev:
        json.dump({"count": len(entries), "roundtripPass": True, "states": summary},
                  open(ev, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
