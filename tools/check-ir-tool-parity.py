#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-ir-tool-parity.py — enforce byte-identical IR learner tool copies.

The IR learning tool lives in two trees that MUST stay in sync:
  * tools/ir-simple-learner/src/            (standalone tool tree)
  * firmware/agent-platformio/tools/ir_simple_learner/  (PlatformIO vendor copy)

Each file listed in DUPLICATE_FILES is required to be byte-identical in both
trees. The preset source (presets.py) and the state machine
(capture_flow.py) are the highest-value contracts, but the full list is
checked so a one-sided fix cannot silently drift.

Exit code non-zero on any mismatch.
"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOOLS_TREE = os.path.join(ROOT, "tools", "ir-simple-learner", "src")
PIO_TREE = os.path.join(ROOT, "firmware", "agent-platformio", "tools", "ir_simple_learner")

# Files that must be byte-identical in both trees.
DUPLICATE_FILES = [
    "capture_flow.py",
    "frame_validator.py",
    "presets.py",
    "protocol_adapter.py",
    "serial_worker.py",
    "simple_ir_learner.py",
    "storage.py",
]

# Test contracts that must be byte-identical as well.
DUPLICATE_TESTS = [
    "test_simple_learner.py",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_pair(rel, a_root, b_root, failures, counter_name, counter):
    pa = os.path.join(a_root, rel)
    pb = os.path.join(b_root, rel)
    if not os.path.exists(pa):
        failures.append(f"MISSING {rel} in {a_root}")
        return counter
    if not os.path.exists(pb):
        failures.append(f"MISSING {rel} in {b_root}")
        return counter
    ha = sha256_file(pa)
    hb = sha256_file(pb)
    same = ha == hb
    print(f"IR_PARITY {rel}: {'MATCH' if same else 'MISMATCH'}")
    if not same:
        failures.append(
            f"DIFF {rel}: {a_root} {ha} vs {b_root} {hb}"
        )
    return counter + 1


def main():
    failures = []
    checked = 0
    for rel in DUPLICATE_FILES:
        checked = check_pair(rel, TOOLS_TREE, PIO_TREE, failures, None, checked)
    for rel in DUPLICATE_TESTS:
        checked = check_pair(
            os.path.join("tests", rel), TOOLS_TREE, PIO_TREE, failures, None, checked
        )

    # Preset count + codeId uniqueness, from the TOOLS tree (authoritative).
    try:
        sys.path.insert(0, TOOLS_TREE)
        import presets
        ids = [p["codeId"] for p in presets.PRESETS]
        count = len(presets.PRESETS)
        unique = len(set(ids)) == len(ids)
        print(f"IR_PRESET_COUNT={count}")
        print(f"IR_PRESET_IDS_UNIQUE={unique}")
        if count != 10:
            failures.append(f"PRESET_COUNT={count} expected 10")
        if not unique:
            failures.append("PRESET codeId duplicates found")
    except Exception as e:  # pragma: no cover - defensive
        failures.append(f"PRESET_IMPORT_FAILED: {e}")

    print(f"IR_PARITY_FILES_CHECKED={checked}")
    if failures:
        for f in failures:
            print(f"IR_PARITY_ERROR: {f}")
        print("IR_TOOL_PARITY_PASS=False")
        return 1
    print("IR_CAPTURE_FLOW_DUPLICATE_FILES_MATCH=True")
    print("IR_PRESET_DUPLICATE_FILES_MATCH=True")
    print("IR_TOOL_PARITY_PASS=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
