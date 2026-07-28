// ============================================================
// wifi_manager.cpp - campus Wi-Fi + srun auth state machine (see header)
// v0.3.4: PortalDetector integration, BACKOFF discipline, timestamp-scheduled
// verification (no delay in loop), heap telemetry, single-source portal logic.
// ============================================================
#include "network/wifi_manager.h"
#include <ESP8266HTTPClient.h>
#include "network/net_telemetry.h"
#include "config/campus_credentials.h"
#include "config/campus_config.h"

// ---- timing constants ----
static const uint32_t PORTAL_BACKOFF_MS = 30000;                 // 二.1: 30s on portal-unknown
static const uint32_t AUTH_BACKOFF_MS[] = {30000, 60000, 120000}; // 二.2: 30/60/120s
static const uint32_t VERIFY_GAP_MS = 3000;                      // 三.2: gap between verify rounds
static const uint32_t NET_CHECK_MS = 5UL * 60UL * 1000UL;        // ONLINE re-check every 5 min
static const uint8_t  MAX_AUTH_RETRIES = 2;                      // initial + 2 retries = 3 attempts

void WifiManager::begin(const char* ssid) {
  if (ssid && *ssid) _cfgSsid = ssid;
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  enterState(WIFI_DISCONNECTED);
}

void WifiManager::connect() {
  if (_state == WIFI_BLOCKED) {
    Serial.println(F("WIFI_BLOCKED clear block first (power-cycle or fix creds/TLS)"));
    return;
  }
  Serial.print(F("WIFI_CONNECT ssid="));
  Serial.println(_cfgSsid);
  WiFi.begin(_cfgSsid.c_str());   // OPEN SSID, no password
  enterState(WIFI_ASSOCIATING);
}

void WifiManager::disconnect() {
  WiFi.disconnect();
  enterState(WIFI_DISCONNECTED);
}

void WifiManager::scan() {
  Serial.println(F("WIFI_SCAN_START"));
  const int n = WiFi.scanNetworks();
  Serial.print(F("WIFI_SCAN_FOUND="));
  Serial.println(n);
  for (int i = 0; i < n; i++) {
    Serial.print(F("  AP["));
    Serial.print(i);
    Serial.print(F("] "));
    Serial.print(WiFi.SSID(i));
    Serial.print(F(" rssi="));
    Serial.print(WiFi.RSSI(i));
    Serial.print(F(" enc="));
    Serial.println((WiFi.encryptionType(i) == ENC_TYPE_NONE) ? F("OPEN") : F("WEP/WPA"));
  }
  Serial.println(F("WIFI_SCAN_DONE"));
}

void WifiManager::enterState(WifiState s) {
  _state = s;
  _stateEnterMs = millis();
  switch (s) {
    case WIFI_PORTAL_CHECK:       _portalChecked = false; break;
    case WIFI_VERIFYING_INTERNET: _verifyRound = 0; _verifyOkCount = 0; _nextVerifyMs = millis(); break;
    default: break;
  }
}

void WifiManager::schedulePortalBackoff() {
  _backoffReason = BACKOFF_PORTAL_UNKNOWN;
  _nextRetryMs = millis() + PORTAL_BACKOFF_MS;
}

void WifiManager::scheduleAuthBackoff() {
  _backoffReason = BACKOFF_AUTH_RETRY;
  const uint8_t maxStep = sizeof(AUTH_BACKOFF_MS) / sizeof(AUTH_BACKOFF_MS[0]);
  uint32_t ms = (_backoffStep < maxStep) ? AUTH_BACKOFF_MS[_backoffStep] : 120000;
  _nextRetryMs = millis() + ms;
  if (_backoffStep < maxStep) _backoffStep++;
}

// Delegates to the shared PortalDetector module (no credentials sent).
void WifiManager::doPortalDetect() {
  PortalResult res;
  _portalDetected = PortalDetector::detect(res);   // prints CAPTIVE_PORTAL_DETECTED=YES/HOST/AC_ID
  _portalHost = res.portalHost;
  _portalUrl  = res.portalUrl;
  _acId       = res.acId;
}

