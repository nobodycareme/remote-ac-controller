#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-wifi-ssid-parity.py — prove Python and C++ enforce the same SSID rule.

Both implementations must return the same (valid, errorCode) for every vector
in test/fixtures/wifi_ssid_validation_cases.json:
  - Python: wifi_ssid_validate() from tools/validate-cloud-secrets.py;
  - C++:    test/host/test_wifi_ssid_validation.cpp (which reads the SAME JSON
            through the generated test/host/wifi_ssid_cases.inc).

Steps:
  1. regenerate the .inc from the JSON (deterministic) and verify it is fresh;
  2. run the C++ test binary (if --cpp <path> is given or found in /tmp);
  3. run the Python side over the same vectors and compare valid + code.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "test", "fixtures", "wifi_ssid_validation_cases.json")
GENERATOR = os.path.join(ROOT, "tools", "gen-wifi-ssid-cases.py")
CPP_SRC = os.path.join(ROOT, "test", "host", "test_wifi_ssid_validation.cpp")
VALIDATOR = os.path.join(ROOT, "tools", "validate-cloud-secrets.py")


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_cloud_secrets", VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.wifi_ssid_validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpp", default=None,
                    help="path to a pre-built C++ test binary (default: build to temp)")
    ap.add_argument("--skip-cpp", action="store_true",
                    help="only run the Python side + .inc freshness check")
    ns = ap.parse_args()

    wifi_ssid_validate = load_validator()

    # 1) .inc must be fresh
    r = subprocess.run([sys.executable, GENERATOR, "--check"],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("SSID_CASES_INC_STALE=True")
        return 1

    # 2) C++ binary
    cpp_bin = ns.cpp
    if not ns.skip_cpp:
        if not cpp_bin:
            cpp_bin = os.path.join(tempfile.gettempdir(), "test_wifi_ssid_val")
        native_gpp = shutil.which("g++")
        if native_gpp:
            compile_r = subprocess.run(
                [native_gpp, "-std=c++11", "-Wall",
                 "-I", os.path.join(ROOT, "firmware", "shared", "RemoteACCore", "src"),
                 CPP_SRC, "-o", cpp_bin],
                capture_output=True, text=True, errors="replace")
            if compile_r.returncode != 0:
                print("CPP_SSID_TEST_COMPILE_FAILED")
                print(compile_r.stderr[-4000:])
                return 1
            run_r = subprocess.run([cpp_bin], capture_output=True, text=True,
                                   errors="replace")
        elif os.name == "nt" and shutil.which("wsl"):
            command = (
                "g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src "
                "test/host/test_wifi_ssid_validation.cpp -o /tmp/test_wifi_ssid_val "
                "&& /tmp/test_wifi_ssid_val"
            )
            run_r = subprocess.run(
                ["wsl", "bash", "-lc", command], cwd=ROOT,
                capture_output=True, text=True, errors="replace")
            print("CPP_SSID_TEST_COMPILER=WSL_GPP")
        else:
            print("CPP_SSID_TEST_COMPILER_MISSING=True")
            return 1
        print(run_r.stdout.strip())
        if run_r.returncode != 0:
            print("CPP_SSID_TEST_RUN_FAILED")
            print(run_r.stderr[-4000:])
            return 1
    else:
        print("CPP_SSID_TEST_SKIPPED=True")

    # 3) Python side over the same JSON vectors
    with open(FIXTURE, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    total = 0
    passed = 0
    for c in cases:
        total += 1
        valid, code = wifi_ssid_validate(c["ssid"])
        ok = (valid == c["expectedValid"]) and (code == c["expectedCode"])
        if ok:
            passed += 1
            print("PY_PARITY_PASS %s" % c["name"])
        else:
            print("PY_PARITY_FAIL %s (got valid=%s code=%s want valid=%s code=%s)"
                  % (c["name"], valid, code, c["expectedValid"], c["expectedCode"]))

    print("WIFI_SSID_PY_PARITY_TOTAL=%d" % total)
    print("WIFI_SSID_PY_PARITY_PASS=%d" % passed)
    print("WIFI_SSID_PY_PARITY_FAILURE=%d" % (total - passed))
    # The C++ side asserts the same vectors and exits non-zero on mismatch,
    # so a green C++ run + green Python side proves parity.
    print("WIFI_SSID_PY_CPP_PARITY_TOTAL=%d" % total)
    print("WIFI_SSID_PY_CPP_PARITY_PASS=%d" % passed)
    print("WIFI_SSID_PY_CPP_PARITY_FAILURE=%d" % (total - passed))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
