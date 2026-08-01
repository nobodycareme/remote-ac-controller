#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""package-pcb-release.py — build the deterministic PCB manufacturing package.

Contract (hardware/pcb/fabrication/manufacturing-manifest.md):

  remote-ac-controller-pcb-rev1.0.1.zip contains only:
    gerber/  (8 Gerber layers)
    drill/   (2 Excellon drill files)
    test/FlyingProbeTesting.json
    manufacturing-manifest.md
    PCB下单必读.txt

The package is built from **git-controlled bytes** (`git show <ref>:<path>`),
never from the working tree, so Windows core.autocrlf conversion cannot alter
the published bytes. The same commit always produces the same ZIP.

Options:
  --ref <ref>          commit/tag to package from (default: HEAD)
  --out <dir>          output directory (repository-external)
  --name <name>        package file name (default remote-ac-controller-pcb-rev1.0.1.zip)
  --include-eprj2      also include the EasyEDA source file (not part of the
                       default manufacturing contract)
  --verify             verify every entry against the manifest after writing
  --list-manifest      print the manifest table that must be recorded in
                       manufacturing-manifest.md and exit

Never includes Private/, Evidence/, Archives/, secrets, databases or real IR.
"""
import argparse, hashlib, io, os, subprocess, sys, zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = "hardware/pcb"

# Package contract: zip-relative path -> git path
CONTRACT = [
    ("gerber/Gerber_TopLayer.GTL",              "hardware/pcb/fabrication/gerber/Gerber_TopLayer.GTL"),
    ("gerber/Gerber_BottomLayer.GBL",           "hardware/pcb/fabrication/gerber/Gerber_BottomLayer.GBL"),
    ("gerber/Gerber_TopSilkscreenLayer.GTO",    "hardware/pcb/fabrication/gerber/Gerber_TopSilkscreenLayer.GTO"),
    ("gerber/Gerber_BottomSilkscreenLayer.GBO", "hardware/pcb/fabrication/gerber/Gerber_BottomSilkscreenLayer.GBO"),
    ("gerber/Gerber_TopSolderMaskLayer.GTS",    "hardware/pcb/fabrication/gerber/Gerber_TopSolderMaskLayer.GTS"),
    ("gerber/Gerber_BottomSolderMaskLayer.GBS", "hardware/pcb/fabrication/gerber/Gerber_BottomSolderMaskLayer.GBS"),
    ("gerber/Gerber_BoardOutlineLayer.GKO",     "hardware/pcb/fabrication/gerber/Gerber_BoardOutlineLayer.GKO"),
    ("gerber/Gerber_DrillDrawingLayer.GDD",     "hardware/pcb/fabrication/gerber/Gerber_DrillDrawingLayer.GDD"),
    ("drill/Drill_PTH_Through.DRL",             "hardware/pcb/fabrication/drill/Drill_PTH_Through.DRL"),
    ("drill/Drill_PTH_Through_Via.DRL",         "hardware/pcb/fabrication/drill/Drill_PTH_Through_Via.DRL"),
    ("test/FlyingProbeTesting.json",            "hardware/pcb/fabrication/test/FlyingProbeTesting.json"),
    ("manufacturing-manifest.md",               "hardware/pcb/fabrication/manufacturing-manifest.md"),
    ("PCB下单必读.txt",                          "hardware/pcb/fabrication/PCB下单必读.txt"),
]
EPRJ2 = ("source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2",
         "hardware/pcb/source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2")

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="remote-ac-controller-pcb-rev1.0.1.zip")
    ap.add_argument("--include-eprj2", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list-manifest", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    # build entry bytes from git
    entries = []  # (name, bytes)
    for zname, gpath in CONTRACT:
        entries.append((zname, git_show(args.ref, gpath)))
    if args.include_eprj2:
        entries.append((EPRJ2[0], git_show(args.ref, EPRJ2[1])))

    if args.list_manifest:
        rows = [(n, len(b), sha256(b)) for n, b in entries]
        print(manifest_table(rows))
        return 0

    # deterministic zip: fixed timestamps, sorted names, no extra fields
    out_path = os.path.join(args.out, args.name)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries, key=lambda e: e[0]):
            zi = zipfile.ZipInfo(name, date_time=ZIP_MTIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o100644 << 16
            z.writestr(zi, data)

    pkg_hash = sha256(open(out_path, "rb").read())
    print(f"PACKAGE_PATH={out_path}")
    print(f"PACKAGE_SHA256={pkg_hash}")
    print(f"PACKAGE_ENTRY_COUNT={len(entries)}")
    print(f"PACKAGE_SOURCE_REF={args.ref}")

    if args.verify:
        # verify entries match manifest table inside the package
        with zipfile.ZipFile(out_path) as z:
            manifest_blob = z.read("manufacturing-manifest.md").decode("utf-8", "replace")
            import re
            ok = True
            for name, data in entries:
                if name == "manufacturing-manifest.md":
                    continue
                m = re.search(rf"\| `{re.escape(name)}` \| (\d+) \| `([0-9a-f]{{64}})` \|", manifest_blob)
                if not m:
                    print(f"MANIFEST_ENTRY_MISSING {name}")
                    ok = False
                    continue
                size, h = int(m.group(1)), m.group(2)
                if size != len(data) or h != sha256(data):
                    print(f"MANIFEST_MISMATCH {name} recorded=({size},{h[:12]}) actual=({len(data)},{sha256(data)[:12]})")
                    ok = False
            print(f"PACKAGE_MANIFEST_VERIFY={'PASS' if ok else 'FAIL'}")
            if not ok:
                return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
