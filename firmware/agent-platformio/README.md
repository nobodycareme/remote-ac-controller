# Remote AC Controller — PlatformIO Build

PlatformIO-based firmware for the **Remote AC Controller** (ESP8266 NodeMCU v2).

## Project Structure

```
agent-platformio/
├── platformio.ini          # PlatformIO configuration
├── src/
│   ├── main.cpp            # Thin entry point (→ appSetup/appLoop)
│   └── private_ir_codes/   # Private IR code data (PlatformIO only)
├── include/
│   └── cloud_secrets.example.h  # MQTT credential template
├── lib/                    # PlatformIO-managed libraries
├── test/                   # Unit tests
├── tools/
│   └── dev.ps1             # Main development entry point
└── docs/                   # Project documentation
```

The shared business logic lives in `../shared/RemoteACCore/` and is compiled as a local library.

## Quick Start

### Prerequisites

- [PlatformIO IDE](https://platformio.org/install) (VS Code extension or CLI)
- ESP8266 board support (auto-installed by PlatformIO)

### Building

DO NOT run `pio` directly. Use the development script:

```powershell
# Public build (safe defaults, no credentials)
.\tools\dev.ps1

# With cloud features (requires cloud_secrets.h)
.\tools\dev.ps1 -WithCloud
```

### Configuration

1. **Cloud credentials** (for MQTT connectivity):
   ```bash
   cp include/cloud_secrets.example.h include/cloud_secrets.h
   # Edit include/cloud_secrets.h with your MQTT broker details
   ```

2. **Campus network** (for srun authentication):
   Edit `shared/RemoteACCore/src/config/campus_credentials.h`

3. **Private IR codes**:
   IR mutating commands require `src/private_ir_codes/`. Generated codes go in `src/private_ir_codes/generated/`.

### Building Profiles

| Profile    | ENABLE_CLOUD | ENABLE_IR_MUTATING | Use Case              |
|-----------|-------------|-------------------|-----------------------|
| Public    | 1           | 0                 | Safe default build    |
| Private   | 1           | 1                 | IR lab / full feature |

Set via `dev.ps1 -Profile Public|Private`.

### Upload

```powershell
.\tools\dev.ps1 -Upload
```

## Testing

```bash
pio test -e nodemcuv2
```

## Dependencies

Libraries in `lib/` are vendored. PlatformIO will auto-download missing dependencies.

## Version

See `VERSION` file. Current: v0.4.0-cloud-foundation.