// ---------------------------------------------------------------------------
// Login orchestration. Blocking (srun_login is synchronous) but only runs on an
// explicit, protected request. Retries on TIMEOUT only, gated by BACKOFF.
// ---------------------------------------------------------------------------
void WifiManager::doAuth() {
  if (!CampusCredentials::ready()) {
    Serial.println(F("CAMPUS_CREDS_READY=NO"));
    Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
    enterState(WIFI_AUTH_READY);
    return;
  }
  if (!_auth.tlsPinValid()) {
    Serial.println(F("TLS_PIN_MISMATCH"));
    _tlsOk = false;
    _lastAuth = CAMPUS_AUTH_TLS_PIN_MISMATCH;
    enterState(WIFI_BLOCKED);
    return;
  }
  _tlsOk = true;

  Serial.println(F("CAMPUS_AUTH_START"));
  CampusAuthResult r = _auth.login(localIp());
  _lastAuth = r;

  if (r == CAMPUS_AUTH_SUCCESS) {
    Serial.println(F("CAMPUS_AUTH_PASS"));
    enterState(WIFI_VERIFYING_INTERNET);
    return;
  }

  Serial.print(F("CAMPUS_AUTH_FAIL reason="));
  Serial.println(CampusAuthVendor::resultStr(r));
  // Print server error fields for diagnosis (no credentials)
  const char* err = _auth.lastErrMsg();
  const char* suc = _auth.lastSucMsg();
  if (err && err[0]) { Serial.print(F("AUTH_SERVER_ERROR=")); Serial.println(err); }
  if (suc && suc[0]) { Serial.print(F("AUTH_SERVER_SUC=")); Serial.println(suc); }

  // Retry only on timeout-class errors, max 3 attempts (initial + 2 retries).
  if (r == CAMPUS_AUTH_TIMEOUT) {
    if (_authRetry < MAX_AUTH_RETRIES) {
      _authRetry++;
      Serial.print(F("AUTH_RETRY n="));
      Serial.println(_authRetry + 1);
      enterState(WIFI_BACKOFF);
      scheduleAuthBackoff();
      return;
    }
    Serial.println(F("AUTH_RETRY_EXHAUSTED"));
    enterState(WIFI_BLOCKED);
    return;
  }

  // Hard blocks: never auto-login again.
  if (r == CAMPUS_AUTH_BAD_CREDENTIALS || r == CAMPUS_AUTH_WRONG_DOMAIN ||
      r == CAMPUS_AUTH_TLS_PIN_MISMATCH) {
    enterState(WIFI_BLOCKED);
    return;
  }
  // Other failures -> backoff then REAL re-auth (二.7), not a silent stop.
  enterState(WIFI_BACKOFF);
  scheduleAuthBackoff();
}

// ---------------------------------------------------------------------------
// ONE internet-verification round (三.2): timestamp-scheduled, no delay().
// Only ALL 3 rounds success -> ONLINE.
// ---------------------------------------------------------------------------
void WifiManager::doVerifyRound() {
  bool ok = probeInternet();
  if (ok) { _verifyOkCount++; _failStreak = 0; }
  else    { _failStreak++; }

  _verifyRound++;
  Serial.print(F("INTERNET_VERIFY round="));
  Serial.print(_verifyRound);
  Serial.print(F(" ok="));
  Serial.print(ok ? "YES" : "NO");
  Serial.print(F(" cumulative_ok="));
  Serial.println(_verifyOkCount);

  if (_verifyRound >= 3) {
    if (_verifyOkCount >= 3) {
      Serial.println(F("INTERNET_ONLINE"));
      enterState(WIFI_ONLINE);
      _lastNetCheckMs = millis();
    } else {
      Serial.println(F("AUTH_RESPONSE_OK_BUT_INTERNET_BLOCKED"));
      // No-cred gate (二.9): honest blocker printed ONCE, then periodic backoff.
      if (!CampusCredentials::ready() && !_authBlockedReported) {
        Serial.println(F("CAMPUS_CREDS_READY=NO"));
        Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
        _authBlockedReported = true;
      }
      enterState(WIFI_BACKOFF);
      schedulePortalBackoff();
    }
    return;
  }
  _nextVerifyMs = millis() + VERIFY_GAP_MS;   // schedule next independent round
}

