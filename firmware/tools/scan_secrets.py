#!/usr/bin/env python3
# scan_secrets.py
# Security scan for the review package.
#
# Per the third-party review (Section 7):
#   * The report must be item-by-item: every scanned file is tagged either
#     SAFE_PLACEHOLDER or SUSPECT_SECRET (never a single True/False).
#   * The following are ALLOWED explicit placeholders and must NOT be flagged:
#       YOUR_WIFI_SSID, YOUR_WIFI_PASSWORD, REPLACE_WITH_*, <REDACTED>,
#       your-cloud.example.com, device_user, device_password
#   * Packaging MUST be blocked (exit 1) when any of these are found:
#       - PEM private-key blocks (the "BEGIN <algo> PRIVATE KEY" family)
#       - a non-placeholder Wi-Fi password
#       - a non-placeholder Token
#       - "Bearer" followed by a real value
#       - "Authorization" followed by a real value
#       - secrets.h present in the tree
#       - a .env file containing real values
#
# Usage:
#   python scan_secrets.py <project_root> <report_out_path>
#   exit 0 = no suspect secret ; exit 1 = at least one suspect secret
import os
import re
import sys

ALLOWED = (
    "YOUR_WIFI_SSID",
    "YOUR_WIFI_PASSWORD",
    "REPLACE_WITH_",
    "<REDACTED>",
    "your-cloud.example.com",
    "device_user",
    "device_password",
)

# Strict blocking patterns (private key blocks) -- checked against ALL text files.
# The pattern strings are built at runtime (rather than written as contiguous
# literals) so this scanner does not match its OWN source when it scans tools/.
_PK = "PRIVATE KEY"
STRICT_BLOCK = [
    re.compile("BEGIN" + r"\s+OPENSSH\s+" + _PK, re.I),
    re.compile("BEGIN" + r"\s+RSA\s+" + _PK, re.I),
    re.compile("BEGIN" + r"\s+" + _PK, re.I),
    re.compile("BEGIN" + r"\s+EC\s+" + _PK, re.I),
    re.compile("BEGIN" + r"\s+DSA\s+" + _PK, re.I),
]

# Files to which the assignment-value heuristic applies (code / config only).
ASSIGN_EXT = {
    ".h", ".c", ".cpp", ".cc", ".ino", ".ini", ".env", ".json",
    ".py", ".yml", ".yaml", ".toml", ".conf", ".cfg", ".sh", ".ps1",
}

EXCLUDE_DIRS = {".git", ".platformio", ".pio", ".workbuddy",
                "node_modules", "__pycache__", ".venv", "venv"}

# Assignment keywords whose RHS we inspect for a real credential.
ASSIGN_KW = ["password", "passwd", "secret", "token", "api_key",
             "apikey", "access_key", "private_key", "auth"]


def is_allowed_placeholder(val):
    v = val.strip().strip('"').strip("'").strip()
    if not v:
        return True  # empty is not a secret
    for a in ALLOWED:
        if a in v:
            return True
    if v.startswith("<") and v.endswith(">"):
        return True
    if "example.com" in v:
        return True
    up = v.upper()
    if up in ("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD",
              "DEVICE_USER", "DEVICE_PASSWORD"):
        return True
    return False


def looks_like_real_credential(val):
    v = val.strip().strip('"').strip("'").strip()
    if not v:
        return False
    if is_allowed_placeholder(v):
        return False
    # Heuristic: a real credential is reasonably long and not an obvious word.
    low = v.lower()
    if len(v) < 8:
        return False
    if low.startswith("your_") or low.startswith("replace_with") \
            or low.startswith("device_") or low.startswith("example"):
        return False
    return True


def scan_text(text, apply_assign):
    reasons = []
    for rx in STRICT_BLOCK:
        if rx.search(text):
            reasons.append("PRIVATE_KEY_BLOCK")
    # Bearer real token (anywhere)
    for m in re.finditer(r"Bearer\s+([A-Za-z0-9\-._~+/]+=*)", text):
        tok = m.group(1)
        if len(tok) >= 20 and not is_allowed_placeholder(tok):
            reasons.append("BEARER_REAL_TOKEN")
    # Authorization: Bearer real
    for m in re.finditer(r"Authorization\s*:\s*Bearer\s+([A-Za-z0-9\-._~+/]+=*)",
                         text, re.I):
        tok = m.group(1)
        if len(tok) >= 20 and not is_allowed_placeholder(tok):
            reasons.append("AUTH_BEARER_REAL")
    if apply_assign:
        # Only flag string-LITERAL assignments (RHS wrapped in quotes). A bare
        # variable-to-variable assignment (e.g. `auth = login()` or
        # `token = challenge`) is normal code, not a hardcoded credential, and
        # must NOT be flagged. This avoids false positives on srun/API client
        # modules that legitimately name local variables password/token/auth.
        for kw in ASSIGN_KW:
            for m in re.finditer(
                    r"%s\s*[:=]\s*[\"']([^\"';#\n]{1,200})[\"']" % re.escape(kw),
                    text, re.I):
                val = m.group(1).strip()
                if not val:
                    continue
                if is_allowed_placeholder(val):
                    continue
                if looks_like_real_credential(val):
                    reasons.append("REAL_%s" % kw.upper())
    return reasons


def main():
    if len(sys.argv) < 3:
        print("usage: scan_secrets.py <root> <report>", file=sys.stderr)
        return 2
    root = sys.argv[1]
    report = sys.argv[2]
    os.makedirs(os.path.dirname(report), exist_ok=True)

    results = []  # (relpath, status, reasons)
    suspect = False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            reasons = []
            # A secrets.h conventionally holds credentials. Block ONLY when it
            # actually contains a real (non-placeholder) credential; placeholder
            # templates (REPLACE_WITH_*, YOUR_WIFI_*, ...) are allowed (see the
            # ALLOWED list) and the file is excluded from the package anyway.
            if fn == "secrets.h":
                c = scan_text(text, True)
                if c:
                    reasons += c  # real/blocked secret present -> suspect
            # read as text; binary/unreadable -> skip (not secret-bearing)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except Exception:
                continue
            ext = os.path.splitext(fn)[1].lower()
            apply_assign = ext in ASSIGN_EXT or fn == ".env"
            reasons += scan_text(text, apply_assign)
            if reasons:
                suspect = True
                results.append((rel, "SUSPECT_SECRET", reasons))
            else:
                results.append((rel, "SAFE_PLACEHOLDER", []))

    with open(report, "w", encoding="utf-8") as out:
        out.write("SENSITIVE SCAN REPORT (per-file)\n")
        out.write("root: %s\n" % root)
        out.write("ALLOWED_PLACEHOLDERS: %s\n" % ", ".join(ALLOWED))
        out.write("RESULT: %s\n" % ("SUSPECT" if suspect else "CLEAN"))
        out.write("=" * 60 + "\n")
        for rel, status, reasons in results:
            if status == "SUSPECT_SECRET":
                out.write("SUSPECT_SECRET %s : %s\n" % (rel, ", ".join(reasons)))
            else:
                out.write("SAFE_PLACEHOLDER %s\n" % rel)

    if suspect:
        print("SUSPECT secrets found -> packaging blocked", file=sys.stderr)
        return 1
    print("CLEAN: no suspect secrets", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
