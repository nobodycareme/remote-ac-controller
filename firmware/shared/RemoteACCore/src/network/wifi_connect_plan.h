#pragma once
/*
 * wifi_connect_plan.h - PURE, host-testable Wi-Fi connection decision.
 *
 * v1.2.2 adds local WPA/WPA2 credentials (wifi_secrets.h) alongside the
 * existing OPEN campus SSID path. v1.2.3 adds an explicit configuration
 * validity result so that an empty SSID can never reach WiFi.begin().
 * This header contains the ONLY place that decides WHICH WiFi.begin()
 * overload the firmware calls, whether the link may come up automatically at
 * boot, and whether a configuration is valid at all. It has no
 * Arduino/ESP8266 dependency, so host tests compile it directly on any
 * platform.
 *
 * Design contract (enforced by test/host/test_wifi_connect.cpp):
 *   - the security label and the begin() overload depend ONLY on whether a
 *     password is present (never on the password content);
 *   - the password is never passed into any logging/formatting function;
 *   - campus mode never reads the local Wi-Fi password;
 *   - local-Wi-Fi mode never reads campus credentials;
 *   - a conflicting build (local credentials + campus auth) is rejected at
 *     compile time by feature_gates.h; this plan assumes legal flag sets;
 *   - when configurationValid is false the caller MUST NOT call any
 *     WiFi.begin() overload; the reason names the missing piece.
 */
#include "config/feature_gates.h"

enum WifiSecurityType {
  WIFI_SECURITY_OPEN = 0,        // WiFi.begin(ssid)
  WIFI_SECURITY_WPA_OR_WPA2      // WiFi.begin(ssid, password)
};

enum WifiConnectReason {
  WIFI_PLAN_OK = 0,               // configuration is complete and usable
  SSID_NOT_CONFIGURED,            // no SSID source carries a non-empty value
  WIFI_PASSWORD_NOT_CONFIGURED    // local WPA mode but the password is empty
};

struct WifiConnectPlan {
  bool configurationValid;      // false -> WiFi.begin() MUST NOT be called
  bool ssidPresent;             // a concrete SSID string is available
  bool passwordPresent;         // a WPA password is available (never logged)
  WifiSecurityType securityType;
  WifiConnectReason reason;     // WIFI_PLAN_OK or the reason it is invalid
  bool autoConnectAllowed;      // derived from WIFI_AUTOCONNECT_ON_BOOT
};

inline const char* wifiSecurityLabel(WifiSecurityType t) {
  return t == WIFI_SECURITY_WPA_OR_WPA2 ? "WPA_OR_WPA2" : "OPEN";
}

inline const char* wifiPlanReasonLabel(WifiConnectReason r) {
  switch (r) {
    case WIFI_PLAN_OK:             return "OK";
    case SSID_NOT_CONFIGURED:      return "SSID_NOT_CONFIGURED";
    case WIFI_PASSWORD_NOT_CONFIGURED: return "WIFI_PASSWORD_NOT_CONFIGURED";
  }
  return "UNKNOWN";
}

/*
 * Build the connection plan from the available SSID sources.
 *
 *   campusSsid       - the campus open SSID (CAMPUS_SSID). In a build without
 *                      campus auth this is the inert "" placeholder, so an
 *                      empty value must be treated as "not configured".
 *   localSsid        - LOCAL_WIFI_SSID when ENABLE_WIFI_CREDENTIALS, else
 *                      nullptr. A NON-NULL pointer selects the local WPA
 *                      mode; the campus SSID is then never used (the two
 *                      modes are mutually exclusive at compile time).
 *   hasLocalPassword - true only when the build enables WIFI_CREDENTIALS AND
 *                      the local password value is non-empty. (The password
 *                      VALUE is never read here; only its presence.)
 *
 * Priority: when local credentials are enabled (localSsid != nullptr), the
 * protected home/lab network is the only candidate; otherwise the OPEN
 * campus SSID is used. autoConnectAllowed reflects the single authoritative
 * WIFI_AUTOCONNECT_ON_BOOT expression, and additionally requires a valid
 * configuration — a boot autoconnect can never fire on an empty SSID.
 */
inline WifiConnectPlan makeWifiConnectPlan(const char* campusSsid,
                                           const char* localSsid,
                                           bool hasLocalPassword) {
  WifiConnectPlan p;
  p.reason = WIFI_PLAN_OK;
  p.passwordPresent = hasLocalPassword;
  p.ssidPresent = false;
  p.securityType = WIFI_SECURITY_OPEN;

  if (localSsid) {
    // Local WPA mode: the campus SSID must NOT be used.
    if (*localSsid) {
      p.ssidPresent = true;
      if (hasLocalPassword) {
        p.configurationValid = true;
        p.securityType = WIFI_SECURITY_WPA_OR_WPA2;
      } else {
        p.configurationValid = false;
        p.reason = WIFI_PASSWORD_NOT_CONFIGURED;
      }
    } else {
      p.configurationValid = false;
      p.reason = SSID_NOT_CONFIGURED;
    }
  } else if (campusSsid && *campusSsid) {
    // OPEN campus path (only legal when local credentials are compiled out).
    p.ssidPresent = true;
    p.configurationValid = true;
    p.securityType = WIFI_SECURITY_OPEN;
  } else {
    p.configurationValid = false;
    p.reason = SSID_NOT_CONFIGURED;
  }

  p.autoConnectAllowed = WIFI_AUTOCONNECT_ON_BOOT && p.configurationValid;
  return p;
}
