**English** | [简体中文](./README.md)

# PCB Design Document (Rev 1.0.1)

## Overview

This PCB is designed for the **Remote AC Controller** project. The firmware runs
on a **NodeMCU ESP8266 development board**. The PCB carries the interface and
peripheral circuitry for an IR transmitter/receiver module and a
temperature/humidity sensor, used for air-conditioner IR remote control and
local data acquisition.

This repository publishes the PCB manufacturing files and the EasyEDA project
source. **It does not include a Bill of Materials (BOM), coordinate files, or
pick-and-place files**; you must compile those yourself for assembly.

## Design tool and revision

- **EasyEDA Pro** (professional edition)
- Project file: `source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2`
- Logical revision: **Rev 1.0.1** (`hardware/pcb/REVISION`)

> **Revision separation**: the software release version (v1.2.1) and the PCB
> design revision (Rev 1.0.1) are independent. The silkscreen still reads v1.0,
> but Rev 1.0.1 is the only valid manufacturing data.

## Layers and manufacturing files

**2-layer board**; manufacturing files live in `fabrication/gerber/`,
`fabrication/drill/`, and `fabrication/test/`:

| File | Description |
|------|-------------|
| `Gerber_TopLayer.GTL` | Top copper |
| `Gerber_BottomLayer.GBL` | Bottom copper |
| `Gerber_TopSilkscreenLayer.GTO` | Top silkscreen |
| `Gerber_BottomSilkscreenLayer.GBO` | Bottom silkscreen |
| `Gerber_TopSolderMaskLayer.GTS` | Top solder mask |
| `Gerber_BottomSolderMaskLayer.GBS` | Bottom solder mask |
| `Gerber_BoardOutlineLayer.GKO` | Board outline |
| `Gerber_DrillDrawingLayer.GDD` | Drill drawing layer |
| `Drill_PTH_Through.DRL` | Plated through-hole drill file |
| `Drill_PTH_Through_Via.DRL` | Via drill file |
| `FlyingProbeTesting.json` | Flying-probe test data (`fabrication/test/`) |
| `manufacturing-manifest.md` | Manufacturing manifest (per-file hashes) |

The manufacturing package contract is defined in
`fabrication/manufacturing-manifest.md`.

## Manufacturing notes

1. **Gerber format**: standard RS-274X (exported by EasyEDA Pro). Review the
   Gerber preview in the fab-house order page before ordering.
2. **Drill files**: separate Excellon `.DRL` files are provided; verify drill
   sizes and counts.
3. **Board outline**: defined by `Gerber_BoardOutlineLayer.GKO`; make sure the
   outline is closed.
4. **DRC**: run a design-rule check before fabrication to satisfy the
   manufacturer's process requirements.
5. **Rev 1.0 manufacturing files are superseded**: do not manufacture from the
   Rev 1.0 Gerber/drill files; use the Rev 1.0.1 data.

## License

The PCB design files are licensed under the [Apache License 2.0](../../LICENSE).

## Risk notes

> **Notice**: this PCB is open-source hardware for learning and research; open
> designs require the user to perform their own suitability verification.
>
> - Check power polarity and solder shorts before powering on.
> - The IR LED driver must use correct current-limiting resistors to avoid
>   damaging components.
> - Review the Gerber preview and drill files before fabrication.
> - Rev 1.0 manufacturing files are superseded and must not be used.
> - The author accepts no liability for any direct or indirect loss caused by
>   the use of this design.
