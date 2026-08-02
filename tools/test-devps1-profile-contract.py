#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test-devps1-profile-contract.py — static contract test for tools/dev.ps1
profile semantics (v1.2.3).

The firmware toolchain is not vendored into the public repository, so the
PlatformIO profile definitions in dev.ps1 are validated here by parsing the
authoritative BUILD_FLAGS_PUBLIC lines and the pre-flight secret checks.
These are the ONLY places that decide what each profile compiles.

Verified contract (v1.2.3):
  public             ENABLE_CLOUD=1, ENABLE_CLOUD_CREDENTIALS=0,
                     no AUTO_WIFI / AUTO_CAMPUS_AUTH flags -> boot autoconnect OFF
  public-cloud-example ENABLE_CLOUD=1, ENABLE_CLOUD_CREDENTIALS=0 (compile example)
  local-wifi         ENABLE_WIFI_CREDENTIALS=1, ENABLE_AUTO_WIFI_CONNECT=1,
                     ENABLE_CLOUD=0
  local-wifi-cloud   ENABLE_WIFI_CREDENTIALS=1, ENABLE_AUTO_WIFI_CONNECT=1,
                     ENABLE_CLOUD=1, ENABLE_CLOUD_CREDENTIALS=1  (name matches reality)
  local-campus-example ENABLE_CAMPUS_AUTH=1, ENABLE_AUTO_CAMPUS_AUTH=0,
                     ENABLE_CONTROLLED_LIVE_AUTH=0 (public compile-only)

Pre-flight checks:
  - local-wifi / local-wifi-cloud require wifi_secrets.h (WIFI_SECRETS_MISSING -> exit 5)
  - local-wifi-cloud additionally requires cloud_secrets.h (CLOUD_SECRETS_MISSING -> exit 5)
  - no credential VALUE may ever be written to a log line.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVPS1 = os.path.join(REPO, "firmware", "agent-platformio", "tools", "dev.ps1")

_TOTAL = [0]
_FAILS = [0]


def check(name, cond):
    _TOTAL[0] += 1
    if cond:
        print("PASS " + name)
        return
    _FAILS[0] += 1
    print("FAIL " + name)


def profile_flags(src, name):
    """Return the BUILD_FLAGS_PUBLIC string for a profile switch branch.
    `public` is the `default` branch of the switch."""
    if name == "public":
        pat = re.compile(r"default\s*\{[^}]*?\$env:BUILD_FLAGS_PUBLIC\s*=\s*'([^']+)'", re.S)
    else:
        pat = re.compile(
            r"'%s'\s*\{[^}]*?\$env:BUILD_FLAGS_PUBLIC\s*=\s*'([^']+)'" % re.escape(name),
            re.S)
    m = pat.search(src)
    return m.group(1) if m else None


def has_flag(flags, macro, value):
    return re.search(r"-D%s=%s\b" % (re.escape(macro), re.escape(value)), flags) is not None


