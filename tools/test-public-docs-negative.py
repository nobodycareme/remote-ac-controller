#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-public-docs-negative.py — prove check-public-docs.py actually fails.

Each negative case copies the repository into a temp dir, applies ONE
sabotage, and asserts check-public-docs.py --root <temp> returns non-zero.
The real working tree is never modified.

Cases (section 9.3):
  1. put a Markdown link back inside the <p> nav block
  2. point the IR learning link to a non-existent #fragment
  3. call the public profile an "offline build"
  4. claim local-campus-example performs real authentication
  5. delete the desktop screenshot
  6. delete the mobile screenshot
  7. change the Chinese heading back to "Development and testing"
  8. add "连续 20 轮" (internal test language) to the README
  9. add a ../../docs image path back into the release notes
 10. make the CN/EN H2 structures inconsistent

Exit code non-zero if any negative case fails to fail.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "tools", "check-public-docs.py")


def build_temp_copy():
    tmp = tempfile.mkdtemp(prefix="pubdocs-neg-")
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
    r = subprocess.run([sys.executable, CHECKER, "--root", root_dir],
                       capture_output=True, text=True, timeout=180)
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
    # put a Markdown link back inside the HTML <p> nav block
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        '  <a href="#项目简介">项目简介</a>',
        '  [项目简介](#项目简介)')
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_2(root):
    # IR learning link points to a non-existent fragment
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "[红外学习工具](./docs/中文/红外学习.md)",
        "[红外学习工具](#红外学习工具)")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_3(root):
    # call the public profile an "offline build"
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "这是无凭据公开构建，不是完全离线构建",
        "这是一个完全离线的离线构建")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_4(root):
    # claim local-campus-example performs real authentication
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "只用于安全的公开编译验证",
        "启用了校园自动认证，填写 campus_secrets.h 后即可真实登录")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_5(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-desktop.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_6(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-mobile.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_7(root):
    # change the Chinese heading back to an English release heading
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("## 参与贡献与支持", "## Development and testing")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_8(root):
    # add internal test language to the README
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\n稳定性：连续 20 轮测试全部通过。\n"
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_9(root):
    # add a ../../docs image path back into the release notes
    p = os.path.join(root, ".github/release-notes/v1.2.2.md")
    txt = open(p, encoding="utf-8").read()
    txt += '\n<img src="../../docs/assets/screenshots/dashboard-desktop.png" />\n'
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_10(root):
    # make the CN/EN H2 structures inconsistent (drop one EN heading)
    p = os.path.join(root, "README.en.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("## System layout", "## System layout (extra words)")
    open(p, "w", encoding="utf-8").write(txt)


def main():
    results = [
        case(1, "markdown_in_html_block", sabotage_1),
        case(2, "broken_ir_fragment", sabotage_2),
        case(3, "false_offline_claim", sabotage_3),
        case(4, "campus_live_auth_claim", sabotage_4),
        case(5, "desktop_screenshot_deleted", sabotage_5),
        case(6, "mobile_screenshot_deleted", sabotage_6),
        case(7, "cn_english_heading", sabotage_7),
        case(8, "internal_test_language", sabotage_8),
        case(9, "release_image_path", sabotage_9),
        case(10, "h2_structure_drift", sabotage_10),
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