bool WifiManager::probeInternet() {
  unsigned long t0 = millis();
  WiFiClient client;
  HTTPClient http;
  http.begin(client, "http://www.baidu.com/");
  http.setTimeout(8000);
  int code = http.GET();
  unsigned long t1 = millis();
  bool ok = false;
  if (code > 0) {
    String body = http.getString();
    bool intercepted =
        (body.indexOf("portal.campus.example.edu") >= 0) ||
        (body.indexOf("srun_portal") >= 0) ||
        (body.indexOf("index_8.html") >= 0);
    ok = !intercepted && (code == 200);
  }
  http.end();
  logNetOp("probe_internet", t0, t1);
  return ok;
}

void WifiManager::campusLogin() {
  if (!CampusCredentials::ready()) {
    Serial.println(F("CAMPUS_CREDS_READY=NO"));
    Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
    return;
  }
  if (_state == WIFI_DISCONNECTED || _state == WIFI_ASSOCIATING) {
    Serial.println(F("WIFI_NOT_ASSOCIATED connect first"));
    return;
  }
  // 二.10: if Wi-Fi is associated but portal detection is not yet determined,
  // trigger detection first instead of silently waiting.
  if (_state == WIFI_DHCP_WAIT) {
    Serial.println(F("PORTAL_NOT_READY trigger detect"));
    enterState(WIFI_PORTAL_CHECK);
    return;
  }
  // Protected, single request. The actual login runs in update() (AUTHENTICATING).
  _authRetry = 0;
  _authRequested = true;
  Serial.println(F("CAMPUS_LOGIN_REQUESTED"));
}

void WifiManager::campusLogout() {
  if (!CampusCredentials::ready()) {
    Serial.println(F("CAMPUS_CREDS_READY=NO"));
    return;
  }
  CampusAuthResult r = _auth.logout();
  Serial.print(F("CAMPUS_LOGOUT result="));
  Serial.println(CampusAuthVendor::resultStr(r));
}

// -- Direct login helper (for controlled-auth firmware; call after raw WiFi connect) --
CampusAuthResult WifiManager::executeLogin() {
  if (!CampusCredentials::ready()) return CAMPUS_AUTH_UNKNOWN_RESPONSE;
  if (!_auth.tlsPinValid())         return CAMPUS_AUTH_TLS_PIN_MISMATCH;
  _tlsOk = true;
  Serial.println(F("CAMPUS_AUTH_START"));
  return _auth.login(localIp());
}

