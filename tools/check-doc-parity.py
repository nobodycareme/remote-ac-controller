#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-doc-parity.py — verify the CN<->EN documentation map.

Outputs the metrics required by the v1.2.0 consolidation spec:
  DOC_MAP_ENTRY_COUNT / CHINESE_DOC_COUNT / ENGLISH_DOC_COUNT /
  UNPAIRED_CHINESE_DOC_COUNT / UNPAIRED_ENGLISH_DOC_COUNT /
  MISSING_LANGUAGE_SWITCH_COUNT
Exit code 0 only when all counters are 0 except the *_COUNT totals.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "docs", "doc-map.json")

def main():
    with open(MAP, encoding="utf-8") as f:
        docmap = json.load(f)
    pairs = docmap["pairs"]
    zh_set = set(p["zh"] for p in pairs)
    en_set = set(p["en"] for p in pairs)
    zh_set.add(docmap["readme_cn"])
    en_set.add(docmap["readme_en"])
    zh_set.add(docmap["docs_root_cn"])
    en_set.add(docmap["docs_root_en"])

    zh_docs = []
    en_docs = []
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, "docs")):
        if ".git" in dirs: dirs.remove(".git")
        for fn in files:
            if not fn.endswith(".md"): continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace("\\", "/")
            if "/中文/" in rel: zh_docs.append(rel)
            elif rel.startswith("docs/English/"): en_docs.append(rel)
    # root README pair
    zh_docs.append(docmap["readme_cn"])
    en_docs.append(docmap["readme_en"])
    en_docs.append("LICENSE")  # mapped target for the Apache translation reference

    unpaired_zh = sorted(set(zh_docs) - zh_set)
    unpaired_en = sorted(set(en_docs) - en_set)
    mapped_missing_zh = sorted(zh_set - set(zh_docs))
    mapped_missing_en = sorted(en_set - set(en_docs))

    missing_switch = 0
    lang_re = re.compile(r"\*\*?(简体中文|English|中文)\*\*?")
    for p in pairs:
        for side in ("zh", "en"):
            path = os.path.join(ROOT, p[side])
            if not os.path.exists(path):
                continue
            if p[side] == "LICENSE":
                continue  # license text is not a navigable document
            head = open(path, encoding="utf-8", errors="replace").read(400)
            if not lang_re.search(head):
                missing_switch += 1
                print(f"MISSING_LANGUAGE_SWITCH {p[side]}")

    for d in mapped_missing_zh:
        print(f"MAP_POINTS_TO_MISSING_ZH {d}")
    for d in mapped_missing_en:
        print(f"MAP_POINTS_TO_MISSING_EN {d}")

    print(f"DOC_MAP_ENTRY_COUNT={len(pairs)}")
    print(f"CHINESE_DOC_COUNT={len(zh_docs)}")
    print(f"ENGLISH_DOC_COUNT={len(en_docs)}")
    print(f"UNPAIRED_CHINESE_DOC_COUNT={len(unpaired_zh)}")
    print(f"UNPAIRED_ENGLISH_DOC_COUNT={len(unpaired_en)}")
    print(f"MISSING_LANGUAGE_SWITCH_COUNT={missing_switch}")

    ok = (not unpaired_zh) and (not unpaired_en) and missing_switch == 0 \
         and (not mapped_missing_zh) and (not mapped_missing_en)
    print("DOC_PARITY_PASS=" + ("True" if ok else "False"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
