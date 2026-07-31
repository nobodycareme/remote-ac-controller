#pragma once
/*
 * wifi_manager.h - non-blocking campus Wi-Fi + srun auth state machine.
 *
 * States (per task §二/§三): DISCONNECTED, ASSOCIATING, DHCP_WAIT, PORTAL_CHECK,
 * AUTH_READY, AUTHENTICATING, VERIFYING_INTERNET, ONLINE, BACKOFF, BLOCKED.
 *
 * Rules enforced (v0.3.4):
 *   - Wi-Fi link loss (except DISCONNECTED/ASSOCIATING) -> immediate re-associate.
 *   - DHCP IP change -> re-detect portal.
 *   - Portal UNKNOWN / detect failure -> 30s BACKOFF (no immediate re-loop).
 *   - TIMEOUT auth retry -> 30/60/120s BACKOFF, then REAL re-auth (not stuck).
 *   - ONLINE: internet check every 5 min; 2 consecutive failures -> PORTAL_CHECK.
 *   - 3 internet-verification rounds are TIMESTAMP-scheduled (no delay() in loop);
 *     each round is an independent single request.
 *   - BAD_CREDENTIALS / WRONG_DOMAIN / TLS_PIN_MISMATCH -> BLOCKED (no auto-login).
 *   - No auto-logout, no kick of other terminals, no high-frequency request storm.
 *   - Login is gated behind an explicit, protected request (campus login).
 *   - Every HTTP/TLS op is wrapped with begin/end time + heap telemetry.
 *
 * Portal detection is delegated to the shared PortalDetector module
 * (network/portal_detector.*) — the SAME module the standalone portal-probe
 * firmware uses. No dual-logic drift.
 */
#include <Arduino.h>
#include <ESP8266WiFi.h>
#if ENABLE_CAMPUS_AUTH
#include "network/campus_auth_vendor.h"
#endif
#include "network/portal_detector.h"
#include "config/campus_config.h"

enum WifiState {
  WIFI_DISCONNECTED = 0,
  WIFI_ASSOCIATING,
  WIFI_DHCP_WAIT,
  WIFI_PORTAL_CHECK,
  WIFI_AUTH_READY,
  WIFI_AUTHENTICATING,
  WIFI_VERIFYING_INTERNET,
  WIFI_ONLINE,
  WIFI_BACKOFF,
  WIFI_BLOCKED
};

enum BackoffReason {
  BACKOFF_PORTAL_UNKNOWN = 0,   // portal detection failed/unknown -> re-detect
  BACKOFF_AUTH_RETRY          // retryable auth error -> real re-auth
};

class WifiManager {
public:
  void begin(const char* ssid = nullptr);
  void connect();                 // start association to the OPEN campus SSID
  void disconnect();
  void scan();                    // list nearby APs (read-only)
  void update();                  // non-blocking state-machine tick; call every loop

#if ENABLE_CAMPUS_AUTH
  void campusLogin();             // protected, one-shot request (gated)
  void campusLogout();
  CampusAuthResult executeLogin(); // direct login for controlled-auth (raw WiFi connect first)
  const char* authLastError()  const { return _auth.lastErrMsg(); }
  const char* authLastSuccess() const { return _auth.lastSucMsg(); }
#endif

  WifiState       state() const { return _state; }
  static const char* stateStr(WifiState s);

  String ssid() const { return _cfgSsid; }
  String localIp() const { return WiFi.localIP().toString(); }
  // MAC is MASKED to avoid leaking the device identity into logs.
  String macMasked() const {
    String m = WiFi.macAddress();
    int last = m.lastIndexOf(':');
    return (last > 0) ? (m.substring(0, last) + ":XX:XX") : m;
  }
  bool portalDetected() const { return _portalDetected; }
  String portalHost() const { return _portalHost; }
  String acId() const { return _acId; }
  bool internetUp() const { return _state == WIFI_ONLINE; }
  bool tlsPinValid() const { return _tlsOk; }

#if ENABLE_CAMPUS_AUTH
  const char* lastAuthResultStr() const {
    return CampusAuthVendor::resultStr(_lastAuth);
  }
#endif

private:
  void enterState(WifiState s);
  void doPortalDetect();          // uses shared PortalDetector (no creds)
#if ENABLE_CAMPUS_AUTH
  void doAuth();                  // perform srun login (blocking, with retries)
#endif
  void doVerifyRound();           // ONE internet-verification round
  bool probeInternet();           // one plain-HTTP external probe (with telemetry)

  void schedulePortalBackoff();   // 30s, reason=PORTAL_UNKNOWN
#if ENABLE_CAMPUS_AUTH
  void scheduleAuthBackoff();     // 30/60/120s, reason=AUTH_RETRY
#endif

  String  _cfgSsid = CAMPUS_SSID;
  WifiState _state = WIFI_DISCONNECTED;
  uint32_t _stateEnterMs = 0;
  uint32_t _nextRetryMs = 0;
  uint8_t  _backoffStep = 0;
  uint8_t  _backoffReason = BACKOFF_PORTAL_UNKNOWN;

  bool _portalDetected = false;
  bool _portalChecked = false;
  String _portalHost = "";
  String _portalUrl = "";
  String _acId = "";
  bool _tlsOk = false;

#if ENABLE_CAMPUS_AUTH
  CampusAuthVendor _auth;            // vendored srun-c wrapper (tlsPinValid/login/logout)
  bool _authRequested = false;
  uint8_t _authRetry = 0;
  CampusAuthResult _lastAuth = CAMPUS_AUTH_UNSET;
  bool _authBlockedReported = false;  // one-shot AUTH_BLOCKED marker for no-cred gate
#endif

  uint8_t  _verifyRound = 0;
  uint8_t  _verifyOkCount = 0;
  uint32_t _nextVerifyMs = 0;
  uint32_t _lastNetCheckMs = 0;

  uint8_t  _failStreak = 0;            // member (was a static local) — no cross-state leak
  String   _lastLocalIp = "";          // DHCP IP change detection
};
