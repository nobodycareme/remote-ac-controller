[简体中文](./README.md) | **English**

# Remote AC Controller — Arduino IDE Build Guide

Build instructions for the **Remote AC Controller** (ESP8266 NodeMCU v2) using
the Arduino IDE / arduino-cli.

This sketch is a thin entry point; all business logic lives in the shared
library `firmware/shared/RemoteACCore/`. The PlatformIO build
(`firmware/agent-platformio/`) compiles the exact same sources.

---

## 1. Prerequisites

### 1.1 ESP8266 board support

1. Arduino IDE → File → Preferences
2. Add to "Additional Boards Manager URLs":
   `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
3. Tools → Board → Boards Manager → search `esp8266` → install (**3.1.x or newer**)

### 1.2 Dependency libraries (Library Manager)

Install via Sketch → Include Library → Manage Libraries. **Not all are
mandatory** — install according to the feature switches you enable:

| Library                 | Author          | Pinned version | Required when                                 |
|-------------------------|-----------------|----------------|-----------------------------------------------|
| DHT sensor library      | Adafruit        | **1.4.7**      | Always (`dht11_sensor.h` includes it unconditionally) |
| Adafruit Unified Sensor | Adafruit        | **1.1.15**     | Always (dependency of the DHT library)         |
| ArduinoJson             | Benoit Blanchon | **6.21.5**     | Install always; mandatory with `ENABLE_CAMPUS_AUTH=1` |
| PubSubClient            | Nick O'Leary    | **2.8.0**      | Mandatory with `ENABLE_CLOUD=1`                |

> Versions are **pinned** on purpose — do not take "latest". ArduinoJson 7.x is
> API-incompatible with this project.

> **Do NOT install any third-party library named "Crypto".**
> Earlier revisions of this document listed Crypto (Rhys Weatherley) as
> required. That was incorrect. The `#include <Crypto.h>` and
> `#include <base64.h>` in `serial_cli.cpp` sit inside an
> `#if ENABLE_IR_LAB_LEARNING_COMMANDS` block, and both headers **ship with the
> ESP8266 core** (`framework-arduinoespressif8266/cores/esp8266/`).
> Installing a same-named third-party library can cause header conflicts.

**SoftwareSerial** (used by the IR module) also ships with the ESP8266 core — no
separate install needed.

### 1.3 The two in-repo libraries (use the script, do not copy by hand)

The Arduino IDE only discovers libraries inside your **sketchbook's `libraries`
directory**. This repository ships two libraries:

- `firmware/shared/RemoteACCore` — already in Arduino library layout
- `firmware/agent-platformio/lib/srun-c` — PlatformIO layout (`include/` +
  `src/`), which **arduino-cli does not understand**; it must be flattened into
  a single `src/` directory to be recognised

So use the provided script rather than a manual `cp -r`:

```bash
# macOS / Linux / Git Bash
./firmware/arduino-ide/tools/install-arduino-libraries.sh

# Windows PowerShell
.\firmware\arduino-ide\tools\install-arduino-libraries.ps1

# custom sketchbook location
ARDUINO_SKETCHBOOK=/your/sketchbook ./firmware/arduino-ide/tools/install-arduino-libraries.sh
```

The script **symlinks** RemoteACCore into the sketchbook (repository edits take
effect immediately) and **generates** a flattened Arduino-layout copy of
srun-c. Re-run it after changing anything under `lib/srun-c`. The script never
touches credentials, never compiles, and never flashes.

**Restart the Arduino IDE** afterwards, otherwise the new libraries are not
picked up.

> `firmware/agent-platformio/lib/srun-c` is the **single authoritative copy** of
> srun-c in this repository; the sketchbook copy is generated — never edit code
> there. srun-c is only compiled when `ENABLE_CAMPUS_AUTH=1`.

---

## 2. Configuration: Global Build Options (the only mechanism)

### Why there is only one mechanism

Arduino compiles every `.cpp` inside a library as a **separate translation
unit**. `#include`-ing a config header from the `.ino` **cannot** affect
`RemoteACCore`'s own `.cpp` files. This project therefore uses the ESP8266
core's official **Global Build Options** mechanism: the core's prebuild step
`mkbuildoptglobals.py` automatically force-includes

```
Remote_AC_Controller.ino.globals.h
```

into **every** translation unit. No `-include` flag, no `sketch.yaml` edits, and
you must **not** `#include` it from the `.ino` yourself.

> Earlier revisions told users to "copy `config.example.h` → `config.h`" and to
> "point `sketch.yaml`'s `compile.extra_flags` at globals.h". **Both are
> obsolete**: the `config.h` produced that way is not included by any
> translation unit (setting `CAMPUS_SSID` there silently does nothing), and
> `compile.extra_flags` is not a supported Arduino sketch-project key.
> `config.example.h` has been removed from the repository.

