**English** | [简体中文](../中文/PCB发布流程.md)

# Hardware (PCB) Release Process

This document defines how PCB manufacturing data is published and verified.

## Revision model

- Each PCB revision is recorded in `hardware/pcb/REVISION`; the history lives
  in `hardware/pcb/CHANGELOG.md`.
- The revision is independent of the software version (vX.Y.Z).
- Any manufacturing-data change (layout / manufacturing files) must bump the
  revision.

## Manufacturing package contract

The package `remote-ac-controller-pcb-rev1.0.1.zip` contains exactly:

| ZIP path | Source |
|---|---|
| `gerber/` (8 Gerber files) | `hardware/pcb/fabrication/gerber/` |
| `drill/` (2 drill files) | `hardware/pcb/fabrication/drill/` |
| `test/FlyingProbeTesting.json` | `hardware/pcb/fabrication/test/` |
| `manufacturing-manifest.md` | `hardware/pcb/fabrication/` |
| `PCB下单必读.txt` | `hardware/pcb/fabrication/` |

The EasyEDA source file
(`source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2`) stays in the tagged source
tree and is **not** part of the manufacturing ZIP by default.

## Packaging and verification

- Build with
  `tools/package-pcb-release.py --ref <tag> --out <dir>` from **Git-controlled
  bytes** (`git show <ref>:<path>`), immune to Windows line-ending conversion.
- The same commit must produce the same ZIP twice (deterministic).
- Every entry's size and SHA-256 must match `manufacturing-manifest.md`
  (`--verify` checks automatically).
- After tagging, re-download the manufacturing package and verify per file
  (never substitute the pre-packaging local files).

## Manufacturing file line-ending rules

- `hardware/pcb/fabrication/**` and `hardware/pcb/source/*.eprj2` are marked
  `-text` / `binary` in `.gitattributes`; no line-ending conversion is allowed.
- Hashes are always computed over Git blob bytes.

## Post-release error handling

- Never silently replace a published manufacturing asset.
- If manufacturing files are wrong: bump the PCB revision
  (Rev x.y.z → Rev x.y.z+1), publish a new patch software release, and add a
  bilingual "superseded" notice to the old release body.
- Rev 1.0 manufacturing files are superseded by Rev 1.0.1 and must not be used
  for fabrication.

## Forbidden

- The package must never contain BOM/coordinates, private keys, databases,
  real IR frames, or `Private/` content.
- Do not publish the EasyEDA source as part of the manufacturing package by
  default (unless explicitly decided).

## Related documents

- [Manufacturing manifest](../../hardware/pcb/fabrication/manufacturing-manifest.md)
- 简体中文: [PCB 发布流程](../中文/PCB发布流程.md)、
  [版本管理](../中文/版本管理.md)
