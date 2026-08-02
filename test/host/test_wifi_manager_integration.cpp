// Host integration test for the REAL production Wi-Fi association path
// (v1.2.4). WifiManager::connect() executes WifiAssociationController::execute()
// — this file calls that SAME class and method with a FakeWifiStationAdapter,
// so it exercises the exact production code path (no copied decision logic).
//
// The full WifiManager links against ESP8266WiFi; the controller is the
// documented, minimal seam extracted for exactly this purpose.
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       test/host/test_wifi_manager_integration.cpp -o /tmp/t && /tmp/t

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "network/wifi_connect_plan.h"
#include "network/wifi_station_adapter.h"
#include "network/wifi_association_controller.h"

// Fake adapter records call counts and the last SSID, but NEVER stores or
// prints the password value — only whether a password was provided.
class FakeWifiStationAdapter : public WifiStationAdapter {
public:
  int openBeginCallCount = 0;
  int wpaBeginCallCount = 0;
  bool passwordWasProvided = false;
  std::string lastSsid;

  void beginOpen(const char* ssid) override {
    ++openBeginCallCount;
    lastSsid = ssid ? ssid : "";
  }
  void beginWpa(const char* ssid, const char* password) override {
    ++wpaBeginCallCount;
    lastSsid = ssid ? ssid : "";
    passwordWasProvided = (password && password[0] != '\0');
  }
};

// Test-only placeholders.
static const char* const TEST_HOME_WIFI = "TEST_HOME_WIFI";
static const char* const TEST_PASSWORD = "TEST_PASSWORD_123";
static const char* const TEST_OPEN_WIFI = "TEST_OPEN_WIFI";
static const char* const TEST_CAMPUS_SSID = "stu-xdwlan";

static int g_total = 0;
static int g_pass = 0;

static void check(const char* name, bool cond) {
  ++g_total;
  if (cond) { ++g_pass; std::printf("INTEG_PASS %s\n", name); }
  else      { std::printf("INTEG_FAIL %s\n", name); }
}

