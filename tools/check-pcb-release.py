#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-pcb-release.py — validate the PCB Rev 1.0.1 release contract.

All checks read candidate bytes from a Git ref (default HEAD) — never from
the working tree — and every counter is actually computed.

Checks:
  * contract self-check (single source of truth in pcb_release_contract.py)
  * hardware/pcb/REVISION == contract revision
  * EasyEDA Rev1.0.1 source exists in the tagged tree (git ls-tree)
  * manifest: exactly 12 rows, no duplicates, exact set match, sizes and
    SHA-256 actually computed against Git blob bytes, no self-reference
  * PCB READMEs: no forbidden claims (negation-aware BOM/pick-and-place)
  * no software version used as a PCB asset name
  * fabrication tree: no databases, keys, or real-IR content
  * package is actually built into a repo-external temp dir and the ZIP is
    opened and checked: exactly 13 files, exact set, no dups, ZIP bytes equal
    Git blob bytes
  * --negative-test: 10 sabotage scenarios must all return non-zero

Exit code non-zero on any failure.
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_release_contract import (
    PCB_REVISION,
    PACKAGE_ENTRIES,
    HASHED_MANIFEST_ENTRIES,
    MANIFEST_ZIP_PATH,
    EASYEDA_SOURCE_PATH,
    PACKAGE_NAME,
    self_check as contract_self_check,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_GIT_PATH = "hardware/pcb/fabrication/manufacturing-manifest.md"
FABRICATION_GIT_PREFIX = "hardware/pcb/fabrication/"


def git_show(ref, path):
    p = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:{path}"], capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout


def git_ls_tree(ref, path):
    p = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "--name-only", ref, "--", path],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return []
    return [l for l in p.stdout.splitlines() if l]


def git_ls_tree_dir(ref, path):
    """List a directory's immediate entries (names only)."""
    p = subprocess.run(["git", "-C", ROOT, "ls-tree", "--name-only", ref, path],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return []
    return [l for l in p.stdout.splitlines() if l]


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def parse_manifest_rows(manifest_text):
    """Returns (rows, duplicate_names)."""
    rows = re.findall(r"\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|", manifest_text)
    seen = set()
    dups = []
    for r in rows:
        if r[0] in seen and r[0] not in dups:
            dups.append(r[0])
        seen.add(r[0])
    return rows, sorted(dups)


def verify_manifest(manifest_text, ref):
    """Verify a manifest against the contract and Git bytes.
    Returns (ok, counters dict)."""
    ok = True
    rows, dups = parse_manifest_rows(manifest_text)
    hashed = set(r[0] for r in rows)
    expected = set(HASHED_MANIFEST_ENTRIES)
    missing = sorted(expected - hashed)
    extra = sorted(hashed - expected)
    self_hashed = MANIFEST_ZIP_PATH in hashed

    if len(rows) != len(HASHED_MANIFEST_ENTRIES):
        ok = False
    if dups:
        ok = False
    if missing or extra:
        ok = False
    if self_hashed:
        ok = False

    match = mismatch = 0
    for name, size_s, h in rows:
        if name not in PACKAGE_ENTRIES:
            continue  # extra entry already counted
        blob = git_show(ref, PACKAGE_ENTRIES[name])
        if blob is None:
            mismatch += 1
            ok = False
            continue
        if len(blob) == int(size_s) and sha256(blob) == h:
            match += 1
        else:
            mismatch += 1
            ok = False
    # entries expected but absent also count as mismatches (unverifiable)
    for name in missing:
        blob = git_show(ref, PACKAGE_ENTRIES[name])
        if blob is None:
            mismatch += 1

    counters = {
        "MANIFEST_EXPECTED_ENTRY_COUNT": len(HASHED_MANIFEST_ENTRIES),
        "MANIFEST_ACTUAL_ENTRY_COUNT": len(rows),
        "MANIFEST_DUPLICATE_ENTRY_COUNT": len(dups),
        "MANIFEST_MISSING_ENTRY_COUNT": len(missing),
        "MANIFEST_UNEXPECTED_ENTRY_COUNT": len(extra),
        "PCB_MANIFEST_HASH_MATCH_COUNT": match,
        "PCB_MANIFEST_HASH_MISMATCH_COUNT": mismatch,
        "MANIFEST_SELF_HASHED": self_hashed,
    }
    return ok, counters


def verify_package_zip(zip_path, ref):
    """Open a built ZIP and verify the exact contract. Returns (ok, counters)."""
    ok = True
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}

    actual = set(names)
    expected = set(PACKAGE_ENTRIES)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    dup = len(names) - len(actual)

    if len(names) != len(PACKAGE_ENTRIES):
        ok = False
    if dup:
        ok = False
    if missing or extra:
        ok = False

    g_match = g_mismatch = 0
    for name in names:
        if name not in PACKAGE_ENTRIES:
            continue
        blob = git_show(ref, PACKAGE_ENTRIES[name])
        if blob is None:
            g_mismatch += 1
            ok = False
        elif data[name] == blob:
            g_match += 1
        else:
            g_mismatch += 1
            ok = False

    counters = {
        "PACKAGE_EXPECTED_FILE_COUNT": len(PACKAGE_ENTRIES),
        "PACKAGE_ACTUAL_FILE_COUNT": len(names),
        "PACKAGE_DUPLICATE_FILE_COUNT": dup,
        "PACKAGE_MISSING_FILE_COUNT": len(missing),
        "PACKAGE_UNEXPECTED_FILE_COUNT": len(extra),
        "PACKAGE_GIT_BYTE_MATCH_COUNT": g_match,
        "PACKAGE_GIT_BYTE_MISMATCH_COUNT": g_mismatch,
    }
    return ok, counters


