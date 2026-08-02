#pragma once
/*
 * wifi_ssid_validation.h — PURE, host-testable single SSID validation rule.
 *
 * v1.2.5: this is the ONE C++ rule used everywhere an SSID is accepted:
 *   - wifi_secrets.h build-time validation (mirrored in Python);
 *   - local-wifi / local-wifi-cloud boot configuration;
 *   - `wifi connect <ssid>` runtime open SSID;
 *   - WifiConnectPlan;
 *   - Host tests (which read the SAME shared test-vector JSON as Python).
 *
 * Unified rule (authoritative — mirrored by tools/validate-cloud-secrets.py
 * and enforced by test/fixtures/wifi_ssid_validation_cases.json):
 *   1. SSID must not be nullptr and must not be empty;
 *   2. SSID must not be entirely ASCII whitespace;
 *   3. ASCII control characters are rejected: 0x01-0x1F and 0x7F;
 *   4. ordinary INTERNAL spaces are allowed ("Home WiFi", "Lab Network 2");
 *   5. length must be 1..32 BYTES (UTF-8 byte length, not character count);
 *   6. the template value "your_wifi_name" is rejected;
 *   7. the SSID is NEVER trimmed or truncated — the user's exact SSID is
 *      preserved; a >32-byte SSID is rejected, not silently cut.
 *
 * Note: a C string cannot carry an embedded NUL, so NUL is not a usable
 * SSID; multi-byte UTF-8 is allowed as long as the total byte length <= 32.
 */
#include <stddef.h>

enum WifiSsidValidationCode {
  WIFI_SSID_OK = 0,                // valid, use as-is (never modified)
  WIFI_SSID_ERR_EMPTY,             // nullptr or empty string
  WIFI_SSID_ERR_ALL_SPACE,         // only ASCII spaces/tabs
  WIFI_SSID_ERR_CONTROL_CHARACTER, // contains 0x01-0x1F or 0x7F
  WIFI_SSID_ERR_TOO_LONG,          // more than 32 UTF-8 bytes
  WIFI_SSID_ERR_TEMPLATE           // equals the template value "your_wifi_name"
};

inline const char* wifiSsidValidationLabel(WifiSsidValidationCode c) {
  switch (c) {
    case WIFI_SSID_OK:                 return "OK";
    case WIFI_SSID_ERR_EMPTY:          return "SSID_EMPTY";
    case WIFI_SSID_ERR_ALL_SPACE:      return "SSID_ALL_SPACE";
    case WIFI_SSID_ERR_CONTROL_CHARACTER: return "SSID_CONTROL_CHARACTER";
    case WIFI_SSID_ERR_TOO_LONG:       return "SSID_TOO_LONG";
    case WIFI_SSID_ERR_TEMPLATE:       return "SSID_TEMPLATE";
  }
  return "UNKNOWN";
}

inline WifiSsidValidationCode validateWifiSsid(const char* ssid) {
  if (!ssid) return WIFI_SSID_ERR_EMPTY;
  if (ssid[0] == '\0') return WIFI_SSID_ERR_EMPTY;

  // Reject the template value verbatim (build-time + runtime).
  // Exact string compare on the known template.
  {
    const char* t = "your_wifi_name";
    const char* a = ssid;
    const char* b = t;
    while (*b && *a == *b) { ++a; ++b; }
    if (*b == '\0' && *a == '\0') return WIFI_SSID_ERR_TEMPLATE;
  }

  // Byte length (UTF-8) and control-character scan in one pass.
  size_t bytes = 0;
  int hasNonSpace = 0;
  for (const char* c = ssid; *c; ++c) {
    const unsigned char ch = (unsigned char)*c;
    if (ch == 0x7F) return WIFI_SSID_ERR_CONTROL_CHARACTER;
    if (ch < 0x20)  return WIFI_SSID_ERR_CONTROL_CHARACTER;   // 0x01-0x1F
    ++bytes;
    if (ch != ' ' && ch != '\t') hasNonSpace = 1;
  }

  if (!hasNonSpace) return WIFI_SSID_ERR_ALL_SPACE;
  if (bytes > 32) return WIFI_SSID_ERR_TOO_LONG;
  return WIFI_SSID_OK;
}