def main():
    src = open(DEVPS1, encoding="utf-8").read()

    # ---- profile semantics -------------------------------------------------
    pub = profile_flags(src, "public")
    check("public flags present (default branch)", pub is not None)
    if pub:
        check("public ENABLE_CLOUD=1", has_flag(pub, "ENABLE_CLOUD", "1"))
        check("public ENABLE_CLOUD_CREDENTIALS=0",
              has_flag(pub, "ENABLE_CLOUD_CREDENTIALS", "0"))
        check("public no AUTO_WIFI", "ENABLE_AUTO_WIFI_CONNECT" not in pub)
        check("public no AUTO_CAMPUS", "ENABLE_AUTO_CAMPUS_AUTH" not in pub)

    pce = profile_flags(src, "public-cloud-example")
    check("public-cloud-example flags present", pce is not None)
    if pce:
        check("pce ENABLE_CLOUD=1", has_flag(pce, "ENABLE_CLOUD", "1"))
        check("pce ENABLE_CLOUD_CREDENTIALS=0",
              has_flag(pce, "ENABLE_CLOUD_CREDENTIALS", "0"))
        check("pce no AUTO_WIFI", "ENABLE_AUTO_WIFI_CONNECT" not in pce)

    lw = profile_flags(src, "local-wifi")
    check("local-wifi flags present", lw is not None)
    if lw:
        check("local-wifi ENABLE_WIFI_CREDENTIALS=1",
              has_flag(lw, "ENABLE_WIFI_CREDENTIALS", "1"))
        check("local-wifi ENABLE_AUTO_WIFI_CONNECT=1",
              has_flag(lw, "ENABLE_AUTO_WIFI_CONNECT", "1"))
        check("local-wifi ENABLE_CLOUD=0", has_flag(lw, "ENABLE_CLOUD", "0"))
        check("local-wifi ENABLE_CLOUD_CREDENTIALS=0",
              has_flag(lw, "ENABLE_CLOUD_CREDENTIALS", "0"))

    lwc = profile_flags(src, "local-wifi-cloud")
    check("local-wifi-cloud flags present", lwc is not None)
    if lwc:
        check("local-wifi-cloud ENABLE_WIFI_CREDENTIALS=1",
              has_flag(lwc, "ENABLE_WIFI_CREDENTIALS", "1"))
        check("local-wifi-cloud ENABLE_AUTO_WIFI_CONNECT=1",
              has_flag(lwc, "ENABLE_AUTO_WIFI_CONNECT", "1"))
        check("local-wifi-cloud ENABLE_CLOUD=1",
              has_flag(lwc, "ENABLE_CLOUD", "1"))
        check("local-wifi-cloud ENABLE_CLOUD_CREDENTIALS=1 (v1.2.3)",
              has_flag(lwc, "ENABLE_CLOUD_CREDENTIALS", "1"))
        check("local-wifi-cloud ENABLE_CAMPUS_AUTH=0",
              has_flag(lwc, "ENABLE_CAMPUS_AUTH", "0"))

    lce = profile_flags(src, "local-campus-example")
    check("local-campus-example flags present", lce is not None)
    if lce:
        check("lce ENABLE_CAMPUS_AUTH=1", has_flag(lce, "ENABLE_CAMPUS_AUTH", "1"))
        check("lce ENABLE_AUTO_CAMPUS_AUTH=0",
              has_flag(lce, "ENABLE_AUTO_CAMPUS_AUTH", "0"))
        check("lce ENABLE_CONTROLLED_LIVE_AUTH=0",
              has_flag(lce, "ENABLE_CONTROLLED_LIVE_AUTH", "0"))

    # ---- pre-flight checks --------------------------------------------------
    check("wifi secrets pre-flight exists",
          "WIFI_SECRETS_MISSING=True" in src and "wifi_secrets.h" in src)
    check("cloud secrets pre-flight exists (v1.2.5 canonical path)",
          "CLOUD_SECRETS_MISSING=True" in src
          and "shared/RemoteACCore/src/config/cloud_secrets.h" in src)
    check("legacy Cloud paths hard-fail",
          "LEGACY_CLOUD_SECRETS_PATH_PRESENT=True" in src
          and "CLOUD_SECRETS_PATH_AMBIGUOUS=True" in src)
    check("both legacy Cloud paths named",
          "shared/RemoteACCore/src/cloud_secrets.h" in src
          and "include/cloud_secrets.h" in src)
    check("cloud pre-flight refuses fallback",
          "does NOT fall back to a credentials-free build" in src)
    check("no credential values in log lines",
          "Get-Content" not in src
          or not re.search(r"Get-Content[^\n]*(wifi_secrets|cloud_secrets)", src))

    # ---- v1.2.4 content validation (existence is not enough) ---------------
    check("content validator invoked (v1.2.4)",
          "validate-cloud-secrets.py" in src and "--require-wifi" in src
          and "--require-cloud" in src)
    check("content validation failure aborts the build",
          "LOCAL_SECRET_VALIDATION_FAILED=True" in src and "exit 5" in src)
    check("template copy is rejected",
          "copied from the example template verbatim is NOT accepted" in src)
    check("private credential firmware is marked non-distributable",
          "PRIVATE_FIRMWARE_NOT_FOR_DISTRIBUTION=True" in src
          and "PRIVATE_SECRET_EMBEDDING_EXPECTED=True" in src)
    check("public zero-secret scan stays authoritative",
          "PUBLIC_SECRET_SCAN_PASS=True" in src
          and "PUBLIC_SECRET_HITS=$hits" in src
          and "PUBLIC_SECRET_SCAN_PASS=NOT_APPLICABLE" in src)
    check("secret scan result is not inferred from output objects",
          "$script:SecretScanPassed = $true" in src
          and "$script:SecretScanPassed = $false" in src
          and "if (-not $script:SecretScanPassed)" in src
          and "if (-not (Invoke-SecretScan))" not in src)

    print("DEVPS1_PROFILE_CONTRACT_TOTAL=%d" % _TOTAL[0])
    print("DEVPS1_PROFILE_CONTRACT_PASS=%d" % (_TOTAL[0] - _FAILS[0]))
    print("DEVPS1_PROFILE_CONTRACT_FAIL=%d" % _FAILS[0])
    return 1 if _FAILS[0] else 0


if __name__ == "__main__":
    sys.exit(main())