def verify_easyeda_in_tree(ref, path=EASYEDA_SOURCE_PATH):
    return len(git_ls_tree(ref, path)) > 0


# --- negative tests ---------------------------------------------------------

def _make_broken_manifest(manifest_text, kind):
    rows, _ = parse_manifest_rows(manifest_text)
    lines = manifest_text.splitlines()
    # find the inventory table rows (lines matching the row pattern)
    row_lines = [l for l in lines if re.match(r"\| `[^`]+` \| \d+ \| `[0-9a-f]{64}` \|", l)]
    if kind == "remove":          # 1) drop one row
        lines = [l for l in lines if l != row_lines[0]]
    elif kind == "extra":         # 2) duplicate an existing row with a new name
        extra = row_lines[0].replace(row_lines[0].split("`")[1], "zzz_FABRICATED_EXTRA.txt")
        lines.append(extra)
    elif kind == "duplicate":     # 3) duplicate an existing row verbatim
        lines.append(row_lines[0])
    elif kind == "bad_hash":      # 4) corrupt a hash
        lines = [l if l != row_lines[0] else re.sub(r"[0-9a-f]{64}", "0" * 64, l) for l in lines]
    elif kind == "bad_size":      # 5) corrupt a size
        lines = [l if l != row_lines[0] else re.sub(r"\| (\d+) \|", "| 999999 |", l, count=1) for l in lines]
    elif kind == "self":          # 6) manifest lists itself
        # fabricate a row referencing the manifest (hash won't match anyway)
        lines.append(f"| `{MANIFEST_ZIP_PATH}` | 123 | `{'a' * 64}` |")
    return "\n".join(lines)


