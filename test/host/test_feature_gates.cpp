// Host compile-time test for feature_gates.h derived predicates.
//
// This file is compiled by the `host-tests` CI job under several legal flag
// combinations. Every legal combination MUST satisfy the invariants below; if
// feature_gates.h ever mis-derives a predicate, the compilation fails here.
//
// Illegal combinations (e.g. ENABLE_CAMPUS_AUTH=1 with ENABLE_WIFI=0) are NOT
// compiled here — they are exercised as NEGATIVE tests by the CI script, which
// expects them to fail compilation with the #error from feature_gates.h.
//
//   g++ -std=c++11 -I firmware/shared/RemoteACCore/src \
//       [-DENABLE_WIFI=1 ...] \
//       test/host/test_feature_gates.cpp -o /tmp/t && /tmp/t

#include "config/feature_gates.h"

// ---- Invariants that hold for ANY legal flag combination ---------------------
static_assert(ENABLE_NETWORK_STACK == ENABLE_WIFI,
              "ENABLE_NETWORK_STACK must equal ENABLE_WIFI");

static_assert(CAMPUS_AUTH_IS_AUTOMATIC ==
                  (ENABLE_CAMPUS_AUTH && ENABLE_AUTO_CAMPUS_AUTH),
              "CAMPUS_AUTH_IS_AUTOMATIC must equal (campus && auto)");

static_assert(WIFI_AUTOCONNECT_ON_BOOT ==
                  (ENABLE_WIFI && (ENABLE_CLOUD || ENABLE_AUTO_CAMPUS_AUTH)),
              "WIFI_AUTOCONNECT_ON_BOOT predicate mismatch");

// ---- Build profile string matches the chosen axis ---------------------------
#if ENABLE_CLOUD
static_assert(__builtin_strcmp(BUILD_PROFILE_NET, "cloud") == 0,
              "profile should be cloud when ENABLE_CLOUD");
#elif ENABLE_CAMPUS_AUTH
static_assert(__builtin_strcmp(BUILD_PROFILE_NET, "campus") == 0,
              "profile should be campus when ENABLE_CAMPUS_AUTH");
#elif ENABLE_WIFI
static_assert(__builtin_strcmp(BUILD_PROFILE_NET, "wifi") == 0,
              "profile should be wifi when only ENABLE_WIFI");
#else
static_assert(__builtin_strcmp(BUILD_PROFILE_NET, "offline") == 0,
              "profile should be offline when nothing enabled");
#endif

// ---- Campus authentication is DECOUPLED from the cloud ----------------------
// Regression guard for the pre-1.0 defect described at the top of
// feature_gates.h: Wi-Fi and campus authentication used to be chained to
// ENABLE_CLOUD, so a device could not authenticate to a campus network without
// also speaking MQTT. Each assertion below must hold for its flag set no matter
// what ENABLE_CLOUD is.

#if ENABLE_CAMPUS_AUTH && ENABLE_AUTO_CAMPUS_AUTH
static_assert(CAMPUS_AUTH_IS_AUTOMATIC,
              "automatic campus auth must not require ENABLE_CLOUD");
static_assert(WIFI_AUTOCONNECT_ON_BOOT,
              "unattended campus auth must bring the link up without the cloud");
#endif

#if ENABLE_CLOUD
static_assert(WIFI_AUTOCONNECT_ON_BOOT,
              "cloud builds autoconnect regardless of campus authentication");
#endif

#if !ENABLE_CLOUD && !ENABLE_AUTO_CAMPUS_AUTH
static_assert(!WIFI_AUTOCONNECT_ON_BOOT,
              "offline-first default: no autoconnect without cloud or auto-auth");
#endif

#if ENABLE_CAMPUS_AUTH && !ENABLE_CLOUD
static_assert(__builtin_strcmp(BUILD_PROFILE_NET, "campus") == 0,
              "a campus-only build must not report itself as a cloud build");
static_assert(ENABLE_NETWORK_STACK,
              "campus-only build still needs the network stack");
#endif

// The network stack belongs to Wi-Fi, never to the cloud.
static_assert(ENABLE_NETWORK_STACK == ENABLE_WIFI,
              "ENABLE_NETWORK_STACK must not depend on ENABLE_CLOUD");

int main() {
  // All checks are static_asserts; reaching here means they passed.
  return 0;
}
