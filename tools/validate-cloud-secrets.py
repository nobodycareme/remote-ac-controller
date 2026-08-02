#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate-cloud-secrets.py — build-time content validation for local secrets.

v1.2.4: dev.ps1 (and CI) MUST call this validator instead of only checking
that the secret files exist. The rules mirror the runtime enforcement in
firmware/shared/RemoteACCore/src/cloud/cloud_secret_validation.h and the
host contract tests; this script is the build-time copy of that single spec.

Output contract (§8.7) — only booleans and a non-sensitive error code:
    WIFI_SECRETS_VALID=True/False
    CLOUD_SECRETS_VALID=True/False
    MQTT_HOST_VALID=True/False
    MQTT_PORT_VALID=True/False
    MQTT_DEVICE_ID_VALID=True/False
    MQTT_AUTH_VALID=True/False
    MQTT_TLS_VALID=True/False
    VALIDATION_ERROR_CODE=<non-sensitive code>

NEVER print a secret value.

Usage:
  validate-cloud-secrets.py --require-wifi [--require-cloud]
      reads the default repo paths (wifi_secrets.h / cloud_secrets.h) and
      exits non-zero if a required file is missing or its content is invalid.
  validate-cloud-secrets.py --wifi <path> --cloud <path>
      explicit paths (CI temp-file tests).
  validate-cloud-secrets.py --self-test
      runs the >=20 positive/negative contract cases in a temp dir and prints
      SECRET_VALIDATION_CASE_TOTAL/PASS/FAILURE.
