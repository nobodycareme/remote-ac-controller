[简体中文](../中文/首次配置.md) | **English**

# First-time setup

This guide covers three common first-time scenarios: home/lab WPA or WPA2 Wi-Fi, the Xidian Srun campus network, and a credentials-free public build. All real credentials (Wi-Fi passwords, campus account passwords) live in local files; only the `.example.h` templates are committed.

All compile-time feature switches are controlled by [`firmware/shared/RemoteACCore/src/config/feature_gates.h`](../../firmware/shared/RemoteACCore/src/config/feature_gates.h), where illegal combinations are rejected at compile time.

---

## A. Home or lab WPA / WPA2 Wi-Fi

> Use case: your home or office Wi-Fi is WPA/WPA2 encrypted (password of at least 8 characters), no captive portal.

### A.1 Prepare the local credentials

```powershell
cd firmware/shared/RemoteACCore/src/config
cp wifi_secrets.example.h wifi_secrets.h
```

Edit `wifi_secrets.h`:

```cpp
#define LOCAL_WIFI_SSID     "your_wifi_name"
#define LOCAL_WIFI_PASSWORD "your_wifi_password"
```

> `wifi_secrets.h` stays local and is Git-ignored; never put a real password into README files, `platformio.ini`, or commit history.

### A.2 Pick the PlatformIO profile

`dev.ps1` exposes two local-Wi-Fi profiles:

| Profile | Meaning | Key switches |
|---|---|---|
| `local-wifi` | Home / lab Wi-Fi, no cloud | `ENABLE_CLOUD=0` |
| `local-wifi-cloud` | Home / lab Wi-Fi + cloud (MQTT) | `ENABLE_CLOUD=1` `ENABLE_CLOUD_CREDENTIALS=1` |

**local-wifi (local WPA/WPA2 only, no cloud)**:

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile local-wifi
```

**local-wifi-cloud (requires two local files)**:

1. Copy `wifi_secrets.example.h` to `wifi_secrets.h` and fill in your own router SSID and password;
2. In `firmware/shared/RemoteACCore/src/config/`, copy `cloud_secrets.example.h` to `cloud_secrets.h` and fill in your own MQTT broker settings (host, port, username, password, device ID, CA certificate or TLS fingerprint). PlatformIO and Arduino IDE share this one canonical local file;
3. Run:

```powershell
./tools/dev.ps1 build -Profile local-wifi-cloud
```

This profile enables `ENABLE_CLOUD_CREDENTIALS=1`: if either `wifi_secrets.h` or canonical `firmware/shared/RemoteACCore/src/config/cloud_secrets.h` is missing, the build stops and prints the missing file and template path—there is no fallback to a credentials-free example. Both real files are Git-ignored and never committed. The old `firmware/agent-platformio/include/cloud_secrets.h` and `firmware/shared/RemoteACCore/src/cloud_secrets.h` paths are deprecated; either one causes a hard failure, so do not keep multiple Cloud secret files.

> **Since v1.2.4 copying the template verbatim no longer passes.** Before a build, `local-wifi` / `local-wifi-cloud` run content validation: the Wi-Fi SSID must not be `your_wifi_name` and the password must follow the WPA/WPA2 rules (8-63 printable characters, or a 64-digit hex PSK). `local-wifi-cloud` additionally validates the cloud config — the broker host must not be a template value such as `your-broker.example.com`, the port must be within 1-65535, the device ID and credentials must be changed, and at least one valid CA certificate or TLS fingerprint must be present. On failure the build stops and prints a non-sensitive error code (for example `HOST_PLACEHOLDER`, `TLS_MATERIAL_MISSING`); no secret value is ever printed.

> **Since v1.2.5 the SSID and TLS rules are:** a Wi-Fi SSID may contain ordinary internal spaces (for example `Home WiFi`, `Lab Network 2`); its length is measured in UTF-8 bytes with a hard limit of 32 bytes; it must not be all whitespace, must not contain ASCII control characters (0x01-0x1F, 0x7F), and it is never trimmed or silently truncated. For TLS, the **CA certificate takes priority** — when both a valid CA and a valid fingerprint are configured, only the CA is used (`setTrustAnchors`); a SHA-1 server-certificate fingerprint (`setFingerprint`, 40 hex characters, colons optional) is used only when no valid CA is present. The fingerprint pins the current server certificate, so it must be updated when the certificate rotates. If neither is present, the build/init stops (`TLS_MATERIAL_MISSING`). Disabling TLS validation is not supported (`setInsecure()` is forbidden).

### A.3 Arduino IDE workflow

Open `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino` in Arduino IDE. First copy the template to the local config file (the Arduino ESP8266 build applies it automatically; you do not edit the main `.ino` file):

```powershell
cd firmware/arduino-ide/Remote_AC_Controller
Copy-Item Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

Then edit `Remote_AC_Controller.ino.globals.h`:

```cpp
#define ENABLE_WIFI              1
#define ENABLE_WIFI_CREDENTIALS  1   // enable local WPA credentials
#define ENABLE_AUTO_WIFI_CONNECT 1   // join the network at boot

// local Wi-Fi credentials (same file as the PlatformIO path)
#include "config/wifi_secrets.h"
```

> General Arduino IDE workflow: see [arduino-ide-guide](arduino-ide-guide.md).

### A.4 Serial commands at runtime

The firmware joins the home network at boot using the compiled-in credentials (`local-wifi` / `local-wifi-cloud`). To reconnect or temporarily switch to an open SSID from the serial monitor:

