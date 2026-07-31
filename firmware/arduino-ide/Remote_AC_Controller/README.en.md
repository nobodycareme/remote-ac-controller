[简体中文](./README.md) | **English**

# Remote AC Controller — Arduino IDE Build

Arduino IDE sketch for the **Remote AC Controller** (ESP8266 NodeMCU v2).

---

## Prerequisites

### 1. ESP8266 Board Support

1. Open Arduino IDE → File → Preferences
2. Add the ESP8266 board URL: `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
3. Tools → Board → Boards Manager → search "esp8266" → install

### 2. Required Libraries (Library Manager)

Install all of these via Sketch → Include Library → Manage Libraries:

| Library               | Author              | Note                          |
|-----------------------|---------------------|-------------------------------|
| DHT sensor library    | Adafruit            | For DHT11 temperature sensor  |
| Adafruit Unified Sensor | Adafruit         | Dependency of DHT library     |
| ArduinoJson           | Benoit Blanchon     | JSON parsing/serialization    |
| PubSubClient          | Nick O'Leary        | MQTT client                   |
| Crypto                | Rhys Weatherley     | SHA256, Base64, BLAKE2s       |

### 3. RemoteACCore Shared Library

Copy the shared core library to your Arduino libraries folder:

```bash
# Windows (PowerShell)
Copy-Item -Recurse ..\..\shared\RemoteACCore "$env:USERPROFILE\Documents\Arduino\libraries\RemoteACCore"

# macOS / Linux
cp -r ../../shared/RemoteACCore ~/Arduino/libraries/RemoteACCore
```

### 4. srun-c Library (Campus Network Auth)

If you need campus network authentication, copy the srun-c library:

```bash
# From PlatformIO lib/
cp -r ../agent-platformio/lib/srun-c ~/Arduino/libraries/srun-c
```

### 5. SoftwareSerial

The IR module uses SoftwareSerial. This is included with ESP8266 core — no separate install needed.

## Configuration

1. **Copy and edit the value config file:**
   ```bash
   cp config.example.h config.h
   ```

2. **Edit `config.h`** with your runtime values (values/credential placeholders only):
   - Set `CAMPUS_SSID` to your Wi-Fi network name
   - For campus auth, put your credentials in `config/campus_secrets.h`
     (copy `config/campus_secrets.example.h` -> `config/campus_secrets.h`)
   - Set MQTT broker details if cloud is enabled

3. **(Optional) Copy and edit the global feature-switch header:**
   ```bash
   cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
   ```
   Set `ENABLE_CAMPUS_AUTH` / `ENABLE_CLOUD` / `ENABLE_IR_MUTATING_COMMANDS` etc.
   there, and point `sketch.yaml`'s `compile.extra_flags` at your `globals.h`.
   **Skipping this step still compiles** — the committed `.example.h` ships safe
   public defaults and is auto-injected via the ESP8266 core `-include` mechanism.

4. **Both `config.h` and `globals.h` are git-ignored** — never commit real
   credentials or turn on live authentication.

## Building & Uploading

1. Open `Remote_AC_Controller.ino` in Arduino IDE
2. Select board: Tools → Board → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. Select port: Tools → Port → (your ESP8266 COM port)
4. Click Verify (checkmark) to compile
5. Click Upload (arrow) to flash

## Serial Monitor

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

## Build Profiles

| Feature                | Flag                          | Default (globals.example.h) |
|------------------------|-------------------------------|------------------------------|
| Wi-Fi                  | ENABLE_WIFI                   | ON                           |
| Cloud (MQTT)           | ENABLE_CLOUD                  | OFF                          |
| Cloud credentials      | ENABLE_CLOUD_CREDENTIALS      | OFF                          |
| Auto campus auth       | ENABLE_AUTO_CAMPUS_AUTH       | OFF                          |
| Campus auth            | ENABLE_CAMPUS_AUTH            | OFF                          |
| Controlled live auth   | ENABLE_CONTROLLED_LIVE_AUTH   | OFF                          |
| IR mutating commands   | ENABLE_IR_MUTATING_COMMANDS   | OFF                          |

The compile-time feature switches live in `Remote_AC_Controller.ino.globals.h`
(injected by `sketch.yaml`'s `-include`); runtime values (SSID, broker, TLS) live
in `config.h`. The two are deliberately separate.

## Differences from PlatformIO Build

| Feature          | PlatformIO (`agent-platformio/`) | Arduino IDE (`arduino-ide/`)  |
|------------------|----------------------------------|-------------------------------|
| Entry point      | `src/main.cpp`                   | `Remote_AC_Controller.ino`    |
| Config system    | `include/cloud_secrets.h` + env  | `config.h`                    |
| Private IR codes | Supported (`ENABLE_IR_MUTATING`) | Requires manual setup         |
| Build tool       | PlatformIO CLI / VS Code         | Arduino IDE                   |

Both builds share the **same business logic** via `shared/RemoteACCore/`.

## Troubleshooting

### Compilation error: "RemoteACApp.h not found"
- Ensure RemoteACCore library is in the Arduino libraries folder
- Restart Arduino IDE after copying the library

### Compilation error: "srun.h not found"
- Copy srun-c library or set `ENABLE_CAMPUS_AUTH` to `0`

### Cloud features don't work
- Verify `config.h` has correct MQTT broker details
- Ensure `ENABLE_CLOUD` is set to `1`
- Check serial monitor for `CLOUD_MQTT_INIT_OK`