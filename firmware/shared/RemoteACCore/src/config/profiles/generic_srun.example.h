#pragma once
/*
 * Generic DrCOM / srun (城市热点 / drcom) captive-portal profile — EXAMPLE.
 *
 * Use this as a starting point for ANY campus network that authenticates with
 * the srun / drcom protocol (widely deployed across Chinese universities).
 *
 * Copy to profiles/generic_srun.h (git-ignored), fill in your campus's real
 * PUBLIC values, and select it with:
 *   -DCAMPUS_PROFILE_HEADER="profiles/generic_srun.h"
 *
 * These are PUBLIC, non-secret parameters. NEVER put a username/password here —
 * those go in campus_secrets.h (git-ignored), gated by
 * ENABLE_CONTROLLED_LIVE_AUTH.
 */

// OPEN campus SSID (no WPA key).
#define CAMPUS_SSID         "your-campus-open-ssid"

// srun portal host for your school.
#define CAMPUS_PORTAL_HOST  "portal.your-school.edu.cn"

// ac_id assigned by your campus. 1 is the most common default; verify with the
// portal-probe build before relying on it.
#define CAMPUS_AC_ID        1

// Operator/domain suffix — usually EMPTY. Some campuses use @lt/@yd/@dx; only
// set this if your srun server actually requires it.
#define CAMPUS_DOMAIN       ""

// ---------------------------------------------------------------------------
// Portal TLS leaf-certificate pin — INTENTIONALLY ABSENT in this example.
//
// The ESP8266 pins the leaf certificate (BearSSL setFingerprint); a full CA
// chain does not fit in 80KB of RAM. Because this template has no pin,
// config/campus_tls_pin.h leaves CAMPUS_CERT_SHA1 empty and the firmware
// FAIL-CLOSES: live authentication is refused and no credential is ever sent.
//
// To enable live auth on your campus, extract YOUR portal's fingerprint over a
// trusted network and add the five macros below to your private profile copy:
//
//   openssl s_client -connect <host>:443 -servername <host> -showcerts \
//     </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha1 -dates
//
// Require "Verify return code: 0 (ok)" in the s_client output — otherwise you
// may be pinning an interception proxy instead of the portal.
//
//   #define CAMPUS_CERT_SHA1       "AA:BB:...:FF"   // 20 bytes, colon-separated
//   #define CAMPUS_CERT_NOT_BEFORE "YYYY-MM-DD"
//   #define CAMPUS_CERT_NOT_AFTER  "YYYY-MM-DD"
//   #define CAMPUS_CERT_ISSUER     "<issuer CN>"
//   #define CAMPUS_CERT_SUBJECT    "<subject CN>"
// ---------------------------------------------------------------------------
