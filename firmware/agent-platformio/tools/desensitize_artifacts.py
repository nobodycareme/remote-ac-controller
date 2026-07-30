#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
门禁八 — 工件脱敏辅助。

对仓库内的文本工件做就地脱敏（幂等、可重复执行）：
  - 设备 MAC -> 后两段掩码为 XX:XX（大小写不敏感，二进制安全）。待掩码的 MAC
    由环境变量 DESENSITIZE_MAC 指定；未设置时按通用 MAC 正则匹配。
    注意：TLS 证书 SHA1 指纹（20 字节）与 MAC 字面量不同，不会被误改。
  - Windows 用户名 -> <USER>，PlatformIO 根 -> <PIO_ROOT>（仅作用于捕获的环境
    变量转储与构建文档，避免泄露用户目录布局）。用户名默认取当前登录名，
    可用 DESENSITIZE_USER 覆盖。

不修改 lib/srun-c（门禁五要求 byte-identical）——其中不含设备 MAC，路径掩码仅作用于
明确列出的捕获/文档文件，故不影响 vendored 文件。

退出码 0。
"""
import os
import re
import sys

# Default root = the project dir (two levels up from tools/). If argv[1] is
# given (the review-package staging dir), desensitize THAT instead, so the
# repo itself is never mutated by the packaging pipeline.
if len(sys.argv) > 1 and sys.argv[1]:
    ROOT = os.path.abspath(sys.argv[1])
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MAC to mask. If DESENSITIZE_MAC is unset, fall back to a generic MAC pattern
# so the tool still works on an arbitrary capture dump.
_MAC = (os.environ.get("DESENSITIZE_MAC") or "").strip()
if _MAC:
    MASK_MAC = re.compile(re.escape(_MAC), re.I)
    _MAC_HEAD = ":".join(_MAC.split(":")[:4])
else:
    MASK_MAC = re.compile(r"\b([0-9a-f]{2}(?::[0-9a-f]{2}){3}):[0-9a-f]{2}:[0-9a-f]{2}\b", re.I)
    _MAC_HEAD = None

# Windows account name to mask. Defaults to the current login; override with
# DESENSITIZE_USER. Never hard-code a real account name in this repository.
_USER = (os.environ.get("DESENSITIZE_USER") or os.environ.get("USERNAME") or "").strip()
_USER_RE = re.escape(_USER) if _USER else r"[^/\\\s]+"

RE_USER = re.compile(r"/c/Users/" + _USER_RE)
RE_PIO = re.compile(r"/f/PIO")
RE_WINUSER = re.compile(r"[A-Za-z]:\\Users\\" + _USER_RE, re.I)

# 仅对这些位置做用户名/路径掩码（捕获转储 + 构建文档）
PATH_MASK_DIRS = ("logs/00_inventory", "docs/06", "docs/00")
PATH_MASK_FILES = ("README.md", "setup-report.md")


def mask_text(t):
    if _MAC_HEAD:
        t = MASK_MAC.sub(_MAC_HEAD + ":XX:XX", t)
    else:
        t = MASK_MAC.sub(lambda m: m.group(1) + ":XX:XX", t)
    t = RE_USER.sub("/c/Users/<USER>", t)
    t = RE_PIO.sub("<PIO_ROOT>", t)
    t = RE_WINUSER.sub("<DRIVE>:/Users/<USER>", t)
    return t


def mask_bin(data):
    """Binary-safe MAC masking. Only applies when DESENSITIZE_MAC is set."""
    if not _MAC:
        return data
    out = data
    for variant in (_MAC.lower(), _MAC.upper()):
        head = ":".join(variant.split(":")[:4])
        out = out.replace(variant.encode("ascii"), (head + ":XX:XX").encode("ascii"))
    return out


def main():
    changed = 0
    for dp, dns, fns in os.walk(ROOT):
        rel_dir = os.path.relpath(dp, ROOT).replace("\\", "/")
        if any(p in (".git", ".pio", "node_modules", "__pycache__", ".workbuddy", ".work")
               for p in rel_dir.split("/")):
            dns[:] = []
            continue
        for fn in fns:
            if fn.endswith((".bin", ".exe", ".dll", ".zip", ".png", ".jpg",
                            ".gif", ".pdf", ".pyc")):
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            # 作用域：仅工件/文档（绝不触及 tools/ 与 src/，避免破坏脚本自身常量
            # 与源码；设备 MAC 只可能出现在 logs/、setup-report.md、docs/、review/、
            # README.md 中）。
            in_scope = (rel.startswith(("logs/", "docs/", "review/"))
                        or rel in ("setup-report.md", "README.md"))
            if not in_scope:
                continue
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except Exception:
                continue
            # MAC 掩码：文本/二进制工件（安全且幂等；TLS 证书指纹为 20 字节不受影响）
            needs_mac_mask = bool(_MAC) and (
                _MAC.lower().encode("ascii") in data
                or _MAC.upper().encode("ascii") in data
            )
            if needs_mac_mask:
                if b"\x00" in data[:4096]:
                    new = mask_bin(data)
                else:
                    new = mask_text(data.decode("utf-8", "ignore")).encode("utf-8")
                if new != data:
                    with open(full, "wb") as f:
                        f.write(new)
                    changed += 1
                    print("MASKED(mac) %s" % rel)
                continue
            # 用户名/路径掩码：仅明确位置
            do_path = rel.startswith(PATH_MASK_DIRS) or os.path.basename(rel) in PATH_MASK_FILES
            if not do_path:
                continue
            try:
                text = data.decode("utf-8", "ignore")
            except Exception:
                continue
            new = mask_text(text)
            if new != text:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(new)
                changed += 1
                print("MASKED(path) %s" % rel)
    print("DESENSITIZE_DONE changed=%d" % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
