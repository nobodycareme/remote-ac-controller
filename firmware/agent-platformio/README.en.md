[简体中文](./README.md) | **English**

# Remote AC Controller — PlatformIO Build

PlatformIO-based firmware for the **Remote AC Controller** (ESP8266 NodeMCU v2).

---

## Project Structure

```
agent-platformio/
├── platformio.ini          # PlatformIO configuration
├── src/
│   ├── main.cpp            # Thin entry point (→ appSetup/appLoop)
│   └── private_ir_codes/   # Private IR code data (PlatformIO only)
├── include/                 # PlatformIO-only public headers
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
.\tools\dev.ps1 build -Profile public

# Home/lab WPA or WPA2 Wi-Fi (requires wifi_secrets.h)
.\tools\dev.ps1 build -Profile local-wifi

# Xidian campus network (example profile; requires campus_secrets.h and
# profiles/xidian.h)
.\tools\dev.ps1 build -Profile local-campus-example
```

Full validation: `.\tools\dev.ps1 test -Profile public`; upload:
`.\tools\dev.ps1 upload -Profile public`.

### Configuration (read before first setup)

See the [first-time setup guide](../../docs/English/first-time-setup.md).
Home Wi-Fi passwords and Xidian campus account passwords are two independent
sets of credentials and cannot be interchanged.

1. **Home Wi-Fi credentials** (WPA/WPA2, required by the `local-wifi` profile):
   ```bash
   cd shared/RemoteACCore/src/config
   cp wifi_secrets.example.h wifi_secrets.h
   # Edit wifi_secrets.h:
   #   #define LOCAL_WIFI_SSID     "your_wifi_name"
   #   #define LOCAL_WIFI_PASSWORD "your_wifi_password"
   ```
   The real `wifi_secrets.h` is git-ignored; only the `.example.h` template is
   committed. Passwords never appear in serial logs.

2. **Xidian campus credentials** (srun portal auth, required by the
   `local-campus-example` profile):
   ```bash
   cd shared/RemoteACCore/src/config
   cp profiles/xidian.example.h profiles/xidian.h
   cp campus_secrets.example.h campus_secrets.h
   # Edit campus_secrets.h:
   #   #define CAMPUS_USERNAME "your_student_id"
   #   #define CAMPUS_PASSWORD "your_campus_password"
   ```
   Xidian `stu-xdwlan` is an open SSID (no WPA password at the Wi-Fi layer);
   the campus account/password belongs to the portal authentication. All real
   credential files are git-ignored.

3. **Cloud credentials** (for MQTT connectivity, optional):
   ```bash
   cd ../shared/RemoteACCore/src/config
   cp cloud_secrets.example.h cloud_secrets.h
   # Edit canonical cloud_secrets.h; PlatformIO and Arduino IDE share it
   ```

### Building Profiles

| Profile | ENABLE_CLOUD | ENABLE_WIFI_CREDENTIALS | ENABLE_CAMPUS_AUTH | Use Case |
|---|---|---|---|---|
| `public` | 1 | 0 | 0 | Safe default build (open SSID, no local credentials) |
| `local-wifi` | 0 | 1 | 0 | Home/lab WPA/WPA2 (requires wifi_secrets.h) |
| `local-wifi-cloud` | 1 | 1 | 0 | Home Wi-Fi + cloud (requires wifi_secrets.h + cloud_secrets.h) |
| `local-campus-example` | 0 | 0 | 1 | Xidian campus example (requires profiles/xidian.h + campus_secrets.h) |
| `public-cloud-example` | 1 | 0 | 0 | Explicit name for the public cloud-transport matrix entry |

All public profiles keep `ENABLE_CONTROLLED_LIVE_AUTH=0` and
`ENABLE_IR_MUTATING_COMMANDS=0`. Real credentials live only in git-ignored
files and never in this repository. The only authoritative Cloud path is
`shared/RemoteACCore/src/config/cloud_secrets.h`; `dev.ps1` fails when either
deprecated Cloud secret path still exists.

> **v1.2.4: copying the template verbatim no longer builds.** Before a build,
> `local-wifi` / `local-wifi-cloud` run content validation via
> `tools/validate-cloud-secrets.py` (Wi-Fi SSID/password rules; cloud host,
> port, device ID, credentials and TLS material). Template placeholders such
> as `your_wifi_name`, `your-broker.example.com`, `change-me` or an empty
> CA/fingerprint are rejected with a non-sensitive error code. `wifi connect`
> (no arguments) uses the local WPA configuration; `wifi connect <ssid>`
> temporarily switches to the given open SSID, never uses the local password,
> and never accepts a Wi-Fi password on the command line.
>
> **v1.2.5: SSID and TLS rules.** An SSID may contain ordinary internal
> spaces (`Home WiFi`, `Lab Network 2`); its length is measured in UTF-8 bytes
> with a 32-byte limit, it must not be all whitespace or contain control
> characters, and it is never trimmed or truncated. For TLS the CA certificate
> takes priority: when both a valid CA and a valid fingerprint are present,
> only the CA is used; a SHA-1 server-certificate fingerprint (40 hex
> characters, colons optional) is used only when no valid CA is present and
> must be updated when the certificate rotates; if neither is present the
> build/init stops (`TLS_MATERIAL_MISSING`); disabling TLS validation is not
> supported.

### Upload

```powershell
.\tools\dev.ps1 upload -Profile public
```

## Testing

```powershell
.\tools\dev.ps1 test -Profile public
```

Pure-logic parts of the firmware core (feature-gate dependencies, the Wi-Fi
connect decision, CampusAuthPolicy) additionally have host tests in
`test/host/`, compiled and run by the CI `firmware-host-tests` job.

## Dependencies

Libraries in `lib/` are vendored. PlatformIO will auto-download missing dependencies.

## Version

Software version: see `VERSION` (currently v1.2.2). PCB revision is Rev 1.0.1,
independent from the software version.
