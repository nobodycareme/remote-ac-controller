[简体中文](./README.md) | **English**

# RemoteACCore — Shared Core Library

The core business logic for the **Remote AC Controller** firmware, shared between **PlatformIO** and **Arduino IDE** builds.

---

## Architecture

This library contains all business logic extracted from the legacy `firmware/src/` directory. It is the **single source of truth** for:

| Module       | Description                                     |
|-------------|-------------------------------------------------|
| `cloud/`    | MQTT client, command dispatch, telemetry, connectivity state machine |
| `network/`  | Wi-Fi manager, campus authentication (srun), portal detection |
| `sensors/`  | DHT11 temperature/humidity sensor driver        |
| `diagnostics/` | On-device diagnostic console                 |
| `config/`   | Hardware pin definitions, campus config         |

Plus standalone modules: IR module (`ir_module.cpp`), serial CLI (`serial_cli.cpp`).

## Entry Points

The library exposes two C-linkage functions via `RemoteACApp.h`:

```cpp
void appSetup(void);  // Call once in setup() — initialises all modules
void appLoop(void);   // Call repeatedly in loop() — main control loop
```

Both PlatformIO (`agent-platformio/`) and Arduino IDE (`arduino-ide/`) entry points are **thin wrappers** that call only these two functions.

## Build Integration

### PlatformIO

Compiled as a local library via `lib_extra_dirs` in `platformio.ini`:

```ini
lib_extra_dirs = ../shared
```

### Arduino IDE

Install as a library by copying `shared/RemoteACCore/` to the Arduino `libraries/` folder, or use Library Manager once the library is published.

## Privacy & Security

This library **does not** contain:
- Real cloud credentials (`cloud_secrets.h`)
- Real private IR codes (`ir_code_registry.h` private implementation)
- Production Wi-Fi or MQTT credentials
- Hardware-tied secrets

All credential-sensitive configuration belongs to the build-specific project
layer: PlatformIO uses `agent-platformio/include/` (`cloud_secrets.h` etc.);
Arduino IDE uses the git-ignored secret headers under this library's `src/` and
`src/config/`. Compile-time feature switches always come from
`config/feature_gates.h` and its upstream macros, never from a runtime config
file.

## Dependencies

Arduino libraries (install via PlatformIO Library Manager or Arduino Library
Manager). **Not all are unconditionally required** — it depends on the feature
switches you enable:

| Library                           | Required when                          |
|-----------------------------------|----------------------------------------|
| **DHT sensor library** (Adafruit) | Always (`sensors/dht11_sensor.h`)      |
| **Adafruit Unified Sensor**       | Always (DHT dependency)                |
| **ArduinoJson** (Benoit Blanchon) | `ENABLE_CAMPUS_AUTH=1`                 |
| **PubSubClient** (Nick O'Leary)   | `ENABLE_CLOUD=1`                       |
| **srun-c** (bundled in this repo) | `ENABLE_CAMPUS_AUTH=1`                 |

> A third-party Crypto library is **not** required. The `<Crypto.h>` /
> `<base64.h>` includes in `serial_cli.cpp` are referenced only under
> `ENABLE_IR_LAB_LEARNING_COMMANDS=1`, and both headers ship with the ESP8266
> core. The same applies to `<SoftwareSerial.h>`.

## Version

1.0.0 — Extracted from firmware v0.4.0-cloud-foundation.