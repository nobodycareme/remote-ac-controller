# Arduino IDE Guide

> Complete guide for compiling, uploading, and debugging the Remote AC Controller firmware using Arduino IDE.

---

## Environment Setup

### 1. Install Arduino IDE

Download and install Arduino IDE (2.x recommended) from [arduino.cc](https://www.arduino.cc/en/software).

### 2. Install ESP8266 Board Support

1. Open Arduino IDE → File → Preferences
2. Add the following URL to "Additional Boards Manager URLs":
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
3. Tools → Board → Boards Manager → search "esp8266" → install

### 3. Install Required Libraries

Via Sketch → Include Library → Manage Libraries:

| Library | Author | Version |
|---------|--------|---------|
| DHT sensor library | Adafruit | Latest |
| Adafruit Unified Sensor | Adafruit | Latest |
| ArduinoJson | Benoit Blanchon | 6.x |
| PubSubClient | Nick O'Leary | Latest |
| Crypto | Rhys Weatherley | Latest |

### 4. Install RemoteACCore Shared Library

```bash
# Windows (PowerShell)
Copy-Item -Recurse ..\..\shared\RemoteACCore "$env:USERPROFILE\Documents\Arduino\libraries\RemoteACCore"

# macOS / Linux
cp -r ../../shared/RemoteACCore ~/Arduino/libraries/RemoteACCore
```

### 5. Install srun-c Library (Optional)

For campus network authentication:

```bash
cp -r ../agent-platformio/lib/srun-c ~/Arduino/libraries/srun-c
```

## Configuration

### Copy Configuration File

```bash
cp config.example.h config.h
```

### Edit config.h

Set the following macros according to your use case:

| Macro | Default | Description |
|-------|---------|-------------|
| `ENABLE_WIFI` | 1 | Wi-Fi functionality |
| `ENABLE_CAMPUS_AUTH` | 0 | Campus network authentication |
| `ENABLE_CLOUD` | 0 | MQTT cloud connectivity |
| `ENABLE_IR_MUTATING_COMMANDS` | 0 | IR transmit commands |

**`config.h` is gitignored** and will not be committed.

## Build & Upload

1. Open `Remote_AC_Controller.ino`
2. Select board: Tools → Board → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. Select port: Tools → Port → (your ESP8266 COM port)
4. Click Verify (✓) to compile
5. Click Upload (→) to flash

## Serial Debugging

- Tools → Serial Monitor
- Baud rate: **115200**
- Line ending: Newline

Expected startup output:
```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
```

## Troubleshooting

### Compilation error: "RemoteACApp.h not found"
- Ensure RemoteACCore library is in the Arduino libraries folder
- Restart Arduino IDE after copying the library

### Compilation error: "srun.h not found"
- Copy srun-c library, or set `ENABLE_CAMPUS_AUTH` to `0`

### Upload fails
- Check that the correct port is selected
- Ensure the ESP8266 is connected via USB
- Some ESP8266 modules require holding FLASH + pressing RST to enter download mode

### No serial output
- Check baud rate is 115200
- Check CH9102 driver is installed
- Try a different USB cable or port

## Related Documentation

- [Xidian Campus Network Authentication](./xidian-campus-network-authentication.md)
- [Srun Campus Network Porting Guide](./srun-campus-network-porting-guide.md)