#pragma once
/*
 * portal_detector.h - reusable captive-portal detection module.
 *
 * This is the SINGLE source of truth for captive-portal detection, used by
 * the main Wi-Fi/auth state machine (wifi_manager.cpp). No dual-logic drift is
 * permitted.
 *
 * Detection method (extracted from the proven portal_probe_test.cpp logic):
 *   - Plain-HTTP probes to >= 2 targets, redirects NOT followed.
 *   - 3xx with a Location -> captive (parse host / ac_id from Location).
 *   - HTTP 200 + transparent-intercept page carrying an srun marker (or the
 *     configured campus portal host) -> captive (parse the auto-submit form
 *     action).
 *   - HTTP 204 / plain 200 -> already online / not a captive portal.
 *   - NEVER sends credentials. Query strings are stripped before logging.
 *
 * The optional ac_id forensic fetch is HTTP-only and still sends NO credentials.
 */
#include <Arduino.h>
#include "config/campus_config.h"

struct PortalResult {
  bool   captive    = false;                 // a campus captive portal was seen
  String portalHost = String(CAMPUS_PORTAL_HOST); // configured portal host ("" when campus auth is off)
  String portalUrl  = "";                     // sanitized login URL (no query)
  String acId       = "";                     // extracted ac_id (string)
  int    method     = 0;                      // 0 none, 1 3xx, 2 200-intercept, 3 already-online(204)
};

class PortalDetector {
public:
  // Live detection over plain-HTTP probe targets (no redirect following).
  // Fills `out`; prints the standardized summary lines. Returns captive.
  // Credentials are NEVER sent; query strings are stripped before logging.
  static bool detect(PortalResult& out);

  // Offline classification of one captured response (pure, no network).
  // Used by both live detection and the embedded unit test.
  static bool classifyResponse(int httpCode, const String& location,
                               const String& contentType, const String& body,
                               PortalResult& out);

  // Embedded desensitized fixture tests. Returns true if all classify correctly.
  static bool unitTest();

private:
  static const char* kTargets[];
  static const char* kLabels[];
  static int         kNTargets;

  // Strip everything from '?' onward (query may carry tokens).
  static String sanitizeLocation(const String& loc);
  // Host portion of a URL (no credentials/path/query).
  static String hostOf(const String& url);
  // Best-effort ac_id extraction from a URL query or page body.
  static String extractAcId(const String& url, const String& body);
  // HTTP-only single fetch of the login page to grep ac_id. No credentials.
  static String fetchAcIdHttpOnly(const String& url);
};
