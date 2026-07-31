[简体中文](./README.md) | **English**

# PCB Design Documentation

## Overview

This PCB is designed for the **Remote AC Controller** project, integrating an ESP32 microcontroller, IR transmitter and receiver modules, temperature/humidity sensor, and power management circuitry for air conditioner IR remote control and cloud data acquisition.

## Design Software

- **EasyEDA Pro** (Professional Edition)
- Project file: `source/Remote_AC_Controller_PCB_v1.0.eprj2`

## Layer Count

- **2-layer board**
- Top Layer: `Gerber_TopLayer.GTL`
- Bottom Layer: `Gerber_BottomLayer.GBL`

## Board Specifications

| Item | Specification |
|------|---------------|
| Layers | 2 |
| Board Thickness | 1.6mm (standard) |
| Copper Thickness | 1oz (35μm) |
| Surface Finish | HASL (leaded/lead-free as required) |
| Min Trace/Space | 6mil / 6mil (recommended) |
| Min Hole Size | 0.3mm |
| Solder Mask Color | Green (default) |
| Silkscreen Color | White |
| Laminate | FR-4 TG130-140 |

## Gerber File List

All fabrication files are located in `fabrication/gerber/` and `fabrication/drill/`:

| File Name | Description |
|-----------|-------------|
| `Gerber_TopLayer.GTL` | Top copper layer |
| `Gerber_BottomLayer.GBL` | Bottom copper layer |
| `Gerber_TopSilkscreenLayer.GTO` | Top silkscreen |
| `Gerber_BottomSilkscreenLayer.GBO` | Bottom silkscreen |
| `Gerber_TopSolderMaskLayer.GTS` | Top solder mask |
| `Gerber_BottomSolderMaskLayer.GBS` | Bottom solder mask |
| `Gerber_BoardOutlineLayer.GKO` | Board outline |
| `Gerber_DrillDrawingLayer.GDD` | Drill drawing layer |
| `Drill_PTH_Through.DRL` | Through-hole drill file |
| `Drill_PTH_Through_Via.DRL` | Via drill file |

## Manufacturing Notes

1. **Gerber Format**: Standard RS-274X format exported from EasyEDA Pro.
2. **Drill Files**: Separate Excellon format drill files (`.DRL`) are provided.
3. **Board Outline**: Defined by `Gerber_BoardOutlineLayer.GKO` — verify the outline is closed before submission.
4. **Solder Mask Openings**: The solder mask layer defines pad and via openings; standard process is recommended.
5. **Silkscreen**: Top silkscreen includes component identifiers and labels.

## JLCPCB Ordering Guide

1. Log in to [jlcpcb.com](https://jlcpcb.com) and select "Order Now".
2. Upload all `.GTL`, `.GBL`, `.GTO`, `.GBO`, `.GTS`, `.GBS`, `.GKO`, `.GDD` files from `fabrication/gerber/`.
3. Upload `.DRL` drill files from `fabrication/drill/`.
4. **Recommended Configuration**:
   - Layers: 2 Layers
   - Board Thickness: 1.6mm
   - Copper Weight: 1oz
   - Solder Mask: Green
   - Surface Finish: HASL or LeadFree HASL
   - Quantity: 5 pieces (minimum order)
5. Verify Gerber preview and place the order.

## License

This PCB design is licensed under the [Apache License 2.0](../../LICENSE).

## Disclaimer

> **Note**: This PCB is an open-source hardware design intended for educational and research purposes only. Users should verify the completeness and correctness of the design themselves.
>
> - The circuit may contain high-voltage or high-current sections. Inspect solder joints and check for shorts before powering on.
> - The IR transmitter module uses IR LED drivers. Verify current-limiting resistors to avoid component damage.
> - The ESP32 power supply requires a stable 3.3V output. Use a qualified voltage regulator.
> - Always run DRC (Design Rule Check) before fabrication to ensure the design meets the manufacturer's process requirements.
> - The author assumes no responsibility for any direct or indirect damages resulting from the use of this design.