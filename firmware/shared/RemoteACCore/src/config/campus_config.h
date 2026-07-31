#pragma once
#include "config/feature_gates.h"
/*
 * Campus network static parameters — PUBLIC, non-secret configuration.
 *
 * These values are kept separate from credentials (config/campus_credentials.h)
 * and the TLS pin (config/campus_tls_pin.h).
 *
 * SOURCING THE FOUR MACROS (CAMPUS_SSID / CAMPUS_PORTAL_HOST / CAMPUS_AC_ID /
 * CAMPUS_DOMAIN) — three, mutually exclusive:
 *
 *   A) PROFILE HEADER (preferred; PlatformIO / CI / globals) — select a campus
 *      profile at compile time:
 *        -DCAMPUS_PROFILE_HEADER="profiles/xidian.example.h"
 *      The profile header defines exactly those four macros (and nothing else).
 *      Example profiles live in config/profiles/*.example.h; copy one to a
 *      non-example name (git-ignored) to customise.
 *
 *   B) EXTERNAL DEFINITION (Arduino IDE config.h) — the user's config.h already
 *      defines the four macros before this header is reached, so we keep them
 *      as-is and define nothing here.
 *
 *   C) DEFAULT — if neither (A) nor (B) applies, we fall back to the Xidian
 *      example profile so the firmware still compiles and links out of the box.
 *      This is the reference campus; override via (A) for anything else.
 *
 * Constraints enforced by the task (Phase 7):
 *   - SSID is the OPEN campus network (no WPA pre-shared key).
 *   - host is the srun portal host ONLY; the srun base_url uses NO
 *     "/index_8.html" suffix (that hit is only for the INSECURE_PROBE_ONLY
 *     portal-detection path, which never sends credentials).
 *   - ac_id is the campus-confirmed value.
 *   - domain is EMPTY: NO operator suffix (@lt / @yd / @dx) is ever appended.
 *   - The ESP8266 uses its REAL DHCP-assigned IP (never a phone/fixed IP).
 */

#if defined(CAMPUS_PROFILE_HEADER)
  // (A) Profile header selected at compile time.
  #include CAMPUS_PROFILE_HEADER

#elif defined(CAMPUS_SSID)
  // (B) Values already supplied by an external config (Arduino IDE config.h).

#else
  // (C) Safe default: reference Xidian profile so the tree builds unmodified.
  #include "profiles/xidian.example.h"
#endif
