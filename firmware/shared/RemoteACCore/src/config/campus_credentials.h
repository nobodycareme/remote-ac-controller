#pragma once
#include "config/feature_gates.h"
/*
 * Campus credential loader — SECURE COMPILE-TIME GATE (v0.4.0).
 *
 * Single, authoritative source of the Xidian username/password for ALL
 * compilation units. No other .cpp may define CAMPUS_USERNAME /
 * CAMPUS_PASSWORD directly.
 *
 * GATE POLICY (ENABLE_CONTROLLED_LIVE_AUTH):
 *   = 1 (private build): campus_secrets.h (preferred) or legacy secrets.h is
 *     included if present; if absent, NO fallback placeholders are emitted — the
 *     build may fail or CampusCredentials::ready() returns false, and NO default
 *     credentials are ever used.
 *   = 0 (public build):  campus_secrets.h / secrets.h is NEVER included.
 *     CAMPUS_USERNAME / CAMPUS_PASSWORD are NOT defined. All auth request paths
 *     are unreachable.
 *
 * campus_secrets.h / secrets.h are NEVER committed and are git-ignored.
 */
#if ENABLE_CONTROLLED_LIVE_AUTH
  // ---- PRIVATE BUILD: allow campus_secrets.h (or legacy secrets.h) inclusion ----
  #if defined(__has_include)
  #  if __has_include("campus_secrets.h")
  #    include "campus_secrets.h"
  #  elif __has_include("secrets.h")
  #    include "secrets.h"
  #  endif
  #else
  #  ifdef HAVE_CAMPUS_SECRETS_H
  #    include "campus_secrets.h"
  #  elif defined(HAVE_SECRETS_H)
  #    include "secrets.h"
  #  endif
  #endif

  #ifndef CAMPUS_USERNAME
  #define CAMPUS_USERNAME ""
  #endif
  #ifndef CAMPUS_PASSWORD
  #define CAMPUS_PASSWORD ""
  #endif

#else
  // ---- PUBLIC BUILD: secrets.h is UNREACHABLE ----
  // CAMPUS_USERNAME and CAMPUS_PASSWORD are intentionally NOT defined.
  // Any code that references them will fail at compile time — this is by design.
  #define CAMPUS_CREDS_READY "NO (public build — live auth disabled)"
#endif

namespace CampusCredentials {

#if ENABLE_CONTROLLED_LIVE_AUTH
inline const char *username() {
  return CAMPUS_USERNAME;
}

inline const char *password() {
  return CAMPUS_PASSWORD;
}

inline bool ready() {
  return username()[0] != '\0' && password()[0] != '\0';
}
#else
// Public build: no credentials exist — always return empty/unready.
inline const char *username() { return ""; }
inline const char *password() { return ""; }
inline bool ready() { return false; }
#endif

}  // namespace CampusCredentials
