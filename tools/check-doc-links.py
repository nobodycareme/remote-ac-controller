#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-doc-links.py — verify every first-party relative link resolves.

Scans *.md files in the repository (excluding node_modules/.git) and reports
BROKEN_FIRST_PARTY_LINK_COUNT. Links are resolved relative to the file that
contains them; anchors (#...) and http(s) links are ignored.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "node_modules", ".build", "dist", "coverage"}
SKIP_PREFIXES = ("firmware/agent-platformio/lib/", "firmware/shared/RemoteACCore/lib/")

LINK_RE = re.compile(r"\]\(([^)]+)\)")
broken = []
checked = 0
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        if not fn.endswith(".md"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        if rel.startswith(SKIP_PREFIXES):
            continue  # vendored third-party libraries keep their own (broken) links
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            if not target or target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # strip anchor
            t = target.split("#")[0]
            if not t:
                continue
            checked += 1
            if t.startswith("/"):
                t2 = t.lstrip("/")
                full = os.path.join(ROOT, *t2.split("/"))
            else:
                full = os.path.normpath(os.path.join(dirpath, t))
            if not os.path.exists(full):
                broken.append(f"{rel} -> {target}")

for b in broken:
    print("BROKEN_LINK", b)
print(f"BROKEN_FIRST_PARTY_LINK_COUNT={len(broken)}")
print(f"LINKED_TARGETS_CHECKED={checked}")
ok = not broken
print("DOC_LINKS_PASS=" + ("True" if ok else "False"))
sys.exit(0 if ok else 1)