def run_negative_tests(ref):
    """10 sabotage scenarios; every one must make verification fail."""
    cases = []
    manifest_blob = git_show(ref, MANIFEST_GIT_PATH)
    if manifest_blob is None:
        print("NEGATIVE_TEST_SETUP_FAIL: cannot read manifest")
        return 1, 0
    manifest_text = manifest_blob.decode("utf-8", "replace")

    # scenarios 1-6: broken manifests
    manifest_kinds = [
        ("remove", "manifest missing an entry"),
        ("extra", "manifest with an extra entry"),
        ("duplicate", "manifest with a duplicate entry"),
        ("bad_hash", "manifest with a wrong hash"),
        ("bad_size", "manifest with a wrong size"),
        ("self", "manifest containing itself"),
    ]
    for kind, desc in manifest_kinds:
        broken = _make_broken_manifest(manifest_text, kind)
        ok, _ = verify_manifest(broken, ref)
        cases.append((desc, ok))

    # build a pristine package in a temp dir for ZIP scenarios
    tmp = tempfile.mkdtemp(prefix="pcb-neg-")
    pkg = os.path.join(tmp, PACKAGE_NAME)
    script = os.path.join(ROOT, "tools", "package-pcb-release.py")
    subprocess.run([sys.executable, script, "--ref", ref, "--out", tmp],
                   capture_output=True)
    if not os.path.exists(pkg):
        print("NEGATIVE_TEST_SETUP_FAIL: package build failed")
        return 1, 0

    def _zip_variant(variant):
        """Write a sabotaged ZIP; returns path."""
        out = os.path.join(tmp, f"broken-{variant}.zip")
        with zipfile.ZipFile(pkg) as z:
            names = z.namelist()
            data = {n: z.read(n) for n in names}
        if variant == "missing":          # 7) drop a file
            data.pop(sorted(data)[0])
        elif variant == "extra":          # 8) add a file
            data["zzz_UNEXPECTED.txt"] = b"unexpected"
        elif variant == "tampered":       # 9) modify bytes of one file
            k = sorted(data)[0]
            data[k] = data[k] + b"X"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zo:
            for n in sorted(data):
                zi = zipfile.ZipInfo(n)
                zi.compress_type = zipfile.ZIP_STORED
                zo.writestr(zi, data[n])
        return out

    zip_variants = [
        ("missing", "ZIP missing a file"),
        ("extra", "ZIP with an extra file"),
        ("tampered", "ZIP entry bytes modified"),
    ]
    for variant, desc in zip_variants:
        bp = _zip_variant(variant)
        ok, _ = verify_package_zip(bp, ref)
        cases.append((desc, ok))

    # 10) EasyEDA source missing: check with a fabricated path
    ed_ok = verify_easyeda_in_tree(ref, "hardware/pcb/source/DOES_NOT_EXIST.eprj2")
    cases.append(("EasyEDA source missing", ed_ok))

    total = len(cases)
    failed = [d for d, ok in cases if ok]
    for d, ok in cases:
        # ok==True means the sabotage was NOT detected -> test failed
        print(f"NEGATIVE_TEST {'FAIL' if ok else 'PASS'}: {d}")
    print(f"PCB_NEGATIVE_TEST_TOTAL={total}")
    print(f"PCB_NEGATIVE_TEST_PASS={total - len(failed)}")
    return (0 if not failed else 1), (total - len(failed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--negative-test", action="store_true")
    args = ap.parse_args()
    ref = args.ref

    if args.negative_test:
        code, _ = run_negative_tests(ref)
        return code

    ok = True

    # 0) contract self-check
    cok, errs = contract_self_check()
    for e in errs:
        print(f"PCB_CONTRACT_ERROR: {e}")
        ok = ok and cok
    print(f"PCB_CONTRACT_SINGLE_SOURCE={'True' if cok else 'False'}")

    # 1) REVISION (from git tree)
    rev = git_show(ref, "hardware/pcb/REVISION")
    if rev is None:
        print("REVISION_NOT_IN_TREE")
        ok = False
    else:
        rev_s = rev.decode().strip()
        if rev_s != PCB_REVISION:
            print(f"REVISION_MISMATCH={rev_s} (want {PCB_REVISION})")
            ok = False
        print(f"PCB_REVISION={rev_s}")

    # 2) EasyEDA source in tagged tree (real evidence only)
    ed = verify_easyeda_in_tree(ref)
    if not ed:
        print("EASYEDA_SOURCE_PRESENT_IN_TAGGED_TREE=False")
        ok = False
    else:
        print("EASYEDA_SOURCE_PRESENT_IN_TAGGED_TREE=True")
        print(f"EASYEDA_SOURCE_PATH={EASYEDA_SOURCE_PATH}")

    # 3) manifest (from git tree)
    manifest_blob = git_show(ref, MANIFEST_GIT_PATH)
    if manifest_blob is None:
        print("MANIFEST_NOT_IN_TREE")
        ok = False
    else:
        mok, mcnt = verify_manifest(manifest_blob.decode("utf-8", "replace"), ref)
        ok = ok and mok
        for k, v in mcnt.items():
            print(f"{k}={v}")
        # empty sections check (text-level)
        sections = re.split(r"(?m)^(## .+)$", manifest_blob.decode("utf-8", "replace"))
        for i in range(1, len(sections), 2):
            body = sections[i + 1] if i + 1 < len(sections) else ""
            if not body.strip():
                print(f"MANIFEST_EMPTY_SECTION: {sections[i]}")
                ok = False

    # 4) PCB README forbidden claims (from git tree)
    neg = ("不包含", "不提供", "不包括", "不含", "未提供", "没有",
           "not include", "not provided", "not part", "no ", "does not", "is not")
    for f in ["hardware/pcb/README.md", "hardware/pcb/README.en.md"]:
        txt_b = git_show(ref, f)
        if txt_b is None:
            print(f"PCB_README_MISSING: {f}")
            ok = False
            continue
        txt = txt_b.decode("utf-8", "replace")
        for w in ["ESP32", "板载3.3V稳压器", "high-voltage", "high-current", "高压", "大电流",
                  "SMT贴片", "SMT assembly"]:
            if w in txt:
                print(f"PCB_README_FORBIDDEN {f}: {w!r}")
                ok = False
        for w in ["BOM", "pick-and-place", "坐标"]:
            for para in txt.split("\n\n"):
                if w in para and not any(n in para.lower() for n in neg):
                    print(f"PCB_README_AFFIRMATIVE_CLAIM {f}: {w!r} in {para.strip()[:100]!r}")
                    ok = False

    # 5) no software-version PCB asset name
    for fn in git_ls_tree_dir(ref, "hardware/pcb"):
        if re.search(r"v1\.2\.\d+", fn):
            print(f"PCB_SOFTWARE_VERSION_ASSET_NAME: {fn}")
            ok = False

    # 6) fabrication tree: forbidden file types / content (from git tree)
    for rel in git_ls_tree(ref, "hardware/pcb"):
        if rel.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12")):
            print(f"FORBIDDEN_FILE: {rel}")
            ok = False
        if rel.endswith((".GTL", ".GBL", ".GTO", ".GBO", ".GTS", ".GBS", ".GKO", ".GDD",
                         ".DRL", ".eprj2", ".png", ".jpg", ".zip")):
            continue
        try:
            txt_b = git_show(ref, rel)
            if txt_b and re.search(rb"BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY|rawData\[\d{3,}\]", txt_b):
                print(f"FORBIDDEN_CONTENT: {rel}")
                ok = False
        except Exception:
            pass

    # 7) actually build the package into a repo-external temp dir and verify
    tmp = tempfile.mkdtemp(prefix="pcb-check-")
    script = os.path.join(ROOT, "tools", "package-pcb-release.py")
    p = subprocess.run([sys.executable, script, "--ref", ref, "--out", tmp],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print(f"PACKAGE_BUILD_FAILED rc={p.returncode}: {p.stdout[-300:]} {p.stderr[-300:]}")
        ok = False
    else:
        pkg = os.path.join(tmp, PACKAGE_NAME)
        if not os.path.exists(pkg):
            print("PACKAGE_FILE_NOT_CREATED")
            ok = False
        else:
            pok, pcnt = verify_package_zip(pkg, ref)
            ok = ok and pok
            for k, v in pcnt.items():
                print(f"{k}={v}")
            # security scan of the generated ZIP contents
            with zipfile.ZipFile(pkg) as z:
                for n in z.namelist():
                    d = z.read(n)
                    if n.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12")):
                        print(f"ZIP_FORBIDDEN_FILE: {n}")
                        ok = False
                    if re.search(rb"BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY|rawData\[\d{3,}\]", d):
                        print(f"ZIP_FORBIDDEN_CONTENT: {n}")
                        ok = False

    print(f"PCB_MCU_EVIDENCE_LEVEL=NOT_VERIFIED (the checked-in project file does not expose independently verified component part-number or complete-editability evidence)")
    print(f"CHECK_PCB_RELEASE_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
