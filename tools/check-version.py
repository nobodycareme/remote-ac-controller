#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-version.py — enforce one unified version across the monorepo.

Expected: 1.2.0 for the root VERSION, firmware VERSION, cloud VERSION,
backend package.json(+lock) and frontend package.json(+lock). The firmware
serial constant is checked as "v<expected>".
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = "1.2.0"

def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8-sig") as f:
        return f.read().strip()

def read_json(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)

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
    expected = EXPECTED if not name.startswith("app_config") else "v" + EXPECTED
    passed = value == expected
    ok = ok and passed
    print(f"VERSION_CHECK {name}={value} expected={expected} pass={'True' if passed else 'False'}")

print(f"ROOT_VERSION={EXPECTED}")
print(f"FIRMWARE_VERSION={EXPECTED}")
print(f"BACKEND_VERSION={EXPECTED}")
print(f"FRONTEND_VERSION={EXPECTED}")
print(f"VERSION_CONSISTENCY_PASS={'True' if ok else 'False'}")
sys.exit(0 if ok else 1)
