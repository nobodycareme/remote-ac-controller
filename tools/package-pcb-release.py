#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""package-pcb-release.py — build the deterministic PCB manufacturing package.

The package contract is defined once in ``tools/pcb_release_contract.py``
(single source of truth) and imported here; this script does NOT carry its
own copy of the file list.

Contract:
  remote-ac-controller-pcb-rev1.0.1.zip contains exactly 13 entries:
    gerber/  (8 Gerber layers)
    drill/   (2 Excellon drill files)
    test/FlyingProbeTesting.json
    manufacturing-manifest.md
    PCB下单必读.txt
  Exactly 12 of those entries are recorded in the manifest inventory.

The package is built from **git-controlled bytes** (`git show <ref>:<path>`),
never from the working tree, so Windows core.autocrlf conversion cannot alter
the published bytes.

Determinism policy:
  * ZIP_STORED (no compression) — byte-identical ZIPs across any Python/zlib
    combination. (ZIP_DEFLATED would tie bytes to the zlib version.)
  * fixed entry order (PACKAGE_ENTRIES insertion order)
  * fixed timestamps, fixed permissions, no extra fields, no ZIP comment.

Options:
  --ref <ref>          commit/tag to package from (default: HEAD)
  --out <dir>          output directory (repository-external)
  --name <name>        package file name (default remote-ac-controller-pcb-rev1.0.1.zip)
  --include-eprj2      also include the EasyEDA source file (not part of the
                       default manufacturing contract)
  --verify             verify the ZIP against the exact contract after writing
  --list-manifest      print the 12-row manifest inventory table and exit

Never includes Private/, Evidence/, Archives/, secrets, databases or real IR.
"""
import argparse, hashlib, io, os, re, subprocess, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_release_contract import (
    PACKAGE_ENTRIES,
    HASHED_MANIFEST_ENTRIES,
    MANIFEST_ZIP_PATH,
    EASYEDA_SOURCE_PATH,
    PACKAGE_NAME as CONTRACT_PACKAGE_NAME,
    self_check as contract_self_check,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPRJ2_ZIP_NAME = "source/" + os.path.basename(EASYEDA_SOURCE_PATH)

ZIP_MTIME = (2026, 8, 1, 0, 0, 0)  # fixed timestamp for determinism


def git_show(ref, path):
    p = subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"],
                       capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"git show failed for {ref}:{path}: {p.stderr.decode('utf-8','replace')[:200]}")
    return p.stdout


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def manifest_table(entries):
    lines = [
        "| File | Size (bytes) | SHA-256 |",
        "|---|---|---|",
    ]
    for name, size, h in entries:
        lines.append(f"| `{name}` | {size} | `{h}` |")
    return "\n".join(lines)


def read_manifest_rows(manifest_text):
    """Parse manifest inventory rows. Returns (rows, duplicate_names)."""
    rows = re.findall(r"\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|", manifest_text)
    seen = {}
    dups = set()
    for name, size, h in rows:
        if name in seen:
            dups.add(name)
        seen[name] = (size, h)
    return rows, sorted(dups)


def build_entries(ref, include_eprj2):
    """Fetch git-controlled bytes for every contract entry."""
    entries = []
    for zname, gpath in PACKAGE_ENTRIES.items():
        entries.append((zname, git_show(ref, gpath)))
    if include_eprj2:
        entries.append((EPRJ2_ZIP_NAME, git_show(ref, EASYEDA_SOURCE_PATH)))
    return entries


def write_zip(out_path, entries):
    """Write a deterministic ZIP (STORED, fixed order/timestamp/permissions)."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as z:
        for name, data in entries:  # insertion order == PACKAGE_ENTRIES order
            zi = zipfile.ZipInfo(name, date_time=ZIP_MTIME)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o100644 << 16
            z.writestr(zi, data)


