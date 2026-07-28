#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
test_integrity.py - verify_archive 的回归测试

覆盖第十节要求的 5 个用例：
  1. 正常 tar.gz
  2. 截断 tar.gz
  3. 无 manifest 归档
  4. manifest 版本不匹配
  5. 含路径穿越成员的归档

运行：python tools/test_integrity.py
退出码 0 = 全部通过；非 0 = 存在失败用例。
"""
import os
import io
import sys
import json
import tarfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_verify import verify_archive

PASS = []
FAIL = []


def make_targz(buf, members):
    """members: list of (name, bytes)。写入 buf(字节) 构造 gzip tar。"""
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    buf.write(bio.getvalue())


def case_normal(tmp):
    p = os.path.join(tmp, "normal.tar.gz")
    with open(p, "wb") as f:
        make_targz(f, [
            ("package.json", json.dumps({"name": "demo-tool", "version": "1.2.3"}).encode()),
            ("bin/tool.exe", b"MZ" + b"\x00" * 1000),
        ])
    r = verify_archive(p, expect_name="demo-tool", expect_version="1.2.3")
    ok = r["ok"] and r["members"] == 2 and r["manifest"]["version"] == "1.2.3"
    return ok, f"members={r['members']} manifest={r['manifest']} issues={r['issues']}"


def case_truncated(tmp):
    p = os.path.join(tmp, "truncated.tar.gz")
    with open(p, "wb") as f:
        make_targz(f, [
            ("package.json", json.dumps({"name": "demo-tool", "version": "1.2.3"}).encode()),
            ("big.bin", b"x" * 50000),
        ])
    # 截断到一半
    sz = os.path.getsize(p)
    with open(p, "rb") as f:
        data = f.read(sz // 2)
    with open(p, "wb") as f:
        f.write(data)
    r = verify_archive(p)
    ok = (not r["ok"]) and r["error"] is not None
    return ok, f"error={r['error']}"


def case_no_manifest(tmp):
    p = os.path.join(tmp, "nomanifest.tar.gz")
    with open(p, "wb") as f:
        make_targz(f, [("readme.txt", b"hello"), ("bin/x", b"abc")])
    r = verify_archive(p)
    ok = (not r["ok"]) and any("未找到" in i for i in r["issues"])
    return ok, f"issues={r['issues']}"


def case_version_mismatch(tmp):
    p = os.path.join(tmp, "mismatch.tar.gz")
    with open(p, "wb") as f:
        make_targz(f, [
            ("package.json", json.dumps({"name": "demo-tool", "version": "9.9.9"}).encode()),
            ("bin/tool.exe", b"MZ"),
        ])
    r = verify_archive(p, expect_name="demo-tool", expect_version="1.2.3")
    ok = (not r["ok"]) and any("version 不匹配" in i for i in r["issues"])
    return ok, f"manifest={r['manifest']} issues={r['issues']}"


def case_path_traversal(tmp):
    p = os.path.join(tmp, "traversal.tar.gz")
    with open(p, "wb") as f:
        make_targz(f, [
            ("package.json", json.dumps({"name": "demo-tool", "version": "1.2.3"}).encode()),
            ("../evil.txt", b"pwned"),
        ])
    r = verify_archive(p, expect_name="demo-tool", expect_version="1.2.3")
    ok = (not r["ok"]) and any("路径穿越" in i for i in r["issues"])
    return ok, f"issues={r['issues']}"


def main():
    tmp = tempfile.mkdtemp(prefix="integ_test_")
    cases = [
        ("1. 正常 tar.gz", case_normal),
        ("2. 截断 tar.gz", case_truncated),
        ("3. 无 manifest 归档", case_no_manifest),
        ("4. manifest 版本不匹配", case_version_mismatch),
        ("5. 含路径穿越成员的归档", case_path_traversal),
    ]
    print("=== verify_archive 回归测试 ===")
    for title, fn in cases:
        try:
            ok, detail = fn(tmp)
        except Exception as e:
            ok, detail = False, f"异常: {repr(e)[:160]}"
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {title} :: {detail}")
        (PASS if ok else FAIL).append(title)
    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例:", FAIL)
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
