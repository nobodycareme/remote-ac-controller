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

1. **Copy and edit config file:**
   ```bash
   cp config.example.h config.h
   ```

2. **Edit `config.h`** with your settings:
   - Set `CAMPUS_SSID` to your Wi-Fi network name
   - Set `ENABLE_CAMPUS_AUTH` to `1` if on campus network
   - Set campus login credentials if required
   - Set `ENABLE_CLOUD` to `1` for MQTT cloud connectivity
   - Set MQTT broker details if cloud is enabled

3. **`config.h` is git-ignored** — never commit real credentials.

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

| Feature                | Flag                          | Default |
|------------------------|-------------------------------|---------|
| Wi-Fi                  | ENABLE_WIFI                   | ON      |
| Cloud (MQTT)           | ENABLE_CLOUD                  | OFF     |
| Cloud credentials      | ENABLE_CLOUD_CREDENTIALS      | OFF     |
| Campus auth            | ENABLE_CAMPUS_AUTH            | OFF     |
| IR mutating commands   | ENABLE_IR_MUTATING_COMMANDS   | OFF     |

Set these in `config.h` to match your use case.

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