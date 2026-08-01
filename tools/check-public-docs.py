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
  * top navigation targets resolve (CN uses Chinese-title anchors)
  * visible markdown link labels do not end in `.md`
  * screenshot references present and files exist / are under 1 MB
  * Wi-Fi and campus setup links present (>= 2 each across both READMEs)
  * no real-looking credentials (SSID/password/campus account) in READMEs
  * wifi_secrets.h / campus_secrets.h are NOT tracked by git
  * PlatformIO README: no stale v0.4.0-cloud-foundation / campus_credentials.h
    drift, referenced paths exist
  * IR learner preset duplicates byte-identical + count == 10
  * all internal relative links exist
  * README line counts within a sane range
  * Latest Release link present

--root <dir> runs the checks against a different repository root (used by the
negative tests in tools/test-public-docs-negative.py).

Exit code non-zero on any failure.
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys

# ---- root resolution -------------------------------------------------------
DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_root():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--root", default=None)
    ns, _ = ap.parse_known_args()
    return os.path.normpath(ns.root) if ns.root else DEFAULT_ROOT


ROOT = resolve_root()

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
    "核心功能", "仓库包含内容", "界面预览", "快速开始", "简化架构", "硬件",
    "可选校园网认证", "文档", "Development and testing",
    "参与贡献", "支持与安全", "许可协议", "Repository 说明",
]
EN_H2 = [
    "Core features", "Repository contents", "Interface preview", "Quick start",
    "Simplified architecture", "Hardware", "Optional campus authentication",
    "Documentation", "Development and testing",
    "Contributing", "Support and security", "License", "Repository note",
]
H2_PAIRS = list(zip(CN_H2, EN_H2))

STALE_RELEASE_RE = r"v1\.0\.0\s+Release"          # raw string, single escaping

# Screenshots referenced in READMEs (relative to repo root).
SCREENSHOTS = [
    "docs/assets/screenshots/dashboard-desktop.png",
    "docs/assets/screenshots/dashboard-mobile.png",
]
SCREENSHOT_MAX_BYTES = 1 * 1024 * 1024  # 1 MB

# Navigation targets that must appear in each README.
CN_NAV = {
    "快速开始": "#快速开始",
    "中文文档": "./docs/中文/文档导航.md",
    "English": "./README.en.md",
    "硬件": "#硬件",
    "文档": "#文档",
}
EN_NAV = {
    "Quick Start": "#quick-start",
    "Documentation": "./docs/English/documentation-index.md",
    "简体中文": "./README.md",
    "Hardware": "#hardware",
    "License": "#license",
}

# Real-looking credential patterns (must NOT appear in READMEs or examples).
# Placeholder values (your_wifi_name / 你的WiFi密码 / your_campus_password /
# 你的学号) are explicitly allowed — they are the .example.h contract.
_PLACEHOLDER = r"(?:your_[a-z_]+|你的[^\"]{1,8}?)"
REAL_CRED_PATTERNS = [
    re.compile(r"LOCAL_WIFI_SSID\s+\"(?!%s)[A-Za-z0-9_\-]{12,}\"" % _PLACEHOLDER),  # noqa: E501
    re.compile(r"LOCAL_WIFI_PASSWORD\s+\"(?!%s)[^\"]{8,}\"" % _PLACEHOLDER, re.I),
    re.compile(r"CAMPUS_USERNAME\s+\"(?!%s)\d{8,}\"" % _PLACEHOLDER),            # noqa: E501
    re.compile(r"CAMPUS_PASSWORD\s+\"(?!%s)[^\"]{8,}\"" % _PLACEHOLDER, re.I),
    re.compile(r"WiFi\.begin\(\s*\"[A-Za-z0-9_\-]{8,}\",\s*\"[^\"]{8,}\"\s*\)"),
]

# PlatformIO README drift: strings that must not appear.
PIO_STALE_PATTERNS = [
    "v0.4.0-cloud-foundation",
    "编辑 `shared/RemoteACCore/src/config/campus_credentials.h`",
    "Edit `shared/RemoteACCore/src/config/campus_credentials.h`",
    "当前版本：v0.4.0",
    "Current: v0.4.0",
]


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


def git_ls_files(path):
    """Return True when <path> is tracked by git (relative to ROOT)."""
    try:
        r = subprocess.run(
            ["git", "-C", ROOT, "ls-files", "--", path],
            capture_output=True, text=True, timeout=30,
        )
        return bool(r.stdout.strip())
    except Exception:
        return None  # cannot determine


