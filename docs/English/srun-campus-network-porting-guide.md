[简体中文](../中文/Srun校园网移植指南.md) | **English**

# Srun Campus Network Porting Guide

> Adapting the campus network automatic authentication feature to other schools that use Srun-based authentication systems.

---

## Overview

The campus network authentication module in this project is implemented based on the Srun 4000 protocol, but **different schools may have version differences and configuration variations**. This guide explains how to port the authentication feature to your own campus network.

**Important prerequisites:**
- Not all schools use the Srun authentication system
- Even with Srun, different versions (3000/4000/5000) may have different parameters
- Do **not** disable TLS verification to make it "work"
- You must use your own legally authorized campus network account
- Comply with your school's network usage policies

## Parameters to Identify

Before calibrating campus network authentication, collect the following parameters. These **do not include personal credentials** and are public information about the school's network infrastructure:

### 1. Wi-Fi Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| SSID | Campus Wi-Fi name | `stu-xdwlan` at Xidian; elsewhere typically `eduroam`, `xxx-wlan` |
| Open/Encrypted | Whether a pre-shared key is required | Campus networks are typically Open |
| Auth method | 802.1X / Open | Most Captive Portal networks are Open |

### 2. Portal Parameters

| Parameter | Description | How to Obtain |
|-----------|-------------|---------------|
| Portal Host | Portal server domain | After connecting to campus Wi-Fi, visit an HTTP site and observe the redirect destination; take the hostname only |
| ac_id | Access ID | From the hidden field in the Portal login page HTML form, or from the firmware's `AC_ID=` probe output |
| Domain suffix | Whether an ISP suffix is required | Empty at most schools; a few need `@lt`/`@yd`/`@dx` |

> The Base URL **does not need to be collected**: the firmware always derives it from `CAMPUS_PORTAL_HOST` as `https://<host>`. If your campus portal is HTTP-only or listens on a non-443 port (e.g. `:801`), the current implementation cannot be adapted directly — credentials are only ever sent over a TLS connection with a pinned leaf certificate, and that constraint is not bypassable.

### 3. Authentication API Parameters

| Parameter | Description |
|-----------|-------------|
| Challenge API | Challenge code endpoint (typically `/cgi-bin/get_challenge`) |
| Login API | Authentication request endpoint (typically `/cgi-bin/srun_portal`) |
| Auth algorithm | Challenge-response algorithm (MD5 / SHA1 / other) |
| Challenge parameters | challenge, client_ip, ac_id, username, etc. |

### 4. TLS Certificate

| Parameter | Macro | Description |
|-----------|-------|-------------|
| Certificate fingerprint | `CAMPUS_CERT_SHA1` | **SHA-1** fingerprint of the portal leaf certificate (20 bytes, colon-separated) |
| Not before | `CAMPUS_CERT_NOT_BEFORE` | Certificate notBefore, formatted `YYYY-MM-DD` |
| Not after | `CAMPUS_CERT_NOT_AFTER` | Certificate notAfter; must be re-extracted once passed |
| Issuer | `CAMPUS_CERT_ISSUER` | CN of the issuing CA |
| Subject | `CAMPUS_CERT_SUBJECT` | Domain/subject the certificate is bound to |

> **It must be SHA-1, not SHA-256.** The ESP8266's BearSSL `setFingerprint()` accepts only a 20-byte SHA-1 leaf fingerprint; supplying SHA-256 makes `tlsPinValid()` fail and the build fail-closes, refusing to authenticate. This is not a security compromise — the security of pinning comes from matching one exact certificate, not from the collision resistance of the digest, and the fingerprint is obtained out-of-band over a trusted network.

## Porting Steps

### Step 1: Obtain the Portal Login Page

After connecting to campus Wi-Fi, visit an HTTP site (e.g. `http://example.com`) and observe if you are redirected to a Portal login page. Extract the Portal Host and Base URL from the redirect URL.

### Step 2: Analyze the Login Page

Open the Portal login page, view the HTML source, and extract:
- The `ac_id` value (typically in a hidden `<input>` field)
- The login form submission URL (action attribute)
- The username and password field names

### Step 3: Test the Challenge API

Use browser developer tools or curl to test the Challenge API:

```
GET https://<portal_host>/cgi-bin/get_challenge?callback=json&username=<test_user>
```

Observe the returned challenge value and res status code.

The three endpoints the firmware actually uses are fixed and not configurable:

```
challenge  GET   https://<host>/cgi-bin/get_challenge
login      POST  https://<host>/cgi-bin/srun_portal   (action=login)
logout     POST  https://<host>/cgi-bin/srun_portal   (action=logout)
```

The base URL is derived from `CAMPUS_PORTAL_HOST` as `https://<host>` with **no path suffix**, which is why there is no `CAMPUS_PORTAL_BASE_URL` macro.

### Step 4: Create a Custom Profile

Use `profiles/generic_srun.example.h` as the template, copy it to a git-ignored private name, and fill in your school's real public values:

