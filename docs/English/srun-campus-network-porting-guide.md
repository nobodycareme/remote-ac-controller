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
| SSID | Campus Wi-Fi name | `XDU`, `STU-XDU`, `eduroam` |
| Open/Encrypted | Whether a pre-shared key is required | Campus networks are typically Open |
| Auth method | 802.1X / Open | Most Captive Portal networks are Open |

### 2. Portal Parameters

| Parameter | Description | How to Obtain |
|-----------|-------------|---------------|
| Portal Host | Portal server domain/IP | After connecting to campus Wi-Fi, visit an HTTP site and observe the redirect destination |
| Base URL | Portal API base path | Typically `http://<host>/` or `http://<host>:801/` |
| ac_id | Access ID | Extract from the Portal login page HTML form |
| Account format | Whether ISP suffix is needed | e.g. `@cmcc`, `@unicom`, `@telecom` |
| ISP suffix | Optional ISP identifier | Some schools require selecting an ISP |

### 3. Authentication API Parameters

| Parameter | Description |
|-----------|-------------|
| Challenge API | Challenge code endpoint (typically `/cgi-bin/get_challenge`) |
| Login API | Authentication request endpoint (typically `/cgi-bin/srun_portal`) |
| Auth algorithm | Challenge-response algorithm (MD5 / SHA1 / other) |
| Challenge parameters | challenge, client_ip, ac_id, username, etc. |

### 4. TLS Certificate

| Parameter | Description |
|-----------|-------------|
| Certificate fingerprint | Portal server TLS certificate SHA256 fingerprint |
| Fingerprint extraction time | Timestamp of fingerprint extraction |
| Certificate validity | Certificate start and expiry dates |
| Hostname | Domain name the certificate is bound to |
| Update method | How to update the fingerprint after certificate rotation |

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
GET http://<portal_host>/cgi-bin/get_challenge?callback=json&username=<test_user>
```

Observe the returned challenge value and res status code.

### Step 4: Create a Custom Profile

Based on the collected parameters, create a new Profile file:

```cpp
// profiles/my_university.example.h
#define CAMPUS_SSID "my_university_wifi"
#define CAMPUS_PORTAL_HOST "portal.myuniversity.edu.cn"
#define CAMPUS_PORTAL_BASE_URL "http://portal.myuniversity.edu.cn"
#define CAMPUS_AC_ID "1"
#define CAMPUS_ACCOUNT_SUFFIX "@cmcc"  // Leave empty if not needed
```

### Step 5: Configure TLS Certificate

```cpp
// campus_tls_pin.h
#define CAMPUS_TLS_FINGERPRINT "sha256$..."  // Extracted certificate fingerprint
#define CAMPUS_TLS_EXTRACTED "2026-07-31"
#define CAMPUS_TLS_EXPIRY "2027-07-31"
#define CAMPUS_TLS_HOST "portal.myuniversity.edu.cn"
```

**Security warning:** Do **not** disable TLS verification. If the certificate fingerprint does not match, stop sending credentials.

### Step 6: Verify the Authentication Flow

Observe the authentication flow output via the serial monitor (115200 baud). If authentication fails, adjust parameters based on the error codes in the logs.

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