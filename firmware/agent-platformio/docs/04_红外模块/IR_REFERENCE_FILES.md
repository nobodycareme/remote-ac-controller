# IR Reference Files — Inventory & Provenance

Manufacturer reference material for the **ZJ-IR-V2** IR learn/emit module.
Source directory (read-only, never modified/moved/renamed/deleted):

```
F:\PIO\红外资料
```

## 1. File inventory (captured 2026-07-14)

| # | File name | Size (bytes) | Last modified | SHA256 |
|---|-----------|-------------:|---------------|--------|
| 1 | `Arduino_Nano_IrStudy.ino` | 2,008 | 2026-07-13 16:58:49 | `299C829AB75D4B75D4F4E5D119BA1D88385567219996E438F461D1B1E00B486F` |
| 2 | `红外学习模块485原理图.pdf` | 40,107 | 2026-07-13 16:59:07 | `65EF0C7FC276DA872A2EE18962B5F67F20E0D3E2771FB48D4039B1F9122F3D5C` |
| 3 | `红外学习模块使用说明书V1.0.6.pdf` | 2,039,771 | 2026-07-13 16:59:08 | `B8055B1D5B705FFAC5DB692AF597E533BABA388382B5E80DE161023EE226BD0C` |
| 4 | `红外学习模块测试步骤.doc` | 1,735,168 | 2026-07-13 16:58:50 | `06772839F846C4CE1E3C702336535701C64540BCB99CCD26D6289F2443663443` |

SHA256 computed with PowerShell `Get-FileHash -Algorithm SHA256`.

## 2. Extraction / temporary copies

The original PDF/DOC/INO files are **not** included in the final review package.
Text was extracted (read-only) into a working area that is git-ignored and
excluded from the review package:

```
F:\PIO\Projects\Remote_AC_Controller\.work\ir_reference\
  Arduino_Nano_IrStudy.ino.txt   (copied verbatim, plain text)
  manual_V1.0.6.txt              (text extracted from PDF via pypdf, 35 pages)
  test_steps.txt                 (text extracted from .doc via Word COM)
  schematic_485.txt              (text extracted from PDF via pypdf, 2 pages)
  extract_pdf.py                 (pypdf extraction script, working copy)
  extract_ascii.py               (fallback raw-ASCII extractor, working copy)
```

Extraction method:
- `Arduino_Nano_IrStudy.ino` — read directly (plain text).
- `*.pdf` — **pypdf** (installed into the isolated managed venv) `PdfReader.extract_text()`;
  Word COM PDF import hung (>20 min, no output) in this environment, so pypdf was used instead.
- `红外学习模块测试步骤.doc` — **Microsoft Word COM** (`Word.Application.Documents.Open` + `Content.Text`),
  written as UTF-8 (native `.doc` opens fast; only PDF import hung).

No original file was modified, moved, renamed, or deleted.

## 3. Role & priority of each reference

Per the integration directive, on conflict the priority order is:

1. Physical ZJ-IR-V2 silkscreen + confirmed wiring (authoritative)
2. `红外学习模块使用说明书V1.0.6.pdf` — **primary protocol authority**
3. `红外学习模块测试步骤.doc` — wiring / learn / emit flow + LED behaviour
4. `Arduino_Nano_IrStudy.ino` — manufacturer example logic (ESP8266-rewrite required)
5. `红外学习模块485原理图.pdf` — RS-485 version; A/B diff lines / MAX485 are
   **auxiliary only** and must NOT change the confirmed TTL wiring.

## 4. Status

- [x] Files listed with size / modified time / SHA256.
- [x] Text extracted to `.work/ir_reference/` (read-only on originals; PDF via pypdf, .doc via Word COM).
- [x] `Arduino_Nano_IrStudy.ino` read directly (protocol skeleton confirmed).
- [x] Full protocol analysis consolidated in `IR_PROTOCOL_ANALYSIS.md` (all frames byte-verified).
- [x] **Phase 3 只读 UART probe 实测（2026-07-15）**：通过 `[env:nodemcuv2_probe]`（`-DDISABLE_DHT`）固件
      在 115200 下发 GET_BAUD / GET_ADDR，回包 `68 08 00 00 04 04 08 16` / `68 08 00 00 06 00 06 16`，
      帧头/长度/地址/功能码/校验和/帧尾全部 PASS，`IR_UART_PASS baud=115200`。
      资料中的帧结构与校验算法得到硬件级印证。详见 `IR_PROTOCOL_ANALYSIS.md` §27。
