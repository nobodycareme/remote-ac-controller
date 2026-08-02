#pragma once
/*
 * wifi_connect_plan.h - PURE, host-testable Wi-Fi connection decision.
 *
 * v1.2.2 adds local WPA/WPA2 credentials (wifi_secrets.h) alongside the
 * existing OPEN campus SSID path. v1.2.3 adds an explicit configuration
 * validity result so that an empty SSID can never reach WiFi.begin().
 * v1.2.4 introduces the authoritative CONNECTION SOURCE model: which SSID
 * is used is decided by an explicit runtime source, never by an implicit
 * compile-time priority. This header contains the ONLY place that decides
 * WHICH WiFi.begin() overload the firmware calls, whether the link may come
 * up automatically at boot, and whether a configuration is valid at all.
 * v1.2.5 delegates SSID acceptance to the unified wifi_ssid_validation.h
 * rule (32-byte UTF-8 contract, internal spaces allowed, control chars and
 * the template value rejected) — the SAME rule mirrored by the Python
 * build-time validator and the shared JSON test vectors.
 * It has no Arduino/ESP8266 dependency, so host tests compile it directly
 * on any platform.
 *
 * Design contract (enforced by test/host/test_wifi_connect.cpp and
 * test/host/test_wifi_manager_integration.cpp):
 *   - the security label and the begin() overload depend ONLY on whether a
 *     password is present (never on the password content);
 *   - the password is never passed into any logging/formatting function;
 *   - campus mode never reads the local Wi-Fi password;
 *   - local-Wi-Fi mode never reads campus credentials;
 *   - a conflicting build (local credentials + campus auth) is rejected at
 *     compile time by feature_gates.h; this plan assumes legal flag sets;
 *   - when configurationValid is false the caller MUST NOT call any
 *     WiFi.begin() overload; the reason names the missing piece;
 *   - WIFI_SOURCE_RUNTIME_OPEN_SSID is selected by an explicit operator
 *     command and must NEVER be overridden by compiled local credentials.
 */
#include "config/feature_gates.h"
#include "network/wifi_ssid_validation.h"

enum WifiSecurityType {
  WIFI_SECURITY_OPEN = 0,        // WiFi.begin(ssid)
  WIFI_SECURITY_WPA_OR_WPA2      // WiFi.begin(ssid, password)
};

// Authoritative connection source. The priority between sources is explicit
// and runtime-visible; a compile-time macro can never override a runtime
// operator selection.
enum WifiConnectionSource {
  WIFI_SOURCE_NONE = 0,            // no SSID source configured
  WIFI_SOURCE_COMPILED_LOCAL_WPA,  // wifi_secrets.h (LOCAL_WIFI_SSID/PASSWORD)
  WIFI_SOURCE_CAMPUS_PROFILE_OPEN, // CAMPUS_SSID (open network)
  WIFI_SOURCE_RUNTIME_OPEN_SSID    // `wifi connect <ssid>` (explicit user SSID)
};

enum WifiConnectReason {
  WIFI_PLAN_OK = 0,               // configuration is complete and usable
  SSID_NOT_CONFIGURED,            // no SSID source carries a valid value
  WIFI_PASSWORD_NOT_CONFIGURED,   // local WPA mode but the password is empty
  SSID_INVALID,                   // SSID rejected by wifi_ssid_validation.h
  SSID_TOO_LONG                   // SSID longer than the 32-byte contract
};

struct WifiConnectPlan {
  WifiConnectionSource source;  // the source this plan was built from
  bool configurationValid;      // false -> WiFi.begin() MUST NOT be called
  const char* ssid;             // authoritative SSID for this source (never logged with the password)
  bool ssidPresent;             // a concrete SSID string is available
  bool passwordPresent;         // a WPA password is available (never logged)
  WifiSecurityType securityType;
  WifiConnectReason reason;     // WIFI_PLAN_OK or the reason it is invalid
  bool autoConnectAllowed;      // derived from WIFI_AUTOCONNECT_ON_BOOT
};

inline const char* wifiSecurityLabel(WifiSecurityType t) {
  return t == WIFI_SECURITY_WPA_OR_WPA2 ? "WPA_OR_WPA2" : "OPEN";
}

inline const char* wifiSourceLabel(WifiConnectionSource s) {
  switch (s) {
    case WIFI_SOURCE_NONE:             return "NONE";
    case WIFI_SOURCE_COMPILED_LOCAL_WPA: return "COMPILED_LOCAL_WPA";
    case WIFI_SOURCE_CAMPUS_PROFILE_OPEN: return "CAMPUS_PROFILE_OPEN";
    case WIFI_SOURCE_RUNTIME_OPEN_SSID:   return "RUNTIME_OPEN_SSID";
  }
  return "UNKNOWN";
}

