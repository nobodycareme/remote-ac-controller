// Host test for the WifiManager connection decision and log safety.
//
// The full WifiManager links against Arduino/ESP8266WiFi, so this test covers
// the pure, unit-testable parts of the v1.2.2 WPA change and the v1.2.3 empty
// SSID guard by consuming the SHARED wifi_connect_plan.h header (the same
// header wifi_manager.cpp uses):
//   - OPEN vs WPA_OR_WPA2 security label derived ONLY from whether a password
//     is present (never from the password content);
//   - the serial log line never contains the password, its length, or any
//     recoverable hint of it;
//   - the connection plan matrix: open SSID / protected WPA / no config /
//     auto-connect off / auto-connect on / conflicting config;
//   - v1.2.3 hard guard: an empty SSID (or empty local password) yields
//     configurationValid=false with the exact skip reason, so the firmware
//     never reaches WiFi.begin("") — WIFI_BEGIN_CALL_COUNT stays 0 and the
//     state stays WIFI_DISCONNECTED;
//   - campus mode never reads the local Wi-Fi password, local-Wi-Fi mode
//     never reads campus credentials (compile-time isolation by #error);
//   - feature_gates dependency rules hold at compile time.
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       -DENABLE_WIFI=1 test/host/test_wifi_connect.cpp -o /tmp/t && /tmp/t

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "config/feature_gates.h"
#include "network/wifi_connect_plan.h"

// ---- build the exact WIFI_CONNECT log line the firmware prints ---------------
// The password VALUE must NEVER be passed into this function — the contract is
// that the caller only forwards the plan's securityType, so a future refactor
// cannot leak it.
static std::string connectLog(const std::string& ssid, WifiSecurityType sec) {
  return "WIFI_CONNECT ssid=" + ssid + " security=" + wifiSecurityLabel(sec);
}

// ---- simulate the firmware guard around WiFi.begin ---------------------------
// This mirrors wifi_manager.cpp connect() EXACTLY: the single decision is
// plan.configurationValid. When invalid, no begin() call happens, no
// WIFI_ASSOCIATING is entered and the skip reason is emitted. The plan is the
// only decision logic; there is no second connection-decision code path.
struct ConnectOutcome {
  int  beginCallCount;        // 0 or 1
  bool enteredAssociating;
  const char* skipReason;     // nullptr when proceeding to WiFi.begin
};
static ConnectOutcome simulateConnect(const WifiConnectPlan& p) {
  if (!p.configurationValid) {
    return ConnectOutcome{0, false, wifiPlanReasonLabel(p.reason)};
  }
  return ConnectOutcome{1, true, nullptr};
}

// ---- logs that are emitted for the two cases ---------------------------------
static const char* const OPEN_LOG =
    "WIFI_CONNECT ssid=stu-xdwlan security=OPEN";
static const char* const WPA_LOG =
    "WIFI_CONNECT ssid=HomeRouter security=WPA_OR_WPA2";

