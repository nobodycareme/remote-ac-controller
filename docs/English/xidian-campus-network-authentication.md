# Xidian Campus Network Automatic Authentication

> **ESP8266 automatic Xidian University campus network authentication on boot** — After joining the campus open SSID, the device automatically completes Wi-Fi association, DHCP address acquisition, Captive Portal detection, Srun authentication, and Internet connectivity verification.

---

## Overview

This feature allows the ESP8266 NodeMCU to automatically authenticate on the Xidian University campus network (based on Srun 4000) after power-on, without requiring manual browser-based Portal login. The device connects to the campus open SSID, completes the full authentication flow, and can then proceed to MQTT cloud connectivity.

**This feature is disabled by default** and requires explicit user configuration.

## How It Works

```
ESP8266 Boot
  → Initialize DHT11, IR module, serial CLI
  → If ENABLE_WIFI=1: Start Wi-Fi, connect to campus SSID
  → Obtain DHCP address
  → If ENABLE_AUTO_CAMPUS_AUTH=1: Perform Captive Portal detection
  → If Portal detected: Execute Srun authentication
  → Verify Internet connectivity
  → If ENABLE_CLOUD=1: Start MQTT and telemetry
  → Continuously monitor Wi-Fi, Internet, and MQTT status
```

## Supported Build Macros

| Macro | Default | Description |
|-------|---------|-------------|
| `ENABLE_WIFI` | 1 | Controls Wi-Fi hardware and connection |
| `ENABLE_CAMPUS_AUTH` | 0 | Controls Captive Portal detection and Srun auth |
| `ENABLE_AUTO_CAMPUS_AUTH` | 0 | Controls automatic Portal detection on boot |
| `ENABLE_CLOUD` | 0 | Controls MQTT and cloud connectivity |

## Configuration Steps

### 1. Enable Campus Authentication

In `config.h` (Arduino IDE) or `campus_credentials.h` (PlatformIO):

```cpp
#define ENABLE_WIFI 1
#define ENABLE_CAMPUS_AUTH 1
#define ENABLE_AUTO_CAMPUS_AUTH 1
```

### 2. Configure Campus Network Parameters

Xidian campus network Profile parameters:

| Parameter | Description | Xidian Value |
|-----------|-------------|--------------|
| Wi-Fi SSID | Campus open SSID | `XDU` or `STU-XDU` (depends on campus area) |
| Portal Host | Portal server address | To be determined based on actual network environment |
| ac_id | Authentication access ID | Determined by campus area and network type |
| Account format | Student/employee ID + ISP suffix | Student ID + `@operator` (e.g. `@cmcc`) |
| Auth algorithm | Srun challenge-response | Srun 4000 standard MD5 algorithm |

### 3. Configure Campus Credentials

Credentials must be stored in **git-ignored** files and must not be committed:

```cpp
// In campus_credentials.h (git-ignored)
#define CAMPUS_USERNAME "your_student_id"
#define CAMPUS_PASSWORD "your_password"
```

Copy the template file and fill in your details:

```bash
cp campus_credentials.example.h campus_credentials.h
# Edit campus_credentials.h with your student ID and password
```

## Serial Output Status

During authentication, the serial monitor (115200 baud) outputs key status messages:

```
WIFI_CONNECTING ssid=XDU
WIFI_CONNECTED ip=10.x.x.x
PORTAL_DETECTING host=portal.xidian.edu.cn
PORTAL_DETECTED=YES
CAMPUS_AUTH_STARTING
CAMPUS_AUTH_OK internet=REACHABLE
CLOUD_MQTT_INIT_OK
```

On authentication failure:

```
CAMPUS_AUTH_FAILED reason=PORTAL_UNREACHABLE
CAMPUS_AUTH_BACKOFF next_attempt=30s
```

## Security Notes

- **Credentials reside only in local ignored files**, never in the Git repository
- TLS certificate verification is supported — **do not disable TLS verification**
- Authentication rate limiting and failure backoff are implemented
- Full credentials are never printed in logs
- Portal responses are not printed in full to avoid leaking sensitive information

## Limitations

- This configuration is **specifically adapted for Xidian University (Srun 4000)**
- Other schools' Srun systems may require Profile parameter adjustments
- Automatic authentication is disabled by default, requiring explicit user configuration
- Users must use their own legally authorized campus network accounts
- Please comply with your school's network usage policies

## Related Documentation

- [Srun Campus Network Porting Guide](./srun-campus-network-porting-guide.md) — Generic guide for adapting to other schools
- [Architecture Overview](./architecture.md) — Complete system architecture
- [Security Model](./security-model.md) — Security configuration notes