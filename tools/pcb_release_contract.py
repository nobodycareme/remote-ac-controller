#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcb_release_contract.py — the single source of truth for the PCB release.

Both ``package-pcb-release.py`` (packaging) and ``check-pcb-release.py``
(validation) import the contract from here.  They MUST NOT carry their own
copies of the file list; any drift between the two tools is a defect.

Contract summary
----------------
The manufacturing ZIP ``remote-ac-controller-pcb-rev1.0.1.zip`` contains
exactly 13 entries (zip-relative names):

  gerber/  ... 8 Gerber layers
  drill/   ... 2 Excellon drill files
  test/FlyingProbeTesting.json
  manufacturing-manifest.md        (the manifest itself)
  PCB下单必读.txt

Of those 13 entries, exactly 12 are recorded in the manifest inventory
(one row each with size and SHA-256).  The manifest itself is NOT recorded
inside itself (no self-reference, avoiding a circular hash).

The EasyEDA project container lives in the tagged source tree under
``hardware/pcb/source/`` and is NOT part of the manufacturing ZIP by default.
"""

PCB_REVISION = "1.0.1"
PACKAGE_NAME = "remote-ac-controller-pcb-rev1.0.1.zip"

# zip-relative path -> git path (dict keeps insertion order; keys are unique)
PACKAGE_ENTRIES = {
    "gerber/Gerber_TopLayer.GTL":              "hardware/pcb/fabrication/gerber/Gerber_TopLayer.GTL",
    "gerber/Gerber_BottomLayer.GBL":           "hardware/pcb/fabrication/gerber/Gerber_BottomLayer.GBL",
    "gerber/Gerber_TopSilkscreenLayer.GTO":    "hardware/pcb/fabrication/gerber/Gerber_TopSilkscreenLayer.GTO",
    "gerber/Gerber_BottomSilkscreenLayer.GBO": "hardware/pcb/fabrication/gerber/Gerber_BottomSilkscreenLayer.GBO",
    "gerber/Gerber_TopSolderMaskLayer.GTS":    "hardware/pcb/fabrication/gerber/Gerber_TopSolderMaskLayer.GTS",
    "gerber/Gerber_BottomSolderMaskLayer.GBS": "hardware/pcb/fabrication/gerber/Gerber_BottomSolderMaskLayer.GBS",
    "gerber/Gerber_BoardOutlineLayer.GKO":     "hardware/pcb/fabrication/gerber/Gerber_BoardOutlineLayer.GKO",
    "gerber/Gerber_DrillDrawingLayer.GDD":     "hardware/pcb/fabrication/gerber/Gerber_DrillDrawingLayer.GDD",
    "drill/Drill_PTH_Through.DRL":             "hardware/pcb/fabrication/drill/Drill_PTH_Through.DRL",
    "drill/Drill_PTH_Through_Via.DRL":         "hardware/pcb/fabrication/drill/Drill_PTH_Through_Via.DRL",
    "test/FlyingProbeTesting.json":            "hardware/pcb/fabrication/test/FlyingProbeTesting.json",
    "manufacturing-manifest.md":               "hardware/pcb/fabrication/manufacturing-manifest.md",
    "PCB下单必读.txt":                          "hardware/pcb/fabrication/PCB下单必读.txt",
}

# The 12 files recorded in the manifest inventory (size + SHA-256).
# Deliberately excludes the manifest itself.
HASHED_MANIFEST_ENTRIES = (
    "gerber/Gerber_TopLayer.GTL",
    "gerber/Gerber_BottomLayer.GBL",
    "gerber/Gerber_TopSilkscreenLayer.GTO",
    "gerber/Gerber_BottomSilkscreenLayer.GBO",
    "gerber/Gerber_TopSolderMaskLayer.GTS",
    "gerber/Gerber_BottomSolderMaskLayer.GBS",
    "gerber/Gerber_BoardOutlineLayer.GKO",
    "gerber/Gerber_DrillDrawingLayer.GDD",
    "drill/Drill_PTH_Through.DRL",
    "drill/Drill_PTH_Through_Via.DRL",
    "test/FlyingProbeTesting.json",
    "PCB下单必读.txt",
)

MANIFEST_ZIP_PATH = "manufacturing-manifest.md"

EASYEDA_SOURCE_PATH = (
    "hardware/pcb/source/"
    "Remote_AC_Controller_PCB_Rev1.0.1.eprj2"
)


def self_check():
    """Validate the contract itself. Returns (ok: bool, errors: list)."""
    errors = []
    if len(PACKAGE_ENTRIES) != 13:
        errors.append(f"PACKAGE_ENTRIES length = {len(PACKAGE_ENTRIES)} (want 13)")
    if len(HASHED_MANIFEST_ENTRIES) != 12:
        errors.append(f"HASHED_MANIFEST_ENTRIES length = {len(HASHED_MANIFEST_ENTRIES)} (want 12)")
    if MANIFEST_ZIP_PATH not in PACKAGE_ENTRIES:
        errors.append(f"{MANIFEST_ZIP_PATH} not in PACKAGE_ENTRIES")
    if MANIFEST_ZIP_PATH in HASHED_MANIFEST_ENTRIES:
        errors.append(f"{MANIFEST_ZIP_PATH} must NOT be in HASHED_MANIFEST_ENTRIES")
    if len(set(PACKAGE_ENTRIES)) != len(PACKAGE_ENTRIES):
        errors.append("PACKAGE_ENTRIES contains duplicates")
    if len(set(HASHED_MANIFEST_ENTRIES)) != len(HASHED_MANIFEST_ENTRIES):
        errors.append("HASHED_MANIFEST_ENTRIES contains duplicates")
    expected_hashed = set(PACKAGE_ENTRIES) - {MANIFEST_ZIP_PATH}
    if set(HASHED_MANIFEST_ENTRIES) != expected_hashed:
        errors.append(
            f"HASHED_MANIFEST_ENTRIES != PACKAGE_ENTRIES - {{manifest}}: "
            f"missing={sorted(expected_hashed - set(HASHED_MANIFEST_ENTRIES))} "
            f"extra={sorted(set(HASHED_MANIFEST_ENTRIES) - expected_hashed)}"
        )
    return (len(errors) == 0, errors)


def contract_check():
    """Entry point used by CI/tools: print result, exit non-zero on failure."""
    ok, errors = self_check()
    for e in errors:
        print(f"PCB_CONTRACT_ERROR: {e}")
    print(f"PCB_CONTRACT_SINGLE_SOURCE={'True' if ok else 'False'}")
    print(f"PACKAGE_EXPECTED_FILE_COUNT={len(PACKAGE_ENTRIES)}")
    print(f"MANIFEST_EXPECTED_ENTRY_COUNT={len(HASHED_MANIFEST_ENTRIES)}")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(contract_check())