inline const char* wifiPlanReasonLabel(WifiConnectReason r) {
  switch (r) {
    case WIFI_PLAN_OK:             return "OK";
    case SSID_NOT_CONFIGURED:      return "SSID_NOT_CONFIGURED";
    case WIFI_PASSWORD_NOT_CONFIGURED: return "WIFI_PASSWORD_NOT_CONFIGURED";
    case SSID_INVALID:             return "SSID_INVALID";
    case SSID_TOO_LONG:            return "SSID_TOO_LONG";
  }
  return "UNKNOWN";
}

// Map the unified SSID validation code onto the plan reason.
//   - empty / all-space  -> SSID_NOT_CONFIGURED (backward-compatible reason)
//   - >32 bytes          -> SSID_TOO_LONG (the 32-byte contract)
//   - control / template -> SSID_INVALID
inline WifiConnectReason ssidReason(const char* ssid) {
  WifiSsidValidationCode c = validateWifiSsid(ssid);
  if (c == WIFI_SSID_ERR_TOO_LONG) return SSID_TOO_LONG;
  if (c == WIFI_SSID_ERR_EMPTY || c == WIFI_SSID_ERR_ALL_SPACE) return SSID_NOT_CONFIGURED;
  if (c == WIFI_SSID_OK) return WIFI_PLAN_OK;
  return SSID_INVALID;
}

// An SSID is usable only when it passes the v1.2.5 unified rule
// (wifi_ssid_validation.h): non-empty, not all-space, no control chars,
// 1..32 UTF-8 bytes, not the template value. Ordinary internal spaces and
// UTF-8 names are allowed.
inline bool wifiSsidUsable(const char* ssid) {
  return validateWifiSsid(ssid) == WIFI_SSID_OK;
}

/*
 * Build the connection plan from an EXPLICIT source.
 *
 *   source   - the authoritative source (see WifiConnectionSource).
 *   ssid     - the SSID value for that source:
 *                COMPILED_LOCAL_WPA  -> LOCAL_WIFI_SSID
 *                CAMPUS_PROFILE_OPEN -> CAMPUS_SSID
 *                RUNTIME_OPEN_SSID   -> the operator-provided SSID
 *                NONE                -> ignored
 *   hasPassword - only meaningful for COMPILED_LOCAL_WPA; the caller passes
 *                (LOCAL_WIFI_PASSWORD[0] != '\0'). The VALUE is never read
 *                here, only its presence.
 *
 * RUNTIME_OPEN_SSID never consults the compiled password and can never be
 * overridden by the local-WPA macro: the source decides, not the build.
 */
inline WifiConnectPlan makeWifiConnectPlan(WifiConnectionSource source,
                                           const char* ssid,
                                           bool hasPassword) {
  WifiConnectPlan p;
  p.source = source;
  p.reason = WIFI_PLAN_OK;
  p.ssid = ssid ? ssid : "";
  p.ssidPresent = false;
  p.passwordPresent = false;
  p.securityType = WIFI_SECURITY_OPEN;
  p.configurationValid = false;

  switch (source) {
    case WIFI_SOURCE_COMPILED_LOCAL_WPA:
      if (wifiSsidUsable(ssid)) {
        p.ssidPresent = true;
        p.ssid = ssid;
        if (hasPassword) {
          p.configurationValid = true;
          p.passwordPresent = true;
          p.securityType = WIFI_SECURITY_WPA_OR_WPA2;
        } else {
          p.reason = WIFI_PASSWORD_NOT_CONFIGURED;
        }
      } else {
        p.reason = ssidReason(ssid);
      }
      break;

    case WIFI_SOURCE_CAMPUS_PROFILE_OPEN:
    case WIFI_SOURCE_RUNTIME_OPEN_SSID:
      if (wifiSsidUsable(ssid)) {
        p.ssidPresent = true;
        p.ssid = ssid;
        p.configurationValid = true;
        p.securityType = WIFI_SECURITY_OPEN;
      } else {
        p.reason = ssidReason(ssid);
      }
      break;

    case WIFI_SOURCE_NONE:
    default:
      p.reason = SSID_NOT_CONFIGURED;
      break;
  }

  p.autoConnectAllowed = WIFI_AUTOCONNECT_ON_BOOT && p.configurationValid;
  return p;
}

/*
 * Pure log-line helpers shared by the production WifiManager::connect() and
 * the integration tests. They NEVER accept a password value, so a future
 * refactor cannot leak the password into logs by accident.
 */
inline const char* wifiConnectSkippedLog() {
  return "WIFI_CONNECT_SKIPPED";
}

inline const char* wifiConnectLog() {
  return "WIFI_CONNECT";
}