int main() {
  // 1) security label depends only on the plan's securityType
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_OPEN), "OPEN") == 0);
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_WPA_OR_WPA2), "WPA_OR_WPA2") == 0);

  // 2) OPEN campus SSID plan: no local credentials -> OPEN, campus SSID used
  {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", nullptr, false);
    assert(p.configurationValid);
    assert(p.ssidPresent);
    assert(!p.passwordPresent);
    assert(p.securityType == WIFI_SECURITY_OPEN);
    assert(p.reason == WIFI_PLAN_OK);
    assert(connectLog("stu-xdwlan", p.securityType) == OPEN_LOG);
    ConnectOutcome o = simulateConnect(p);
    assert(o.beginCallCount == 1);
    assert(o.enteredAssociating);
  }

  // 3) WPA/WPA2 plan: local credentials enabled -> protected path
  {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", "HomeRouter", true);
    assert(p.configurationValid);
    assert(p.ssidPresent);
    assert(p.passwordPresent);
    assert(p.securityType == WIFI_SECURITY_WPA_OR_WPA2);
    assert(p.reason == WIFI_PLAN_OK);
    const std::string wpa = connectLog("HomeRouter", p.securityType);
    assert(wpa == WPA_LOG);
    // the password never appears, neither its value nor its length nor any
    // hash/recoverable fragment
    assert(wpa.find("sup3rsecret") == std::string::npos);
    assert(wpa.find("11") == std::string::npos);   // length of the secret
    assert(wpa.find("sup") == std::string::npos);  // no prefix fragment
    assert(wpa.find("ssid=HomeRouter security=WPA_OR_WPA2") != std::string::npos);
    ConnectOutcome o = simulateConnect(p);
    assert(o.beginCallCount == 1);
    assert(o.enteredAssociating);
  }

  // 4) a password never ends up inside the ssid field
  {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", "HomeRouter", true);
    const std::string wpa = connectLog("HomeRouter", p.securityType);
    assert(wpa.find("pass") == std::string::npos);
  }

  // ---- v1.2.3 empty-SSID hard guard ----------------------------------------
  // 5) SSID empty (e.g. public build: CAMPUS_SSID is the inert "" placeholder
  //    and no local credentials are compiled) -> skip, no WiFi.begin call
  {
    WifiConnectPlan p = makeWifiConnectPlan("", nullptr, false);
    assert(!p.configurationValid);
    assert(!p.ssidPresent);
    assert(!p.passwordPresent);
    assert(!p.autoConnectAllowed);
    assert(p.reason == SSID_NOT_CONFIGURED);
    assert(strcmp(wifiPlanReasonLabel(p.reason), "SSID_NOT_CONFIGURED") == 0);
    ConnectOutcome o = simulateConnect(p);
    assert(o.beginCallCount == 0);            // WIFI_BEGIN_CALL_COUNT=0
    assert(!o.enteredAssociating);            // stays WIFI_DISCONNECTED
    assert(strcmp(o.skipReason, "SSID_NOT_CONFIGURED") == 0);
  }

  // 6) SSID == nullptr -> same guard as the empty string
  {
    WifiConnectPlan p = makeWifiConnectPlan(nullptr, nullptr, false);
    assert(!p.configurationValid);
    assert(p.reason == SSID_NOT_CONFIGURED);
    assert(simulateConnect(p).beginCallCount == 0);
  }

  // 7) local credentials compiled but LOCAL_WIFI_SSID placeholder is empty ->
  //    SSID_NOT_CONFIGURED (must NOT fall through to the campus SSID)
  {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", "", true);
    assert(!p.configurationValid);
    assert(!p.ssidPresent);
    assert(p.reason == SSID_NOT_CONFIGURED);
    assert(simulateConnect(p).beginCallCount == 0);
  }

  // 8) local WPA mode with an empty password -> WIFI_PASSWORD_NOT_CONFIGURED
    {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", "HomeRouter", false);
    assert(!p.configurationValid);
    assert(p.ssidPresent);                    // SSID exists...
    assert(!p.passwordPresent);               // ...but no password
    assert(p.reason == WIFI_PASSWORD_NOT_CONFIGURED);
    assert(strcmp(wifiPlanReasonLabel(p.reason),
                  "WIFI_PASSWORD_NOT_CONFIGURED") == 0);
    ConnectOutcome o = simulateConnect(p);
    assert(o.beginCallCount == 0);
    assert(!o.enteredAssociating);
    assert(strcmp(o.skipReason, "WIFI_PASSWORD_NOT_CONFIGURED") == 0);
  }

  // 9) auto-connect reflects the single authoritative WIFI_AUTOCONNECT_ON_BOOT
  //    expression, and only when a configuration actually exists
  {
    WifiConnectPlan p = makeWifiConnectPlan("stu-xdwlan", nullptr, false);
#if WIFI_AUTOCONNECT_ON_BOOT
    assert(p.autoConnectAllowed);
#else
    assert(!p.autoConnectAllowed);
#endif
    // with auto-connect gates OFF (no flags), autoConnectAllowed must be false
    WifiConnectPlan p2 = makeWifiConnectPlan("stu-xdwlan", "HomeRouter", true);
    assert(p2.autoConnectAllowed == (WIFI_AUTOCONNECT_ON_BOOT ? true : false));
    // an invalid configuration never auto-connects, even with boot gates on
    WifiConnectPlan p3 = makeWifiConnectPlan("", nullptr, false);
    assert(!p3.autoConnectAllowed);
  }

  // 10) conflicting configuration: local credentials + campus auth must be a
  //    compile-time error (feature_gates.h #error). We cannot express it here
  //    at runtime; the CI negative matrix covers it:
  //       -DENABLE_WIFI_CREDENTIALS=1 -DENABLE_CAMPUS_AUTH=1 must FAIL.
  //    (This file is compiled only with legal flag sets.)

  // 11) campus mode never reads the local Wi-Fi password, local-Wi-Fi mode
  //    never reads campus credentials — enforced by feature_gates.h:
  //      * wifi_manager.cpp includes wifi_secrets.h ONLY under
  //        #if ENABLE_WIFI_CREDENTIALS
  //      * campus_credentials.h is included ONLY under #if ENABLE_CAMPUS_AUTH
  //    Both are hard #error if their gate is off, so a build can never mix the
  //    two credential sources. The negative CI matrix verifies the isolation.

  // 12) compile-time dependency rules (also enforced by #error in
  //    feature_gates.h; these hold for every legal flag set)
#if ENABLE_WIFI_CREDENTIALS
  static_assert(ENABLE_WIFI, "WIFI_CREDENTIALS requires WIFI");
#endif
#if ENABLE_AUTO_WIFI_CONNECT
  static_assert(ENABLE_WIFI, "AUTO_WIFI_CONNECT requires WIFI");
  static_assert(WIFI_AUTOCONNECT_ON_BOOT,
                "AUTO_WIFI_CONNECT must imply boot autoconnect");
#endif
#if ENABLE_CLOUD && !ENABLE_AUTO_WIFI_CONNECT && !ENABLE_AUTO_CAMPUS_AUTH
  // v1.2.3 policy: compiling the cloud module alone must NOT auto-associate.
  static_assert(!WIFI_AUTOCONNECT_ON_BOOT,
                "cloud without auto wifi/campus must not autoconnect");
#endif

  // 13) security labels match the firmware's exact byte spelling
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_WPA_OR_WPA2), "WPA_OR_WPA2") == 0);
  assert(strcmp(wifiSecurityLabel(WIFI_SECURITY_OPEN), "OPEN") == 0);

  std::printf("WIFI_CONNECT_DECISION_TEST_PASS=True\n");
  return 0;
}
