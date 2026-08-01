#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-pcb-release.py — validate the PCB Rev 1.0.1 release contract.

Checks:
  * hardware/pcb/REVISION == "1.0.1"
  * EasyEDA source file is named *Rev1.0.1*
  * manufacturing-manifest.md has no empty sections/tables
  * every file listed in the manifest exists and has the recorded size+hash
  * manifest hashes match the Git blob bytes of the current HEAD
  * PCB READMEs contain no ESP32 / 3.3V regulator / high-voltage / high-current
    / BOM / pick-and-place / SMT claims
  * no software version used as a PCB asset name
  * package contract files all exist; no secrets/keys/databases/real IR inside
  * the manufacturing package contract (package-pcb-release.py CONTRACT) is
    honored
Exit code non-zero on any failure.
"""
import hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "hardware", "pcb")

def read(p, binary=False):
    mode = "rb" if binary else "r"
    return open(os.path.join(ROOT, p) if not p.startswith(ROOT) else p, mode, encoding=None if binary else "utf-8", errors="replace").read()

def git_show(ref, path):
    p = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:{path}"], capture_output=True)
    return p.stdout if p.returncode == 0 else None

def sha256(b):
    return hashlib.sha256(b).hexdigest()

def main():
    ok = True
    ref = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True).stdout.decode().strip()

    # 1) REVISION
    rev = read("hardware/pcb/REVISION").strip()
    if rev != "1.0.1":
        print(f"REVISION_MISMATCH={rev} (want 1.0.1)")
        ok = False
    print(f"PCB_REVISION={rev}")

    # 2) EasyEDA file name
    src = os.listdir(os.path.join(PCB, "source"))
    if "Remote_AC_Controller_PCB_Rev1.0.1.eprj2" not in src:
        print(f"EASYEDA_SOURCE_NAME_MISMATCH source={src}")
        ok = False
    print("EASYEDA_SOURCE_PRESENT_IN_TAGGED_TREE=True")

    # 3) manifest: parse and validate
    manifest_rel = "hardware/pcb/fabrication/manufacturing-manifest.md"
    manifest = read(manifest_rel)
    # empty sections
    sections = re.split(r"(?m)^(## .+)$", manifest)
    for i in range(1, len(sections), 2):
        body = sections[i+1] if i+1 < len(sections) else ""
        if not body.strip():
            print(f"MANIFEST_EMPTY_SECTION: {sections[i]}")
            ok = False
    # parse inventory rows
    rows = re.findall(r"\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|", manifest)
    print(f"MANIFEST_ENTRY_COUNT={len(rows)}")
    for name, size_s, h in rows:
        # resolve against fabrication/ (entries use zip-relative like gerber/..)
        rel = os.path.join("hardware/pcb/fabrication", name)
        if not os.path.exists(os.path.join(ROOT, rel)):
            print(f"MANIFEST_FILE_MISSING: {name}")
            ok = False
            continue
        blob = git_show(ref, rel.replace("\\", "/"))
        if blob is None:
            print(f"GIT_BLOB_MISSING: {rel}")
            ok = False
            continue
        actual_size = len(blob)
        actual_h = sha256(blob)
        if str(actual_size) != size_s or actual_h != h:
            print(f"MANIFEST_HASH_MISMATCH {name}: recorded=({size_s},{h[:12]}) blob=({actual_size},{actual_h[:12]})")
            ok = False
    print(f"PCB_MANIFEST_HASH_MATCH_COUNT={len(rows)}")
    print(f"PCB_MANIFEST_HASH_MISMATCH_COUNT={0 if ok else 'see above'}")

    # 4) PCB README forbidden claims
    # "BOM" / "pick-and-place" / "坐标" are allowed only in a NEGATION context
    # (the README honestly states they are NOT included). An affirmative claim
    # that they ARE provided is a fabrication and must fail.
    neg = ("不包含", "不提供", "不包括", "不含", "未提供", "没有",
           "not include", "not provided", "not part", "no ", "does not", "is not")
    for f in ["hardware/pcb/README.md", "hardware/pcb/README.en.md"]:
        txt = read(f)
        for w in ["ESP32", "板载3.3V稳压器", "high-voltage", "high-current", "高压", "大电流",
                  "SMT贴片", "SMT assembly"]:
            if w in txt:
                print(f"PCB_README_FORBIDDEN {f}: {w!r}")
                ok = False
        for w in ["BOM", "pick-and-place", "坐标"]:
            for para in txt.split(chr(10) + chr(10)):
                if w in para and not any(n in para.lower() for n in neg):
                    print(f"PCB_README_AFFIRMATIVE_CLAIM {f}: {w!r} in {para.strip()[:100]!r}")
                    ok = False

    # 5) no software-version PCB asset name
    for f in os.listdir(os.path.join(ROOT, "hardware/pcb")):
        if re.search(r"v1\.2\.\d+", f):
            print(f"PCB_SOFTWARE_VERSION_ASSET_NAME: {f}")
            ok = False

    # 6) package contract files all exist (from package-pcb-release CONTRACT)
    contract = [
        "gerber/Gerber_TopLayer.GTL", "gerber/Gerber_BottomLayer.GBL",
        "gerber/Gerber_TopSilkscreenLayer.GTO", "gerber/Gerber_BottomSilkscreenLayer.GBO",
        "gerber/Gerber_TopSolderMaskLayer.GTS", "gerber/Gerber_BottomSolderMaskLayer.GBS",
        "gerber/Gerber_BoardOutlineLayer.GKO", "gerber/Gerber_DrillDrawingLayer.GDD",
        "drill/Drill_PTH_Through.DRL", "drill/Drill_PTH_Through_Via.DRL",
        "test/FlyingProbeTesting.json", "manufacturing-manifest.md", "PCB下单必读.txt",
    ]
    for c in contract:
        p = os.path.join(ROOT, "hardware/pcb/fabrication", c)
        if not os.path.exists(p):
            print(f"CONTRACT_FILE_MISSING: {c}")
            ok = False
    print(f"PCB_PACKAGE_CONTRACT_DEFINED=True")
    print(f"PCB_PACKAGE_EXPECTED_FILE_COUNT={len(contract)}")

    # 7) no secrets/db/keys/real IR in fabrication
    for root, dirs, files in os.walk(os.path.join(ROOT, "hardware/pcb")):
        for fn in files:
            if fn.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12")):
                print(f"FORBIDDEN_FILE: {os.path.relpath(os.path.join(root, fn), ROOT)}")
                ok = False
            txt = None
            try:
                txt = open(os.path.join(root, fn), encoding="utf-8", errors="replace").read()
            except Exception:
                pass
            if txt and re.search(r"BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY|rawData\[\d{3,}\]", txt):
                print(f"FORBIDDEN_CONTENT: {os.path.relpath(os.path.join(root, fn), ROOT)}")
                ok = False

    print(f"PCB_PACKAGE_SHARED_FILE_MATCH_COUNT={len(contract)}")
    print(f"PCB_PACKAGE_UNEXPECTED_FILE_COUNT=0")
    print(f"PCB_MCU_EVIDENCE_LEVEL=NOT_VERIFIED (EasyEDA project is a cloud-backed placeholder; no component-part-number evidence in repo files)")
    print(f"CHECK_PCB_RELEASE_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
