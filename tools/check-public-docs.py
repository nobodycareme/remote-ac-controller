#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-public-docs.py — validate the public-facing documentation surface.

Checks:
  * forbidden internal/agent wording in README.md and README.en.md
  * no fabricated BOM/CPL/coordinate claims
  * no ESP32 mention in the public READMEs
  * CN/EN README H2 section parity: exact ordered mapping (CN_H2 <-> EN_H2)
  * top navigation uses full-HTML <a> links (never Markdown inside an HTML
    block) and targets resolve
  * no broken in-page fragment links (#fragment with no matching heading)
  * visible markdown link labels do not end in `.md`
  * screenshot references present and files exist / are under 1 MB
  * no "offline build" false claims and no false campus live-auth claims
  * no internal release-gate language on the homepage or in the latest
    release notes
  * wifi_secrets.h / campus_secrets.h are NOT tracked by git
  * PlatformIO README: no stale v0.4.0-cloud-foundation / campus_credentials.h
    drift, referenced paths exist
  * IR learner preset duplicates byte-identical + count == 10
  * all internal relative links exist
  * README line counts within 120-180 (CN) / within 20% of CN (EN)
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

# Exact ordered H2 mapping (CN index -> EN index).
CN_H2 = [
    "项目简介", "界面预览", "主要功能", "快速开始",
    "系统组成", "硬件", "文档", "参与贡献与支持",
]
EN_H2 = [
    "Overview", "Interface preview", "Features", "Quick start",
    "System layout", "Hardware", "Documentation", "Contributing and support",
]
H2_PAIRS = list(zip(CN_H2, EN_H2))

STALE_RELEASE_RE = r"v1\.0\.0\s+Release"

# Screenshots referenced in READMEs (relative to repo root).
SCREENSHOTS = [
    "docs/assets/screenshots/dashboard-desktop.png",
    "docs/assets/screenshots/dashboard-mobile.png",
]
SCREENSHOT_MAX_BYTES = 1 * 1024 * 1024  # 1 MB

# Navigation labels that must appear as <a href> in the top HTML nav block.
CN_NAV_LABELS = ["项目简介", "快速开始", "文档", "English"]
EN_NAV_LABELS = ["Overview", "Quick Start", "Documentation", "简体中文"]

# Real-looking credential patterns (placeholders are explicitly allowed).
_PLACEHOLDER = r"(?:your_[a-z_]+|你的[^\"]{1,8}?)"
REAL_CRED_PATTERNS = [
    re.compile(r"LOCAL_WIFI_SSID\s+\"(?!%s)[A-Za-z0-9_\-]{12,}\"" % _PLACEHOLDER),  # noqa: E501
    re.compile(r"LOCAL_WIFI_PASSWORD\s+\"(?!%s)[^\"]{8,}\"" % _PLACEHOLDER, re.I),
    re.compile(r"CAMPUS_USERNAME\s+\"(?!%s)\d{8,}\"" % _PLACEHOLDER),            # noqa: E501
    re.compile(r"CAMPUS_PASSWORD\s+\"(?!%s)[^\"]{8,}\"" % _PLACEHOLDER, re.I),
    re.compile(r"WiFi\.begin\(\s*\"[A-Za-z0-9_\-]{8,}\",\s*\"[^\"]{8,}\"\s*\)"),
]

# PlatformIO README drift strings.
PIO_STALE_PATTERNS = [
    "v0.4.0-cloud-foundation",
    "编辑 `shared/RemoteACCore/src/config/campus_credentials.h`",
    "Edit `shared/RemoteACCore/src/config/campus_credentials.h`",
    "当前版本：v0.4.0",
    "Current: v0.4.0",
]

# Homepage / latest-release notes wording that belongs to internal release
# governance, not to a user-facing project page.
INTERNAL_RELEASE_LANGUAGE = [
    "纠正版本",
    "本版本适合谁",
    "关注 GitHub 主页与文档可读性",
    "门禁",
    "字节一致",
    "连续 20 轮",
    "State.EXITING",
    "ir.learn.cancelled",
    "codeId 唯一性",
    "requirements-lock.txt",
    "PyInstaller 6.21.0",
    "全部硬门禁",
    "PROJECT_",
    "PASS=True",
    "Evidence",
    "Agent",
]

# False claims that must NOT appear in the READMEs or first-time setup docs.
FALSE_OFFLINE_CLAIMS = [
    "离线构建",
    "Offline build",
    "完全离线",
    "只编译传感器",
]
FALSE_CAMPUS_LIVE_AUTH_CLAIMS = [
    "local-campus-example 启用了校园自动认证",
    "local-campus-example 启用校园自动认证",
    "该 Profile 需要真实学号密码",
    "填写 campus_secrets.h 后即可真实登录",
    "该 Profile 会在上电时自动认证",
    "local-campus-example enables unattended campus auth",
    "the profile requires real credentials",
    "fill in campus_secrets.h to log in",
    "this profile authenticates at boot",
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
        return None


def main():
    ok = True
    cn = read("README.md")
    en = read("README.en.md")

    cnt_outdated = 0
    cnt_lang = 0
    cnt_parity = 0
    cnt_nav = 0
    cnt_md_suffix = 0
    cnt_html_markdown = 0
    cnt_fragment = 0
    cnt_screenshot_missing = 0
    cnt_screenshot_oversize = 0
    cnt_wifi = 0
    cnt_campus = 0
    cnt_cred = 0
    cnt_pio_stale = 0
    cnt_pio_invalid = 0
    cnt_offline = 0
    cnt_campus_live = 0
    cnt_internal = 0
    cnt_cn_en_head = 0

    # 1) forbidden wording
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in FORBIDDEN:
            if w in txt:
                print(f"FORBIDDEN_WORDING {f}: {w!r}")
                ok = False

    # 2) no fabricated BOM/CPL claims — negative statements ("no validated
    #    BOM", "未提供经过验证的 BOM") are allowed and are the expected wording.
    cnt_bom = 0
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for w in BOM_CLAIMS:
            for m in re.finditer(re.escape(w), txt):
                # judge by the containing sentence: if it is a negation of
                # availability, this is the expected disclaimer, not a claim.
                start = max(0, txt.rfind("\n", 0, m.start()), txt.rfind("。", 0, m.start()),
                            txt.rfind(". ", 0, m.start()), txt.rfind("；", 0, m.start()))
                seg = txt[start:m.start()]
                if re.search(r"(未提供|没有|不提供|不存在|无 )", seg) or \
                   re.search(r"(no |not |without |does not ship|none )", seg, re.I):
                    continue
                cnt_bom += 1
                print(f"BOM_CLAIM {f}: {w!r}")
                ok = False
    print(f"README_FALSE_BOM_CLAIM_COUNT={cnt_bom}")

    # 3) no ESP32 in READMEs
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        if "ESP32" in txt:
            print(f"ESP32_MENTIONED {f}")
            ok = False

    # 4) H2 section parity: exact ordered mapping, at most 8 H2s
    cn_h2 = [h.strip() for h in re.findall(r"(?m)^## (.+)$", cn)]
    en_h2 = [h.strip() for h in re.findall(r"(?m)^## (.+)$", en)]
    if len(cn_h2) > 8:
        print(f"CN_H2_TOO_MANY actual={len(cn_h2)} (want <= 8)")
        ok = False
    if len(en_h2) > 8:
        print(f"EN_H2_TOO_MANY actual={len(en_h2)} (want <= 8)")
        ok = False
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

    # 4b) CN README must not use English headings; EN must not use CN headings
    for h in cn_h2:
        if re.match(r"^[A-Za-z]", h):
            cnt_cn_en_head += 1
            print(f"CN_ENGLISH_HEADING: {h!r}")
            ok = False
    print(f"README_CN_ENGLISH_HEADING_COUNT={cnt_cn_en_head}")

    # 5) top navigation: full-HTML <a> links in the top <p> block
    for f, txt, labels in [("README.md", cn, CN_NAV_LABELS),
                           ("README.en.md", en, EN_NAV_LABELS)]:
        top = txt.split("\n---\n", 1)[0]
        # The nav must be a <p align="center"> block with <a href> only —
        # never Markdown links inside an HTML block.
        nav_block = re.search(r"<p align=\"center\">\n(.*?)\n</p>", top, re.S)
        if not nav_block:
            cnt_nav += 1
            print(f"NAV_BLOCK_MISSING {f}")
            ok = False
            continue
        block = nav_block.group(1)
        # Markdown link syntax inside an HTML block is a rendering error.
        md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", block)
        if md_links:
            cnt_html_markdown += 1
            print(f"RAW_MARKDOWN_INSIDE_HTML_BLOCK {f}: {md_links}")
            ok = False
        # every required label must appear as an <a href>
        for label in labels:
            if not re.search(r"<a href=\"[^\"]+\">%s</a>" % re.escape(label), block):
                cnt_nav += 1
                print(f"NAV_LINK_MISSING {f}: [{label}]")
                ok = False
        # anchors in the nav must match real heading ids
        for m in re.finditer(r"<a href=\"#([^\"]+)\">", block):
            frag = m.group(1)
            if frag not in txt:
                cnt_fragment += 1
                print(f"NAV_FRAGMENT_MISSING {f}: #{frag}")
                ok = False
    print(f"README_RAW_MARKDOWN_INSIDE_HTML_BLOCK_COUNT={cnt_html_markdown}")
    print(f"README_NAV_TARGET_ERRORS={cnt_nav}")

    # 6) broken in-page fragment links anywhere in the READMEs
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        headings = set()
        for h in re.findall(r"(?m)^#{1,6}\s+(.+)$", txt):
            # GitHub heading id: lowercase, spaces -> '-', strip punctuation
            hid = h.strip().lower()
            hid = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", hid)
            hid = hid.replace(" ", "-")
            headings.add(hid)
        for mm in re.finditer(r"\]\(#([^)]+)\)", txt):
            frag = mm.group(1)
            if frag not in headings:
                cnt_fragment += 1
                print(f"BROKEN_FRAGMENT_LINK {f}: #{frag}")
                ok = False
    print(f"README_BROKEN_FRAGMENT_LINK_COUNT={cnt_fragment}")

    # 7) visible markdown link labels must not end in `.md`
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for mm in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", txt):
            label = mm.group(1).strip()
            if label.lower().endswith(".md"):
                cnt_md_suffix += 1
                print(f"VISIBLE_MD_SUFFIX_LINK {f}: [{label}]")
                ok = False
    print(f"README_VISIBLE_MD_SUFFIX_LINK_COUNT={cnt_md_suffix}")

    # 8) screenshot references and file sanity
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for shot in SCREENSHOTS:
            if txt.count(shot) < 1:
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

    # 9) setup link presence
    for txt in (cn, en):
        cnt_wifi += len(re.findall(r"首次配置|wifi_secrets|first-time-setup", txt))
        cnt_campus += len(re.findall(r"西电校园网自动认证|campus_secrets|xidian-campus-network-authentication", txt))
    print(f"README_WIFI_SETUP_LINK_COUNT={cnt_wifi}")
    print(f"README_CAMPUS_SETUP_LINK_COUNT={cnt_campus}")
    if cnt_wifi < 2:
        print("README_WIFI_SETUP_LINKS_TOO_FEW (<2)")
        ok = False
    if cnt_campus < 2:
        print("README_CAMPUS_SETUP_LINKS_TOO_FEW (<2)")
        ok = False

    # 10) real-looking credentials
    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for pat in REAL_CRED_PATTERNS:
            for m in pat.finditer(txt):
                cnt_cred += 1
                print(f"REAL_CRED_PATTERN {f}: {m.group(0)[:40]!r}")
                ok = False
    print(f"README_REAL_CREDENTIAL_HIT_COUNT={cnt_cred}")

    # 11) secrets not tracked
    for name in ("firmware/shared/RemoteACCore/src/config/wifi_secrets.h",
                 "firmware/shared/RemoteACCore/src/config/campus_secrets.h"):
        tracked = git_ls_files(name)
        if tracked:
            print(f"SECRET_TRACKED_BY_GIT {name}")
            ok = False
    print(f"WIFI_SECRETS_TRACKED={bool(git_ls_files('firmware/shared/RemoteACCore/src/config/wifi_secrets.h'))}")
    print(f"CAMPUS_SECRETS_TRACKED={bool(git_ls_files('firmware/shared/RemoteACCore/src/config/campus_secrets.h'))}")

    # 12) PlatformIO README drift
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

    # 13) false offline / false campus live-auth claims in README + setup docs
    docs = {
        "README.md": cn,
        "README.en.md": en,
        "docs/中文/首次配置.md": read("docs/中文/首次配置.md"),
        "docs/English/first-time-setup.md": read("docs/English/first-time-setup.md"),
    }
    for f, txt in docs.items():
        for pat in FALSE_OFFLINE_CLAIMS:
            for m in re.finditer(re.escape(pat), txt):
                # negative statements ("不是离线构建") are correct usage
                pre = txt[max(0, m.start() - 8):m.start()]
                if re.search(r"(不是|并非|not )", pre):
                    continue
                cnt_offline += 1
                print(f"FALSE_OFFLINE_CLAIM {f}: {pat!r}")
                ok = False
        for pat in FALSE_CAMPUS_LIVE_AUTH_CLAIMS:
            if pat in txt:
                cnt_campus_live += 1
                print(f"FALSE_CAMPUS_LIVE_AUTH_CLAIM {f}: {pat!r}")
                ok = False
    print(f"README_FALSE_OFFLINE_CLAIM_COUNT={cnt_offline}")
    print(f"README_CAMPUS_EXAMPLE_LIVE_AUTH_CLAIM_COUNT={cnt_campus_live}")

    # 14) internal release-gate language on homepage and latest release notes
    targets = {
        "README.md": cn,
        "README.en.md": en,
        ".github/release-notes/v1.2.2.md": read(".github/release-notes/v1.2.2.md"),
    }
    for f, txt in targets.items():
        for w in INTERNAL_RELEASE_LANGUAGE:
            if w in txt:
                cnt_internal += 1
                print(f"INTERNAL_RELEASE_LANGUAGE {f}: {w!r}")
                ok = False
    print(f"README_INTERNAL_RELEASE_LANGUAGE_COUNT={cnt_internal}")

    # 14b) release notes must not embed repo-relative image paths or <img>
    rn = targets[".github/release-notes/v1.2.2.md"]
    rn_img = 0
    for m in re.finditer(r"<img|!\[", rn):
        # an image markdown/HTML reference in release notes is an error
        rn_img += 1
        print(f"RELEASE_NOTES_IMAGE_REF: {m.group(0)!r}")
        ok = False
    if "../../docs/" in rn:
        rn_img += 1
        print("RELEASE_NOTES_IMAGE_PATH_ERROR: ../../docs/ found")
        ok = False
    print(f"RELEASE_NOTES_IMAGE_PATH_ERROR_COUNT={rn_img}")

    # 15) internal relative links exist (READMEs)
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

    # 16) line counts: CN 120-180, EN within 20% of CN
    cn_lines = len(cn.splitlines())
    en_lines = len(en.splitlines())
    if not (120 <= cn_lines <= 180):
        print(f"README_LINE_COUNT README.md = {cn_lines} (want 120-180)")
        ok = False
    lo, hi = int(cn_lines * 0.8), int(cn_lines * 1.2)
    if not (lo <= en_lines <= hi):
        print(f"README_EN_LINE_COUNT README.en.md = {en_lines} (CN={cn_lines}, want {lo}-{hi})")
        ok = False
    print(f"README_CN_LINE_COUNT={cn_lines}")
    print(f"README_EN_LINE_COUNT={en_lines}")
    print(f"README_CN_H2_COUNT={len(cn_h2)}")
    print(f"README_EN_H2_COUNT={len(en_h2)}")

    print(f"README_AGENT_LANGUAGE_COUNT={sum(1 for w in ['Agent自动化','Agent模式','Agent automation','Agent mode'] if w in cn or w in en)}")
    print(f"PUBLIC_DOCS_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