### Configuration steps

```bash
cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

`Remote_AC_Controller.ino.globals.h` is git-ignored. Edit the switches inside:

| Feature                  | Macro                             | Default (example.h) |
|--------------------------|-----------------------------------|---------------------|
| Wi-Fi                    | `ENABLE_WIFI`                     | `1`                 |
| Campus authentication    | `ENABLE_CAMPUS_AUTH`              | `0`                 |
| Automatic campus auth    | `ENABLE_AUTO_CAMPUS_AUTH`         | `0`                 |
| Cloud (MQTT)             | `ENABLE_CLOUD`                    | `0`                 |
| Cloud credential loading | `ENABLE_CLOUD_CREDENTIALS`        | `0`                 |
| Controlled live auth     | `ENABLE_CONTROLLED_LIVE_AUTH`     | `0`                 |
| IR transmit commands     | `ENABLE_IR_MUTATING_COMMANDS`     | `0`                 |
| IR lab-learning commands | `ENABLE_IR_LAB_LEARNING_COMMANDS` | `0`                 |

**You may skip this step entirely** — the committed `.example.h` carries safe
public defaults (everything that can transmit, authenticate, or embed a secret
is `0`), so a fresh clone compiles as-is.

The constraints between switches are defined in one authoritative place,
`RemoteACCore/src/config/feature_gates.h`; violating them raises a compile-time
`#error` instead of silently degrading.

### A profile is mandatory when campus auth is on

```c
#define ENABLE_CAMPUS_AUTH   1
#define CAMPUS_PROFILE_HEADER "profiles/xidian.h"        // your own copy
// or
#define CAMPUS_PROFILE_HEADER "profiles/generic_srun.h"  // your own copy
```

Create the profile copy from an example (everything under `profiles/` except
`*.example.h` is git-ignored):

```bash
cd ~/Arduino/libraries/RemoteACCore/src/config/profiles
cp xidian.example.h xidian.h               # Xidian University, values pre-filled
cp generic_srun.example.h generic_srun.h   # other srun campuses, fill in yourself
```

If `ENABLE_CAMPUS_AUTH=1` and no profile is selected, the build aborts with
`#error` — the firmware **never** targets an unspecified campus portal. See
[Xidian campus network authentication](../../../docs/English/xidian-campus-network-authentication.md)
and the
[srun porting guide](../../../docs/English/srun-campus-network-porting-guide.md).

### Credential files (all git-ignored)

Runtime values are **not** configured in this sketch folder:

| Item                | Location                                                  | Consumed when                     |
|---------------------|-----------------------------------------------------------|-----------------------------------|
| Home Wi-Fi credentials | `RemoteACCore/src/config/wifi_secrets.h` (used by the no-arg `wifi connect`) | `ENABLE_WIFI=1 ENABLE_WIFI_CREDENTIALS=1` |
| Open SSID           | serial command `wifi connect <ssid>` (explicit open SSID)  | `ENABLE_WIFI=1`                   |
| Campus parameters   | the profile header (SSID / portal host / ac_id / cert pin) | `ENABLE_CAMPUS_AUTH=1`            |
| Campus credentials  | `RemoteACCore/src/config/campus_secrets.h`                 | `ENABLE_CONTROLLED_LIVE_AUTH=1`   |
| MQTT broker         | `RemoteACCore/src/cloud_secrets.h`                         | `ENABLE_CLOUD_CREDENTIALS=1`      |

```bash
# Home Wi-Fi credentials (home/lab WPA/WPA2, mutually exclusive with campus)
cp ~/Arduino/libraries/RemoteACCore/src/config/wifi_secrets.example.h \
   ~/Arduino/libraries/RemoteACCore/src/config/wifi_secrets.h
# Edit wifi_secrets.h: LOCAL_WIFI_SSID / LOCAL_WIFI_PASSWORD

# Campus account (create only if you really need live authentication;
# mutually exclusive with home Wi-Fi credentials)
cp ~/Arduino/libraries/RemoteACCore/src/config/campus_secrets.example.h \
   ~/Arduino/libraries/RemoteACCore/src/config/campus_secrets.h

# MQTT credentials (create only when cloud is enabled)
cp ../../agent-platformio/include/cloud_secrets.example.h \
   ~/Arduino/libraries/RemoteACCore/src/cloud_secrets.h
```

> `cloud_secrets.h` must sit in the library's `src/` folder (which Arduino adds
> to the include path); `campus_secrets.h` must sit in `src/config/` (next to
> `campus_credentials.h`, which includes it). If missing, the build fails with
> an explicit `#error` rather than silently using empty credentials.

