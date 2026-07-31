// Host test for the PUBLIC campus profile headers.
//
// Purpose
// -------
// A campus profile is the only place where a campus network is described, and
// it is published. This test proves three things about whatever profile the
// build selected, without a board, a network, or a credential:
//
//   1. the profile defines exactly the four public parameters and no credential;
//   2. the values obey the srun rules the firmware relies on (host only, never a
//      URL or a path; empty operator suffix; positive ac_id);
//   3. when the Xidian example profile is selected, the four values are exactly
//      the verified ones (XIDIAN_PROFILE_PUBLIC_PARAMETERS_VERIFIED, 2026-07-31).
//
// Build (see the host-tests CI job):
//   g++ -std=c++11 -I firmware/shared/RemoteACCore/src \
//       -DENABLE_WIFI=1 -DENABLE_CAMPUS_AUTH=1 \
//       '-DCAMPUS_PROFILE_HEADER="profiles/xidian.example.h"' -DEXPECT_XIDIAN=1 \
//       test/host/test_campus_profiles.cpp -o /tmp/t && /tmp/t

#include "config/campus_config.h"

#include <cstdio>
#include <cstring>

#if !ENABLE_CAMPUS_AUTH
#error "test_campus_profiles.cpp must be compiled with ENABLE_CAMPUS_AUTH=1"
#endif

// ---- 1. The profile must carry public parameters only -----------------------
#if !defined(CAMPUS_SSID) || !defined(CAMPUS_PORTAL_HOST) || \
    !defined(CAMPUS_AC_ID) || !defined(CAMPUS_DOMAIN)
#error "the selected campus profile does not define the four public parameters"
#endif

#if defined(CAMPUS_USERNAME) || defined(CAMPUS_PASSWORD) || \
    defined(CAMPUS_TOKEN) || defined(CAMPUS_COOKIE)
#error "a campus profile must never define a credential macro"
#endif

// ---- 2. srun rules that hold for EVERY profile ------------------------------
// C++11-conformant constexpr scan (no compiler builtins required).
constexpr bool contains_char(const char* s, char c) {
  return *s == '\0' ? false : (*s == c ? true : contains_char(s + 1, c));
}

static_assert(sizeof(CAMPUS_SSID) > 1, "CAMPUS_SSID must not be empty");
static_assert(sizeof(CAMPUS_PORTAL_HOST) > 1,
              "CAMPUS_PORTAL_HOST must not be empty");
static_assert(CAMPUS_AC_ID > 0, "CAMPUS_AC_ID must be a positive integer");

// The portal host is a HOST, not a URL and not a path. The srun base_url is
// derived as https://<host> with no suffix; "/index_8.html" belongs to the
// read-only portal probe, which never sends credentials.
static_assert(!contains_char(CAMPUS_PORTAL_HOST, '/'),
              "CAMPUS_PORTAL_HOST must be a bare host (no scheme, no path)");
static_assert(!contains_char(CAMPUS_PORTAL_HOST, ':'),
              "CAMPUS_PORTAL_HOST must not carry a scheme or a port");

// No operator suffix is ever appended to the srun `info` field.
static_assert(!contains_char(CAMPUS_DOMAIN, '@'),
              "CAMPUS_DOMAIN must not contain '@'");

// ---- 3. Verified Xidian values ----------------------------------------------
#ifdef EXPECT_XIDIAN
static_assert(__builtin_strcmp(CAMPUS_SSID, "stu-xdwlan") == 0,
              "Xidian profile: SSID must be the open stu-xdwlan network");
static_assert(__builtin_strcmp(CAMPUS_PORTAL_HOST, "w.xidian.edu.cn") == 0,
              "Xidian profile: portal host must be w.xidian.edu.cn");
static_assert(CAMPUS_AC_ID == 8, "Xidian profile: ac_id must be 8");
static_assert(__builtin_strcmp(CAMPUS_DOMAIN, "") == 0,
              "Xidian profile: the operator domain suffix must be empty");
#endif

int main() {
  std::printf("CAMPUS_SSID=%s\n", CAMPUS_SSID);
  std::printf("CAMPUS_PORTAL_HOST=%s\n", CAMPUS_PORTAL_HOST);
  std::printf("CAMPUS_AC_ID=%d\n", (int)CAMPUS_AC_ID);
  std::printf("CAMPUS_DOMAIN=%s\n",
              std::strlen(CAMPUS_DOMAIN) == 0 ? "(empty)" : CAMPUS_DOMAIN);
  std::printf("CAMPUS_PROFILE_CONTRACT_PASS=True\n");
  return 0;
}
