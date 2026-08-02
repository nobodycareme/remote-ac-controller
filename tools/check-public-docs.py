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

# ---- v1.2.3 factual-accuracy claims (section 10) ----------------------------
# Claims that have NO code basis and must never appear (positive assertions;
# negated statements are fine and are excluded below by sentence context).
FIRMWARE_ONLY_PHONE_CONTROL_CLAIMS = [
    "只在家里用手机控制空调，可以只部署固件",
    "只部署固件即可手机控制",
    "只部署固件",
    "run only the firmware for home use",
    "only the firmware to control",
]
SIMULATOR_CLAIMS = [
    "模拟设备",
    "先用模拟设备",
    "simulated device",
    "a simulator",
]
COMPONENT_REPLACEMENT_OVERCLAIMS = [
    "单独替换某一端不会影响其他部分",
    "can be replaced without touching the others",
    "can be replaced without touching",
]
HARDWARE_COMPATIBILITY_OVERCLAIMS = [
    "ESP8266 系列开发板配合支持红外发射的模块即可运行固件",
    "any ESP8266-family board with an IR transmitter can run",
]
PUBLIC_PROFILE_AUTO_CONNECT_FALSE = [
    "Cloud 启用就会自动联网",
    "Cloud启用就会自动联网",
    "cloud builds autoconnect",
]
# "完全离线" positive claims are already covered by FALSE_OFFLINE_CLAIMS;
# PUBLIC_PROFILE_OFFLINE_FALSE_CLAIM adds the explicit "public is fully
# offline / sensors only" phrasing that must never be used.
PUBLIC_PROFILE_OFFLINE_FALSE = [
    "public 是完全离线",
    "public 只编译传感器",
    "public is fully offline",
    "public builds sensors only",
]
# First-time setup accuracy.
SETUP_ARDUINO_GLOBALS_WRONG = [
    "编辑 `globals.h`",
    "在 `globals.h` 中配置",
    "configure `globals.h`",
    "in `globals.h`",
    "`globals.h` 中",
]
SETUP_LWC_COMPILE_ONLY_FALSE = [
    "local-wifi-cloud 只编译 Cloud 代码",
    "local-wifi-cloud 无需 Cloud 凭据",
    "local-wifi-cloud does not need cloud credentials",
    "local-wifi-cloud compile-only",
]
# Campus guide internal audit language (never user-facing).
CAMPUS_GUIDE_AUDIT_LANGUAGE = [
    "XIDIAN_PROFILE_PUBLIC_PARAMETERS_VERIFIED",
    "只读实证核验",
    "只读复验",
    "逐字符一致",
    "实证确认",
    "参数核验时间",
    "verified read-only",
    "character for character",
    "re-verification on",
    "confirmed by portal probing",
    "Verification status:",
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
        ".github/release-notes/v1.2.3.md": read(".github/release-notes/v1.2.3.md"),
    }
    for f, txt in targets.items():
        for w in INTERNAL_RELEASE_LANGUAGE:
            if w in txt:
                cnt_internal += 1
                print(f"INTERNAL_RELEASE_LANGUAGE {f}: {w!r}")
                ok = False
    print(f"README_INTERNAL_RELEASE_LANGUAGE_COUNT={cnt_internal}")

    # 14b) release notes must not embed repo-relative image paths or <img>
    rn = targets[".github/release-notes/v1.2.2.md"] + \
         targets[".github/release-notes/v1.2.3.md"]
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

    # 17) v1.2.3 factual-accuracy claims (README / setup / campus guide)
    setup_cn = read("docs/中文/首次配置.md")
    setup_en = read("docs/English/first-time-setup.md")
    campus_cn = read("docs/中文/西电校园网自动认证.md")
    campus_en = read("docs/English/xidian-campus-network-authentication.md")

    cnt_fw = cnt_sim = cnt_rep = cnt_hw = 0
    cnt_pub_auto = cnt_pub_off = 0
    cnt_lwc_compile = cnt_lwc_guide = cnt_globals = 0
    cnt_campus_auto = cnt_campus_cred = cnt_campus_audit = 0

    def sentence_negated(txt, pos):
        # Only an IMMEDIATE negation right before the claim counts ("不是完全
        # 离线构建" / "不要关闭 TLS 校验" are the correct disclaimers). A
        # negation anywhere earlier in the sentence must NOT exempt the claim.
        pre = txt[max(0, pos - 8):pos]
        return bool(re.search(r"(不是|并非|不要|别|勿|请勿|not |never |do not|don'?t )", pre))

    for f, txt in [("README.md", cn), ("README.en.md", en)]:
        for pat in FIRMWARE_ONLY_PHONE_CONTROL_CLAIMS:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                cnt_fw += 1
                print(f"FIRMWARE_ONLY_PHONE_CONTROL_CLAIM {f}: {pat!r}")
                ok = False
        for pat in SIMULATOR_CLAIMS:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                cnt_sim += 1
                print(f"UNDOCUMENTED_SIMULATOR_CLAIM {f}: {pat!r}")
                ok = False
        for pat in COMPONENT_REPLACEMENT_OVERCLAIMS:
            if pat in txt:
                cnt_rep += 1
                print(f"COMPONENT_REPLACEMENT_OVERCLAIM {f}: {pat!r}")
                ok = False
        for pat in HARDWARE_COMPATIBILITY_OVERCLAIMS:
            if pat in txt:
                cnt_hw += 1
                print(f"UNVERIFIED_HARDWARE_COMPATIBILITY_CLAIM {f}: {pat!r}")
                ok = False
        for pat in PUBLIC_PROFILE_AUTO_CONNECT_FALSE:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                cnt_pub_auto += 1
                print(f"PUBLIC_PROFILE_AUTO_CONNECT_FALSE_CLAIM {f}: {pat!r}")
                ok = False
        for pat in PUBLIC_PROFILE_OFFLINE_FALSE:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                cnt_pub_off += 1
                print(f"PUBLIC_PROFILE_OFFLINE_FALSE_CLAIM {f}: {pat!r}")
                ok = False
    print(f"README_FIRMWARE_ONLY_PHONE_CONTROL_CLAIM_COUNT={cnt_fw}")
    print(f"README_UNDOCUMENTED_SIMULATOR_CLAIM_COUNT={cnt_sim}")
    print(f"README_COMPONENT_REPLACEMENT_OVERCLAIM_COUNT={cnt_rep}")
    print(f"README_UNVERIFIED_HARDWARE_COMPATIBILITY_CLAIM_COUNT={cnt_hw}")
    print(f"README_PUBLIC_PROFILE_AUTO_CONNECT_FALSE_CLAIM_COUNT={cnt_pub_auto}")
    print(f"README_PUBLIC_PROFILE_OFFLINE_FALSE_CLAIM_COUNT={cnt_pub_off}")

    for f, txt in [("docs/中文/首次配置.md", setup_cn),
                   ("docs/English/first-time-setup.md", setup_en)]:
        for pat in SETUP_LWC_COMPILE_ONLY_FALSE:
            if pat in txt:
                cnt_lwc_compile += 1
                print(f"SETUP_LOCAL_WIFI_CLOUD_COMPILE_ONLY_FALSE_CLAIM {f}: {pat!r}")
                ok = False
        for pat in SETUP_ARDUINO_GLOBALS_WRONG:
            # wrong generic "globals.h" wording; the correct form always
            # carries the full file name, so no exemption is needed
            if pat in txt:
                cnt_globals += 1
                print(f"SETUP_ARDUINO_GLOBALS_PATH_ERROR {f}: {pat!r}")
                ok = False
    # capability check: the local-wifi-cloud section must show the cloud
    # secrets step and the ENABLE_CLOUD_CREDENTIALS=1 flag
    for f, txt in [("docs/中文/首次配置.md", setup_cn),
                   ("docs/English/first-time-setup.md", setup_en)]:
        lwc = txt.split("local-wifi-cloud")[1:] if "local-wifi-cloud" in txt else []
        joined = " ".join(lwc)
        if not lwc or ("cloud_secrets" not in joined and "cloud_secrets.example.h" not in joined):
            cnt_lwc_guide += 1
            print(f"SETUP_LOCAL_WIFI_CLOUD_MISSING_CLOUD_SECRETS_GUIDE {f}")
            ok = False
    print(f"SETUP_LOCAL_WIFI_CLOUD_COMPILE_ONLY_FALSE_CLAIM_COUNT={cnt_lwc_compile}")
    print(f"SETUP_LOCAL_WIFI_CLOUD_MISSING_CLOUD_SECRETS_GUIDE_COUNT={cnt_lwc_guide}")
    print(f"SETUP_ARDUINO_GLOBALS_PATH_ERROR_COUNT={cnt_globals}")

    campus_guides = {"docs/中文/西电校园网自动认证.md": campus_cn,
                     "docs/English/xidian-campus-network-authentication.md": campus_en}
    for f, txt in campus_guides.items():
        # false claim: local-campus-example expands with AUTO_CAMPUS_AUTH=1
        if re.search(r"(展开为|expands to)[^。\n]{0,90}ENABLE_AUTO_CAMPUS_AUTH=1", txt) or \
           re.search(r"local-campus-example[^。\n]{0,90}ENABLE_AUTO_CAMPUS_AUTH=1", txt):
            cnt_campus_auto += 1
            print(f"CAMPUS_GUIDE_EXAMPLE_AUTO_AUTH_FALSE_CLAIM {f}")
            ok = False
        # false claim: the example profile accepts/uses real credentials
        for pat in ["需要真实学号密码", "填写真实凭据后即可使用", "fill in real credentials",
                    "用真实凭据登录", "使用真实凭据"]:
            for m in re.finditer(re.escape(pat), txt):
                # only flag claims tied to the local-campus-example profile
                ctx = txt[max(0, m.start()-80):m.end()+40]
                if "local-campus-example" in ctx:
                    cnt_campus_cred += 1
                    print(f"CAMPUS_GUIDE_REAL_CREDENTIAL_EXAMPLE_CLAIM {f}: {pat!r}")
                    ok = False
        for pat in CAMPUS_GUIDE_AUDIT_LANGUAGE:
            if pat in txt:
                cnt_campus_audit += 1
                print(f"CAMPUS_GUIDE_INTERNAL_AUDIT_LANGUAGE {f}: {pat!r}")
                ok = False
    print(f"CAMPUS_GUIDE_EXAMPLE_AUTO_AUTH_FALSE_CLAIM_COUNT={cnt_campus_auto}")
    print(f"CAMPUS_GUIDE_REAL_CREDENTIAL_EXAMPLE_CLAIM_COUNT={cnt_campus_cred}")
    print(f"CAMPUS_GUIDE_INTERNAL_AUDIT_LANGUAGE_COUNT={cnt_campus_audit}")

    # 18) v1.2.3 firmware guards that the public docs describe must exist
    #     (empty-SSID hard guard; autoconnect decoupled from ENABLE_CLOUD).
    fw_mgr = read("firmware/shared/RemoteACCore/src/network/wifi_manager.cpp")
    fw_plan = read("firmware/shared/RemoteACCore/src/network/wifi_connect_plan.h")
    fw_gates = read("firmware/shared/RemoteACCore/src/config/feature_gates.h")
    cnt_fw_guard = 0
    if "WIFI_CONNECT_SKIPPED" not in fw_mgr or "SSID_NOT_CONFIGURED" not in fw_plan:
        cnt_fw_guard += 1
        print("FIRMWARE_EMPTY_SSID_GUARD_MISSING wifi_manager.cpp/wifi_connect_plan.h")
        ok = False
    if re.search(r"WIFI_AUTOCONNECT_ON_BOOT[^\n]*ENABLE_CLOUD", fw_gates):
        cnt_fw_guard += 1
        print("FIRMWARE_AUTOCONNECT_CLOUD_DEPENDENT feature_gates.h")
        ok = False
    print(f"FIRMWARE_PUBLIC_DOC_GUARD_ERROR_COUNT={cnt_fw_guard}")

    # 19) v1.2.4 WiFi-runtime / cloud-validation documentation accuracy
    #     (setup docs carry the canonical command semantics).
    setup_pair = {"docs/中文/首次配置.md": setup_cn,
                  "docs/English/first-time-setup.md": setup_en}
    docs_all = {"README.md": cn, "README.en.md": en, **setup_pair,
                "firmware/agent-platformio/README.md": read("firmware/agent-platformio/README.md"),
                "firmware/agent-platformio/README.en.md": read("firmware/agent-platformio/README.en.md")}
    v124_missing = 0
    v124_forbidden = 0

    # presence: runtime open SSID semantics + password warning + boot status
    # + placeholder rejection + TLS requirement
    runtime_sem = ("wifi connect <ssid>" in setup_cn and "wifi connect <ssid>" in setup_en)
    pwd_warn = ("不支持在命令行输入 WiFi 密码" in setup_cn) or \
               ("never accepted on the command line" in setup_en) or \
               ("read or use the" in setup_en and "command line" in setup_en)
    boot_status = ("NET_SOURCE" in setup_cn and "NET_SSID" in setup_cn)
    placeholder_rej = ("your-broker.example.com" in setup_cn and "your_wifi_name" in setup_cn)
    tls_req = ("CA 证书或 TLS 指纹" in setup_cn or "CA certificate or TLS fingerprint" in setup_en)

    if not runtime_sem:
        v124_missing += 1
        print("WIFI_RUNTIME_OPEN_SSID_DOC_PRESENT=False")
        ok = False
    else:
        print("WIFI_RUNTIME_OPEN_SSID_DOC_PRESENT=True")
    if not pwd_warn:
        v124_missing += 1
        print("WIFI_RUNTIME_OPEN_SSID_PASSWORD_WARNING_PRESENT=False")
        ok = False
    else:
        print("WIFI_RUNTIME_OPEN_SSID_PASSWORD_WARNING_PRESENT=True")
    if not boot_status:
        v124_missing += 1
        print("LOCAL_WIFI_BOOT_STATUS_DOC_PRESENT=False")
        ok = False
    else:
        print("LOCAL_WIFI_BOOT_STATUS_DOC_PRESENT=True")
    if not placeholder_rej:
        v124_missing += 1
        print("CLOUD_PLACEHOLDER_REJECTION_DOC_PRESENT=False")
        ok = False
    else:
        print("CLOUD_PLACEHOLDER_REJECTION_DOC_PRESENT=True")
    if not tls_req:
        v124_missing += 1
        print("CLOUD_TLS_REQUIREMENT_DOC_PRESENT=False")
        ok = False
    else:
        print("CLOUD_TLS_REQUIREMENT_DOC_PRESENT=True")

    # forbidden: file-exists == valid; runtime open uses local password;
    # empty-status-is-normal; disable-TLS guidance (positive statements)
    for f, txt in docs_all.items():
        for pat in ["cloud_secrets.h 存在即代表可用", "cloud_secrets.h exists means usable",
                    "存在即有效", "exists means the config is valid"]:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                v124_forbidden += 1
                print(f"CLOUD_FILE_EXISTS_EQUALS_VALID_CLAIM {f}: {pat!r}")
                ok = False
        for pat in ["仍会使用本地密码", "仍会使用本地 WPA 密码", "still uses the local password",
                    "uses the local WPA password", "会使用 wifi_secrets.h 中的密码",
                    "会使用 `wifi_secrets.h` 中的密码", "仍会使用 `wifi_secrets.h`",
                    "using the local WPA password", "using the local password"]:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                v124_forbidden += 1
                print(f"RUNTIME_OPEN_SSID_USES_LOCAL_PASSWORD_CLAIM {f}: {pat!r}")
                ok = False
        for pat in ["不显示实际 SSID 属于正常", "不显示实际SSID属于正常",
                    "不显示实际 SSID", "不显示实际SSID",
                    "empty SSID in status is normal", "may remain `your-broker.example.com`",
                    "broker host may remain"]:
            if pat in txt:
                v124_forbidden += 1
                print(f"LOCAL_WIFI_STATUS_EMPTY_OR_TEMPLATE_ALLOWED {f}: {pat!r}")
                ok = False
        for pat in ["TLS 证书配置可留空", "TLS 可留空", "证书可留空",
                    "TLS can be left empty", "may leave TLS empty", "TLS material can be empty",
                    "CA 证书或指纹可留空"]:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                v124_forbidden += 1
                print(f"DISABLE_TLS_VALIDATION_GUIDANCE {f}: {pat!r}")
                ok = False
        for pat in ["禁用 TLS 校验", "关闭 TLS 校验", "禁用证书校验", "跳过证书验证",
                    "disable TLS validation", "disable certificate validation",
                    "bypass certificate validation"]:
            for m in re.finditer(re.escape(pat), txt):
                if sentence_negated(txt, m.start()):
                    continue
                v124_forbidden += 1
                print(f"DISABLE_TLS_VALIDATION_GUIDANCE {f}: {pat!r}")
                ok = False
    print(f"V124_DOC_MISSING_COUNT={v124_missing}")
    print(f"V124_DOC_FORBIDDEN_CLAIM_COUNT={v124_forbidden}")

    print(f"PUBLIC_DOCS_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
