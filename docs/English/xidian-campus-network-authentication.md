[简体中文](../中文/西电校园网自动认证.md) | **English**

# Xidian Campus Network Automatic Authentication

> **ESP8266 automatic Xidian University campus network authentication on boot** — After joining the campus open SSID, the device automatically completes Wi-Fi association, DHCP address acquisition, captive portal detection, Srun authentication, and Internet connectivity verification.

---

## Overview

This feature lets the ESP8266 NodeMCU join the Xidian University campus network (Srun 4000 authentication system) automatically after power-on, with no manual browser-based portal login. Once associated with the campus open SSID, the device runs the full authentication flow and only then proceeds to the MQTT cloud connection.

**The feature is disabled by default.** In the configuration committed to this repository, `ENABLE_CAMPUS_AUTH`, `ENABLE_AUTO_CAMPUS_AUTH` and `ENABLE_CONTROLLED_LIVE_AUTH` are all `0`, so a fresh clone compiles cleanly and never sends a request to any portal.

## How It Works

```
ESP8266 boot
  → Initialize DHT11, IR module, serial CLI
  → If ENABLE_WIFI=1: start Wi-Fi, associate with the campus SSID
  → Obtain DHCP address
  → If ENABLE_AUTO_CAMPUS_AUTH=1: run captive portal detection
  → If a portal is detected: verify the TLS fingerprint → run Srun authentication
  → Verify Internet connectivity over 3 consecutive rounds (3/3 required for ONLINE)
  → If ENABLE_CLOUD=1: start MQTT and telemetry
  → Continuously monitor Wi-Fi, Internet and MQTT state
```

## Supported Build Macros

| Macro | Default | Description |
|-------|---------|-------------|
| `ENABLE_WIFI` | 1 | Controls Wi-Fi hardware and connection |
| `ENABLE_CAMPUS_AUTH` | 0 | Compiles captive portal detection and Srun authentication |
| `ENABLE_AUTO_CAMPUS_AUTH` | 0 | Whether portal detection and authentication run automatically on boot |
| `ENABLE_CONTROLLED_LIVE_AUTH` | 0 | Whether the real credentials in `campus_secrets.h` are compiled into the firmware |
| `ENABLE_CLOUD` | 0 | Controls MQTT and cloud connectivity |
| `CAMPUS_PROFILE_HEADER` | undefined | Path to the campus parameter profile header; **required** when `ENABLE_CAMPUS_AUTH=1` |

The complete rule set for these switches lives in `firmware/shared/RemoteACCore/src/config/feature_gates.h` (single source of truth). If `ENABLE_CAMPUS_AUTH=1` but no profile is selected, the build stops with an `#error` — the firmware never silently targets an unspecified portal.

## Three Layers of Configuration

Configuration is deliberately split into three layers with distinct responsibilities and confidentiality levels:

| Layer | File | Committed? | Contents |
|-------|------|------------|----------|
| 1. Feature switches | `Remote_AC_Controller.ino.globals.h` (Arduino IDE)<br>`-D` build flags (PlatformIO) | No (git-ignored) | Which features are enabled, which profile is selected |
| 2. Public campus parameters | `config/profiles/xidian.h` | No (only `*.example.h` is committed) | SSID, portal host, ac_id, TLS fingerprint |
| 3. Account credentials | `config/campus_secrets.h` | No (git-ignored) | Student ID, password |

Layer 2 contains **public, non-secret** parameters only; layer 3 holds the credentials. The separation is what allows layer 2 to be published with the repository as `*.example.h` while layer 3 never leaves your disk.

## Configuration Steps

### 1. Copy the Profile

```bash
cd firmware/shared/RemoteACCore/src/config/profiles
cp xidian.example.h xidian.h        # xidian.h is git-ignored
```

The parameters in `xidian.example.h` are all public information and can be used as-is; no edits are required.

### 2. Enable Campus Authentication

**Arduino IDE** (official Global Build Options workflow):

```bash
cd firmware/arduino-ide/Remote_AC_Controller
cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

Edit `Remote_AC_Controller.ino.globals.h`:

```cpp
#define ENABLE_WIFI                 1
#define ENABLE_CAMPUS_AUTH          1
#define ENABLE_AUTO_CAMPUS_AUTH     1
#define CAMPUS_PROFILE_HEADER       "profiles/xidian.h"
```

The ESP8266 core's `mkbuildoptglobals.py` prebuild step force-includes this file into **every** compilation unit. You never `#include` it yourself, and you never edit `sketch.yaml`. See the [Arduino IDE Guide](./arduino-ide-guide.md) for the full workflow.

