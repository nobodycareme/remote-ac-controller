#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-public-docs.py — validate the public-facing documentation surface.

Checks:
  * forbidden internal/agent wording in README.md and README.en.md
  * 'unique official repository' statement appears exactly once
  * no stale 'v1.0.0 Release' links (independent counter)
  * no fabricated BOM/CPL/coordinate claims
  * no ESP32 mention in the public READMEs
  * CN/EN README H2 section parity: exact ordered mapping (CN_H2 <-> EN_H2)
  * Quick Start workflow links: the PlatformIO section links to
    firmware/agent-platformio/README.md and must NOT link the Arduino IDE
    guide; the Arduino IDE section MUST link the Arduino IDE guide
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
    "authEpoch", "CampusAuthPolicy",
]
BOM_CLAIMS = ["BOM", "pick-and-place", "坐标", "centroid", "CPL"]

# Exact ordered H2 mapping (CN index -> EN index). Order matters: the pairs
# must appear in the same relative order in both files.
CN_H2 = [
    "核心功能", "仓库包含内容", "快速开始", "简化架构", "硬件",
    "可选校园网认证", "文档", "Development and testing",
    "参与贡献", "支持与安全", "许可协议", "Repository 说明",
]
EN_H2 = [
    "Core features", "Repository contents", "Quick start",
    "Simplified architecture", "Hardware", "Optional campus authentication",
    "Documentation", "Development and testing",
    "Contributing", "Support and security", "License", "Repository note",
]
H2_PAIRS = list(zip(CN_H2, EN_H2))

STALE_RELEASE_RE = r"v1\.0\.0\s+Release"          # raw string, single escaping


def read(p):
    return open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read()


def _section_block(txt, h2_start, h2_end):
    """Return the text between two H2 headings (exclusive)."""
    m = re.search(r"(?m)^## %s\n(.*?)(?=^## |\Z)" % re.escape(h2_start), txt, re.S)
    if not m:
        return ""
    block = m.group(1)
    if h2_end:
        e = re.search(r"(?m)^## %s$" % re.escape(h2_end), block, re.M)
        if e:
            block = block[: e.start()]
    return block


