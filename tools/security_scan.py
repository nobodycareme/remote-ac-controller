# -*- coding: utf-8 -*-
"""Full-repository security scan for the canonical monorepo.

Scan scopes: current tracked tree, full git history (all branches/tags),
private-key blocks, real IR frame data, database artefacts. Only counts are
printed; matched content is never printed.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pattern groups -> label
PATS = [
    ("OLD_MQTT", r"mqtt[_-]?password\s*=\s*['\"][A-Za-z0-9_!@#]{6,}['\"]"),
    ("MQTT_V2", r"MQTT_PASSWORD\s*=\s*['\"][A-Za-z0-9_!@#]{6,}['\"]"),
    ("CAMPUS_ACCT", r"(campus_username|CAMPUS_USERNAME)\s*=\s*['\"][0-9A-Za-z]{6,}['\"]"),
    ("CAMPUS_PW", r"(campus_password|CAMPUS_PASSWORD)\s*=\s*['\"][^'\"]{6,}['\"]"),
    ("WIFI_PW", r"(WIFI_PASSWORD|wifi_password)\s*=\s*['\"][^'\"]{6,}['\"]"),
    ("OWNER_PW", r"(owner_password|OWNER_PASSWORD|WEB_PASSWORD)\s*=\s*['\"][^'\"]{6,}['\"]"),
    ("TOKEN", r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})"),
    ("COOKIE", r"(cookie|session)[_-]?(token|secret)\s*=\s*['\"][A-Za-z0-9]{16,}['\"]"),
]

def scan_text(txt):
    hits = 0
    for name, p in PATS:
        if re.search(p, txt, re.I):
            hits += 1
    return hits

def is_placeholder(line):
    return bool(re.search(r"(example|placeholder|CHANGE_ME|YOUR_|xxx|<[^>]+>|your_|Your_|REPLACE|\.example|test|mock|smoke)", line, re.I))

# ---- 1) current tracked tree ----
tree_hits = 0
tree_files = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"],
                            capture_output=True).stdout.decode("utf-8", "replace").split("\x00")
for f in tree_files:
    if not f:
        continue
    if "/tests/" in f or "/test/" in f or f.endswith(".test.ts") or f.endswith(".spec.ts"):
        continue  # test fixtures intentionally carry mock credentials
    fp = os.path.join(ROOT, f)
    try:
        raw = open(fp, "rb").read()
    except Exception:
        continue
    txt = raw.decode("utf-8", "replace")
    for line in txt.splitlines():
        if is_placeholder(line):
            continue
        tree_hits += scan_text(line)
print("CANONICAL_CURRENT_TREE_SECRET_HITS=", tree_hits)

# ---- 2) full history ----
hist_hits = 0
for ref in ["--all"]:
    p = subprocess.run(["git", "-C", ROOT, "log", "--all", "-p",
                        "--no-merges", "--full-history"], capture_output=True)
    if p.returncode != 0:
        continue
    text = p.stdout.decode("utf-8", "replace")
    cur = None
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            continue
        if not line.startswith(("+", "-")):
            continue
        if line.startswith(("+++", "---")):
            continue
        if cur and ("/tests/" in cur or "/test/" in cur):
            continue  # same test-fixture exemption as the tree scan
        if not is_placeholder(line):
            hist_hits += scan_text(line)
print("CANONICAL_FULL_HISTORY_SECRET_HITS=", hist_hits)

# ---- 3) private keys ----
key_hits = 0
key_re = re.compile(r"BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY")
for f in tree_files:
    if not f:
        continue
    fp = os.path.join(ROOT, f)
    try:
        raw = open(fp, "rb").read()
    except Exception:
        continue
    if key_re.search(raw.decode("utf-8", "replace")):
        key_hits += 1
print("CANONICAL_PRIVATE_KEY_HITS=", key_hits)

# ---- 4) real IR frame data ----
ir_hits = 0
ir_re = re.compile(r"rawData\[\d{3,}\]|uint16_t\s+(ir_)?(frame|raw)_[a-z0-9_]+\[|0x[0-9A-Fa-f]{2},\s*0x[0-9A-Fa-f]{2}.*\{.*\}")
for f in tree_files:
    if not f:
        continue
    fp = os.path.join(ROOT, f)
    try:
        raw = open(fp, "rb").read()
    except Exception:
        continue
    if ir_re.search(raw.decode("utf-8", "replace")):
        ir_hits += 1
print("CANONICAL_REAL_IR_HITS=", ir_hits)

# ---- 5) database artefacts ----
db_hits = 0
db_re = re.compile(r"\.(db|sqlite|sqlite3)$")
for f in tree_files:
    if db_re.search(f):
        db_hits += 1
print("CANONICAL_DATABASE_HITS=", db_hits)

ok = tree_hits == 0 and hist_hits == 0 and key_hits == 0 and ir_hits == 0 and db_hits == 0
print("FULL_SECURITY_SCAN_PASS=" + ("True" if ok else "False"))
sys.exit(0 if ok else 1)
