[简体中文](./README.md) | **English**

# IR Simple Learner

A minimal Windows GUI tool for capturing infrared (IR) signals from air conditioner remote controls via a CH9102 USB-to-UART adapter connected to an ESP8266 NodeMCU with a ZJ-IR-V2 IR learning module.

---

## Purpose

This tool communicates with an ESP8266 firmware (public profile) over a serial port to learn IR frames emitted by an air conditioner remote. Captured frames are validated, compared, and saved for integration into the remote-ac-controller firmware.

**This tool does not contain any real AC IR frames or production credentials.** All distributed test vectors are synthetic.

## Requirements

- **Operating System**: Windows 10/11 (x64)
- **Python**: 3.9 or later
- **Hardware**: ESP8266 NodeMCU with CH9102 USB chip + ZJ-IR-V2 IR learning module
- **Driver**: CH9102 driver ([WCH official download](https://www.wch.cn/downloads/CH341SER_EXE.html))

## Quick Start (Pre-built EXE)

1. Download `IR_Simple_Learner_v4_windows_x64.exe` from the [Releases](https://github.com/nobodycareme/remote-ac-controller/releases) page.
2. Windows may show a SmartScreen warning because the EXE is **unsigned**. Click "More info" then "Run anyway".
3. Connect the ESP8266 NodeMCU via USB.
4. Run the EXE and follow the on-screen instructions.

### SHA256 Verification

Verify the downloaded EXE against the published SHA256 hash:

```powershell
Get-FileHash IR_Simple_Learner_v4_windows_x64.exe -Algorithm SHA256
```

The expected hash is published alongside each GitHub Release.

## Install from Source

```powershell
cd tools/ir-simple-learner

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the tool
python src/simple_ir_learner.py
```

### Run Unit Tests

```powershell
python -m unittest discover -s src/tests -p "test_*.py" -v
```

## Build the EXE

```powershell
pwsh tools/ir-simple-learner/build.ps1
```

The EXE will be written to `tools/ir-simple-learner/dist/`. Use `-Clean` to rebuild from scratch:

```powershell
pwsh tools/ir-simple-learner/build.ps1 -Clean
```

## Usage

### 1. Connect the Device

Connect the ESP8266 NodeMCU to your PC via USB. The CH9102 driver should auto-install; if not, download it from the [WCH website](https://www.wch.cn/downloads/CH341SER_EXE.html).

### 2. Launch the Tool

Run the EXE or `python src/simple_ir_learner.py`. The main window has three sections:

- **Device Connection** (top): Scan ports, connect/disconnect, status LED.
- **AC State** (left): Preset selector, mode, temperature, fan, extra options.
- **Capture** (right): Capture buttons (1-3), compare, approve canonical frame.

### 3. Capture Workflow

1. Click **Scan Ports** to find the CH9102 device.
2. Select the port and click **Connect**.
3. Choose an AC state from the preset dropdown or fill in parameters manually.
4. Click **Capture 1**. When the status shows "please press remote", press the remote control button once.
5. Wait for the capture to save (SHA256 and byte count shown in log).
6. Repeat for **Capture 2** and **Capture 3**.
7. Click **Compare All** to see byte-level differences between captures.
8. Select the canonical capture (1, 2, or 3) and click **Select Canonical**.

### 4. Save Location

Captured data is saved to a user-configurable directory (default: `~/IR_Learned/`). To change it, click **Set Save Directory** in the tool.

## CH9102 Driver Note

The ESP8266 NodeMCU used in this project uses a **CH9102** USB-to-serial chip (VID 0x1A86, PID 0x55D4). Windows may not install the driver automatically.

- Download: [WCH CH341SER driver package](https://www.wch.cn/downloads/CH341SER_EXE.html)
- After installation, the device should appear as a COM port in Device Manager.

## Security

- **The EXE is unsigned.** This is expected. Windows SmartScreen will show a warning. Verify the SHA256 hash against the published value.
- **No production credentials, WiFi passwords, or real IR codes** are embedded in the tool or its source code.
- All test data in the repository (including `presets.py`) contains configuration metadata only, not actual IR frame payloads.
- Captured IR data is saved locally and never transmitted anywhere by this tool.

Report security issues via [SECURITY.md](../../SECURITY.md).

## License

This tool is part of the remote-ac-controller project, licensed under the Apache License, Version 2.0. See [LICENSE](../../LICENSE) for the full text.

Third-party component licenses are listed in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## Related Documentation

- [Firmware README](../../firmware/README.md) — ESP8266 firmware build and flash
- [Project README](../../README.md) — Full project overview