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
  * ZIP_STORED (no compression) — no zlib-version dependency.
  * every ZIP entry header field is explicitly pinned via make_zip_info
    (create_system=3, create/extract_version=20, flag_bits=0, volume=0,
    internal_attr=0, external_attr=0644<<16, extra=b"", comment=b"",
    fixed date_time) — no reliance on OS/platform defaults.
  * archive-level comment forced empty (z.comment = b"").
  * fixed entry order (PACKAGE_ENTRIES insertion order).

The EasyEDA project container is NOT part of the manufacturing ZIP; it is
delivered through the GitHub source archive. There is no option to include it.

Options:
  --ref <ref>          commit/tag to package from (default: HEAD)
  --out <dir>          output directory (repository-external)
  --name <name>        must equal the contract package name
                       (remote-ac-controller-pcb-rev1.0.1.zip); anything else
                       is rejected
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
    PACKAGE_NAME as CONTRACT_PACKAGE_NAME,
    make_zip_info,
    self_check as contract_self_check,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def build_entries(ref):
    """Fetch git-controlled bytes for every contract entry (exactly 13)."""
    entries = []
    for zname, gpath in PACKAGE_ENTRIES.items():
        entries.append((zname, git_show(ref, gpath)))
    if len(entries) != len(PACKAGE_ENTRIES):
        raise SystemExit(f"PACKAGE_ENTRY_COUNT={len(entries)} (want {len(PACKAGE_ENTRIES)}) -> FAIL")
    return entries


def write_zip(out_path, entries):
    """Write a deterministic ZIP (STORED, fixed order/timestamps/permissions).

    ZIP header metadata is explicitly pinned via make_zip_info (imported from
    the contract module), and the archive-level comment is forced empty, so
    the byte output does not depend on the platform (win32 vs linux) or the
    Python/zlib version.
    """
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as z:
        z.comment = b""
        for name, data in entries:  # insertion order == PACKAGE_ENTRIES order
            z.writestr(make_zip_info(name), data)


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
    # --name is kept only for explicitness; anything other than the contract
    # package name is rejected so no command line can produce a differently
    # named archive with the contract content (or vice versa).
    ap.add_argument("--name", default=CONTRACT_PACKAGE_NAME)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list-manifest", action="store_true")
    args = ap.parse_args()

    if args.name != CONTRACT_PACKAGE_NAME:
        print(f"PACKAGE_NAME_MISMATCH: {args.name!r} (contract requires {CONTRACT_PACKAGE_NAME!r}) -> FAIL")
        return 1

    ok, errs = contract_self_check()
    for e in errs:
        print(f"PCB_CONTRACT_ERROR: {e}")
    if not ok:
        print("PCB_CONTRACT_SINGLE_SOURCE=False")
        return 1
    print("PCB_CONTRACT_SINGLE_SOURCE=True")

    entries = build_entries(args.ref)

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