| Command | Behaviour |
|---|---|
| `wifi connect` | re-select the local WPA/WPA2 configuration from `wifi_secrets.h` (password never enters the serial stream) |
| `wifi connect <ssid>` | temporarily switch to the given open SSID; **does not** read or use the `wifi_secrets.h` password, and a Wi-Fi password is never accepted on the command line. The SSID may contain spaces: `wifi connect Home WiFi` connects to the full `Home WiFi` as an open SSID (it is not split into `Home`) and never uses the local WPA password |
| `wifi status` | print state, connection source (`NET_SOURCE`), the actual SSID (`NET_SSID`) and IP |
| `wifi scan` | list nearby APs (read-only) |
| `wifi disconnect` | drop the current association |

The connection source (`NET_SOURCE`) is one of: `COMPILED_LOCAL_WPA` (local WPA credentials), `CAMPUS_PROFILE_OPEN` (campus open SSID), `RUNTIME_OPEN_SSID` (`wifi connect <ssid>`), or `NONE` (not configured). The SSID shown by `wifi status` always matches the SSID actually used for the connection, and the boot log prints the actual SSID and source.

The serial stream never contains the password value, only:

```
WIFI_CONNECT source=COMPILED_LOCAL_WPA ssid=<ssid> security=WPA_OR_WPA2
WIFI_CONNECT source=CAMPUS_PROFILE_OPEN ssid=<ssid> security=OPEN
WIFI_CONNECT source=RUNTIME_OPEN_SSID ssid=<ssid> security=OPEN
WIFI_CONNECT_SKIPPED source=<source> reason=<SSID_NOT_CONFIGURED|WIFI_PASSWORD_NOT_CONFIGURED|SSID_INVALID|SSID_TOO_LONG>
```

SSID validation rules (since v1.2.5, identical to the build-time checks):

- An SSID may contain ordinary internal spaces — `Home WiFi`, `Lab Network 2` and `My Router` are all valid;
- Length is measured in UTF-8 encoded BYTES and must be 1..32 bytes; longer SSIDs are rejected (`SSID_TOO_LONG`), never silently truncated;
- An SSID must not be empty, must not be all whitespace, and must not contain ASCII control characters (0x01-0x1F, 0x7F — including Tab and newline);
- The template value `your_wifi_name` is rejected;
- The SSID is never trimmed or modified — the exact value you provide is what is used.

---

## B. Xidian Srun campus network

> Use case: Xidian campus Wi-Fi `stu-xdwlan` is an open SSID; login goes through the Srun captive portal. Xidian Srun is published as the public example profile (`profiles/xidian.example.h`); other Srun deployments see [srun-campus-network-porting-guide](srun-campus-network-porting-guide.md).

### B.1 PlatformIO public example

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile local-campus-example
```

`local-campus-example` is for safe public compile verification only: it compiles the campus auth code to prove it builds, but it does **not** read real campus credentials and does **not** perform a real login. The profile sets `ENABLE_AUTO_CAMPUS_AUTH=0` and `ENABLE_CONTROLLED_LIVE_AUTH=0`, so it never authenticates at boot and never accepts real credentials.

### B.2 Real campus authentication (Arduino IDE)

The verifiable entry point for real authentication in the public repository is the local globals configuration. First copy the template:

```powershell
cd firmware/arduino-ide/Remote_AC_Controller
Copy-Item Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

Then edit `Remote_AC_Controller.ino.globals.h` (applied automatically by the Arduino ESP8266 build; do not edit the main `.ino` file):

```cpp
#define ENABLE_WIFI                 1
#define ENABLE_CAMPUS_AUTH          1
#define ENABLE_AUTO_WIFI_CONNECT    1
#define ENABLE_AUTO_CAMPUS_AUTH     1
#define ENABLE_CONTROLLED_LIVE_AUTH 1
#define CAMPUS_PROFILE_HEADER       "profiles/xidian.h"
```

And two local files (both Git-ignored, never committed):

```powershell
cd firmware/shared/RemoteACCore/src/config
cp profiles/xidian.example.h profiles/xidian.h
cp campus_secrets.example.h campus_secrets.h
```

Edit `campus_secrets.h`:

```cpp
#define CAMPUS_USERNAME "your_student_id"
#define CAMPUS_PASSWORD "your_campus_password"
```

> `xidian.h` and `campus_secrets.h` are never committed; do not put plaintext passwords into `platformio.ini` or `Remote_AC_Controller.ino.globals.h`.

Security requirements:

- Do not disable TLS verification (no `setInsecure()`);
- stop authentication when the TLS fingerprint does not match — `BAD_CREDENTIALS` / `WRONG_DOMAIN` / `TLS_PIN_MISMATCH` enter the `BLOCKED` state without high-frequency retries;
- the hourly quota, minimum interval, failure backoff, and hard-block latch are all controlled by `campus_auth_policy.h`.

Full details in [xidian-campus-network-authentication](xidian-campus-network-authentication.md).

---

## C. Credentials-free public build

> Use case: compile once to verify the public firmware builds safely, with no real credentials.

**public (full public firmware compile check)**:

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile public
```

The `public` profile compiles the Wi-Fi and cloud modules, but:

- it contains no real credentials (`wifi_secrets.h`, `cloud_secrets.h` are not involved);
- it does not auto-associate at boot (there is no auto-connect configuration);
- it does not connect to a real MQTT broker;
- it is suitable for public CI and toolchain verification.

This is not a fully offline build and not "sensors only": the firmware still compiles the Wi-Fi and cloud code paths, just without any real credentials and without auto-connecting.

**public-cloud-example (cloud module compile example)**:

```powershell
./tools/dev.ps1 build -Profile public-cloud-example
```

This profile only verifies that credentials-free cloud code builds safely: it compiles the cloud module with `ENABLE_CLOUD_CREDENTIALS=0`, connects to no real MQTT broker, and does not auto-associate Wi-Fi.
