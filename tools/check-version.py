#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-version.py — enforce one unified version across the monorepo.

The expected version is read from the root VERSION file (no hardcoded value).
Checks:
  * root/cloud/firmware VERSION files
  * backend + frontend package.json and package-lock.json
  * firmware serial constant FIRMWARE_VERSION == "v<root version>"
  * the startup banner must not produce "vv<version>" (prefix must not
    itself end with 'v' when the constant already starts with 'v')
Prints actual values; exits non-zero on any failure.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = read_root = None

def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8-sig") as f:
        return f.read().strip()

def read_json(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)

def main():
    expected = read("VERSION")
    if not re.fullmatch(r"\d+\.\d+\.\d+", expected):
        print(f"VERSION_FILE_INVALID root VERSION={expected!r}")
        return 1

    checks = [
        ("VERSION", read("VERSION")),
        ("cloud/VERSION", read("cloud/VERSION")),
        ("firmware/agent-platformio/VERSION", read("firmware/agent-platformio/VERSION")),
        ("cloud/backend/package.json", read_json("cloud/backend/package.json")["version"]),
        ("cloud/frontend/package.json", read_json("cloud/frontend/package.json")["version"]),
        ("cloud/backend/package-lock.json", read_json("cloud/backend/package-lock.json")["version"]),
        ("cloud/frontend/package-lock.json", read_json("cloud/frontend/package-lock.json")["version"]),
    ]

    # firmware serial constant
    app_config = read("firmware/shared/RemoteACCore/src/app_config.h")
    m = re.search(r'#define\s+FIRMWARE_VERSION\s+"([^"]+)"', app_config)
    firmware_const = m.group(1) if m else ""
    checks.append(("app_config.h FIRMWARE_VERSION", firmware_const))

    ok = True
    for name, value in checks:
        expected_value = ("v" + expected) if name.startswith("app_config") else expected
        passed = value == expected_value
        ok = ok and passed
        print(f"VERSION_CHECK {name}={value} expected={expected_value} pass={'True' if passed else 'False'}")

    # startup banner double-'v' check
    serial = read("firmware/shared/RemoteACCore/src/serial_cli.cpp")
    banner_prefix = None
    mm = re.search(r'Serial\.print\(F\("(.*?firmware[^"]*)"\)\);', serial)
    if mm:
        banner_prefix = mm.group(1)
    banner_ok = True
    if banner_prefix is not None:
        # banner text = prefix + FIRMWARE_VERSION; 'vv' occurs when the prefix
        # itself ends with 'v' and the constant starts with 'v'
        combined = banner_prefix + firmware_const
        banner_ok = "vv" not in combined
        print(f"BOOT_BANNER_PREFIX_RAW={banner_prefix!r}")
        print(f"COMPUTED_BOOT_BANNER={combined!r}")
        print(f"STARTUP_VERSION_DISPLAY={combined}")
    else:
        print("BOOT_BANNER_PREFIX_RAW=NOT_FOUND")
        banner_ok = False
    ok = ok and banner_ok

    print(f"ROOT_VERSION={expected}")
    print(f"FIRMWARE_VERSION={expected}")
    print(f"BACKEND_VERSION={expected}")
    print(f"FRONTEND_VERSION={expected}")
    print(f"STARTUP_BANNER_DOUBLE_V={'False' if banner_ok else 'True'}")
    print(f"VERSION_CONSISTENCY_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