"""

import argparse
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WIFI = os.path.join(REPO, "firmware", "shared", "RemoteACCore", "src",
                            "config", "wifi_secrets.h")
DEFAULT_CLOUD = os.path.join(REPO, "firmware", "agent-platformio", "include",
                             "cloud_secrets.h")

# ---------------------------------------------------------------- rules ----
# These MUST mirror cloud_secret_validation.h (see the contract tests).

PLACEHOLDER_PREFIXES = ("your-", "change-", "placeholder", "example.", "invalid")


def host_valid(host):
    if not host:
        return False
    if host.startswith(("https://", "http://")):
        return False
    if any(ch in host for ch in (" ", "\t")):
        return False
    if host.startswith(PLACEHOLDER_PREFIXES):
        return False
    if host.endswith(".invalid"):
        return False
    if host.endswith(".example.com") or host.endswith(".example.org"):
        return False
    return True


def port_valid(port):
    return isinstance(port, int) and 1 <= port <= 65535


def device_id_valid(dev_id):
    if not dev_id:
        return False
    # exact template values (a real user device may legitimately be bedroom-*)
    if dev_id in ("bedroom-ac-01", "your-device-id"):
        return False
    if dev_id.startswith("your-"):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", dev_id):
        return False
    return True


def auth_valid(user, pwd):
    if not user or not pwd:
        return False
    # exact template values only; a real user may legitimately use bedroom-*
    if user in ("bedroom-ac-01", "your-device-id") or user.startswith("your-"):
        return False
    if pwd.startswith(("change-", "your-")):
        return False
    return True


def ca_cert_valid(ca):
    if not ca:
        return False
    if ca.startswith(("your-", "change-", "placeholder")):
        return False
    return "BEGIN CERTIFICATE" in ca and "END CERTIFICATE" in ca


def fingerprint_valid(fp):
    if not fp:
        return False
    hexchars = [c for c in fp if c not in (":", " ")]
    if len(hexchars) != 40:
        return False
    try:
        int("".join(hexchars), 16)
    except ValueError:
        return False
    return any(c != "0" for c in hexchars)


def tls_valid(ca, fp):
    return ca_cert_valid(ca) or fingerprint_valid(fp)


def wifi_ssid_valid(ssid):
    return bool(ssid) and ssid != "your_wifi_name" and " " not in ssid


def wifi_password_valid(pwd):
    if not pwd or pwd == "your_wifi_password":
        return False
    if 8 <= len(pwd) <= 63:
        # printable ASCII, no control chars
        return all(32 <= ord(c) <= 126 for c in pwd)
    if len(pwd) == 64:
        return re.fullmatch(r"[0-9a-fA-F]{64}", pwd) is not None
    return False


# ------------------------------------------------------------- file parse ----
def parse_defines(path):
    """Return {MACRO: value} for #define MACRO "..." / #define MACRO <int>.

    Handles realistic user files:
      - line continuations (trailing backslash);
      - multi-segment quoted strings ("a" "b" -> "ab");
      - single-quoted-string PEM certificates with embedded \\n escapes.
    """
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()
    # join continuation lines
    logical = []
    buf = ""
    for line in raw_lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped.rstrip().endswith("\\"):
            buf += stripped.rstrip()[:-1] + " "
        else:
            logical.append(buf + stripped)
            buf = ""
    if buf:
        logical.append(buf)
    for line in logical:
        m = re.match(r"\s*#\s*define\s+([A-Z0-9_]+)\s+(.+)", line)
        if not m:
            continue
        name, raw = m.group(1), m.group(2).strip()
        # quoted value: concatenate every "..." segment on the statement
        segs = re.findall(r'"([^"]*)"', raw)
        if segs:
            out[name] = "".join(segs)
            continue
        i = re.match(r"^(\d+)", raw)
        if i:
            out[name] = int(i.group(1))
    return out


# ------------------------------------------------------------- validation ---
def validate_wifi_file(path, require=False):
    d = parse_defines(path)
    if require and not os.path.exists(path):
        return False, "FILE_MISSING"
    if not d:
        return False, "FILE_MISSING" if require else "OK_EMPTY"
    ssid = d.get("LOCAL_WIFI_SSID", "")
    pwd = d.get("LOCAL_WIFI_PASSWORD", "")
    if not wifi_ssid_valid(ssid):
        return False, "WIFI_SSID_INVALID"
    if not wifi_password_valid(pwd):
        return False, "WIFI_PASSWORD_INVALID"
    return True, "OK"


def validate_cloud_file(path, require=False):
    d = parse_defines(path)
    if require and not os.path.exists(path):
        return False, "FILE_MISSING"
    if not d:
        return False, "FILE_MISSING" if require else "OK_EMPTY"
    host = d.get("MQTT_BROKER_HOST", "")
    port = d.get("MQTT_BROKER_PORT", 0)
    dev = d.get("MQTT_DEVICE_ID", "")
    user = d.get("MQTT_USERNAME", "")
    pwd = d.get("MQTT_PASSWORD", "")
    ca = d.get("MQTT_CA_CERT", "")
    fp = d.get("MQTT_TLS_FINGERPRINT", "")
    if not host_valid(host):
        return False, "HOST_INVALID"
    if not port_valid(port):
        return False, "PORT_INVALID"
    if not device_id_valid(dev):
        return False, "DEVICE_ID_INVALID"
    if not auth_valid(user, pwd):
        return False, "AUTH_INVALID"
    if not tls_valid(ca, fp):
        return False, "TLS_MATERIAL_MISSING"
    return True, "OK"


def validate_both(wifi_path, cloud_path, require_wifi, require_cloud):
    wf_ok, wf_code = validate_wifi_file(wifi_path, require=require_wifi)
    cf_ok, cf_code = validate_cloud_file(cloud_path, require=require_cloud)
    print(f"WIFI_SECRETS_VALID={str(wf_ok)}")
    print(f"CLOUD_SECRETS_VALID={str(cf_ok)}")
    # detail lines
    d = parse_defines(cloud_path)
    if d:
        print(f"MQTT_HOST_VALID={str(host_valid(d.get('MQTT_BROKER_HOST','')))}")
        print(f"MQTT_PORT_VALID={str(port_valid(d.get('MQTT_BROKER_PORT',0)))}")
        print(f"MQTT_DEVICE_ID_VALID={str(device_id_valid(d.get('MQTT_DEVICE_ID','')))}")
        print(f"MQTT_AUTH_VALID={str(auth_valid(d.get('MQTT_USERNAME',''), d.get('MQTT_PASSWORD','')))}")
        print(f"MQTT_TLS_VALID={str(tls_valid(d.get('MQTT_CA_CERT',''), d.get('MQTT_TLS_FINGERPRINT','')))}")
    else:
        for k in ("MQTT_HOST_VALID", "MQTT_PORT_VALID", "MQTT_DEVICE_ID_VALID",
                  "MQTT_AUTH_VALID", "MQTT_TLS_VALID"):
            print(f"{k}=False")
    code = "OK"
    if not wf_ok and require_wifi:
        code = wf_code
    elif not cf_ok and require_cloud:
        code = cf_code
    print(f"VALIDATION_ERROR_CODE={code}")
    return (wf_ok or not require_wifi) and (cf_ok or not require_cloud)


# ------------------------------------------------------------- self-test ----
def _write(p, text):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def run_self_test():
    total = 0
    passed = 0

    def case(name, expect_valid, wifi=None, cloud=None, expect_code=None):
        nonlocal total, passed
        total += 1
        tmp = tempfile.mkdtemp(prefix="secval-")
        try:
            wp = os.path.join(tmp, "wifi_secrets.h")
            cp = os.path.join(tmp, "cloud_secrets.h")
            if wifi is not None:
                _write(wp, wifi)
            if cloud is not None:
                _write(cp, cloud)
            wok, wcode = validate_wifi_file(wp, require=True)
            cok, ccode = validate_cloud_file(cp, require=True)
            # wifi-only cases (cloud=None) only judge wifi; cloud-only judge cloud
            if cloud is None:
                ok = (wok == expect_valid)
                code = wcode
            elif wifi is None:
                ok = (cok == expect_valid)
                code = ccode
            else:
                ok = (wok == expect_valid and cok == expect_valid)
                code = ccode if not cok else wcode
            if expect_code is not None:
                ok = ok and (code == expect_code)
            if ok:
                passed += 1
                print(f"SELFTEST_PASS {name}")
            else:
                print(f"SELFTEST_FAIL {name} (got wifi={wok}/{wcode} cloud={cok}/{ccode})")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    W_VALID = '#define LOCAL_WIFI_SSID "TEST_HOME_WIFI"\n#define LOCAL_WIFI_PASSWORD "TEST_PASSWORD_123"\n'
    C_VALID = (
        '#define MQTT_BROKER_HOST "mqtt.myhome.example.net"\n'
        '#define MQTT_BROKER_PORT 8883\n'
        '#define MQTT_DEVICE_ID "bedroom-ac-42"\n'
        '#define MQTT_USERNAME "my-user-01"\n'
        '#define MQTT_PASSWORD "a-real-password-2026"\n'
        '#define MQTT_CA_CERT "-----BEGIN CERTIFICATE-----\\nMIID\\n-----END CERTIFICATE-----"\n'
        '#define MQTT_TLS_FINGERPRINT ""\n')

    case("1 wifi file missing", False, wifi=None, cloud=None, expect_code="FILE_MISSING")
    case("2 wifi ssid empty", False, wifi='#define LOCAL_WIFI_SSID ""\n#define LOCAL_WIFI_PASSWORD "TEST_PASSWORD_123"\n')
    case("3 wifi ssid template", False, wifi='#define LOCAL_WIFI_SSID "your_wifi_name"\n#define LOCAL_WIFI_PASSWORD "TEST_PASSWORD_123"\n')
    case("4 wifi password too short", False, wifi='#define LOCAL_WIFI_SSID "TEST_HOME_WIFI"\n#define LOCAL_WIFI_PASSWORD "short"\n')
    case("5 wifi password valid 8-63", True, wifi=W_VALID)
    case("6 wifi password valid 64hex", True, wifi='#define LOCAL_WIFI_SSID "TEST_HOME_WIFI"\n#define LOCAL_WIFI_PASSWORD "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"\n')
    case("7 cloud file missing", False, cloud=None, expect_code="FILE_MISSING")
    case("8 cloud broker template", False, cloud=C_VALID.replace('"mqtt.myhome.example.net"', '"your-broker.example.com"'), expect_code="HOST_INVALID")
    case("9 cloud broker https scheme", False, cloud=C_VALID.replace('"mqtt.myhome.example.net"', '"https://mqtt.myhome.example.net"'), expect_code="HOST_INVALID")
    case("10 cloud port 0", False, cloud=C_VALID.replace("8883", "0"), expect_code="PORT_INVALID")
    case("11 cloud port 65536", False, cloud=C_VALID.replace("8883", "65536"), expect_code="PORT_INVALID")
    case("12 cloud device id template", False, cloud=C_VALID.replace('"bedroom-ac-42"', '"bedroom-ac-01"'), expect_code="DEVICE_ID_INVALID")
    case("13 cloud username template", False, cloud=C_VALID.replace('"my-user-01"', '"bedroom-ac-01"'), expect_code="AUTH_INVALID")
    case("14 cloud password template", False, cloud=C_VALID.replace('"a-real-password-2026"', '"change-me"'), expect_code="AUTH_INVALID")
    case("15 cloud ca+fp empty", False, cloud=C_VALID.replace('"-----BEGIN CERTIFICATE-----\\nMIID\\n-----END CERTIFICATE-----"', '""'), expect_code="TLS_MATERIAL_MISSING")
    case("16 cloud fingerprint wrong length", False, cloud=C_VALID.replace('"-----BEGIN CERTIFICATE-----\\nMIID\\n-----END CERTIFICATE-----"', '""').replace('#define MQTT_TLS_FINGERPRINT ""', '#define MQTT_TLS_FINGERPRINT "F4:BD:59:32"'), expect_code="TLS_MATERIAL_MISSING")
    case("17 cloud fingerprint non-hex", False, cloud=C_VALID.replace('"-----BEGIN CERTIFICATE-----\\nMIID\\n-----END CERTIFICATE-----"', '""').replace('#define MQTT_TLS_FINGERPRINT ""', '#define MQTT_TLS_FINGERPRINT "G4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9"'), expect_code="TLS_MATERIAL_MISSING")
    case("18 ca missing end marker", False, cloud=C_VALID.replace('"-----BEGIN CERTIFICATE-----\\nMIID\\n-----END CERTIFICATE-----"', '"-----BEGIN CERTIFICATE-----\\nMIID"'), expect_code="TLS_MATERIAL_MISSING")
    case("19 all fields valid", True, wifi=W_VALID, cloud=C_VALID)
    # 20: valid config must not leak secrets — parse output lines for forbidden values
    _leak = 0
    import io as _io
    buf = _io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        validate_both(DEFAULT_WIFI if os.path.exists(DEFAULT_WIFI) else None,
                      None, False, False)
    finally:
        sys.stdout = old
    out = buf.getvalue()
    for secret in ("TEST_PASSWORD_123", "a-real-password-2026", "your_wifi_password"):
        if secret in out:
            _leak += 1
    total += 1
    if _leak == 0:
        passed += 1
        print("SELFTEST_PASS 20 no secret leak in output")
    else:
        print(f"SELFTEST_FAIL 20 secret leaked in output ({_leak})")

    print(f"SECRET_VALIDATION_CASE_TOTAL={total}")
    print(f"SECRET_VALIDATION_CASE_PASS={passed}")
    print(f"SECRET_VALIDATION_CASE_FAILURE={total - passed}")
    return 0 if passed == total else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wifi", default=None)
    ap.add_argument("--cloud", default=None)
    ap.add_argument("--require-wifi", action="store_true")
    ap.add_argument("--require-cloud", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ns = ap.parse_args()

    if ns.self_test:
        return run_self_test()

    wifi_path = ns.wifi or DEFAULT_WIFI
    cloud_path = ns.cloud or DEFAULT_CLOUD
    ok = validate_both(wifi_path, cloud_path, ns.require_wifi, ns.require_cloud)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