**PlatformIO**: select the profile through `tools/dev.ps1`; do not invoke `pio` directly.

```powershell
./tools/dev.ps1 build -Profile local-campus-example
```

This profile only verifies that the public campus authentication code compiles. It expands to `-DENABLE_CAMPUS_AUTH=1 -DENABLE_AUTO_CAMPUS_AUTH=0 -DENABLE_CONTROLLED_LIVE_AUTH=0 -DCAMPUS_PROFILE_HEADER=\"profiles/xidian.example.h\"`: it reads no real campus credentials, never logs in automatically, and cannot be used as a flash configuration for real campus authentication. For real authentication use the Arduino IDE local globals configuration below. Note that the double quotes in a string-valued `-D` macro **must be escaped**; otherwise PlatformIO strips them and the build fails with `#include expects "FILENAME" or <FILENAME>`.

### 3. Xidian Campus Network Parameters (Public, Non-Secret)

The table below is taken from `config/profiles/xidian.example.h`:

| Parameter | Macro | Value | Notes |
|-----------|-------|-------|-------|
| Wi-Fi SSID | `CAMPUS_SSID` | `stu-xdwlan` | Open campus SSID, no WPA pre-shared key |
| Portal host | `CAMPUS_PORTAL_HOST` | `w.xidian.edu.cn` | base_url is exactly `https://w.xidian.edu.cn`, no path suffix |
| ac_id | `CAMPUS_AC_ID` | `8` | Access-controller ID |
| Domain suffix | `CAMPUS_DOMAIN` | `""` (empty) | Do **not** append `@lt`/`@yd`/`@dx`; the srun `info` field is built with an empty domain |
| Auth algorithm | — | Srun 4000 | Challenge-response with `srun_bx1` encoding |

Srun endpoints (identical across all srun campus networks):

```
challenge  GET   https://w.xidian.edu.cn/cgi-bin/get_challenge
login      POST  https://w.xidian.edu.cn/cgi-bin/srun_portal   (action=login)
logout     POST  https://w.xidian.edu.cn/cgi-bin/srun_portal   (action=logout)
```

`/index_8.html` is used **only** for read-only portal probing (`INSECURE_PROBE_ONLY`); credentials are never sent to that path.

### 4. TLS Leaf Certificate Pinning

The ESP8266 has roughly 80 KB of usable RAM, which is not enough for full CA chain validation, so BearSSL uses **leaf certificate fingerprint pinning** (`setFingerprint`). The fingerprint, issuer and validity window are public information and ship with the profile:

| Field | Value |
|-------|-------|
| SHA-1 fingerprint | `F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9` |
| Not before | 2025-10-16 |
| **Not after** | **2026-11-17** |
| Issuer | GlobalSign RSA OV SSL CA 2018 |
| Subject | `CN=*.xidian.edu.cn, O=Xidian University` |

**Fail-closed semantics (cannot be disabled):**

- Fingerprint mismatch → print `TLS_PIN_MISMATCH`, abort the handshake immediately, **credentials are never transmitted**;
- No fingerprint compiled in → authentication is refused all the same (the fail-closed default in `config/campus_tls_pin.h`);
- **Never falls back to `setInsecure()`.**

The pin expires with the certificate on 2026-11-17. After that date, re-extract it using the `openssl` procedure documented in `campus_tls_pin.h` and update the `CAMPUS_CERT_*` macros **in the profile you use** (do not write them back into `campus_tls_pin.h`). See [TLS Certificate Pinning and Renewal](../../firmware/agent-platformio/docs/03_协议与接口/TLS证书固定与更新.md) for the full procedure.

### 5. Configure Campus Credentials

Credentials must live in the **git-ignored** `campus_secrets.h`:

```bash
cd firmware/shared/RemoteACCore/src/config
cp campus_secrets.example.h campus_secrets.h
# Edit campus_secrets.h with a student ID and password you are authorised to use
```

```cpp
// campus_secrets.h (git-ignored, never committed)
#define CAMPUS_USERNAME "your_student_id"
#define CAMPUS_PASSWORD "your_password"
```

**Credentials are compiled in only when you additionally set `ENABLE_CONTROLLED_LIVE_AUTH=1` explicitly.** In a default build, the contents of `campus_secrets.h` never reach the firmware binary even if the file exists — this is the second gate against accidentally publishing a credential-bearing firmware image.

```cpp
// Add this line to globals.h only when you intend to perform real authentication
#define ENABLE_CONTROLLED_LIVE_AUTH 1
```

