#pragma once
#include "config/feature_gates.h"
/*
 * campus_auth_vendor.h - thin C++ wrapper around the vendored srun-c client.
 *
 * SECURITY GATE (ENABLE_CONTROLLED_LIVE_AUTH):
 *   = 0 (public build): login() / logout() are blocked at the deepest layer.
 *     Even if CLI bypasses its own check, the business layer refuses to proceed.
 *   = 1 (private build): full auth capability available, gated by secrets.h presence.
 *
 * This wrapper does NOT re-implement the algorithm. It only:
 *   - loads credentials from CampusCredentials (never logs them),
 *   - performs a pre-flight TLS certificate-pin check (no credentials sent),
 *   - calls the upstream srun_login() / srun_logout() (canonical srun v2),
 *   - classifies the result into the task's failure categories.
 *
 * The actual HMAC-MD5 / x_encode / Srun-Base64 / SHA-1 chksum algorithm lives
 * entirely in lib/srun-c (upstream, byte-identical). See the docs directory
 * "03_协议与接口" (campus network protocol and interface notes) for details.
 */
#include <Arduino.h>
#include "config/campus_credentials.h"
#include "config/campus_tls_pin.h"
#include "config/campus_config.h"
#include "srun.h"

// Declared in lib/srun-c/src/esp8266_http_adapter_secure.cpp (last portal body
// capture, used only for result classification — never printed in full).
extern char campus_last_portal_body[];

enum CampusAuthResult {
  CAMPUS_AUTH_UNSET = 0,
  CAMPUS_AUTH_SUCCESS,
  CAMPUS_AUTH_BLOCKED_NEEDS_CREDS,
  CAMPUS_AUTH_TLS_PIN_MISMATCH,
  CAMPUS_AUTH_TLS_HANDSHAKE_FAIL,
  CAMPUS_AUTH_DNS_FAIL,
  CAMPUS_AUTH_WIFI_DISCONNECTED,
  CAMPUS_AUTH_CHALLENGE_HTTP_FAIL,
  CAMPUS_AUTH_CHALLENGE_PARSE_FAIL,
  CAMPUS_AUTH_CHALLENGE_EMPTY_BODY,
  CAMPUS_AUTH_BAD_CREDENTIALS,
  CAMPUS_AUTH_WRONG_DOMAIN,
  CAMPUS_AUTH_WRONG_AC_ID,
  CAMPUS_AUTH_IP_MISMATCH,
  CAMPUS_AUTH_CONCURRENT_SESSION_LIMIT,
  CAMPUS_AUTH_SERVER_REJECTED,
  CAMPUS_AUTH_PORTAL_FORMAT_CHANGED,
  CAMPUS_AUTH_TIMEOUT,
  CAMPUS_AUTH_OUT_OF_MEMORY,
  CAMPUS_AUTH_UNKNOWN_RESPONSE,
  CAMPUS_AUTH_RESPONSE_OK_BUT_INTERNET_BLOCKED
};

class CampusAuthVendor {
public:
  // Pre-flight TLS certificate-pin check. Connects to the portal host with the
  // pinned leaf fingerprint and verifies the handshake. Sends NO credentials.
  // Returns true only if the server presents exactly the pinned certificate.
  bool tlsPinValid();

  // Attempt login. localIp MUST be the ESP8266's real DHCP IP (not a phone IP,
  // not a fixed 10.0.x.x). Returns a classified result. On success the
  // caller MUST still verify internet reachability (3 rounds) before declaring
  // ONLINE.
  CampusAuthResult login(const String& localIp);

  // Best-effort logout. Does NOT kick other terminals, does NOT unbind beyond
  // the srun default.
  CampusAuthResult logout();

  CampusAuthResult lastResult() const { return _last; }
  const char* lastErrMsg() const { return _lastErrMsg.c_str(); }
  const char* lastSucMsg() const { return _lastSucMsg.c_str(); }
  static const char* resultStr(CampusAuthResult r);

  // Offline fixture classification unit test (task 四.5). True if all known
  // Xidian responses map to the expected category.
  static bool classifyUnitTest();

private:
  CampusAuthResult _last = CAMPUS_AUTH_UNSET;
  // Parsed portal response messages (task 四.2-四.6), kept for diagnostics.
  // Copied from the JsonDocument so they survive past the parse scope.
  String _lastErrMsg;
  String _lastSucMsg;
  CampusAuthResult classify(int srunRet);
  CampusAuthResult mapResponse(const char* body, int srunRet);
};
