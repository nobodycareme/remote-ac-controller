#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-doc-language-links.py — cross-language link hygiene.

Rule: an English document may only link to a Chinese document from the
top-of-file language switch (or an explicitly marked translation-source note).
The same applies in reverse. Any other cross-language body link is reported.

Outputs:
  ENGLISH_TO_CHINESE_BODY_LINK_COUNT / CHINESE_TO_ENGLISH_BODY_LINK_COUNT
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LINK_RE = re.compile(r"\]\(([^)]+)\)")
ZH_DIR = os.path.join(ROOT, "docs", "中文")
EN_DIR = os.path.join(ROOT, "docs", "English")

def is_zh(rel):
    return "/中文/" in rel or rel == "README.md"

def is_en(rel):
    return rel.startswith("docs/English/") or rel == "README.en.md"

def resolve(base_dir, target):
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return None
    t = target.split("#")[0]
    if not t:
        return None
    if t.startswith("/"):
        return os.path.normpath(os.path.join(ROOT, *t.lstrip("/").split("/")))
    return os.path.normpath(os.path.join(base_dir, t))

en_to_zh = []
zh_to_en = []
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".build", "dist"}]
    for fn in files:
        if not fn.endswith(".md"):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        try:
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            # Header language-switch / nav zone: lines that carry the language
            # toggle (中文 <-> English) are exempt, as are explicit
            # translation-source notes.
            is_header_nav = ("简体中文" in line and "English" in line) or                             ("中文" in line and "English" in line and i < 14)
            is_trans_note = ("translation" in line.lower() or "参考译文" in line or
                             "翻译" in line)
            is_bilingual_table = line.strip().startswith("|") and                                 ("中文" in line or "简体中文" in line) and "English" in line
            for m in LINK_RE.finditer(line):
                target = m.group(1).strip()
                full = resolve(dirpath, target)
                if full is None or not os.path.exists(full):
                    continue
                trel = os.path.relpath(full, ROOT).replace("\\", "/")
                is_index_nav = ("documentation-index" in trel or "文档导航" in trel)
                if i <= 1 or is_header_nav or is_trans_note or is_bilingual_table or is_index_nav:
                    continue
                if is_en(rel) and is_zh(trel):
                    en_to_zh.append(f"{rel}:{i+1} -> {trel}")
                elif is_zh(rel) and is_en(trel):
                    zh_to_en.append(f"{rel}:{i+1} -> {trel}")

for b in en_to_zh[:30]:
    print("EN_TO_ZH_BODY_LINK", b)
for b in zh_to_en[:30]:
    print("ZH_TO_EN_BODY_LINK", b)
print(f"ENGLISH_TO_CHINESE_BODY_LINK_COUNT={len(en_to_zh)}")
print(f"CHINESE_TO_ENGLISH_BODY_LINK_COUNT={len(zh_to_en)}")
ok = not en_to_zh and not zh_to_en
print("DOC_LANGUAGE_LINKS_PASS=" + ("True" if ok else "False"))
sys.exit(0 if ok else 1)
