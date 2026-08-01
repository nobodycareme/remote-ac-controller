[简体中文](../中文/首次配置.md) | **English**

# First-time setup

This guide covers the three most common first-time paths: a home or lab WPA/WPA2 network, the Xidian Srun campus network, and a credentials-free offline build. **Every real secret** (Wi-Fi password, campus account) **lives in a local, git-ignored file**; only the `.example.h` template may be committed. Never paste credentials into `platformio.ini`, `build_flags`, serial logs, terminal history, or CI logs.

All compile-time feature switches live in [`firmware/shared/RemoteACCore/src/config/feature_gates.h`](../../firmware/shared/RemoteACCore/src/config/feature_gates.h). Every legal combination — and every illegal one — is enforced by a hard `#error` in that header.

---

## A. Home or lab WPA / WPA2 Wi-Fi

> Use case: your home or office Wi-Fi is WPA/WPA2 encrypted (≥ 8 character password), no captive portal.
> Compile flags: `ENABLE_WIFI=1 ENABLE_WIFI_CREDENTIALS=1 ENABLE_AUTO_WIFI_CONNECT=1 ENABLE_CLOUD=0`.

### A.1 Prepare the local credentials

Real credentials live in `wifi_secrets.h`. That file is git-ignored and must **never** be committed.

```powershell
cd firmware/shared/RemoteACCore/src/config
cp wifi_secrets.example.h wifi_secrets.h
```

Edit `wifi_secrets.h`:

```cpp
#define LOCAL_WIFI_SSID     "your_wifi_name"
#define LOCAL_WIFI_PASSWORD "your_wifi_password"
```

### A.2 Pick the PlatformIO profile

`dev.ps1` exposes two local-Wi-Fi profiles:

| Profile | Meaning | ENABLE_CLOUD |
|---|---|---|
| `local-wifi` | Home / lab Wi-Fi, no cloud | 0 |
| `local-wifi-cloud` | Home / lab Wi-Fi + cloud (MQTT / HTTPS) | 1 |

Build (and flash, the dev script auto-detects the CH9102 port):

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile local-wifi
./tools/dev.ps1 build -Profile local-wifi-cloud
```

### A.3 Arduino IDE workflow

Open `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino` in Arduino IDE and set, near the top of `globals.h` (or the sketch secrets block):

```cpp
#define ENABLE_WIFI              1
#define ENABLE_WIFI_CREDENTIALS  1   // enable local WPA credentials
#define ENABLE_AUTO_WIFI_CONNECT 1   // join the network at boot

// local Wi-Fi credentials (same file as the PlatformIO path)
#include "config/wifi_secrets.h"
```

> General Arduino IDE workflow: see [arduino-ide-guide](arduino-ide-guide.md).

### A.4 Serial commands at runtime

The firmware uses the compiled-in local credentials and auto-joins the home network at boot (because `WIFI_AUTOCONNECT_ON_BOOT` is true). To force a re-connect or switch to an open SSID from the serial monitor:

| Command | Behaviour |
|---|---|
| `wifi connect` | re-join the home network from `wifi_secrets.h` (WPA path, password never enters the serial stream) |
| `wifi connect stu-xdwlan` | connect to the Xidian open SSID (does **not** read `wifi_secrets.h`) |
| `wifi status` | print `NET_STATE` / `NET_SSID` / `LOCAL_IP` / MAC (masked) |
| `wifi scan` | list nearby APs (read-only) |
| `wifi disconnect` | drop the current association |

**The serial stream never contains** the password, its length, a password prefix, or any fragment that would help recover the secret. Only these lines are logged:

```
WIFI_CONNECT ssid=<ssid> security=WPA_OR_WPA2
WIFI_CONNECT ssid=<ssid> security=OPEN
```

### A.5 Compile-time safety rails (enforced in feature_gates.h)

- `ENABLE_WIFI_CREDENTIALS=1` requires `ENABLE_WIFI=1`, else `#error`.
- `ENABLE_AUTO_WIFI_CONNECT=1` requires `ENABLE_WIFI=1`, else `#error`.
- Campus auth (`ENABLE_CAMPUS_AUTH=1`) and local Wi-Fi credentials are **independent** paths.
- Public builds never include `wifi_secrets.h`; the file is `.gitignore`d.
- Never put the Wi-Fi password into:
  - `platformio.ini`;
  - `build_flags`;
  - shell history;
  - serial logs (enforced by the WiFiManager);
  - CI logs;
  - README example values (use `your_wifi_name` / `your_wifi_password` placeholders).

---

## B. Xidian Srun campus network

> Use case: Xidian campus Wi-Fi `stu-xdwlan` is an open SSID; login goes through the Srun captive portal with your student account.
> Compile flags: `ENABLE_WIFI=1 ENABLE_CAMPUS_AUTH=1 ENABLE_AUTO_CAMPUS_AUTH=1 ENABLE_CONTROLLED_LIVE_AUTH=1 ENABLE_AUTO_WIFI_CONNECT=1 ENABLE_CLOUD=0`.
> Xidian Srun is published as the example profile (`profiles/xidian.example.h`); other Srun deployments see [srun-campus-network-porting-guide](srun-campus-network-porting-guide.md).

