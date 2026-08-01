#pragma once
/*
 * wifi_connect_plan.h - PURE, host-testable Wi-Fi connection decision.
 *
 * v1.2.2 adds local WPA/WPA2 credentials (wifi_secrets.h) alongside the
 * existing OPEN campus SSID path. This header contains the ONLY place that
 * decides WHICH WiFi.begin() overload the firmware calls and whether the link
 * may come up automatically at boot. It has no Arduino/ESP8266 dependency,
 * so host tests compile it directly on any platform.
 *
 * Design contract (enforced by test/host/test_wifi_connect.cpp):
 *   - the security label and the begin() overload depend ONLY on whether a
 *     password is present (never on the password content);
 *   - the password is never passed into any logging/formatting function;
 *   - campus mode never reads the local Wi-Fi password;
 *   - local-Wi-Fi mode never reads campus credentials;
 *   - a conflicting build (local credentials + campus auth) is rejected at
 *     compile time by feature_gates.h; this plan assumes legal flag sets.
 */
#include "config/feature_gates.h"

enum WifiSecurityType {
  WIFI_SECURITY_OPEN = 0,        // WiFi.begin(ssid)
  WIFI_SECURITY_WPA_OR_WPA2      // WiFi.begin(ssid, password)
};

struct WifiConnectPlan {
  bool configurationValid;      // an SSID source exists at all
  bool ssidPresent;             // a concrete SSID string is available
  bool passwordPresent;         // a WPA password is available (never logged)
  WifiSecurityType securityType;
  bool autoConnectAllowed;      // derived from WIFI_AUTOCONNECT_ON_BOOT
};

inline const char* wifiSecurityLabel(WifiSecurityType t) {
  return t == WIFI_SECURITY_WPA_OR_WPA2 ? "WPA_OR_WPA2" : "OPEN";
}

/*
 * Build the connection plan from the available SSID sources.
 *
 *   campusSsid       - the campus open SSID (CAMPUS_SSID), always non-null in
 *                      an ENABLE_WIFI build.
 *   localSsid        - LOCAL_WIFI_SSID when ENABLE_WIFI_CREDENTIALS, else
 *                      nullptr.
 *   hasLocalPassword - true only when the build enables WIFI_CREDENTIALS AND
 *                      the secrets file is present. (The password VALUE is
 *                      never read here; only its presence.)
 *
 * Priority: when local credentials are enabled, the protected home/lab
 * network wins; otherwise the OPEN campus SSID is used. autoConnectAllowed
 * reflects the single authoritative WIFI_AUTOCONNECT_ON_BOOT expression.
 */
inline WifiConnectPlan makeWifiConnectPlan(const char* campusSsid,
                                           const char* localSsid,
                                           bool hasLocalPassword) {
  WifiConnectPlan p;
  p.configurationValid = (campusSsid && *campusSsid) || (localSsid && *localSsid);
  p.passwordPresent = hasLocalPassword;
  p.ssidPresent = hasLocalPassword
                      ? (localSsid && *localSsid)
                      : (campusSsid && *campusSsid);
  p.securityType = hasLocalPassword ? WIFI_SECURITY_WPA_OR_WPA2
                                    : WIFI_SECURITY_OPEN;
  p.autoConnectAllowed =
      WIFI_AUTOCONNECT_ON_BOOT && p.configurationValid;
  return p;
}