def verify_zip(out_path, ref):
    """Verify the written ZIP against the exact contract. Returns exit code."""
    ok = True

    with zipfile.ZipFile(out_path) as z:
        names = z.namelist()
        zipped = {n: z.read(n) for n in names}

    # 1) exactly the contract file set, no dups, no extras
    expected_names = set(PACKAGE_ENTRIES)
    actual_names = set(names)
    dup = len(names) - len(actual_names)
    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names)
    print(f"PACKAGE_ACTUAL_FILE_COUNT={len(names)}")
    print(f"PACKAGE_DUPLICATE_FILE_COUNT={dup}")
    print(f"PACKAGE_MISSING_FILE_COUNT={len(missing)}")
    print(f"PACKAGE_UNEXPECTED_FILE_COUNT={len(unexpected)}")
    if len(names) != len(PACKAGE_ENTRIES):
        print(f"PACKAGE_ENTRY_COUNT_MISMATCH: actual={len(names)} want={len(PACKAGE_ENTRIES)}")
        ok = False
    if dup:
        print("PACKAGE_DUPLICATE_ENTRIES: yes")
        ok = False
    if missing:
        print(f"PACKAGE_MISSING_FILES={missing}")
        ok = False
    if unexpected:
        print(f"PACKAGE_UNEXPECTED_FILES={unexpected}")
        ok = False

    # 2) manifest: exactly 12 rows, exact set, no self, hashes match git bytes
    manifest_text = zipped[MANIFEST_ZIP_PATH].decode("utf-8", "replace")
    rows, dups = read_manifest_rows(manifest_text)
    hashed_names = set(r[0] for r in rows)
    expected_hashed = set(HASHED_MANIFEST_ENTRIES)
    man_missing = sorted(expected_hashed - hashed_names)
    man_extra = sorted(hashed_names - expected_hashed)
    self_hashed = MANIFEST_ZIP_PATH in hashed_names
    print(f"MANIFEST_ACTUAL_ENTRY_COUNT={len(rows)}")
    print(f"MANIFEST_DUPLICATE_ENTRY_COUNT={len(dups)}")
    print(f"MANIFEST_MISSING_ENTRY_COUNT={len(man_missing)}")
    print(f"MANIFEST_UNEXPECTED_ENTRY_COUNT={len(man_extra)}")
    print(f"MANIFEST_SELF_HASHED={self_hashed}")
    if len(rows) != len(HASHED_MANIFEST_ENTRIES):
        print(f"MANIFEST_ENTRY_COUNT_MISMATCH: actual={len(rows)} want={len(HASHED_MANIFEST_ENTRIES)}")
        ok = False
    if dups:
        print(f"MANIFEST_DUPLICATE_ENTRIES={dups}")
        ok = False
    if man_missing:
        print(f"MANIFEST_MISSING_ENTRIES={man_missing}")
        ok = False
    if man_extra:
        print(f"MANIFEST_UNEXPECTED_ENTRIES={man_extra}")
        ok = False
    if self_hashed:
        print("MANIFEST_SELF_REFERENCE_PRESENT")
        ok = False

    # 3) every manifest row: recorded size + hash == git blob bytes
    match = mismatch = 0
    for name, size_s, h in rows:
        if name not in PACKAGE_ENTRIES:
            continue  # already counted as unexpected
        blob = git_show(ref, PACKAGE_ENTRIES[name])
        if len(blob) == int(size_s) and sha256(blob) == h:
            match += 1
        else:
            mismatch += 1
            print(f"MANIFEST_HASH_MISMATCH {name}: recorded=({size_s},{h[:12]}) git_blob=({len(blob)},{sha256(blob)[:12]})")
    print(f"PCB_MANIFEST_HASH_MATCH_COUNT={match}")
    print(f"PCB_MANIFEST_HASH_MISMATCH_COUNT={mismatch}")
    if mismatch:
        ok = False

    # 4) every ZIP entry == git blob bytes (byte-for-byte)
    g_match = g_mismatch = 0
    for name, data in zipped.items():
        if name not in PACKAGE_ENTRIES:
            continue
        blob = git_show(ref, PACKAGE_ENTRIES[name])
        if data == blob:
            g_match += 1
        else:
            g_mismatch += 1
            print(f"ZIP_GIT_BYTE_MISMATCH {name}")
    print(f"PACKAGE_GIT_BYTE_MATCH_COUNT={g_match}")
    print(f"PACKAGE_GIT_BYTE_MISMATCH_COUNT={g_mismatch}")
    if g_mismatch:
        ok = False

    print(f"PACKAGE_MANIFEST_VERIFY={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default=CONTRACT_PACKAGE_NAME)
    ap.add_argument("--include-eprj2", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list-manifest", action="store_true")
    args = ap.parse_args()

    ok, errs = contract_self_check()
    for e in errs:
        print(f"PCB_CONTRACT_ERROR: {e}")
    if not ok:
        print("PCB_CONTRACT_SINGLE_SOURCE=False")
        return 1
    print("PCB_CONTRACT_SINGLE_SOURCE=True")

    entries = build_entries(args.ref, args.include_eprj2)

    if args.list_manifest:
        # ONLY the 12 hashed entries; the manifest itself is never listed.
        rows = []
        for zname, data in entries:
            if zname == MANIFEST_ZIP_PATH:
                continue
            rows.append((zname, len(data), sha256(data)))
        if len(rows) != len(HASHED_MANIFEST_ENTRIES):
            print(f"LIST_MANIFEST_ENTRY_COUNT={len(rows)} (want 12) -> FAIL")
            return 1
        print(manifest_table(rows))
        print(f"LIST_MANIFEST_ENTRY_COUNT={len(rows)}")
        print(f"LIST_MANIFEST_CONTAINS_SELF=False")
        return 0

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, args.name)
    write_zip(out_path, entries)

    pkg_hash = sha256(open(out_path, "rb").read())
    print(f"PACKAGE_PATH={out_path}")
    print(f"PACKAGE_SHA256={pkg_hash}")
    print(f"PACKAGE_ENTRY_COUNT={len(entries)}")
    print(f"PACKAGE_SOURCE_REF={args.ref}")
    print(f"PACKAGE_COMPRESSION=ZIP_STORED")

    if args.verify:
        return verify_zip(out_path, args.ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
