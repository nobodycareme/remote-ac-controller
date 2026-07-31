#pragma once
#include "config/feature_gates.h"
/*
 * Campus network static parameters — PUBLIC, non-secret configuration.
 *
 * These values are kept separate from credentials (config/campus_credentials.h)
 * and the TLS settings. They describe the campus network only; they never carry
 * a username, password, cookie, token, or private key.
 *
 * SOURCING THE FOUR MACROS (CAMPUS_SSID / CAMPUS_PORTAL_HOST / CAMPUS_AC_ID /
 * CAMPUS_DOMAIN) — two, mutually exclusive, and ONLY when campus auth is on:
 *
 *   A) PROFILE HEADER (preferred; PlatformIO / Arduino globals / CI) — select a
 *      campus profile at compile time via CAMPUS_PROFILE_HEADER:
 *        -DCAMPUS_PROFILE_HEADER="profiles/xidian.h"
 *      The profile header defines those four macros and, optionally, the portal
 *      TLS pin (see config/campus_tls_pin.h). It never defines a credential.
 *      Example profiles live in config/profiles/ and are named
 *      <campus>.example.h; copy one to a non-example name (git-ignored) to
 *      customise it.
 *
 *   B) FULL EXTERNAL DEFINITION — an external config.h / globals.h already
 *      defines ALL FOUR macros before this header is reached, so we keep them
 *      as-is and define nothing here.
 *
 * There is intentionally NO implicit default profile. If ENABLE_CAMPUS_AUTH=1
 * but neither (A) nor (B) applies, compilation fails with a clear #error so the
 * firmware can never silently auto-target an unspecified campus portal.
 *
 * WHEN CAMPUS AUTH IS COMPILED OUT (ENABLE_CAMPUS_AUTH=0) the four macros are
 * defined as INERT placeholders: empty strings and ac_id 0. Modules that are
 * NOT part of the login path — most notably the captive-portal detector — still
 * report these values, so they must exist for the build to succeed. An empty
 * host cannot address any portal and the detector explicitly refuses to match
 * on it, so this is NOT an implicit default campus profile.
 *
 * Constraints (enforced by policy, not by this header alone):
 *   - SSID is the OPEN campus network (no WPA pre-shared key).
 *   - host is the srun portal host ONLY; the srun base_url uses NO
 *     "/index_8.html" suffix (that hit is only for the INSECURE_PROBE_ONLY
 *     portal-detection path, which never sends credentials).
 *   - ac_id is the campus-confirmed value.
 *   - domain is EMPTY: NO operator suffix (@lt / @yd / @dx) is ever appended.
 *   - The ESP8266 uses its REAL DHCP-assigned IP (never a phone/fixed IP).
 */

#if ENABLE_CAMPUS_AUTH
  #if defined(CAMPUS_PROFILE_HEADER)
    // (A) Profile header selected at compile time.
    #include CAMPUS_PROFILE_HEADER

  #elif defined(CAMPUS_SSID) && defined(CAMPUS_PORTAL_HOST) \
     && defined(CAMPUS_AC_ID) && defined(CAMPUS_DOMAIN)
    // (B) All four supplied externally — keep as-is, define nothing.

  #else
    #error "ENABLE_CAMPUS_AUTH=1 requires CAMPUS_PROFILE_HEADER (or a complete \
external campus config: CAMPUS_SSID, CAMPUS_PORTAL_HOST, CAMPUS_AC_ID, \
CAMPUS_DOMAIN). The build must not silently fall back to any campus profile."
  #endif

#else
  // Campus authentication is compiled OUT. These are inert placeholders, not a
  // default profile: an empty SSID connects to nothing and an empty host
  // matches nothing (portal_detector.cpp guards on sizeof(...) > 1).
  #ifndef CAMPUS_SSID
    #define CAMPUS_SSID        ""
  #endif
  #ifndef CAMPUS_PORTAL_HOST
    #define CAMPUS_PORTAL_HOST ""
  #endif
  #ifndef CAMPUS_AC_ID
    #define CAMPUS_AC_ID       0
  #endif
  #ifndef CAMPUS_DOMAIN
    #define CAMPUS_DOMAIN      ""
  #endif
#endif
