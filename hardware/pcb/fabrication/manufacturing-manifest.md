# Manufacturing Manifest — PCB Rev 1.0.1

Revision: **Rev 1.0.1** (`hardware/pcb/REVISION`)
Generated for: Remote AC Controller software release v1.2.1
Source: JLCPCB/EasyEDA Pro one-click export (`嘉立创下单文件.zip`), corrected 2026-08-01.

## Package contract

The manufacturing package for Rev 1.0.1 is published as
`remote-ac-controller-pcb-rev1.0.1.zip` and **contains exactly**:

| ZIP entry | Description |
|---|---|
| `gerber/` (8 files) | RS-274X Gerber layers |
| `drill/` (2 files) | Excellon drill files |
| `test/FlyingProbeTesting.json` | Flying-probe test data |
| `manufacturing-manifest.md` | This manifest |
| `PCB下单必读.txt` | JLCPCB ordering hint (public, no secrets) |

The EasyEDA project source `source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2`
lives in the tagged source tree but is **not** part of the manufacturing ZIP
(unless a future release explicitly publishes it as a separate asset).

Rev 1.0 manufacturing files are superseded and must not be used for fabrication.

## File inventory (package entries)

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `gerber/Gerber_TopLayer.GTL` | 42046 | `b0c6e7afb2f122b318d78ec9063c847b915a3579c1f767a85c8a9fe96dd961b8` |
| `gerber/Gerber_BottomLayer.GBL` | 43792 | `26eeaa523c9bcfab8dffae6c2740ac2c4968441baf4c1ba586a7ad7eddd34b41` |
| `gerber/Gerber_TopSilkscreenLayer.GTO` | 149826 | `59b57e62728e68c7bb1a2392c5c9854c45977e03f603dd5c5621428465687070` |
| `gerber/Gerber_BottomSilkscreenLayer.GBO` | 121299 | `7f2bd96e02bd688822b5a844830c917ae764d051becb3afada7d08d4d4d8d287` |
| `gerber/Gerber_TopSolderMaskLayer.GTS` | 1945 | `612d52759b0f241dd9672c41bc77815878dc88d38b639ccfb912c2747a1d732b` |
| `gerber/Gerber_BottomSolderMaskLayer.GBS` | 1948 | `15ef036b9663358119c0fa88e01aa8eff1dd2ab6df6eabf135d66e147785a805` |
| `gerber/Gerber_BoardOutlineLayer.GKO` | 885 | `7cc20d58987d37c1e48df1f18b183f08e89b8d9576de14b4956017328f5fc5dc` |
| `gerber/Gerber_DrillDrawingLayer.GDD` | 123276 | `bd1740df1e1b0258795ab766933355123d1f927ef5b1610c7bca1bbef48573f1` |
| `drill/Drill_PTH_Through.DRL` | 1130 | `028f629baba8dbbc961054f89956635068ea3a2e3d78aa9e20fe71e020ddb282` |
| `drill/Drill_PTH_Through_Via.DRL` | 424 | `d0026e650645e644b98b49cb215b4145463bb5399e02267789dfb4cffc223abb` |
| `test/FlyingProbeTesting.json` | 7259 | `e8ae9a9185143f103b4171b41c01bdfa8d062ff29cb8ceae4e3b0a4c753d36ed` |
| `PCB下单必读.txt` | 94 | `dcb3ee1c645c17a009d70726ad9ab708b68a074556fabcf75a4a059d3b43ec59` |

> The manifest itself is not listed (no self-reference); its hash is fixed by
> the Git object for `hardware/pcb/fabrication/manufacturing-manifest.md`.
>
> The hashes above are computed over the exact bytes as stored in Git
> (`git show <ref>:<path>`) and therefore also over the exact bytes inside the
> deterministically built package. Working-tree line-ending conversion cannot
> alter these values (see `.gitattributes`).

## Byte provenance

- All manufacturing files are stored in Git with LF line endings
  (`-text` in `.gitattributes`); `core.autocrlf` does not apply to them.
- The package is built from Git-controlled bytes via `tools/package-pcb-release.py`,
  never from the working tree.
- Same commit → same ZIP (fixed entry order and fixed timestamps).

## Known constraints

- A verified BOM and pick-and-place/coordinate files are **not** included in
  this repository or in the manufacturing package.
- Gerber format: RS-274X, metric units, 4.5 precision.
- Drill format: Excellon, metric, leading zero suppression.
