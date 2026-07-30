#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
download_verify.py - PlatformIO 依赖纯下载 + SHA256 校验 + 证据记录工具

设计原则（依据用户纠正指令）：
  1. 本脚本【只下载 + 校验 + 记录证据】，绝不手工写入 .piopm，绝不手工安装。
  2. 所有包名/版本来自 PlatformIO 官方 registry / 已安装平台 manifest，绝不猜测。
  3. 支持断点续传（HTTP Range），避免浪费已下载流量。
  4. 每包下载完成，将证据写入 F:\PIO\Downloads\download_evidence.csv。

子命令：
  download <type> <name> <version>        下载单个指定版本包
  platform-tools <archive>                读取平台归档内 platform.json，打印所需工具版本
  batch                                   下载本工程全部依赖（平台 + 工具），工具版本由平台 manifest 区间决定
"""
import os
import sys
import json
import time
import csv
import hashlib
import tarfile
import urllib.request

REG_API = "https://api.registry.platformio.org/v3/packages/platformio"
DOWNLOADS = r"F:\PIO\Downloads"
EVIDENCE_CSV = os.path.join(DOWNLOADS, "download_evidence.csv")
DEFAULT_OS = "windows_amd64"

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
VIA_PROXY = "127.0.0.1:10808" in PROXY
UA = {"User-Agent": "pio/6"}


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_file(files):
    if not files:
        return None
    indep = next((x for x in files if not x.get("system")), None)
    if indep:
        return indep
    win = next((x for x in files if any(s.startswith("windows") for s in x.get("system", []))), None)
    return win or files[0]


def all_versions(ptype, name):
    d = fetch_json(f"{REG_API}/{ptype}/{name}")
    return d.get("versions", []), d.get("id")


def resolve_pkg(ptype, name, version=None):
    """解析单个包的下载元数据。version=None -> latest。"""
    vers, pkg_id = all_versions(ptype, name)
    if version:
        v = next((x for x in vers if x.get("name") == version), None)
        if not v:
            raise SystemExit(f"[resolve] {name} 找不到版本 {version}")
    else:
        v = next((x for x in vers if x.get("name")), None)  # 列表末尾一般为 latest
    ver = v.get("name")
    f = pick_file(v.get("files", []))
    if not f:
        raise SystemExit(f"[resolve] {name} 无可用文件")
    return {
        "type": ptype, "name": name, "version": ver, "id": pkg_id,
        "dl": f["download_url"], "sha256": (f.get("checksum") or {}).get("sha256"),
        "size": f.get("size"),
        "registry_url": f"{REG_API}/{ptype}/{name}/versions/{ver}",
    }


def version_tuple(v):
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def resolve_version_in_range(name, range_str):
    """依据平台 manifest 的版本区间，从官方 registry 选出满足条件的最高版本。
    覆盖本工程出现的区间形态：~1.30000.0 / ~2.100300.220621 / ~3.30102.0 / <2 / ~1.200.0 / ~1.203.0。"""
    vers, _ = all_versions("tool", name)
    names = [v.get("name") for v in vers if v.get("name")]
    if range_str.startswith("~"):
        parts = range_str[1:].split(".")
        prefix = ".".join(parts[:-1])  # 取 major.minor
        cands = [n for n in names if n.startswith(prefix + ".")]
        if cands:
            return max(cands, key=version_tuple)
    elif range_str.startswith("<"):
        upper = int(range_str[1:].split(".")[0])
        cands = [n for n in names if version_tuple(n)[0] < upper]
        if cands:
            return max(cands, key=version_tuple)
    elif range_str.startswith(">="):
        lower_t = version_tuple(range_str[2:])
        cands = [n for n in names if version_tuple(n) >= lower_t]
        if cands:
            return max(cands, key=version_tuple)
    # 兜底：返回 latest
    return names[-1] if names else None


def canonical_name(pkg):
    if pkg["type"] == "tool":
        return f"{pkg['name']}-{DEFAULT_OS}-{pkg['version']}.tar.gz"
    return f"{pkg['name']}-{pkg['version']}.tar.gz"


def find_existing(pkg):
    """兼容官方命名(含 -windows_amd64)与旧命名(无 OS 段)。"""
    cands = [
        os.path.join(DOWNLOADS, canonical_name(pkg)),
        os.path.join(DOWNLOADS, f"{pkg['name']}-{pkg['version']}.tar.gz"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def download(pkg):
    """断点续传下载 + SHA256 校验。返回 (path, resume_count, start, end, actual_sha, match)。"""
    expected = pkg["sha256"]
    os.makedirs(DOWNLOADS, exist_ok=True)
    existing = find_existing(pkg)
    if existing and expected and sha256_file(existing) == expected:
        print(f"  [skip] {pkg['name']}@{pkg['version']} 已存在且 SHA256 匹配")
        # 统一命名为官方命名，便于后续 file:// 安装
        canon = os.path.join(DOWNLOADS, canonical_name(pkg))
        if existing != canon:
            os.replace(existing, canon)
        return canon, 0, None, None, sha256_file(canon), True

    tar = os.path.join(DOWNLOADS, canonical_name(pkg))
    total = pkg.get("size")
    if total is None:
        try:
            req = urllib.request.Request(pkg["dl"], method="HEAD", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                total = int(r.headers.get("Content-Length", 0))
        except Exception:
            total = None

    cur = os.path.getsize(tar) if os.path.exists(tar) else 0
    resume_count = 0
    if cur and total and cur >= total:
        if expected and sha256_file(tar) == expected:
            return tar, 0, None, None, sha256_file(tar), True
        cur = 0

    start = time.time()
    mode = "ab" if cur else "wb"
    print(f"  downloading {pkg['name']}@{pkg['version']} (total={total or '?'}, resume_from={cur}, proxy={VIA_PROXY}) ...")
    while True:
        hdr = dict(UA)
        if cur:
            hdr["Range"] = f"bytes={cur}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(pkg["dl"], headers=hdr), timeout=60) as r:
                with open(tar, mode) as out:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        cur += len(chunk)
            break
        except Exception as e:
            resume_count += 1
            print(f"    interrupted at {cur}: {repr(e)[:80]}; retry #{resume_count}")
            time.sleep(2)
            mode = "ab"
    end = time.time()
    got = sha256_file(tar)
    match = (got == expected) if expected else None
    print(f"  done in {end-start:.1f}s, size={os.path.getsize(tar)}, sha256={got}")
    if expected and not match:
        raise SystemExit(f"[verify] {pkg['name']} SHA256 不匹配！want={expected} got={got}")
    if not expected:
        print("  [warn] registry 未提供 SHA256，无法比对")
    return tar, resume_count, start, end, got, match


def verify_archive(path, expect_name=None, expect_version=None,
                   max_members=200000, max_uncompressed=2 * 1024 * 1024 * 1024):
    """完整校验 PlatformIO 归档(.tar.gz)的结构与内容完整性。

    返回 dict，含 ok / members / uncompressed_bytes / manifest / issues / error。
    仅“列出成员”不足以判定完整：本函数遍历全部成员，并实际读取每个普通
    文件的数据以触发解压，捕获解压异常；同时检查路径穿越(../ 或绝对路径)、
    manifest(package.json/platform.json)存在性与 name/version 是否匹配，
    记录成员数与未压缩总大小以防御归档炸弹。
    """
    res = {"ok": False, "members": 0, "uncompressed_bytes": 0,
           "manifest": None, "issues": [], "error": None}
    try:
        with tarfile.open(path, "r:gz") as tf:
            members = tf.getmembers()
            uncompressed = 0
            manifest_name = manifest_version = None
            manifest_data = None
            candidates = []
            for m in members:
                norm = m.name.replace("\\", "/")
                parts = norm.split("/")
                if norm.startswith("/") or norm.startswith("//") or ".." in parts:
                    res["issues"].append(f"路径穿越成员: {m.name!r}")
                if m.isfile():
                    try:
                        f = tf.extractfile(m)
                        if f is not None:
                            while True:
                                chunk = f.read(1 << 20)
                                if not chunk:
                                    break
                                uncompressed += len(chunk)
                                if uncompressed > max_uncompressed:
                                    res["issues"].append("未压缩总大小超过上限(疑似归档炸弹)")
                                    break
                    except Exception as e:
                        res["issues"].append(f"解压失败: {m.name!r}: {repr(e)[:120]}")
                base = parts[-1]
                if base in ("package.json", "platform.json"):
                    try:
                        raw = tf.extractfile(m).read().decode("utf-8")
                        md = json.loads(raw)
                        candidates.append((m.name, md.get("name"), md.get("version"), "/" not in norm))
                    except Exception as e:
                        res["issues"].append(f"manifest 解析失败: {repr(e)[:120]}")
            res["members"] = len(members)
            res["uncompressed_bytes"] = uncompressed
            # 选择 manifest：优先匹配期望 name；否则优先顶层 package.json；否则第一个
            if candidates:
                pick = next((c for c in candidates if expect_name and c[1] == expect_name), None)
                if pick is None:
                    top = [c for c in candidates if c[3]]
                    pick = top[0] if top else candidates[0]
                manifest_name, manifest_version = pick[1], pick[2]
                manifest_data = {"name": manifest_name, "version": manifest_version}
            res["manifest"] = {"name": manifest_name, "version": manifest_version}
            if manifest_data is None:
                res["issues"].append("归档内未找到 package.json / platform.json")
            if expect_name is not None and manifest_name != expect_name:
                res["issues"].append(f"manifest name 不匹配: 期望 {expect_name!r} 实际 {manifest_name!r}")
            if expect_version is not None and manifest_version != expect_version:
                res["issues"].append(f"manifest version 不匹配: 期望 {expect_version!r} 实际 {manifest_version!r}")
    except Exception as e:
        res["error"] = f"无法打开归档(结构损坏/截断): {repr(e)[:120]}"
        return res
    res["ok"] = (not res["issues"]) and manifest_data is not None \
        and (expect_name is None or manifest_name == expect_name) \
        and (expect_version is None or manifest_version == expect_version)
    return res


def integrity_test(path, expect_name=None, expect_version=None):
    try:
        r = verify_archive(path, expect_name, expect_version)
        if r["error"]:
            return f"ERROR:{r['error']}"
        if r["ok"]:
            return f"OK (members={r['members']}, uncompressed={r['uncompressed_bytes']}, manifest={r['manifest']['name']}@{r['manifest']['version']})"
        return "ISSUES:" + "; ".join(r["issues"])
    except Exception as e:
        return f"ERROR:{repr(e)[:80]}"


def read_manifest_in_archive(path):
    with tarfile.open(path) as tf:
        m = next((x for x in tf.getmembers() if x.name.endswith("platform.json")), None)
        if not m:
            return None, None, {}
        data = json.loads(tf.extractfile(m).read().decode("utf-8"))
    return data.get("name"), data.get("version"), data.get("packages", {})


def record_evidence(pkg, tar, rc, start, end, got, match, integ, install_cmd="", exit_code=""):
    row = {
        "package": pkg["name"], "version": pkg["version"], "type": pkg["type"],
        "os_arch": DEFAULT_OS if pkg["type"] == "tool" else "platform-independent",
        "registry_metadata_url": pkg.get("registry_url", ""),
        "download_url": pkg["dl"],
        "via_proxy_127_0_0_1_10808": "yes" if VIA_PROXY else "no",
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start)) if start else "",
        "end_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(end)) if end else "",
        "resume_count": rc,
        "final_size": os.path.getsize(tar) if tar and os.path.exists(tar) else "",
        "expected_sha256": pkg.get("sha256") or "",
        "actual_sha256": got or "",
        "sha256_match": "yes" if match else ("unknown" if match is None else "NO"),
        "archive_integrity": integ,
        "manifest_name": "", "manifest_version": "",
        "official_install_command": install_cmd, "install_exit_code": exit_code,
    }
    write_header = not os.path.exists(EVIDENCE_CSV)
    with open(EVIDENCE_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)
    print(f"  evidence -> {EVIDENCE_CSV}")


def file_install_cmd(ptype, path):
    # PlatformIO Core 6.1.19 Windows 本地归档 URI 兼容性变通方案：
    #   - 三斜杠 file:///F:/path 在 Windows 上会被 install_from_uri 解析为
    #     uri[7:] = "/F:/path"（非法路径），导致 os.path.isfile 失败并走
    #     copytree 目录分支而报错（完整错误见 review/logs/install_threeslash*.log）。
    #   - 两斜杠 file://F:/path 解析为 uri[7:] = "F:/path"，Windows 可识别为
    #     文件，pio 调用 self.unpack 正常解包（成功命令见 review/logs/install_*.log）。
    # 该变通方案针对 PlatformIO Core 6.1.19，可能不适用于其他版本。
    kind = "platform" if ptype == "platform" else "tool"
    name = os.path.basename(path).split("-" + DEFAULT_OS + "-")[0] if ptype == "tool" else os.path.basename(path).split("-")[0]
    return f'pio pkg install --global --{kind} "{name}=file://{path.replace(chr(92), "/")}" --force'


def cmd_download(args):
    ptype, name, version = args[0], args[1], args[2]
    pkg = resolve_pkg(ptype, name, version)
    print(f"[resolve] {name}@{pkg['version']} id={pkg['id']} sha={(pkg['sha256'] or '')[:12]}")
    tar, rc, s, e, got, match = download(pkg)
    vr = verify_archive(tar, expect_name=pkg["name"], expect_version=pkg["version"])
    integ = integrity_test(tar, pkg["name"], pkg["version"])
    print(f"  integrity: {integ}")
    record_evidence(pkg, tar, rc, s, e, got, match, integ,
                    install_cmd=file_install_cmd(ptype, tar),
                    manifest_name=vr["manifest"]["name"] or "",
                    manifest_version=vr["manifest"]["version"] or "")
    print(f"[done] {name}@{pkg['version']} -> {tar}")


def cmd_platform_tools(args):
    archive = args[0]
    mname, mver, pkgs = read_manifest_in_archive(archive)
    print(f"平台 manifest: name={mname} version={mver}")
    print("所需 packages（来自平台官方 manifest）:")
    for k, v in pkgs.items():
        print(f"  - {k}: type={v.get('type')} owner={v.get('owner')} version={v.get('version')} optional={v.get('optional', False)}")
    out = os.path.join(DOWNLOADS, "platform_required_packages.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"platform": mname, "version": mver, "packages": pkgs}, f, indent=2, ensure_ascii=False)
    print(f"[done] 已写出 {out}")


def cmd_batch(args):
    plat = resolve_pkg("platform", "espressif8266", None)
    print(f"[platform] {plat['name']}@{plat['version']}")
    tar, rc, s, e, got, match = download(plat)
    vr = verify_archive(tar, expect_name=plat["name"], expect_version=plat["version"])
    integ = integrity_test(tar, plat["name"], plat["version"])
    record_evidence(plat, tar, rc, s, e, got, match, integ,
                    install_cmd=file_install_cmd("platform", tar),
                    manifest_name=vr["manifest"]["name"] or "",
                    manifest_version=vr["manifest"]["version"] or "")
    mname, mver, pkgs = read_manifest_in_archive(tar)
    print(f"[platform] manifest={mname}@{mver}, 解析到 {len(pkgs)} 个依赖包")
    # framework-arduinoespressif8266 在 manifest 中标记为 optional，但本工程 platformio.ini
    # 使用 framework=arduino，故必须安装；filesystem 工具也一并预置。
    wanted_optional = {"tool-mkspiffs", "tool-mklittlefs", "framework-arduinoespressif8266"}
    for k, v in pkgs.items():
        ver_range = v.get("version")
        optional = v.get("optional", False)
        if optional and k not in wanted_optional:
            print(f"  [skip optional] {k} {ver_range}")
            continue
        concrete = resolve_version_in_range(k, ver_range)
        if not concrete:
            print(f"  [error] {k}: 无法解析版本（区间 {ver_range}）")
            continue
        print(f"[tool] {k}: 平台区间 {ver_range} -> 选用 {concrete}")
        tpkg = resolve_pkg("tool", k, concrete)
        t2, rc2, s2, e2, g2, m2 = download(tpkg)
        vr2 = verify_archive(t2, expect_name=tpkg["name"], expect_version=tpkg["version"])
        integ2 = integrity_test(t2, tpkg["name"], tpkg["version"])
        record_evidence(tpkg, t2, rc2, s2, e2, g2, m2, integ2,
                        install_cmd=file_install_cmd("tool", t2),
                        manifest_name=vr2["manifest"]["name"] or "",
                        manifest_version=vr2["manifest"]["version"] or "")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "download":
        cmd_download(rest)
    elif cmd == "platform-tools":
        cmd_platform_tools(rest)
    elif cmd == "batch":
        cmd_batch(rest)
    else:
        print(f"未知子命令: {cmd}\n{__doc__}"); sys.exit(1)


if __name__ == "__main__":
    main()