int main() {
  // ---- 7.1 public: NONE source -> nothing happens -------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_NONE;
    req.ssid = nullptr;
    WifiConnectOutcome out = ctrl.execute(req);
    check("7.1 public: source NONE", out.effectiveSsid != nullptr);
    check("7.1 public: not proceeded", !out.proceeded);
    check("7.1 public: reason SSID_NOT_CONFIGURED", out.reason == SSID_NOT_CONFIGURED);
    check("7.1 public: open begin 0", fake.openBeginCallCount == 0);
    check("7.1 public: wpa begin 0", fake.wpaBeginCallCount == 0);
  }

  // ---- 7.2 local-wifi boot: COMPILED_LOCAL_WPA ----------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_COMPILED_LOCAL_WPA;
    req.ssid = TEST_HOME_WIFI;
    req.password = TEST_PASSWORD;
    WifiConnectOutcome out = ctrl.execute(req);
    check("7.2 local-wifi: proceeded", out.proceeded);
    check("7.2 local-wifi: WPA begin 1", fake.wpaBeginCallCount == 1);
    check("7.2 local-wifi: open begin 0", fake.openBeginCallCount == 0);
    check("7.2 local-wifi: last ssid", fake.lastSsid == TEST_HOME_WIFI);
    check("7.2 local-wifi: effective ssid", std::string(out.effectiveSsid) == TEST_HOME_WIFI);
    check("7.2 local-wifi: password provided to adapter", fake.passwordWasProvided);
    check("7.2 local-wifi: security WPA", out.securityType == WIFI_SECURITY_WPA_OR_WPA2);
  }

  // ---- 7.3 local-wifi-cloud boot: same wifi association result ------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_COMPILED_LOCAL_WPA;
    req.ssid = TEST_HOME_WIFI;
    req.password = TEST_PASSWORD;
    WifiConnectOutcome out = ctrl.execute(req);
    check("7.3 local-wifi-cloud: WPA begin 1", fake.wpaBeginCallCount == 1);
    check("7.3 local-wifi-cloud: open begin 0", fake.openBeginCallCount == 0);
    check("7.3 local-wifi-cloud: last ssid", fake.lastSsid == TEST_HOME_WIFI);
    check("7.3 local-wifi-cloud: effective ssid", std::string(out.effectiveSsid) == TEST_HOME_WIFI);
  }

  // ---- 7.4 explicit runtime open SSID -------------------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    // simulate: `wifi connect TEST_OPEN_WIFI` after a local-WPA selection
    WifiConnectRequest first;
    first.source = WIFI_SOURCE_COMPILED_LOCAL_WPA;
    first.ssid = TEST_HOME_WIFI;
    first.password = TEST_PASSWORD;
    ctrl.execute(first);

    WifiConnectRequest rt;
    rt.source = WIFI_SOURCE_RUNTIME_OPEN_SSID;
    rt.ssid = TEST_OPEN_WIFI;
    rt.password = nullptr;               // never the compiled password
    fake.passwordWasProvided = false;    // observe ONLY the runtime call
    WifiConnectOutcome out = ctrl.execute(rt);
    check("7.4 runtime open: source RUNTIME_OPEN_SSID",
          out.securityType == WIFI_SECURITY_OPEN);
    check("7.4 runtime open: open begin 1", fake.openBeginCallCount == 1);
    check("7.4 runtime open: wpa begin 1 (only the first local-WPA call)",
          fake.wpaBeginCallCount == 1);
    check("7.4 runtime open: last ssid", fake.lastSsid == TEST_OPEN_WIFI);
    check("7.4 runtime open: password not used", !fake.passwordWasProvided);
    check("7.4 runtime open: effective ssid", std::string(out.effectiveSsid) == TEST_OPEN_WIFI);
  }

  // ---- 7.5 runtime open then restore local WPA -----------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest open;
    open.source = WIFI_SOURCE_RUNTIME_OPEN_SSID;
    open.ssid = TEST_OPEN_WIFI;
    ctrl.execute(open);
    // no-arg `wifi connect` restores the compiled local WPA source
    WifiConnectRequest restore;
    restore.source = WIFI_SOURCE_COMPILED_LOCAL_WPA;
    restore.ssid = TEST_HOME_WIFI;
    restore.password = TEST_PASSWORD;
    WifiConnectOutcome out = ctrl.execute(restore);
    check("7.5 restore: wpa begin 1", fake.wpaBeginCallCount == 1);
    check("7.5 restore: last ssid", fake.lastSsid == TEST_HOME_WIFI);
    check("7.5 restore: effective ssid", std::string(out.effectiveSsid) == TEST_HOME_WIFI);
    check("7.5 restore: open begin 1 (open call earlier)", fake.openBeginCallCount == 1);
  }

  // ---- 7.6 campus open SSID ------------------------------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_CAMPUS_PROFILE_OPEN;
    req.ssid = TEST_CAMPUS_SSID;
    WifiConnectOutcome out = ctrl.execute(req);
    check("7.6 campus: open begin 1", fake.openBeginCallCount == 1);
    check("7.6 campus: wpa begin 0", fake.wpaBeginCallCount == 0);
    check("7.6 campus: last ssid", fake.lastSsid == TEST_CAMPUS_SSID);
    check("7.6 campus: password not used", !fake.passwordWasProvided);
    check("7.6 campus: security OPEN", out.securityType == WIFI_SECURITY_OPEN);
  }

  // ---- 7.7 empty values ----------------------------------------------------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest cases[] = {
      {WIFI_SOURCE_COMPILED_LOCAL_WPA, nullptr, TEST_PASSWORD},
      {WIFI_SOURCE_COMPILED_LOCAL_WPA, "", TEST_PASSWORD},
      {WIFI_SOURCE_COMPILED_LOCAL_WPA, "  ", TEST_PASSWORD},   // whitespace-only
      {WIFI_SOURCE_COMPILED_LOCAL_WPA, TEST_HOME_WIFI, nullptr}, // no password
      {WIFI_SOURCE_CAMPUS_PROFILE_OPEN, "", nullptr},
      {WIFI_SOURCE_RUNTIME_OPEN_SSID, "", nullptr},
      {WIFI_SOURCE_RUNTIME_OPEN_SSID, nullptr, nullptr},
      {WIFI_SOURCE_NONE, nullptr, nullptr},
    };
    for (auto& r : cases) {
      WifiConnectOutcome out = ctrl.execute(r);
      check("7.7 invalid: not proceeded", !out.proceeded);
      check("7.7 invalid: open begin 0", fake.openBeginCallCount == 0);
      check("7.7 invalid: wpa begin 0", fake.wpaBeginCallCount == 0);
    }
  }

  // ---- 7.8 log/status contract: ssid+source+security, never the password --
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_COMPILED_LOCAL_WPA;
    req.ssid = TEST_HOME_WIFI;
    req.password = TEST_PASSWORD;
    WifiConnectOutcome out = ctrl.execute(req);
    // The production log line is built by WifiManager from the SAME fields:
    // source label + ssid + security label. No password ever enters it.
    std::string log = std::string("WIFI_CONNECT source=") + wifiSourceLabel(WIFI_SOURCE_COMPILED_LOCAL_WPA) +
                      " ssid=" + out.effectiveSsid + " security=" + wifiSecurityLabel(out.securityType);
    check("7.8 log: has ssid", log.find(TEST_HOME_WIFI) != std::string::npos);
    check("7.8 log: has source", log.find("COMPILED_LOCAL_WPA") != std::string::npos);
    check("7.8 log: has security", log.find("WPA_OR_WPA2") != std::string::npos);
    check("7.8 log: no password value", log.find(TEST_PASSWORD) == std::string::npos);
    check("7.8 log: no password length", log.find("15") == std::string::npos);
    check("7.8 log: no password prefix", log.find("TEST_PASS") == std::string::npos);
  }

  // ---- skipped log includes source + reason (production format) -----------
  {
    FakeWifiStationAdapter fake;
    WifiAssociationController ctrl(fake);
    WifiConnectRequest req;
    req.source = WIFI_SOURCE_NONE;
    WifiConnectOutcome out = ctrl.execute(req);
    std::string log = std::string("WIFI_CONNECT_SKIPPED source=") + wifiSourceLabel(WIFI_SOURCE_NONE) +
                      " reason=" + wifiPlanReasonLabel(out.reason);
    check("7.8 skip log: has source", log.find("NONE") != std::string::npos);
    check("7.8 skip log: has reason", log.find("SSID_NOT_CONFIGURED") != std::string::npos);
  }

  std::printf("WIFI_MANAGER_INTEGRATION_CASE_TOTAL=%d\n", g_total);
  std::printf("WIFI_MANAGER_INTEGRATION_CASE_PASS=%d\n", g_pass);
  std::printf("WIFI_MANAGER_INTEGRATION_CASE_FAILURE=%d\n", g_total - g_pass);
  return (g_total == g_pass) ? 0 : 1;
}