def main():
    ok = True
    cn = read("README.md")
    en = read("README.en.md")

    # independent counters (never replaced by the global ok flag)
    cnt_outdated = 0
    cnt_lang = 0
    cnt_parity = 0

    # 1) forbidden wording
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in FORBIDDEN:
            if w in txt:
                print(f"FORBIDDEN_WORDING {f}: {w!r}")
                ok = False

    # 2) canonical statement exactly once (per file)
    if txt_cn := cn.count("唯一正式"):
        pass
    if cn.count("唯一正式") != 1:
        print(f"CANONICAL_STATEMENT_COUNT README.md = {cn.count('唯一正式')} (want 1)")
        ok = False
    if en.count("single official") != 1:
        print(f"CANONICAL_STATEMENT_COUNT README.en.md = {en.count('single official')} (want 1)")
        ok = False

    # 3) no stale v1.0.0 release links + Latest Release link
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        n = len(re.findall(STALE_RELEASE_RE, txt, re.I))
        cnt_outdated += n
        if n:
            print(f"STALE_RELEASE_LINK {f}: {n}")
            ok = False
        if "Latest Release" not in txt and "releases" not in txt.lower():
            print(f"MISSING_RELEASE_LINK {f}")
            ok = False
    print(f"README_OUTDATED_RELEASE_LINK_COUNT={cnt_outdated}")

    # 4) no fabricated BOM/CPL claims
    cnt_bom = 0
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in BOM_CLAIMS:
            if w in txt:
                cnt_bom += 1
                print(f"BOM_CLAIM {f}: {w!r}")
                ok = False
    print(f"README_FALSE_BOM_CLAIM_COUNT={cnt_bom}")

    # 5) no ESP32 in READMEs
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        if "ESP32" in txt:
            print(f"ESP32_MENTIONED {f}")
            ok = False

    # 6) H2 section parity: exact ordered mapping
    cn_h2 = [h.strip() for h in re.findall(r"(?m)^## (.+)$", cn)]
    en_h2 = [h.strip() for h in re.findall(r"(?m)^## (.+)$", en)]
    if len(cn_h2) != len(CN_H2):
        cnt_parity += 1
        print(f"CN_H2_COUNT_MISMATCH actual={len(cn_h2)} want={len(CN_H2)}")
        ok = False
    if len(en_h2) != len(EN_H2):
        cnt_parity += 1
        print(f"EN_H2_COUNT_MISMATCH actual={len(en_h2)} want={len(EN_H2)}")
        ok = False
    for i, (c, e) in enumerate(H2_PAIRS):
        if i >= len(cn_h2) or cn_h2[i] != c:
            cnt_parity += 1
            print(f"CN_H2_ORDER_MISMATCH idx={i} actual={cn_h2[i] if i < len(cn_h2) else '<missing>'} want={c}")
            ok = False
        if i >= len(en_h2) or en_h2[i] != e:
            cnt_parity += 1
            print(f"EN_H2_ORDER_MISMATCH idx={i} actual={en_h2[i] if i < len(en_h2) else '<missing>'} want={e}")
            ok = False
    print(f"README_SECTION_PARITY_ERRORS={cnt_parity}")

    # 6b) Quick Start workflow links
    # PlatformIO section: must link firmware/agent-platformio/README.md and
    # must NOT point the reader to the Arduino IDE guide.
    cn_pio = _section_block(cn, "快速开始", None)
    # isolate the PlatformIO sub-block (### 1 ... ### 2)
    m1 = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", cn_pio)
    cn_pio_block = m1.group(0) if m1 else cn_pio
    en_pio_block = _section_block(en, "Quick start", None)
    m2 = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", en_pio_block)
    en_pio_block = m2.group(0) if m2 else en_pio_block

    for f, blk in [("README.md", cn_pio_block), ("README.en.md", en_pio_block)]:
        if "firmware/agent-platformio/README.md" not in blk:
            print(f"PLATFORMIO_SECTION_MISSING_PIO_README {f}")
            ok = False
        if "Arduino-IDE使用指南" in blk or "arduino-ide-guide" in blk:
            print(f"PLATFORMIO_SECTION_LINKS_ARDUINO_GUIDE {f}")
            cnt_lang += 1
            ok = False
    # Arduino IDE section: must include the Arduino IDE guide
    cn_ard = _section_block(cn, "快速开始", None)
    m3 = re.search(r"(?ms)^### 2\..*?(?=^### 3\.|\Z)", cn_ard)
    cn_ard_block = m3.group(0) if m3 else ""
    en_ard_block = _section_block(en, "Quick start", None)
    m4 = re.search(r"(?ms)^### 2\..*?(?=^### 3\.|\Z)", en_ard_block)
    en_ard_block = m4.group(0) if m4 else ""
    for f, blk in [("README.md", cn_ard_block), ("README.en.md", en_ard_block)]:
        if "Arduino-IDE使用指南" not in blk and "arduino-ide-guide" not in blk:
            print(f"ARDUINO_SECTION_MISSING_GUIDE {f}")
            ok = False
    print(f"README_PLATFORMIO_LINK_CORRECT={'True' if ('firmware/agent-platformio/README.md' in cn_pio_block and 'firmware/agent-platformio/README.md' in en_pio_block) else 'False'}")

    # 7) semantic language links
    if "docs/English/documentation-index.md" in cn:
        print("CN_README_LINKS_TO_EN_INDEX")
        cnt_lang += 1
        ok = False
    m = re.search(r"\[中文文档\]\((\./[^)]*)\)", cn)
    if m and "中文" not in m.group(1):
        print(f"CN_NAV_LINK_WRONG_TARGET: {m.group(1)}")
        cnt_lang += 1
        ok = False
    print(f"README_SEMANTIC_LANGUAGE_LINK_ERRORS={cnt_lang}")

    # 7b) changelog language discipline
    # Chinese changelog must not contain full English status phrases.
    cn_chg = read("docs/中文/更新日志.md")
    en_chg = read("docs/English/changelog.md")
    cn_bad = re.findall(
        r"## \[1\.2\.1\] - Unreleased|^### (Changed|Fixed|Security|Known issues|Added)$|"
        r"No cloud API or database schema changes\.",
        cn_chg, re.M | re.I)
    if cn_bad:
        for b in cn_bad:
            print(f"CN_CHANGELOG_ENGLISH_STATUS_PHRASE: {b!r}")
            cnt_lang += 1
            ok = False
    # English changelog must not contain Chinese body text (language-switch
    # link lines are exempt).
    for i, line in enumerate(en_chg.splitlines(), 1):
        if re.search(r"[\u4e00-\u9fff]", line) and "](<" not in line and "](.." not in line and "](.\\" not in line:
            # a line with CJK that is not a markdown link is body text
            if "](" not in line:
                print(f"EN_CHANGELOG_CHINESE_BODY line {i}: {line.strip()[:60]!r}")
                cnt_lang += 1
                ok = False
    print(f"CHINESE_CHANGELOG_LANGUAGE_ERRORS={cn_bad.__len__()}")

    # 7c) IR-learner preset duplicates must stay byte-identical
    p1 = read("tools/ir-simple-learner/src/presets.py")
    p2 = read("firmware/agent-platformio/tools/ir_simple_learner/presets.py")
    p1b = open(os.path.join(ROOT, "tools/ir-simple-learner/src/presets.py"), "rb").read()
    p2b = open(os.path.join(ROOT, "firmware/agent-platformio/tools/ir_simple_learner/presets.py"), "rb").read()
    preset_match = p1b == p2b
    if not preset_match:
        print("IR_PRESET_DUPLICATE_FILES_MATCH=False (presets.py copies drifted)")
        ok = False
    # preset count comes from the actual list, never a hardcoded docstring
    preset_count = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "presets_mod", os.path.join(ROOT, "tools/ir-simple-learner/src/presets.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        preset_count = len(mod.PRESETS)
    except Exception:
        pass
    if preset_count != 10:
        print(f"IR_LEARNER_PRESET_COUNT={preset_count} (want 10)")
        ok = False
    else:
        print(f"IR_LEARNER_PRESET_COUNT={preset_count}")
    print(f"IR_PRESET_DUPLICATE_FILES_MATCH={preset_match}")

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
    print(f"PUBLIC_DOCS_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