### B.1 Prepare the profile and campus credentials

```powershell
cd firmware/shared/RemoteACCore/src/config
# 1. Copy the public example profile (keeps the STU-XDWLAN defaults; edit xidian.h to customise)
cp profiles/xidian.example.h profiles/xidian.h
# 2. Prepare the campus Portal credentials
cp campus_secrets.example.h campus_secrets.h
```

Edit `campus_secrets.h`:

```cpp
#define CAMPUS_USERNAME "your_student_id"
#define CAMPUS_PASSWORD "your_campus_password"
```

> Do **not** save these values anywhere else, in particular not in `platformio.ini` or `globals.h`.

### B.2 Pick the PlatformIO profile

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile local-campus-example
```

`local-campus-example` enables unattended campus auth (`ENABLE_AUTO_CAMPUS_AUTH=1`) and, by design, requires `campus_secrets.h` to contain real values when `ENABLE_CONTROLLED_LIVE_AUTH=1` — fill in B.1 first.

### B.3 Arduino IDE workflow

```cpp
#define ENABLE_WIFI                 1
#define ENABLE_CAMPUS_AUTH          1
#define ENABLE_AUTO_WIFI_CONNECT    1
#define ENABLE_AUTO_CAMPUS_AUTH     1
#define ENABLE_CONTROLLED_LIVE_AUTH 1
#define CAMPUS_PROFILE_HEADER       "profiles/xidian.h"
#include "config/campus_secrets.h"
```

### B.4 Safety rails (enforced in feature_gates.h)

- Never commit `campus_secrets.h` (already `.gitignore`d).
- Never put the campus password in `platformio.ini` or `globals.h`.
- Never call `setInsecure()` / disable TLS verification.
- A public profile may not compile real credentials: `ENABLE_AUTO_CAMPUS_AUTH=1` *without* `ENABLE_CONTROLLED_LIVE_AUTH=1` is a compile-time `#error`.
- A `BAD_CREDENTIALS` / `WRONG_DOMAIN` / `TLS_PIN_MISMATCH` result transitions the Wi-Fi state machine to `BLOCKED`. The state machine **does not** spin a high-frequency retry.
- The hourly quota, the minimum interval between attempts, the failure backoff, and the hard-block latch all live in `campus_auth_policy.h` (a host-unit-tested module). Do not re-implement pacing in `WifiManager`.

Full details in [xidian-campus-network-authentication](xidian-campus-network-authentication.md) and `firmware/shared/RemoteACCore/src/network/campus_auth_policy.h`.

---

## C. Offline / credentials-free build

> Use case: DHT11 sensor + serial CLI + safe read-only path; no Wi-Fi, no campus auth, no credentials.

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile public
```

The `public` profile defaults are:

- `ENABLE_WIFI=1`
- `ENABLE_CLOUD=1` (cloud is on, but `cloud_secrets.h` remains the example placeholder — **no real credentials are compiled in**)
- `ENABLE_CAMPUS_AUTH=0`
- `ENABLE_WIFI_CREDENTIALS=0`
- `ENABLE_AUTO_WIFI_CONNECT=0` (offline-first: the radio stays idle until an operator issues `wifi connect`)

If you want a strictly offline build that compiles without Wi-Fi, the network stack, or any cloud dependency, the feature gates already default every transmission/auth switch to `0` — a build with **no `-D` flags at all** produces a local, offline, read-only firmware.

---

## FAQ

**Q: Build fails with `ENABLE_WIFI_CREDENTIALS=1 requires ENABLE_WIFI=1`?**
A: you forgot `-DENABLE_WIFI=1`. The PlatformIO default is on; in Arduino IDE you must `#define ENABLE_WIFI 1` in `globals.h`.

**Q: `dev.ps1 build -Profile local-wifi` reports `WIFI_SECRETS_MISSING`?**
A: `firmware/shared/RemoteACCore/src/config/wifi_secrets.h` is missing — copy from `wifi_secrets.example.h` and fill in the placeholders.

**Q: After flashing the device stays in `WIFI_DISCONNECTED` for 30 s?**
A: run `wifi status` to see the current state, `wifi scan` to confirm your SSID is visible, and double-check the password is correct (most home routers are case-sensitive). The `WIFI_CONNECT ssid=...` log line tells you whether the WPA or the OPEN path is being used.

**Q: Can I commit `wifi_secrets.h`?**
A: **No.** It is `.gitignore`d. Only the `wifi_secrets.example.h` template may be committed.

**Q: How do I rotate the Wi-Fi password?**
A: edit `wifi_secrets.h` and reflash. There is no runtime API to change the password (deliberate — keeps the secret out of the serial stream and the air path).