When it is off, the authentication path prints `CAMPUS_CREDS_READY=DISABLED REAL_AUTH_REQUEST_ALLOWED=BLOCKED_BY_BUILD_POLICY` and stops without issuing any login request.

## Serial Output Status

During authentication the serial monitor (115200 baud) emits the following markers:

```
WIFI_CONNECT source=CAMPUS_PROFILE_OPEN ssid=stu-xdwlan security=OPEN
WIFI_ASSOC_PASS
LOCAL_IP=10.x.x.x
GATEWAY=10.x.x.1
DNS_IP=10.x.x.1
PORTAL_DETECT_START
PORTAL_PROBE_TARGET label=baidu host=www.baidu.com
  HTTP_CODE=302
  LOCATION=https://w.xidian.edu.cn/index_8.html
PORTAL_DETECT_RESULT captive=YES
CAPTIVE_PORTAL_DETECTED=YES
PORTAL_HOST=w.xidian.edu.cn
AC_ID=8
CAMPUS_AUTH_START
CAMPUS_AUTH_PASS
INTERNET_VERIFY round=1 ok=YES cumulative_ok=1
INTERNET_VERIFY round=2 ok=YES cumulative_ok=2
INTERNET_VERIFY round=3 ok=YES cumulative_ok=3
INTERNET_ONLINE
```

Portal detection tries three targets in order: `baidu` (`http://www.baidu.com/`), `miui_204` (`http://connect.rom.miui.com/generate_204`), and `msft_ncsi` (`http://www.msftncsi.com/ncsi.txt`). Internet verification requires **three consecutive successful rounds** before `INTERNET_ONLINE` is declared.

Common failure output:

```
TLS_PIN_MISMATCH                       # fingerprint mismatch, credentials not sent, enters BLOCKED
CAMPUS_AUTH_FAIL reason=BAD_CREDENTIALS
AUTH_SERVER_ERROR=<error field returned by the portal>
AUTH_BACKOFF ms=<backoff milliseconds> fail_streak=<consecutive failures>
CAMPUS_CREDS_READY=NO
AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS   # no credentials, or ENABLE_CONTROLLED_LIVE_AUTH is off
AUTH_RESPONSE_OK_BUT_INTERNET_BLOCKED  # portal returned OK but connectivity failed 3/3
CAPTIVE_PORTAL_DETECTED=NO
```

**A rejected password (`BAD_CREDENTIALS`), a wrong domain (`WRONG_DOMAIN`) and a fingerprint mismatch (`TLS_PIN_MISMATCH`) are hard failures.** They latch the device into `WIFI_BLOCKED` and are never retried automatically — automatically replaying a rejected password is exactly how a campus account gets locked out.

There are three ways to clear the latch:

| Method | Behaviour |
|--------|-----------|
| `campus unblock` | Clears the latch and **re-enters the pipeline at portal detection**; usable without credentials compiled in |
| `campus login` | Clears the latch and **immediately attempts one login**; requires credentials (`ENABLE_CONTROLLED_LIVE_AUTH=1`) |
| Power cycle | Full state reset |

The complete set of campus subcommands in the serial CLI is `status | login | logout | unblock`.

## Security Notes

- **Credentials exist only in local git-ignored files** and additionally require the `ENABLE_CONTROLLED_LIVE_AUTH=1` switch to be compiled in;
- TLS leaf certificate pinning is **fail-closed**; verification must never be disabled and must never fall back to `setInsecure()`;
- Authentication rate limiting (hourly quota) and exponential backoff are implemented; hard failures latch to prevent account lockout;
- Full credentials are never printed in logs; the query string of a `LOCATION` header is stripped to avoid leaking tokens;
- Portal responses are never printed in full;
- The committed `xidian.example.h` contains **no** account, password, cookie, token or private key.

## Limitations

- This profile is **specific to the Xidian campus network (Srun 4000)**;
- The TLS fingerprint expires on **2026-11-17**, after which it must be re-extracted or authentication will fail closed;
- Other institutions' Srun deployments require profile adjustments — see the [Srun Campus Network Porting Guide](./srun-campus-network-porting-guide.md);
- Automatic authentication is off by default and requires explicit configuration;
- You must use a campus account **you are authorised to use** and comply with your institution's network usage policies.

## Related Documentation

- [Arduino IDE Guide](./arduino-ide-guide.md) — full Global Build Options workflow
- [Srun Campus Network Porting Guide](./srun-campus-network-porting-guide.md) — adapting to other institutions
- [Architecture Overview](./architecture.md) — complete system architecture
- [Security Model](./security-model.md) — security boundaries and threat model
- [Troubleshooting](./troubleshooting.md) — common issues
