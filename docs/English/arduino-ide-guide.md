[简体中文](../中文/Arduino-IDE使用指南.md) | **English**

# Arduino IDE Guide

> End-to-end workflow for building, uploading and debugging the Remote AC Controller
> firmware with Arduino IDE 2.x (or `arduino-cli`). PlatformIO is **not** required.

---

## 0. The one thing to understand first

Feature switches (`ENABLE_*`) are **not** configured in `sketch.yaml`, and you never
`#include` a config header yourself. This project uses the ESP8266 core's official
**Global Build Options** mechanism:

- The ESP8266 core (arduino-esp8266 >= 2.5) runs a prebuild step,
  `mkbuildoptglobals.py`, that **force-includes `<sketch>.ino.globals.h` into every
  single compilation unit**;
- so you only need to drop a `Remote_AC_Controller.ino.globals.h` next to the sketch
  and your macros apply globally;
- **no** `-include` flag, **no** `compile.extra_flags` in `sketch.yaml`, and **no**
  `#include` inside the `.ino` are needed.

Reference: [Arduino ESP8266 — Global Build Options](https://arduino-esp8266.readthedocs.io/en/latest/faq/a06-global-build-options.html)

---

## 1. Prerequisites

### 1.1 Install Arduino IDE

Download and install Arduino IDE **2.x** from [arduino.cc](https://www.arduino.cc/en/software).

### 1.2 Add ESP8266 board support

1. File → Preferences → "Additional boards manager URLs":
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
2. Tools → Board → Boards Manager → search `esp8266` → Install
   (verified on **3.1.2**, which matches PlatformIO's `espressif8266@4.2.1`)
3. Tools → Board → ESP8266 → **NodeMCU 1.0 (ESP-12E Module)**

### 1.3 Third-party libraries (Library Manager)

Sketch → Include Library → Manage Libraries, install these **exact versions**:

| Library | Author | Pinned version | Needed when |
|---------|--------|----------------|-------------|
| DHT sensor library | Adafruit | **1.4.7** | always |
| Adafruit Unified Sensor | Adafruit | **1.1.15** | always (DHT dependency) |
| PubSubClient | Nick O'Leary | **2.8.0** | `ENABLE_CLOUD=1` |
| ArduinoJson | Benoit Blanchon | **6.21.5** | always |

> Versions are pinned on purpose — do not take "latest". ArduinoJson 7.x is API
> incompatible with this project.
>
> **Do not install any third-party library named "Crypto"** (e.g. Rhys
> Weatherley's Crypto). Campus authentication does not need it — `srun-c` ships
> its own MD5/SHA1/HMAC implementation. The only `#include <Crypto.h>` /
> `#include <base64.h>` in the firmware sit inside the
> `#if ENABLE_IR_LAB_LEARNING_COMMANDS` block of `serial_cli.cpp`, and both
> headers **ship with the ESP8266 core**. Installing a same-named third-party
> library can cause header conflicts. The same applies to `SoftwareSerial`.

### 1.4 Install the two in-repo libraries (one script)

The Arduino IDE only discovers libraries inside your **sketchbook's `libraries`
directory**. The repository ships a script so you do not have to copy things by hand:

```bash
# macOS / Linux / Git Bash
./firmware/arduino-ide/tools/install-arduino-libraries.sh

# custom sketchbook location
ARDUINO_SKETCHBOOK=/your/sketchbook ./firmware/arduino-ide/tools/install-arduino-libraries.sh
```

```powershell
# Windows PowerShell
.\firmware\arduino-ide\tools\install-arduino-libraries.ps1
```

What it does:

| Library | Method | Why |
|---------|--------|-----|
| `RemoteACCore` | **symlink** to `firmware/shared/RemoteACCore` | already in Arduino library layout; a symlink means repository edits (e.g. dropping your own `config/profiles/xidian.h`) take effect immediately |
| `srun-c` | **generated** flattened copy | upstream uses PlatformIO's `include/` + `src/` split, which `arduino-cli` does not understand; the script merges it into a single `src/` and writes a `library.properties` |

> If symlinks are unavailable (e.g. Windows without Developer Mode) the script falls
> back to copying — in that case **re-run it after every repository edit**.
> Likewise, re-run it whenever you change anything under `lib/srun-c`.
> The script never touches credentials, never compiles and never flashes.

---

## 2. Configure feature switches (the globals workflow)

### 2.1 Copy the globals header

```bash
cd firmware/arduino-ide/Remote_AC_Controller
cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

`Remote_AC_Controller.ino.globals.h` is **git-ignored** — it can enable live
authentication and must never be committed. Only the `.example.h` is tracked, and its
defaults are safe (everything that can transmit, authenticate or embed a secret is
`0`), so a fresh clone compiles out of the box.

### 2.2 Edit the switches

| Macro | Default | Meaning |
|-------|---------|---------|
| `ENABLE_WIFI` | 1 | Wi-Fi core functionality |
| `ENABLE_CAMPUS_AUTH` | 0 | compile srun campus authentication |
| `ENABLE_AUTO_CAMPUS_AUTH` | 0 | authenticate automatically on captive-portal detection |
| `ENABLE_CLOUD` | 0 | MQTT cloud link |
| `ENABLE_CLOUD_CREDENTIALS` | 0 | compile cloud credentials |
| `ENABLE_CONTROLLED_LIVE_AUTH` | 0 | **live** login (compiles real account + password) |
| `ENABLE_IR_MUTATING_COMMANDS` | 0 | real IR transmission |
| `ENABLE_IR_LAB_LEARNING_COMMANDS` | 0 | IR learning lab commands |

Each macro is `#ifndef`-guarded, so a command-line `-D` still overrides it.

### 2.3 Campus auth requires an explicit profile

If `ENABLE_CAMPUS_AUTH=1` and no profile is selected, the build **stops with
`#error`** — the project never silently targets an unspecified campus portal.

```bash
# Xidian example: copy the example profile to a git-ignored real one
cd firmware/shared/RemoteACCore/src/config/profiles
cp xidian.example.h xidian.h
```

Then, in `Remote_AC_Controller.ino.globals.h`:

```c
#define ENABLE_CAMPUS_AUTH    1
#define CAMPUS_PROFILE_HEADER "profiles/xidian.h"
```

For other universities start from `generic_srun.example.h` and follow the
[Srun campus network porting guide](./srun-campus-network-porting-guide.md).

### 2.4 Where credentials live

Your username and password go **only** into the git-ignored `campus_secrets.h`, and
are compiled **only** when you additionally set `ENABLE_CONTROLLED_LIVE_AUTH=1`
locally. The repository contains no account, password, cookie, token or private key.

---

## 3. Build and upload

Arduino IDE:

1. Open `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino`
2. Tools → Board → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. Tools → Port → your ESP8266 serial port
4. Click Verify (✓) to compile, Upload (→) to flash

`arduino-cli`:

```bash
cd firmware/arduino-ide/Remote_AC_Controller
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 .
arduino-cli upload  --fqbn esp8266:esp8266:nodemcuv2 -p COM3 .
```

> Upload takes roughly 2–3 minutes. Do not disconnect mid-flash.

---

## 4. Serial debugging

- Tools → Serial Monitor, baud **115200**, line ending Newline

Expected boot output:

```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
```

With campus auth enabled you will also see portal detection, e.g.:

```
CAPTIVE_PORTAL_DETECTED host=w.xidian.edu.cn AC_ID=8
```

Without credentials the firmware states this explicitly (by design, not a fault):

```
CAMPUS_CREDS_READY=NO
AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS
```

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `RemoteACApp.h: No such file` | `install-arduino-libraries` not run, or IDE not restarted afterwards |
| `srun.h: No such file` | same as above; or set `ENABLE_CAMPUS_AUTH` back to `0` |
| `#error ... no campus profile selected` | `ENABLE_CAMPUS_AUTH=1` without `CAMPUS_PROFILE_HEADER`; see §2.3 |
| edited a macro in globals but **nothing changed** | the file must be named **exactly** `Remote_AC_Controller.ino.globals.h` and sit in the **same directory** as the `.ino`; any other name or location is ignored by the core |
| `#include expects "FILENAME"` | `CAMPUS_PROFILE_HEADER` must keep its quotes, e.g. `"profiles/xidian.h"` |
| repository edits not picked up | the script fell back to copy mode; re-run `install-arduino-libraries` |
| upload fails | check the port; some modules need FLASH held while tapping RST |
| no serial output | baud must be 115200; install the CH9102/CP2102 driver; try another USB cable |
| `TLS_PIN_MISMATCH` | the portal certificate rotated — re-pin per [TLS certificate pinning](../../firmware/agent-platformio/docs/03_协议与接口/TLS证书固定与更新.md); **never** fall back to `setInsecure()` |

---

## 6. Related documents

- [Xidian campus network authentication](./xidian-campus-network-authentication.md)
- [Srun campus network porting guide](./srun-campus-network-porting-guide.md)
- [Security model](./security-model.md)
- [Hardware](./hardware.md) · [Wiring](./wiring.md)