void WifiManager::update() {
  const uint32_t now = millis();

  // 二.3: link-loss guard (except DISCONNECTED/ASSOCIATING/BLOCKED).
  if (_state != WIFI_DISCONNECTED && _state != WIFI_ASSOCIATING && _state != WIFI_BLOCKED) {
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println(F("WIFI_LINK_LOST re-associate"));
      connect();   // -> ASSOCIATING
      return;
    }
    // 二.4: DHCP IP change -> re-detect portal.
    String ip = localIp();
    if (ip != _lastLocalIp) {
      _lastLocalIp = ip;
      if (_state != WIFI_PORTAL_CHECK) {
        Serial.println(F("DHCP_IP_CHANGED re-detect portal"));
        enterState(WIFI_PORTAL_CHECK);
      }
    }
  }

  switch (_state) {
    case WIFI_ASSOCIATING:
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println(F("WIFI_ASSOC_PASS"));
        Serial.print(F("LOCAL_IP="));
        Serial.println(localIp());
        Serial.print(F("GATEWAY="));
        Serial.println(WiFi.gatewayIP().toString());
        Serial.print(F("DNS_IP="));
        Serial.println(WiFi.dnsIP().toString());
        _lastLocalIp = localIp();
        enterState(WIFI_DHCP_WAIT);
      } else if (now - _stateEnterMs > 15000) {
        Serial.println(F("WIFI_ASSOC_TIMEOUT -> BACKOFF"));
        enterState(WIFI_BACKOFF);
        schedulePortalBackoff();
      }
      break;

    case WIFI_DHCP_WAIT:
      if (now - _stateEnterMs > 1500) {
        enterState(WIFI_PORTAL_CHECK);
      }
      break;

    case WIFI_PORTAL_CHECK:
      if (!_portalChecked) {
        doPortalDetect();
        _portalChecked = true;
      }
      if (_portalDetected) {
        enterState(WIFI_AUTH_READY);
      } else if (now - _stateEnterMs > 500) {
        // No captive portal detected — verify internet before going online
        if (probeInternet()) {
          Serial.println(F("PORTAL_CAPTIVE=NO INTERNET_OK AUTH=NOT_REQUIRED"));
          enterState(WIFI_VERIFYING_INTERNET);
        } else {
          Serial.println(F("PORTAL_CAPTIVE=NO INTERNET_FAIL BACKOFF"));
          enterState(WIFI_BACKOFF);
          schedulePortalBackoff();
        }
      }
      break;

    case WIFI_AUTH_READY:
      if (_authRequested) {
        _authRequested = false;
        enterState(WIFI_AUTHENTICATING);
      }
      break;

    case WIFI_AUTHENTICATING:
      doAuth();
      break;

    case WIFI_VERIFYING_INTERNET:
      if (now >= _nextVerifyMs) {
        doVerifyRound();
      }
      break;

    case WIFI_ONLINE:
      if (now - _lastNetCheckMs > NET_CHECK_MS) {
        _lastNetCheckMs = now;
        if (!probeInternet()) {
          _failStreak++;
          Serial.print(F("INTERNET_CHECK_FAIL streak="));
          Serial.println(_failStreak);
          if (_failStreak >= 2) {
            _failStreak = 0;
            enterState(WIFI_PORTAL_CHECK);
          }
        } else {
          _failStreak = 0;   // 二.5: success resets streak
          Serial.println(F("INTERNET_CHECK_OK"));
        }
      }
      break;

    case WIFI_BACKOFF:
      if (now >= _nextRetryMs) {
        if (_backoffReason == BACKOFF_PORTAL_UNKNOWN) {
          if (WiFi.status() == WL_CONNECTED) enterState(WIFI_PORTAL_CHECK);
          else connect();    // re-associate
        } else {
          enterState(WIFI_AUTHENTICATING);   // 二.7: real re-auth, not stuck at AUTH_READY
        }
      }
      break;

    case WIFI_BLOCKED:
    case WIFI_DISCONNECTED:
    default:
      break;
  }
}

const char* WifiManager::stateStr(WifiState s) {
  switch (s) {
    case WIFI_DISCONNECTED:        return "DISCONNECTED";
    case WIFI_ASSOCIATING:         return "ASSOCIATING";
    case WIFI_DHCP_WAIT:           return "DHCP_WAIT";
    case WIFI_PORTAL_CHECK:        return "PORTAL_CHECK";
    case WIFI_AUTH_READY:          return "AUTH_READY";
    case WIFI_AUTHENTICATING:      return "AUTHENTICATING";
    case WIFI_VERIFYING_INTERNET:  return "VERIFYING_INTERNET";
    case WIFI_ONLINE:              return "ONLINE";
    case WIFI_BACKOFF:             return "BACKOFF";
    case WIFI_BLOCKED:             return "BLOCKED";
    default:                       return "UNKNOWN";
  }
}
