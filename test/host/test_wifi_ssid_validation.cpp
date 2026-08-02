// Host test for the unified WiFi SSID validation rule (v1.2.5).
//
// Reads the SAME test vectors as the Python parity test — both come from
// test/fixtures/wifi_ssid_validation_cases.json via
// tools/gen-wifi-ssid-cases.py (which emits wifi_ssid_cases.inc).
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       test/host/test_wifi_ssid_validation.cpp -o /tmp/t && /tmp/t

#include <cassert>
#include <cstdio>
#include <cstring>

#include "network/wifi_ssid_validation.h"
#include "network/wifi_connect_plan.h"

#include "wifi_ssid_cases.inc"

static int g_total = 0;
static int g_pass = 0;
static void check(const char* name, bool cond) {
  ++g_total;
  if (cond) { ++g_pass; std::printf("SSIDVAL_PASS %s\n", name); }
  else      { std::printf("SSIDVAL_FAIL %s\n", name); }
}

int main() {
  // ---- shared JSON vectors (identical to the Python parity test) ---------
  for (int i = 0; i < kWifiSsidCaseCount; ++i) {
    const WifiSsidCase& c = kWifiSsidCases[i];
    WifiSsidValidationCode code = validateWifiSsid(c.ssid);
    bool valid = (code == WIFI_SSID_OK);
    char name[160];
    std::snprintf(name, sizeof(name), "vector %d %s (valid=%d code=%s)",
                  i, c.name, valid ? 1 : 0, wifiSsidValidationLabel(code));
    check(name, (valid == c.expectedValid) && (code == c.expectedCode));
  }

  // ---- explicit extra checks beyond the JSON ------------------------------
  // 32-byte boundary (already in JSON, restated for the report).
  check("exactly 32 ascii accepted",
        validateWifiSsid("abcdefghijklmnopqrstuvwxyz012345") == WIFI_SSID_OK);
  check("33 ascii rejected as TOO_LONG",
        validateWifiSsid("abcdefghijklmnopqrstuvwxyz0123456") == WIFI_SSID_ERR_TOO_LONG);
  check("33 byte runtime reason SSID_TOO_LONG",
        ssidReason("abcdefghijklmnopqrstuvwxyz0123456") == SSID_TOO_LONG);

  // runtime `wifi connect Home WiFi` keeps the full SSID (association plan).
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID,
                                            "Home WiFi", false);
    check("runtime open ssid with space: valid",
          p.configurationValid && p.ssidPresent);
    check("runtime open ssid preserved whole",
          p.ssid && strcmp(p.ssid, "Home WiFi") == 0);
    check("runtime open ssid: OPEN security",
          p.securityType == WIFI_SECURITY_OPEN);
    check("runtime open ssid: reason OK", p.reason == WIFI_PLAN_OK);
  }
  // `Home WiFi` must NOT be split into "Home" and never use a WPA password:
  // beginOpen receives the whole string (integration test covers the adapter
  // call; here we prove the plan keeps it intact).
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID,
                                            "Home WiFi", true /* hasPassword */);
    check("runtime open ssid ignores compiled password",
          p.securityType == WIFI_SECURITY_OPEN && !p.passwordPresent);
  }
  // 33-byte runtime SSID must not proceed.
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID,
                                            "abcdefghijklmnopqrstuvwxyz0123456", false);
    check("33 byte runtime: not valid", !p.configurationValid);
    check("33 byte runtime: reason SSID_TOO_LONG", p.reason == SSID_TOO_LONG);
  }

  // plan-level mapping of the other rejections
  check("empty plan reason SSID_NOT_CONFIGURED",
        makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "", false).reason == SSID_NOT_CONFIGURED);
  check("all-space plan reason SSID_NOT_CONFIGURED",
        makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "   ", false).reason == SSID_NOT_CONFIGURED);
  check("template plan reason SSID_INVALID",
        makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "your_wifi_name", false).reason == SSID_INVALID);
  check("control char plan reason SSID_INVALID",
        makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "My\tWiFi", false).reason == SSID_INVALID);

  std::printf("WIFI_SSID_VALIDATION_CASE_TOTAL=%d\n", g_total);
  std::printf("WIFI_SSID_VALIDATION_CASE_PASS=%d\n", g_pass);
  std::printf("WIFI_SSID_VALIDATION_CASE_FAILURE=%d\n", g_total - g_pass);
  return (g_total == g_pass) ? 0 : 1;
}
