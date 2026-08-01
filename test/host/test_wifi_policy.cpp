// Host test for the v1.2.3 boot-time Wi-Fi auto-connect policy matrix.
//
// WIFI_AUTOCONNECT_ON_BOOT must be driven ONLY by features that carry a
// concrete SSID source (ENABLE_AUTO_WIFI_CONNECT with wifi_secrets.h, or
// ENABLE_AUTO_CAMPUS_AUTH with the campus SSID). A plain ENABLE_CLOUD build
// compiles the cloud module but provides NO SSID — it must never
// auto-associate, and never reach WiFi.begin("").
//
// The CI matrix compiles this file once per profile semantics with the
// -DV123_CASE_<id> macro; the LITERAL expected values below are the policy
// spec, and the single authoritative expression (feature_gates.h) is the
// value under test. Each case also verifies the plan agrees
// (autoConnectAllowed == WIFI_AUTOCONNECT_ON_BOOT for a valid config).
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       -DENABLE_WIFI=1 -DENABLE_CLOUD=1 -DV123_CASE_PUBLIC \
//       test/host/test_wifi_policy.cpp -o /tmp/tp && /tmp/tp

#include <cassert>
#include <cstdio>

#include "config/feature_gates.h"
#include "network/wifi_connect_plan.h"

static int runCase(const char* name, int expected) {
  const int actual = WIFI_AUTOCONNECT_ON_BOOT ? 1 : 0;
  std::printf("WIFI_AUTOCONNECT_POLICY_CASE=%s expected=%d actual=%d\n",
              name, expected, actual);
  // plan agreement: for a valid configuration the plan must mirror the gate
  const WifiConnectPlan p = makeWifiConnectPlan("any-ssid", nullptr, false);
  assert(p.autoConnectAllowed == (actual ? true : false));
  if (actual != expected) {
    std::printf("WIFI_AUTOCONNECT_POLICY_CASE_FAIL=%s\n", name);
    return 1;
  }
  std::printf("WIFI_AUTOCONNECT_POLICY_CASE_PASS=%s\n", name);
  return 0;
}

int main() {
#if defined(V123_CASE_PUBLIC)
  return runCase("public", 0);                  // cloud on, no auto flags
#elif defined(V123_CASE_PUBLIC_CLOUD_EXAMPLE)
  return runCase("public-cloud-example", 0);    // cloud on, no auto flags
#elif defined(V123_CASE_LOCAL_WIFI)
  return runCase("local-wifi", 1);              // wifi creds + auto wifi
#elif defined(V123_CASE_LOCAL_WIFI_CLOUD)
  return runCase("local-wifi-cloud", 1);        // wifi creds + auto wifi + cloud
#elif defined(V123_CASE_LOCAL_CAMPUS_EXAMPLE)
  return runCase("local-campus-example", 0);    // campus compiled, AUTO=0
#elif defined(V123_CASE_CAMPUS_AUTO)
  return runCase("campus-auto-live", 1);        // AUTO=1 + LIVE=1
#elif defined(V123_CASE_WIFI_OFF)
  return runCase("wifi-off", 0);                // ENABLE_WIFI=0
#else
  #error "test_wifi_policy.cpp requires exactly one -DV123_CASE_<id> macro"
#endif
}