```bash
cd firmware/shared/RemoteACCore/src/config/profiles
cp generic_srun.example.h my_university.h    # any non-*.example.h name is git-ignored
```

The complete set of profile macros is below — this is the authoritative list, there are no others:

```cpp
// profiles/my_university.h
#define CAMPUS_SSID         "my-campus-open-ssid"        // open SSID, never a WPA key
#define CAMPUS_PORTAL_HOST  "portal.myuniversity.edu.cn" // hostname only, no scheme or path
#define CAMPUS_AC_ID        1                            // integer, not a string
#define CAMPUS_DOMAIN       ""                           // ISP/domain suffix, usually empty

// TLS leaf certificate pin (see Step 5)
#define CAMPUS_CERT_SHA1        "AA:BB:...:FF"
#define CAMPUS_CERT_NOT_BEFORE  "YYYY-MM-DD"
#define CAMPUS_CERT_NOT_AFTER   "YYYY-MM-DD"
#define CAMPUS_CERT_ISSUER      "<issuing CA CN>"
#define CAMPUS_CERT_SUBJECT     "<certificate subject>"
```

Three common mistakes to avoid: `CAMPUS_AC_ID` is an **integer** (`1`, not `"1"`); the suffix macro is named `CAMPUS_DOMAIN` (not `CAMPUS_ACCOUNT_SUFFIX`); and at most schools `CAMPUS_DOMAIN` should stay empty — only set `@lt`/`@yd`/`@dx` if your srun server genuinely requires it.

Then select the profile in your build configuration:

```cpp
// Arduino IDE: Remote_AC_Controller.ino.globals.h
#define CAMPUS_PROFILE_HEADER "profiles/my_university.h"
```

```ini
; PlatformIO: the double quotes must be escaped
-DCAMPUS_PROFILE_HEADER=\"profiles/my_university.h\"
```

### Step 5: Extract and Pin the TLS Certificate Fingerprint

**The certificate macros belong in your profile — do not edit `config/campus_tls_pin.h`.** That header only supplies the fail-closed empty defaults and is shared infrastructure across all profiles.

Extract the fingerprint out-of-band over a **trusted network** (not from inside the campus network you are adapting to):

```bash
openssl s_client -connect <host>:443 -servername <host> -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha1 -subject -issuer -dates
```

The output **must** contain `Verify return code: 0 (ok)`. If it does not, the system trust chain did not validate and you may be pinning an interception proxy rather than the real portal — stop, move to a trusted network, and re-extract.

Fill the resulting values into the five `CAMPUS_CERT_*` macros from Step 4.

**Security warning:** Do not disable TLS verification and do not fall back to `setInsecure()`. When the pin is missing or mismatched, the firmware prints `TLS_PIN_MISMATCH` and fail-closes — **credentials are never sent**. That is designed behaviour, not a fault to work around.

### Step 6: Verify the Authentication Flow

First verify the detection path **without credentials compiled in** (`ENABLE_CAMPUS_AUTH=1`, `ENABLE_CONTROLLED_LIVE_AUTH=0`). Confirm via the serial monitor (115200 baud):

```
CAPTIVE_PORTAL_DETECTED=YES
PORTAL_HOST=<your portal host>
AC_ID=<detected ac_id>
```

If the detected `AC_ID` differs from what you put in the profile, **trust the detected value**. Once this is correct, set `ENABLE_CONTROLLED_LIVE_AUTH=1`, populate `campus_secrets.h`, and attempt real authentication. On failure, adjust parameters based on the `CAMPUS_AUTH_FAIL reason=` and `AUTH_SERVER_ERROR=` fields in the log.

If a hard failure such as a wrong password latches the device into `WIFI_BLOCKED`, clear it with the serial command `campus unblock`. Do **not** retry in a loop — automatically replaying a rejected password is how campus accounts get locked out.

## Frequently Asked Questions

### Q: My school does not use Srun?
This project currently only supports the Srun protocol. If your school uses a different authentication system (e.g. H3C, Ruijie, Cisco ISE), additional adaptation work is required.

### Q: The authentication algorithm does not match?
Srun 4000 standard uses MD5 challenge-response. If your school uses a different algorithm, the authentication implementation in the `srun-c` library will need to be modified.

### Q: Authentication fails with no error message?
Check whether the Portal address is correct and whether the Challenge API is reachable. Some schools may use non-standard API paths.

### Q: Do I need to disable TLS verification?
**Absolutely not.** If TLS verification fails, the certificate fingerprint either does not match or the certificate has been rotated — update the fingerprint rather than disabling verification.

## Compliance Requirements

- This feature is only for use with campus network accounts that you are legally authorized to use
- Users must comply with their school's network usage policies
- This project is not intended for bypassing authentication, sharing accounts, or unauthorized network access
- Do not use this project for any activities that violate applicable laws or regulations

## Related Documentation

- [Xidian Campus Network Authentication](./xidian-campus-network-authentication.md) — Xidian Srun configuration reference
- [Architecture Overview](./architecture.md) — Network authentication in the system architecture