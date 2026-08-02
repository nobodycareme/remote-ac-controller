#!/usr/bin/env python3
"""Verify the single authoritative local Cloud credential path."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL = "firmware/shared/RemoteACCore/src/config/cloud_secrets.h"
TEMPLATE = "firmware/shared/RemoteACCore/src/config/cloud_secrets.example.h"
LEGACY = (
    "firmware/shared/RemoteACCore/src/cloud_secrets.h",
    "firmware/agent-platformio/include/cloud_secrets.h",
)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as handle:
        return handle.read()


def run_checks(root):
    checks = []
    def check(name, condition):
        checks.append(bool(condition))
        print(("PASS " if condition else "FAIL ") + name)

    credentials = read(root, "firmware/shared/RemoteACCore/src/cloud/cloud_credentials.cpp")
    dev = read(root, "firmware/agent-platformio/tools/dev.ps1")
    validator = read(root, "tools/validate-cloud-secrets.py")
    code_parts = []
    for base, _, files in os.walk(os.path.join(root, "firmware", "shared", "RemoteACCore", "src")):
        for name in files:
            if name.endswith((".h", ".cpp")):
                code_parts.append(open(os.path.join(base, name), encoding="utf-8").read())
    code = "\n".join(code_parts)

    check("canonical template exists", os.path.isfile(os.path.join(root, TEMPLATE)))
    check("old template removed", not os.path.exists(os.path.join(root, "firmware/agent-platformio/include/cloud_secrets.example.h")))
    check("qualified production include", '#include "config/cloud_secrets.h"' in credentials)
    ambiguous = re.findall(r'(?:#\s*include|__has_include\s*\()\s*["<]cloud_secrets\.h', code)
    check("no ambiguous production include", len(ambiguous) == 0)
    check("dev uses canonical path", "shared/RemoteACCore/src/config/cloud_secrets.h" in dev)
    check("dev rejects shared legacy path", "shared/RemoteACCore/src/cloud_secrets.h" in dev and "LEGACY_CLOUD_SECRETS_PATH_PRESENT=True" in dev)
    check("dev rejects PlatformIO legacy path", "include/cloud_secrets.h" in dev and "CLOUD_SECRETS_PATH_AMBIGUOUS=True" in dev)
    check("validator uses canonical path", '"config", "cloud_secrets.h"' in validator and '"agent-platformio", "include"' not in validator.split("DEFAULT_CLOUD", 1)[1].split("# ---------------------------------------------------------------- rules", 1)[0])

    docs = [
        "docs/中文/首次配置.md", "docs/English/first-time-setup.md",
        "firmware/agent-platformio/README.md", "firmware/agent-platformio/README.en.md",
        "firmware/arduino-ide/Remote_AC_Controller/README.md",
        "firmware/arduino-ide/Remote_AC_Controller/README.en.md",
    ]
    doc_text = "\n".join(read(root, rel) for rel in docs)
    check("canonical docs present", "RemoteACCore/src/config/cloud_secrets.h" in doc_text or "shared/RemoteACCore/src/config/cloud_secrets.h" in doc_text)
    old_instruction = re.search(r'(?:cp|Copy-Item)[^\n]*(?:agent-platformio/include/cloud_secrets|RemoteACCore/src/cloud_secrets)', doc_text)
    check("no legacy copy instruction", old_instruction is None)

    total = len(checks)
    passed = sum(checks)
    print(f"CLOUD_PATH_AUTHORITY_TEST_TOTAL={total}")
    print(f"CLOUD_PATH_AUTHORITY_TEST_PASS={passed}")
    print(f"CLOUD_PATH_AUTHORITY_TEST_FAILURE={total - passed}")
    print(f"AMBIGUOUS_CLOUD_SECRETS_INCLUDE_COUNT={len(ambiguous)}")
    print(f"CANONICAL_CLOUD_SECRETS_PATH={CANONICAL}")
    return 0 if total == passed else 1


def self_test(root):
    cases = []

    def copy_test_tree(destination):
        required = {
            "firmware/agent-platformio/tools/dev.ps1",
            "firmware/shared/RemoteACCore/src/cloud/cloud_credentials.cpp",
            "firmware/shared/RemoteACCore/src/cloud/mqtt_tls_adapter.h",
            "firmware/shared/RemoteACCore/src/cloud/mqtt_tls_policy.h",
            "firmware/shared/RemoteACCore/src/config/cloud_secrets.example.h",
            "firmware/shared/RemoteACCore/src/network/wifi_ssid_validation.h",
            "tools/check-cloud-secret-authority.py",
            "tools/validate-cloud-secrets.py",
            "docs/\u4e2d\u6587/\u9996\u6b21\u914d\u7f6e.md",
            "docs/English/first-time-setup.md",
            "firmware/agent-platformio/README.md",
            "firmware/agent-platformio/README.en.md",
            "firmware/arduino-ide/Remote_AC_Controller/README.md",
            "firmware/arduino-ide/Remote_AC_Controller/README.en.md",
        }
        for rel in required:
            source = os.path.join(root, rel)
            target = os.path.join(destination, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)

    def sabotage(name, mutate):
        with tempfile.TemporaryDirectory(prefix="cloud-authority-") as tmp:
            copy_test_tree(tmp)
            mutate(tmp)
            result = subprocess.run([sys.executable, os.path.join(tmp, "tools", "check-cloud-secret-authority.py"), "--root", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = result.returncode != 0
            cases.append(ok)
            print(("PASS " if ok else "FAIL ") + name)

    def ambiguous_include(tmp):
        p = os.path.join(tmp, "firmware/shared/RemoteACCore/src/cloud/cloud_credentials.cpp")
        text = open(p, encoding="utf-8").read().replace('"config/cloud_secrets.h"', '"cloud_secrets.h"')
        open(p, "w", encoding="utf-8").write(text)
    def old_dev_path(tmp):
        p = os.path.join(tmp, "firmware/agent-platformio/tools/dev.ps1")
        text = open(p, encoding="utf-8").read().replace("shared/RemoteACCore/src/config/cloud_secrets.h", "agent-platformio/include/cloud_secrets.h")
        open(p, "w", encoding="utf-8").write(text)
    def old_doc_path(tmp):
        p = os.path.join(tmp, "docs/English/first-time-setup.md")
        with open(p, "a", encoding="utf-8") as handle:
            handle.write("\ncp firmware/agent-platformio/include/cloud_secrets.example.h firmware/agent-platformio/include/cloud_secrets.h\n")

    sabotage("ambiguous include rejected", ambiguous_include)
    sabotage("legacy dev path rejected", old_dev_path)
    sabotage("legacy documentation instruction rejected", old_doc_path)
    total = len(cases); passed = sum(cases)
    print(f"CLOUD_PATH_AUTHORITY_NEGATIVE_TOTAL={total}")
    print(f"CLOUD_PATH_AUTHORITY_NEGATIVE_PASS={passed}")
    print(f"CLOUD_PATH_AUTHORITY_NEGATIVE_FAILURE={total - passed}")
    return 0 if total == passed else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    return self_test(root) if args.self_test else run_checks(root)

if __name__ == "__main__":
    sys.exit(main())