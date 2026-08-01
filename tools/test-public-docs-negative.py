#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-public-docs-negative.py — prove check-public-docs.py actually fails.

Each negative case copies the repository into a temp dir, applies ONE
sabotage, and asserts check-public-docs.py --root <temp> returns non-zero.
The real working tree is never modified.

Cases:
  1. remove the Chinese "快速开始" anchor (nav target broken)
  2. point the English nav back to the wrong docs root
  3. change a link label back to CONTRIBUTING.md (visible .md suffix)
  4. delete the desktop screenshot
  5. delete the mobile screenshot
  6. use a wrong-language documentation target
  7. write back the stale v0.4.0 text into the PlatformIO README
  8. remove the first-time setup links (Wi-Fi/campus link count too low)
  9. make the two IR preset files inconsistent
 10. add a real-looking password (security scan fails)

Exit code non-zero if any negative case fails to fail.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "tools", "check-public-docs.py")

# paths (relative to repo root) that must exist to build the temp copy
REQUIRED = [
    "README.md",
    "README.en.md",
    "docs/doc-map.json",
    "docs/中文/更新日志.md",
    "docs/English/changelog.md",
    "docs/assets/screenshots/dashboard-desktop.png",
    "docs/assets/screenshots/dashboard-mobile.png",
    "tools/ir-simple-learner/src/presets.py",
    "firmware/agent-platformio/tools/ir_simple_learner/presets.py",
    "firmware/agent-platformio/README.md",
    "firmware/agent-platformio/README.en.md",
]


def build_temp_copy():
    """Copy the repo into a temp dir (excluding .git and heavy dirs)."""
    tmp = tempfile.mkdtemp(prefix="pubdocs-neg-")
    # copy whole tree except .git / node_modules / .venv / dist
    for entry in os.listdir(ROOT):
        src = os.path.join(ROOT, entry)
        if entry in (".git", "node_modules", ".venv", "dist", "build"):
            continue
        dst = os.path.join(tmp, entry)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                ".git", "node_modules", ".venv", "dist", "build",
                "__pycache__", ".pio", ".build"))
        else:
            shutil.copy2(src, dst)
    return tmp


def run_checker(root_dir):
    """Run check-public-docs.py --root <dir>; return exit code."""
    r = subprocess.run([sys.executable, CHECKER, "--root", root_dir],
                       capture_output=True, text=True, timeout=120)
    return r.returncode


def case(no, name, sabotage, expect_fail=True):
    tmp = build_temp_copy()
    try:
        sabotage(tmp)
        rc = run_checker(tmp)
        if expect_fail:
            passed = rc != 0
        else:
            passed = rc == 0
        print(f"NEGATIVE_{no}_{name}_PASS={'True' if passed else 'False'} (rc={rc})")
        return passed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sabotage_1(root):
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("[快速开始](#快速开始)", "[快速开始](#wrong-anchor)")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_2(root):
    p = os.path.join(root, "README.en.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("./docs/English/documentation-index.md", "./docs/English/README.md")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_3(root):
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("[贡献指南](./CONTRIBUTING.md)", "[CONTRIBUTING.md](./CONTRIBUTING.md)")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_4(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-desktop.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_5(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-mobile.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_6(root):
    # wrong-language doc target: Chinese README linking the English index
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("docs/中文/文档导航.md", "docs/English/documentation-index.md")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_7(root):
    p = os.path.join(root, "firmware/agent-platformio/README.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\n> 当前版本：v0.4.0-cloud-foundation（stale）\n"
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_8(root):
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    # strip every first-time-setup / wifi_secrets mention
    txt = txt.replace("首次配置", "XXXXXX")
    txt = txt.replace("wifi_secrets", "XXXXXX")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_9(root):
    p = os.path.join(root, "firmware/agent-platformio/tools/ir_simple_learner/presets.py")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("PRESETS = [", "PRESETS = [\n    {\"codeId\": \"x1\", \"name\": \"extra\"},")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_10(root):
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\nLOCAL_WIFI_PASSWORD \"sup3rRealSecret12345\"\n"
    open(p, "w", encoding="utf-8").write(txt)


def main():
    results = [
        case(1, "cn_anchor_removed", sabotage_1),
        case(2, "en_nav_wrong_docs_root", sabotage_2),
        case(3, "visible_md_suffix", sabotage_3),
        case(4, "desktop_screenshot_deleted", sabotage_4),
        case(5, "mobile_screenshot_deleted", sabotage_5),
        case(6, "wrong_language_doc_target", sabotage_6),
        case(7, "stale_v040_text", sabotage_7),
        case(8, "setup_links_removed", sabotage_8),
        case(9, "ir_preset_drift", sabotage_9),
        case(10, "real_password_added", sabotage_10),
    ]
    total = len(results)
    passed = sum(results)
    print(f"PUBLIC_DOC_NEGATIVE_TEST_TOTAL={total}")
    print(f"PUBLIC_DOC_NEGATIVE_TEST_PASS={passed}")
    if passed != total:
        print("PUBLIC_DOC_NEGATIVE_TEST_RESULT=FAIL")
        return 1
    print("PUBLIC_DOC_NEGATIVE_TEST_RESULT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
