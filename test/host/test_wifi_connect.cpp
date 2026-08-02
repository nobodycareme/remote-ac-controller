// Host test for the PURE WifiConnectPlan decision logic (v1.2.4 source model).
//
// This file only validates the PLAN generation: which source maps to which
// begin() overload, whether a configuration is valid, and the reason when it
// is not. The REAL association execution (adapter dispatch, state
// transitions, effective SSID sync) is covered by
// test/host/test_wifi_manager_integration.cpp using the same production
// WifiAssociationController that WifiManager::connect() calls.
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       [-D<flags>] test/host/test_wifi_connect.cpp -o /tmp/t && /tmp/t

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "config/feature_gates.h"
#include "network/wifi_connect_plan.h"

// ---- build the exact WIFI_CONNECT log line the firmware prints ---------------
// The password VALUE must NEVER be passed into this function — the contract is
// that the caller only forwards the plan's securityType and source, so a
// future refactor cannot leak it.
static std::string connectLog(WifiConnectionSource src, const std::string& ssid,
                              WifiSecurityType sec) {
  return std::string("WIFI_CONNECT source=") + wifiSourceLabel(src) +
         " ssid=" + ssid + " security=" + wifiSecurityLabel(sec);
}

int main() {
  // 1) labels
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_OPEN), "OPEN") == 0);
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_WPA_OR_WPA2), "WPA_OR_WPA2") == 0);
  assert(strcmp(wifiSourceLabel(WIFI_SOURCE_NONE), "NONE") == 0);
  assert(strcmp(wifiSourceLabel(WIFI_SOURCE_COMPILED_LOCAL_WPA), "COMPILED_LOCAL_WPA") == 0);
  assert(strcmp(wifiSourceLabel(WIFI_SOURCE_CAMPUS_PROFILE_OPEN), "CAMPUS_PROFILE_OPEN") == 0);
  assert(strcmp(wifiSourceLabel(WIFI_SOURCE_RUNTIME_OPEN_SSID), "RUNTIME_OPEN_SSID") == 0);
  assert(strcmp(wifiPlanReasonLabel(SSID_NOT_CONFIGURED), "SSID_NOT_CONFIGURED") == 0);
  assert(strcmp(wifiPlanReasonLabel(WIFI_PASSWORD_NOT_CONFIGURED), "WIFI_PASSWORD_NOT_CONFIGURED") == 0);

  // 2) COMPILED_LOCAL_WPA with SSID + password -> valid WPA
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_COMPILED_LOCAL_WPA, "HomeRouter", true);
    assert(p.source == WIFI_SOURCE_COMPILED_LOCAL_WPA);
    assert(p.configurationValid);
    assert(p.ssidPresent);
    assert(p.passwordPresent);
    assert(p.securityType == WIFI_SECURITY_WPA_OR_WPA2);
    assert(p.reason == WIFI_PLAN_OK);
    assert(strcmp(p.ssid, "HomeRouter") == 0);
    const std::string wpa = connectLog(WIFI_SOURCE_COMPILED_LOCAL_WPA, "HomeRouter", p.securityType);
    assert(wpa.find("WPA_OR_WPA2") != std::string::npos);
    // password never appears, neither value nor length nor prefix
    assert(wpa.find("sup3rsecret") == std::string::npos);
    assert(wpa.find("11") == std::string::npos);
    assert(wpa.find("sup") == std::string::npos);
  }

  // 3) COMPILED_LOCAL_WPA with SSID but NO password -> WIFI_PASSWORD_NOT_CONFIGURED
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_COMPILED_LOCAL_WPA, "HomeRouter", false);
    assert(!p.configurationValid);
    assert(p.ssidPresent);
    assert(!p.passwordPresent);
    assert(p.reason == WIFI_PASSWORD_NOT_CONFIGURED);
  }

  // 4) COMPILED_LOCAL_WPA with EMPTY SSID -> SSID_NOT_CONFIGURED
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_COMPILED_LOCAL_WPA, "", true);
    assert(!p.configurationValid);
    assert(!p.ssidPresent);
    assert(p.reason == SSID_NOT_CONFIGURED);
  }

  // 5) CAMPUS_PROFILE_OPEN with SSID -> OPEN, no password
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_CAMPUS_PROFILE_OPEN, "stu-xdwlan", false);
    assert(p.configurationValid);
    assert(p.ssidPresent);
    assert(!p.passwordPresent);
    assert(p.securityType == WIFI_SECURITY_OPEN);
    assert(p.reason == WIFI_PLAN_OK);
    assert(strcmp(p.ssid, "stu-xdwlan") == 0);
    assert(connectLog(WIFI_SOURCE_CAMPUS_PROFILE_OPEN, "stu-xdwlan", p.securityType)
               .find("security=OPEN") != std::string::npos);
  }

  // 6) CAMPUS_PROFILE_OPEN with empty SSID -> SSID_NOT_CONFIGURED
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_CAMPUS_PROFILE_OPEN, "", false);
    assert(!p.configurationValid);
    assert(p.reason == SSID_NOT_CONFIGURED);
  }

  // 7) RUNTIME_OPEN_SSID with an explicit SSID -> OPEN; a compiled password
  //    is NEVER consulted, so passing hasPassword=true must not change the
  //    security type (runtime selection wins over the local-WPA macro).
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "TEST_OPEN_WIFI", true);
    assert(p.configurationValid);
    assert(p.ssidPresent);
    assert(!p.passwordPresent);                 // never uses the compiled password
    assert(p.securityType == WIFI_SECURITY_OPEN);
    assert(p.reason == WIFI_PLAN_OK);
    assert(strcmp(p.ssid, "TEST_OPEN_WIFI") == 0);
    WifiConnectPlan p2 = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "TEST_OPEN_WIFI", false);
    assert(p2.securityType == WIFI_SECURITY_OPEN);
    assert(p2.configurationValid);
  }

  // 8) RUNTIME_OPEN_SSID with an empty SSID -> SSID_NOT_CONFIGURED
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, "", false);
    assert(!p.configurationValid);
    assert(p.reason == SSID_NOT_CONFIGURED);
    WifiConnectPlan p2 = makeWifiConnectPlan(WIFI_SOURCE_RUNTIME_OPEN_SSID, nullptr, false);
    assert(!p2.configurationValid);
    assert(p2.reason == SSID_NOT_CONFIGURED);
  }

  // 9) WIFI_SOURCE_NONE -> never valid
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_NONE, "any-ssid", false);
    assert(!p.configurationValid);
    assert(p.reason == SSID_NOT_CONFIGURED);
  }

  // 10) autoConnectAllowed mirrors WIFI_AUTOCONNECT_ON_BOOT and requires a
  //     valid configuration
  {
    WifiConnectPlan p = makeWifiConnectPlan(WIFI_SOURCE_COMPILED_LOCAL_WPA, "HomeRouter", true);
    assert(p.autoConnectAllowed == (WIFI_AUTOCONNECT_ON_BOOT ? true : false));
    WifiConnectPlan bad = makeWifiConnectPlan(WIFI_SOURCE_NONE, "", false);
    assert(!bad.autoConnectAllowed);
  }

  // 11) compile-time dependency rules
#if ENABLE_WIFI_CREDENTIALS
  static_assert(ENABLE_WIFI, "WIFI_CREDENTIALS requires WIFI");
#endif
#if ENABLE_AUTO_WIFI_CONNECT
  static_assert(ENABLE_WIFI, "AUTO_WIFI_CONNECT requires WIFI");
  static_assert(WIFI_AUTOCONNECT_ON_BOOT, "AUTO_WIFI_CONNECT must imply boot autoconnect");
#endif
#if ENABLE_CLOUD && !ENABLE_AUTO_WIFI_CONNECT && !ENABLE_AUTO_CAMPUS_AUTH
  static_assert(!WIFI_AUTOCONNECT_ON_BOOT,
                "cloud without auto wifi/campus must not autoconnect");
#endif

  std::printf("WIFI_CONNECT_PLAN_TEST_PASS=True\n");
  return 0;
}
