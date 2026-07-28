# Remote AC Controller

## v0.4.0-cloud-foundation

Single-environment NodeMCU ESP8266 firmware with runtime diagnostics, campus network auth, and cloud-ready foundation.

### Quick Start

```powershell
.\tools\dev.ps1 status                       # Show project/COM/security status
.\tools\dev.ps1 build [-Profile public]      # Incremental build (public)
.\tools\dev.ps1 build -Profile private       # Incremental build (private)
.\tools\dev.ps1 clean-build [-Profile public] # Clean + full rebuild
.\tools\dev.ps1 upload [-Profile private]    # Build + flash (dynamic COM detect)
.\tools\dev.ps1 monitor                      # Serial monitor @115200
.\tools\dev.ps1 verify                       # Run verification checks
.\tools\dev.ps1 help                         # This help
```

### Environment

| Item | Value |
|------|-------|
| Env | `[env:nodemcuv2]` |
| Platform | espressif8266@4.2.1 |
| Board | NodeMCU ESP8266 ESP-12E |
| Framework | Arduino |
| Stable Core | `<PioStableRoot>\Core` |
| Dev entry | `tools\dev.ps1` (ONLY supported entry) |

### Profiles

| Profile | ENABLE_CONTROLLED_LIVE_AUTH | ENABLE_IR_MUTATING_COMMANDS |
|---------|----------------------------|-----------------------------|
| `public` (default) | 0 — NO live auth, NO secrets.h | 0 — IR read-only |
| `private` | 1 — secrets.h required | 0 — IR read-only |

### Verified Status

| Feature | Status |
|---------|--------|
| DHT11 sensor (D1/GPIO5, Adafruit lib, >=2.5s interval) | Verified |
| Wi-Fi association (OPEN SSID) | Verified |
| DHCP | Verified |
| Captive portal detection (meta-refresh + HTTP redirect) | Verified |
| Campus network auth (Xidian Srun v2, TLS SHA-1 pin) | Verified (2026-07-18) |
| Campus auth non-standard success response (whitelist) | Verified |
| IR UART read-only probe (ZJ-IR-V2, GET_BAUD/GET_ADDR) | Verified |
| IR learning / emission | NOT authorized |
| MQTT cloud connection | In development (this version) |
| Hisense AC real response | NOT validated |

### Serial Commands

```
help          status        version       dht read      dht test
ir probe      ir info       ir learn N*   ir send N*    ir cancel*
wifi connect  wifi status   wifi scan     wifi disconnect
net check     campus status campus login* campus logout*
run_all_safe  dht_test      ir_uart_probe wifi_scan
wifi_assoc    dhcp_info     portal_probe  tls_pin_check
srun_vector   auth_dry_run  heap_status   reset_reason
```

`*` = blocked by build policy in public profile

### Build

All builds MUST use `tools\dev.ps1`:

```powershell
.\tools\dev.ps1 clean-build -Profile public
.\tools\dev.ps1 clean-build -Profile private
```

Build output goes to `<PioStableRoot>\build\Remote_AC_Controller\<profile>\`, never to the project `.pio` directory.

### Security

- **Public builds**: zero credentials in binary; live auth request paths unreachable
- **Private builds**: `include/secrets.h` required; never committed
- **IR policy**: all mutating commands blocked at CLI + service + driver layers
- **Secrets**: `include/secrets.h`, `include/cloud_secrets.h` git-ignored
- Full security gate report: `docs/reports/SECURITY_GATE_REPORT.md`

### Not Yet Completed

- IR learning and emission (policy blocked, not authorized)
- Hisense AC real response validation
- MQTT / cloud server / mobile web UI (in development — this version)

### History

- v0.3.x: multi-env prototyping, then single-env consolidation
- v0.3.4-v0.3.6: campus auth live validation, IR probe, security hardening
- v0.4.0: secure baseline, MQTT cloud foundation