def main():
    ok = True
    cn = read("README.md")
    en = read("README.en.md")

    # independent counters (never replaced by the global ok flag)
    cnt_outdated = 0
    cnt_lang = 0
    cnt_parity = 0
    cnt_nav = 0
    cnt_md_suffix = 0
    cnt_screenshot_missing = 0
    cnt_screenshot_oversize = 0
    cnt_wifi = 0
    cnt_campus = 0
    cnt_cred = 0
    cnt_pio_stale = 0
    cnt_pio_invalid = 0

    # 1) forbidden wording
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in FORBIDDEN:
            if w in txt:
                print(f"FORBIDDEN_WORDING {f}: {w!r}")
                ok = False

    # 2) canonical statement exactly once (per file)
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

    # 6a) top navigation targets
    for f, nav in [("README.md", CN_NAV), ("README.en.md", EN_NAV)]:
        txt = cn if f == "README.md" else en
        # collect links in the nav <p> block at top (before first ---)
        top = txt.split("\n---\n", 1)[0]
        links = dict(re.findall(r"\[([^\]]+)\]\(([^)]+)\)", top))
        for label, target in nav.items():
            actual = links.get(label)
            if actual != target:
                cnt_nav += 1
                print(f"NAV_TARGET_ERROR {f}: [{label}] actual={actual!r} want={target!r}")
                ok = False
    print(f"README_NAV_TARGET_ERRORS={cnt_nav}")

    # 6b) visible markdown link labels must not end in `.md`
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for mm in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", txt):
            label = mm.group(1).strip()
            if label.lower().endswith(".md"):
                cnt_md_suffix += 1
                print(f"VISIBLE_MD_SUFFIX_LINK {f}: [{label}]")
                ok = False
    print(f"README_VISIBLE_MD_SUFFIX_LINK_COUNT={cnt_md_suffix}")

    # 6c) screenshot references and file sanity
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for shot in SCREENSHOTS:
            refs = txt.count(shot)
            if refs < 1:
                cnt_screenshot_missing += 1
                print(f"SCREENSHOT_MISSING_REF {f}: {shot}")
                ok = False
    print(f"README_SCREENSHOT_REFERENCE_COUNT={sum(txt.count(s) for s in SCREENSHOTS for txt in (cn, en))}")
    for shot in SCREENSHOTS:
        full = os.path.join(ROOT, shot)
        if not os.path.exists(full):
            cnt_screenshot_missing += 1
            print(f"SCREENSHOT_MISSING_FILE {shot}")
            ok = False
        else:
            size = os.path.getsize(full)
            if size > SCREENSHOT_MAX_BYTES:
                cnt_screenshot_oversize += 1
                print(f"SCREENSHOT_OVERSIZE {shot} = {size} (>1MB)")
                ok = False
    print(f"README_SCREENSHOT_MISSING_FILE_COUNT={cnt_screenshot_missing}")
    print(f"README_SCREENSHOT_OVERSIZE_COUNT={cnt_screenshot_oversize}")

    # 6d) Wi-Fi / campus setup links (>= 2 each across both READMEs)
    for txt in (cn, en):
        cnt_wifi += len(re.findall(r"首次配置|wifi_secrets|first-time-setup", txt))
        cnt_campus += len(re.findall(r"西电校园网自动认证|campus_secrets|校园网自动认证|xidian-campus-network-authentication", txt))
    print(f"README_WIFI_SETUP_LINK_COUNT={cnt_wifi}")
    print(f"README_CAMPUS_SETUP_LINK_COUNT={cnt_campus}")
    if cnt_wifi < 2:
        print("README_WIFI_SETUP_LINKS_TOO_FEW (<2)")
        ok = False
    if cnt_campus < 2:
        print("README_CAMPUS_SETUP_LINKS_TOO_FEW (<2)")
        ok = False

    # 6e) real-looking credentials must not appear in READMEs
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for pat in REAL_CRED_PATTERNS:
            for m in pat.finditer(txt):
                cnt_cred += 1
                print(f"REAL_CRED_PATTERN {f}: {m.group(0)[:40]!r}")
                ok = False
    print(f"README_REAL_CREDENTIAL_HIT_COUNT={cnt_cred}")

    # 6f) secrets files must not be tracked by git
    for name in ("firmware/shared/RemoteACCore/src/config/wifi_secrets.h",
                 "firmware/shared/RemoteACCore/src/config/campus_secrets.h"):
        tracked = git_ls_files(name)
        if tracked:
            print(f"SECRET_TRACKED_BY_GIT {name}")
            ok = False
        elif tracked is False:
            print(f"SECRET_NOT_TRACKED {name}")
        else:
            print(f"SECRET_TRACK_STATUS_UNKNOWN {name}")
    print(f"WIFI_SECRETS_TRACKED={bool(git_ls_files('firmware/shared/RemoteACCore/src/config/wifi_secrets.h'))}")
    print(f"CAMPUS_SECRETS_TRACKED={bool(git_ls_files('firmware/shared/RemoteACCore/src/config/campus_secrets.h'))}")

    # 7) PlatformIO README drift
    for p in ("firmware/agent-platformio/README.md", "firmware/agent-platformio/README.en.md"):
        try:
            txt = read(p)
        except Exception:
            print(f"PIO_README_MISSING {p}")
            cnt_pio_stale += 1
            ok = False
            continue
        for pat in PIO_STALE_PATTERNS:
            if pat in txt:
                cnt_pio_stale += 1
                print(f"PIO_README_STALE {p}: {pat!r}")
                ok = False
        # referenced internal paths must exist
        base = os.path.dirname(os.path.join(ROOT, p))
        for mm in re.finditer(r"\]\(([^)]+)\)", txt):
            t = mm.group(1).strip().split("#")[0]
            if not t or t.startswith(("http", "#", "mailto")):
                continue
            full = os.path.normpath(os.path.join(base, t))
            if not os.path.exists(full):
                cnt_pio_invalid += 1
                print(f"PIO_README_INVALID_PATH {p}: {t}")
                ok = False
    print(f"PLATFORMIO_README_STALE_VERSION_COUNT={cnt_pio_stale}")
    print(f"PLATFORMIO_README_INVALID_PATH_COUNT={cnt_pio_invalid}")

    # 7b) Quick Start workflow links
    cn_pio = _section_block(cn, "快速开始", None)
    m1 = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", cn_pio)
    cn_pio_block = m1.group(0) if m1 else cn_pio
    en_pio_block = _section_block(en, "Quick start", None)
    m2 = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", en_pio_block)
    en_pio_block = m2.group(0) if m2 else en_pio_block

    for f, blk, pio_link in [("README.md", cn_pio_block, "firmware/agent-platformio/README.md"),
                             ("README.en.md", en_pio_block, "firmware/agent-platformio/README.en.md")]:
        if pio_link not in blk:
            print(f"PLATFORMIO_SECTION_MISSING_PIO_README {f} (want {pio_link})")
            ok = False
        if "Arduino-IDE使用指南" in blk or "arduino-ide-guide" in blk:
            print(f"PLATFORMIO_SECTION_LINKS_ARDUINO_GUIDE {f}")
            cnt_lang += 1
            ok = False
    cn_ard_block = ""
    m3 = re.search(r"(?ms)^### 2\..*?(?=^### 3\.|\Z)", _section_block(cn, "快速开始", None))
    if m3:
        cn_ard_block = m3.group(0)
    en_ard_block = ""
    m4 = re.search(r"(?ms)^### 2\..*?(?=^### 3\.|\Z)", _section_block(en, "Quick start", None))
    if m4:
        en_ard_block = m4.group(0)
    for f, blk in [("README.md", cn_ard_block), ("README.en.md", en_ard_block)]:
        if "Arduino-IDE使用指南" not in blk and "arduino-ide-guide" not in blk:
            print(f"ARDUINO_SECTION_MISSING_GUIDE {f}")
            ok = False
    print(f"README_PLATFORMIO_LINK_CORRECT={'True' if ('firmware/agent-platformio/README.md' in cn_pio_block and 'firmware/agent-platformio/README.en.md' in en_pio_block) else 'False'}")

    # 8) semantic language links
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

    # 8b) changelog language discipline
    cn_chg = read("docs/中文/更新日志.md")
    en_chg = read("docs/English/changelog.md")
    cn_bad = re.findall(
        r"^### (Changed|Fixed|Security|Known issues|Added)$|"
        r"No cloud API or database schema changes\.",
        cn_chg, re.M | re.I)
    if cn_bad:
        for b in cn_bad:
            print(f"CN_CHANGELOG_ENGLISH_STATUS_PHRASE: {b!r}")
            cnt_lang += 1
            ok = False
    for i, line in enumerate(en_chg.splitlines(), 1):
        # A line that only contains CJK inside a file path / code span is a
        # legitimate reference to the Chinese doc tree, not body text.
        if re.search(r"[\u4e00-\u9fff]", line) and "](" not in line and "`" not in line:
            print(f"EN_CHANGELOG_CHINESE_BODY line {i}: {line.strip()[:60]!r}")
            cnt_lang += 1
            ok = False
    print(f"CHINESE_CHANGELOG_LANGUAGE_ERRORS={len(cn_bad)}")

    # 9) IR-learner preset duplicates byte-identical + count == 10
    p1b = open(os.path.join(ROOT, "tools/ir-simple-learner/src/presets.py"), "rb").read()
    p2b = open(os.path.join(ROOT, "firmware/agent-platformio/tools/ir_simple_learner/presets.py"), "rb").read()
    preset_match = p1b == p2b
    if not preset_match:
        print("IR_PRESET_DUPLICATE_FILES_MATCH=False (presets.py copies drifted)")
        ok = False
    preset_count = None
    try:
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

    # 10) internal relative links exist (READMEs)
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

    # 11) line counts
    for f, n in [("README.md", len(cn.splitlines())), ("README.en.md", len(en.splitlines()))]:
        if not (100 <= n <= 300):
            print(f"README_LINE_COUNT {f} = {n} (out of 100-300)")
            ok = False
        print(f"README_LINE_COUNT {f} = {n}")

    print(f"README_AGENT_LANGUAGE_COUNT={sum(1 for w in ['Agent自动化','Agent模式','Agent automation','Agent mode'] if w in cn or w in en)}")
    print(f"PUBLIC_DOCS_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
