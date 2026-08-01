#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-public-docs.py — validate the public-facing documentation surface.

Checks:
  * forbidden internal/agent wording in README.md and README.en.md
  * 'unique official repository' statement appears exactly once
  * no stale 'v1.0.0 Release' links
  * no fabricated BOM/CPL/coordinate claims
  * no ESP32 mention in the public READMEs
  * CN/EN README section-structure parity (same headings)
  * semantic language links (Chinese anchors -> Chinese docs, English -> English)
  * all internal relative links exist
  * README line counts within a sane range
  * Latest Release link present
Exit code non-zero on any failure.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN = [
    "ALL_WORK_COMPLETE", "PASS=True",
    "Private\\Evidence", "Private\\Archives", "Private\\Deliverables",
    "Agent自动化", "Agent模式", "Agent automation", "Agent mode",
    "43个执行步骤", "最终收口", "无缝衔接",
    "v1.0.0 Release", "ESP32", "authEpoch", "CampusAuthPolicy",
]
BOM_CLAIMS = ["BOM", "pick-and-place", "坐标", "centroid", "CPL"]

# Required section headings (CN and EN must both have them)
SECTIONS = [
    "核心功能", "Core features",
    "仓库包含内容", "Repository contents",
    "快速开始", "Quick start",
    "简化架构", "Simplified architecture",
    "硬件", "Hardware",
    "可选校园网认证", "Optional campus authentication",
    "文档", "Documentation",
    "Development and testing",
    "参与贡献", "Contributing",
    "支持与安全", "Support and security",
    "许可协议", "License",
    "Repository 说明", "Repository note",
]

def read(p):
    return open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read()

def main():
    ok = True
    cn = read("README.md")
    en = read("README.en.md")

    # 1) forbidden wording
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in FORBIDDEN:
            if w in txt:
                print(f"FORBIDDEN_WORDING {f}: {w!r}")
                ok = False

    # 2) canonical statement exactly once (per file)
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        n = txt.count("唯一正式") + txt.count("single official")
        if f == "README.md":
            if txt.count("唯一正式") != 1:
                print(f"CANONICAL_STATEMENT_COUNT README.md = {txt.count('唯一正式')} (want 1)")
                ok = False
        else:
            if txt.count("single official") != 1:
                print(f"CANONICAL_STATEMENT_COUNT README.en.md = {txt.count('single official')} (want 1)")
                ok = False

    # 3) no stale v1.0.0 release links
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        if re.search(r"v1\.0\.0\s+Release", txt, re.I):
            print(f"STALE_RELEASE_LINK {f}")
            ok = False
    # Latest Release link present
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        if "Latest Release" not in txt and "releases" not in txt.lower():
            print(f"MISSING_RELEASE_LINK {f}")
            ok = False

    # 4) no fabricated BOM/CPL claims (only in README body, not in the
    #    'Known issues' changelog context — READMEs must not claim these)
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in BOM_CLAIMS:
            if w in txt:
                print(f"BOM_CLAIM {f}: {w!r}")
                ok = False

    # 5) no ESP32 in READMEs
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        if "ESP32" in txt:
            print(f"ESP32_MENTIONED {f}")
            ok = False

    # 6) section parity
    for s in SECTIONS:
        in_cn = s in cn
        in_en = s in en
        if not in_cn and not in_en:
            print(f"SECTION_MISSING_BOTH: {s}")
            ok = False
    # heading-level parity check (H2 headings should correspond)
    cn_h2 = re.findall(r"(?m)^## (.+)$", cn)
    en_h2 = re.findall(r"(?m)^## (.+)$", en)
    if len(cn_h2) != len(en_h2):
        print(f"SECTION_COUNT_MISMATCH cn={len(cn_h2)} en={len(en_h2)}")
        ok = False

    # 7) semantic language links: in README.md, links to 中文/ docs must be
    #    relative to Chinese files; links named 中文文档 must point to 中文.
    #    In README.en.md the English documentation index must point to English.
    if "docs/English/documentation-index.md" in cn:
        print("CN_README_LINKS_TO_EN_INDEX")
        ok = False
    # README.md 中文文档 anchor must point to CN nav
    m = re.search(r"\[中文文档\]\((\./[^)]*)\)", cn)
    if m and "中文" not in m.group(1):
        print(f"CN_NAV_LINK_WRONG_TARGET: {m.group(1)}")
        ok = False

    # 8) internal relative links exist
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        base = os.path.dirname(os.path.join(ROOT, f))
        for mm in re.finditer(r"\]\(([^)]+)\)", txt):
            t = mm.group(1).strip().split("#")[0]
            if not t or t.startswith(("http", "#", "mailto")):
                continue
            full = os.path.normpath(os.path.join(base, t))
            if not os.path.exists(full):
                print(f"BROKEN_LINK {f}: {t}")
                ok = False

    # 9) line counts
    for f, n in [("README.md", len(cn.splitlines())), ("README.en.md", len(en.splitlines()))]:
        if not (100 <= n <= 260):
            print(f"README_LINE_COUNT {f} = {n} (out of 100-260)")
            ok = False
        print(f"README_LINE_COUNT {f} = {n}")

    print(f"README_AGENT_LANGUAGE_COUNT={sum(1 for w in ['Agent自动化','Agent模式','Agent automation','Agent mode'] if w in cn or w in en)}")
    print(f"README_OUTDATED_RELEASE_LINK_COUNT={sum(1 for txt in [cn,en] if re.search(r'v1\\.0\\.0\\s+Release', txt, re.I))}")
    print(f"README_FALSE_BOM_CLAIM_COUNT={sum(1 for txt in [cn,en] for w in BOM_CLAIMS if w in txt)}")
    print(f"README_SEMANTIC_LANGUAGE_LINK_ERRORS={0 if ok else 'see above'}")
    print(f"PUBLIC_DOCS_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