**Never commit** `globals.h`, `campus_secrets.h`, `cloud_secrets.h`, or any
non-`.example.h` profile.

---

## 3. Build & upload

1. Open `Remote_AC_Controller.ino` in the Arduino IDE
2. Tools → Board → ESP8266 → **NodeMCU 1.0 (ESP-12E Module)**
3. Tools → Port → your ESP8266 serial port
4. Click Verify (✓) to compile
5. Click Upload (→) to flash

arduino-cli equivalents:

```bash
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 .
arduino-cli upload  --fqbn esp8266:esp8266:nodemcuv2 -p COM3 .
```

Reference footprint (`ENABLE_WIFI=1`, everything else `0`): ~43% Flash, ~45% RAM.

---

## 4. Serial monitor & first run

- Tools → Serial Monitor
- Baud rate: **115200**
- Line ending: Newline

Expected startup messages:

```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
SINGLE_SERIAL_ROUTER=TRUE
```

**Wi-Fi does not auto-connect** (offline-first design). After boot you will see:

```
AUTO_WIFI_CONNECT_SKIPPED (manual `wifi connect`)
```

Common commands:

```
help                  - command overview
wifi connect [ssid]   - associate with an OPEN SSID (defaults to the profile's CAMPUS_SSID)
wifi status           - connection state
campus status         - campus authentication state
campus login          - trigger authentication manually
campus logout         - log out
campus unblock        - clear a latched hard block, re-detect the portal
```

> The no-argument `wifi connect` uses the local WPA/WPA2 credentials from
> `wifi_secrets.h` when `ENABLE_WIFI_CREDENTIALS=1` (`WiFi.begin(ssid,
> password)`); `wifi connect <ssid>` explicitly joins an OPEN SSID
> (`WiFi.begin(ssid)`), matching the open access SSID model used by srun-style
> campus networks. Passwords never appear in serial logs.

---

## 5. Differences from the PlatformIO build

| Aspect             | PlatformIO (`agent-platformio/`)      | Arduino IDE (`arduino-ide/`)                    |
|--------------------|---------------------------------------|-------------------------------------------------|
| Entry point        | `src/main.cpp`                        | `Remote_AC_Controller.ino`                      |
| Switch injection   | `build_flags -D` in `platformio.ini`  | `*.ino.globals.h` (core force-includes it)      |
| Dependencies       | vendored under `lib/`, nothing to install | Library Manager + manual copy of RemoteACCore/srun-c |
| Multiple profiles  | `-e` environments, whole matrix in one command | edit `globals.h` and rebuild manually    |
| Build tool         | PlatformIO CLI / VS Code              | Arduino IDE / arduino-cli                       |

Both builds share the **same business logic** (`shared/RemoteACCore/`) and behave
identically.

---

## 6. Troubleshooting

### `RemoteACApp.h: No such file or directory`
- RemoteACCore is not in the Arduino libraries folder, or the IDE was not
  restarted after copying it.

### `srun.h: No such file or directory`
- You set `ENABLE_CAMPUS_AUTH=1` without installing srun-c. Install it, or set
  the switch back to `0`.

### `ArduinoJson.h` / `PubSubClient.h` not found
- These correspond to `ENABLE_CAMPUS_AUTH=1` and `ENABLE_CLOUD=1` respectively.
  Install the matching library from the table in §1.2.

### `ENABLE_CAMPUS_AUTH=1 but no campus profile selected`
- Add `#define CAMPUS_PROFILE_HEADER "profiles/<yours>.h"` to `globals.h`, and
  make sure that file exists under `RemoteACCore/src/config/profiles/`.

### Edits to `globals.h` have no effect
1. Verify the filename is **exactly** `Remote_AC_Controller.ino.globals.h`
   (sketch name + `.globals.h`, in the same folder as the `.ino`).
2. Verify the ESP8266 core is ≥ 2.5 (Global Build Options was introduced there).
3. Enable verbose compilation output and check that `mkbuildoptglobals.py` and
   your globals path appear in the log.
4. Force a full rebuild — the Arduino IDE build cache occasionally needs clearing.

### Cloud features do not work
- You need both `ENABLE_CLOUD=1` and `ENABLE_CLOUD_CREDENTIALS=1`, plus an
  existing `cloud_secrets.h`.
- The serial log should show `CLOUD_MQTT_INIT_OK`.

### Campus auth latches into `WIFI_BLOCKED` and stops retrying
- This is the intended behaviour of the **hard-failure latch** (bad credentials /
  wrong domain / TLS pin mismatch), which prevents repeatedly locking out your
  account. Clear it with `campus unblock` (or `campus login`, or a power cycle).
