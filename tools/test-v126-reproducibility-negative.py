#!/usr/bin/env python3
"""Negative tests prove the v1.2.6 contract checker catches regressions."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check-v126-reproducibility.py"


def run_case(label, relative_path, old, new):
    with tempfile.TemporaryDirectory(prefix="rac-v126-negative-") as temp:
        clone = Path(temp) / "repo"
        shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", "node_modules", "dist", "coverage"))
        target = clone / relative_path
        text = target.read_text(encoding="utf-8")
        if old not in text:
            raise RuntimeError(f"fixture missing for {label}: {old}")
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        result = subprocess.run([sys.executable, str(clone / CHECKER.relative_to(ROOT))], cwd=clone, capture_output=True, text=True)
        passed = result.returncode != 0
        print(f"V126_NEGATIVE {label}={'PASS' if passed else 'FAIL'}")
        if not passed:
            print(result.stdout)
            return False
    return True


cases = [
    ("STALE_ACCEPTED_MOCK", "docs/English/deployment.md", "blocked_by_ir_policy", "accepted_mock"),
    ("SAFE_RESULT_CALLED_FAILURE", "docs/English/deployment.md", "proves the whole path works", "command loop failed"),
    ("PHYSICAL_IR_FALSE_CLAIM", "docs/English/deployment.md", "physical IR remains safely blocked", "physical IR was transmitted"),
    ("OWNER_EMPTY_SWITCH", "cloud/backend/src/routes/auth.ts", "if (!config.WEB_PASSWORD)", "if (!config.IR_OWNER_PASSWORD)"),
    ("FLOATING_MOSQUITTO", "cloud/docker-compose.yml", "@sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797", ""),
]

results = [run_case(*case) for case in cases]
ok = all(results)
print(f"V126_NEGATIVE_TESTS_PASS={str(ok)}")
sys.exit(0 if ok else 1)
