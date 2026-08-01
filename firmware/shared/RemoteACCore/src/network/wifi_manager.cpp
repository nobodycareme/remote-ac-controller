/*
 * wifi_manager.cpp - campus Wi-Fi + srun auth state machine (see header)
 * v0.3.5: Base WiFi (begin/connect/disconnect/scan/update/state/localIp) ALWAYS
 *         compiled. Campus-auth-specific members (doAuth/campusLogin/campusLogout/
 *         executeLogin) conditionally compiled under ENABLE_CAMPUS_AUTH.
 *
 * v0.3.4 foundation: PortalDetector integration, BACKOFF discipline,
 * timestamp-scheduled verification (no delay in loop), heap telemetry,
 * single-source portal logic.
 */
#include "network/wifi_manager.h"
#include "network/wifi_connect_plan.h"
#include <ESP8266HTTPClient.h>
#include "network/net_telemetry.h"

#if ENABLE_CAMPUS_AUTH
#include "config/campus_credentials.h"
#endif
#if ENABLE_WIFI_CREDENTIALS
#include "config/wifi_secrets.h"
#endif
#include "config/campus_config.h"

// ---- timing constants ----
static const uint32_t PORTAL_BACKOFF_MS = 30000;                 // 30s on portal-unknown
static const uint32_t NO_AUTH_BACKOFF_MS = 5UL * 60UL * 1000UL;  // 5min when the build cannot authenticate
static const uint32_t VERIFY_GAP_MS = 3000;                      // gap between verify rounds
static const uint32_t NET_CHECK_MS = 5UL * 60UL * 1000UL;        // ONLINE re-check every 5 min
#if ENABLE_CAMPUS_AUTH && !ENABLE_AUTO_CAMPUS_AUTH
static const uint8_t  MAX_AUTH_RETRIES = 2;                      // manual mode: initial + 2 retries
#endif

void WifiManager::begin(const char* ssid, const char* password) {
  if (ssid && *ssid) _cfgSsid = ssid;
  if (password) _cfgPass = password;   // may be "" to clear a previous password
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
#if ENABLE_CAMPUS_AUTH
  _autoAuth.resetAll();
  _authInProgress = false;
#endif
  _lastLocalIp = "";
  enterState(WIFI_DISCONNECTED);
}

#if ENABLE_WIFI_CREDENTIALS
void WifiManager::beginLocalWifi() {
  // Compiled-in home/lab WPA/WPA2 credentials from wifi_secrets.h. The
  // password is stored in _cfgPass for WiFi.begin() only; it is never
  // printed, hashed into logs, or exposed via any status command.
  _cfgSsid = LOCAL_WIFI_SSID;
  _cfgPass = LOCAL_WIFI_PASSWORD;
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
#if ENABLE_CAMPUS_AUTH
  _autoAuth.resetAll();
  _authInProgress = false;
#endif
  _lastLocalIp = "";
  enterState(WIFI_DISCONNECTED);
}
#endif

void WifiManager::connect() {
  if (_state == WIFI_BLOCKED) {
    Serial.println(F("WIFI_BLOCKED clear block first (power-cycle or fix creds/TLS)"));
    return;
  }
  // Single source of truth for the connection decision (pure, host-tested):
  //   - local WPA credentials enabled -> WiFi.begin(ssid, password)
  //   - otherwise -> WiFi.begin(ssid) (OPEN campus SSID)
  // The password VALUE is never logged; only its presence selects the path.
#if ENABLE_WIFI_CREDENTIALS
  const char* localSsid = LOCAL_WIFI_SSID;
  const bool hasLocalPass = (LOCAL_WIFI_PASSWORD[0] != '\0');
#else
  const char* localSsid = nullptr;
  const bool hasLocalPass = false;
#endif
  const WifiConnectPlan plan = makeWifiConnectPlan(_cfgSsid.c_str(), localSsid, hasLocalPass);
  if (!plan.configurationValid) {
    // Hard guard: never call WiFi.begin("") or begin with an empty password.
    // State stays WIFI_DISCONNECTED; no WIFI_ASSOCIATING is entered.
    Serial.print(F("WIFI_CONNECT_SKIPPED reason="));
    Serial.println(wifiPlanReasonLabel(plan.reason));
    return;
  }
  Serial.print(F("WIFI_CONNECT ssid="));
  Serial.print(_cfgSsid);
  Serial.print(F(" security="));
  Serial.println(wifiSecurityLabel(plan.securityType));
#if ENABLE_WIFI_CREDENTIALS
  if (plan.securityType == WIFI_SECURITY_WPA_OR_WPA2) {
    // Local WPA path: the authoritative SSID/password are the compiled-in
    // LOCAL_WIFI_* values (wifi_secrets.h). Using them directly here (rather
    // than the runtime _cfgSsid copy) guarantees the boot-time autoconnect
    // never associates with an empty SSID before beginLocalWifi() runs.
    WiFi.begin(LOCAL_WIFI_SSID, LOCAL_WIFI_PASSWORD);  // WPA/WPA2 home/lab router
    enterState(WIFI_ASSOCIATING);
    return;
  }
#endif
  WiFi.begin(_cfgSsid.c_str());                     // OPEN campus SSID
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

void WifiManager::scheduleNoAuthBackoff() {
  _backoffReason = BACKOFF_NO_AUTH_SUPPORT;
  _nextRetryMs = millis() + NO_AUTH_BACKOFF_MS;
}

#if ENABLE_CAMPUS_AUTH
// AUTH_READY service routine — the ONLY place a login may start.
//
// Two independent conditions must hold:
//   1. Intent. Either the operator asked (`campus login` -> _authRequested) or
//      the build authenticates unattended (ENABLE_AUTO_CAMPUS_AUTH).
//   2. Permission. CampusAuthPolicy must allow an attempt right now: minimum
//      spacing, failure backoff, hourly quota and the hard-block latch are all
//      evaluated there, not scattered through the state machine.
void WifiManager::serviceAuthReady() {
#if ENABLE_AUTO_CAMPUS_AUTH
  const bool intent = true;
#else
  const bool intent = _authRequested;
#endif
  if (!intent) return;

  if (!CampusCredentials::ready()) {
    if (!_authBlockedReported) {
      Serial.println(F("CAMPUS_CREDS_READY=NO"));
      Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
      _authBlockedReported = true;
    }
    _authRequested = false;
#if ENABLE_AUTO_CAMPUS_AUTH
    Serial.println(F("AUTO_CAMPUS_AUTH_ELIGIBLE=NO AUTO_CAMPUS_AUTH_SKIPPED_REASON=NO_CREDENTIALS"));
#endif
    return;
  }

#if ENABLE_AUTO_CAMPUS_AUTH
  // Unattended decision point (task §十三): eligibility + per-epoch first
  // attempt latch, with desensitized logging.
  Serial.print(F("AUTO_CAMPUS_AUTH_ELIGIBLE=YES AUTO_CAMPUS_AUTH_EPOCH="));
  Serial.println(_autoAuth.epoch());
  if (!_autoAuth.mayStartAuth()) {
    Serial.println(F("AUTO_CAMPUS_AUTH_DUPLICATE_SUPPRESSED=True AUTO_CAMPUS_AUTH_SKIPPED_REASON=EPOCH_ALREADY_TRIGGERED"));
    // Retries after a failed first attempt are paced by CampusAuthPolicy and
    // do NOT consume the epoch latch; this guard only stops a SECOND
    // independent trigger while one decision is still pending.
    return;
  }
#endif

  const uint32_t now = millis();
  const CampusAuthGateDecision gate = _authPolicy.evaluate(now);
  if (gate != CAMPUS_GATE_ALLOW) {
    // Report each distinct reason once, so a 10-minute quota wait does not
    // produce 10 minutes of identical serial noise.
    if ((uint8_t)gate != _lastGateReported) {
      _lastGateReported = (uint8_t)gate;
      Serial.print(F("AUTH_GATE_DENY reason="));
      Serial.print(CampusAuthPolicy::decisionStr(gate));
      Serial.print(F(" retry_in_ms="));
      Serial.println(_authPolicy.retryDelayMs(now));
    }
    return;
  }

  _lastGateReported = 0xFF;
  _authRequested = false;
  _authPolicy.noteAttempt(now);
  _autoAuth.markAuthTriggered();
#if ENABLE_AUTO_CAMPUS_AUTH
  Serial.print(F("AUTO_CAMPUS_AUTH_TRIGGERED=True AUTO_CAMPUS_AUTH_EPOCH="));
  Serial.println(_autoAuth.epoch());
#endif
  _authInProgress = true;
  enterState(WIFI_AUTHENTICATING);
}

// Login orchestration. Blocking (srun_login is synchronous). Entry is only ever
// reached through serviceAuthReady(), so the policy has already authorised the
// attempt and counted it.
void WifiManager::doAuth() {
  _authInProgress = true;
  if (!_auth.tlsPinValid()) {
    Serial.println(F("TLS_PIN_MISMATCH"));
    _tlsOk = false;
    _lastAuth = CAMPUS_AUTH_TLS_PIN_MISMATCH;
    _authPolicy.noteHardFailure(millis());
    _authInProgress = false;
    enterState(WIFI_BLOCKED);
    return;
  }
  _tlsOk = true;

  Serial.println(F("CAMPUS_AUTH_START"));
  CampusAuthResult r = _auth.login(localIp());
  _lastAuth = r;

  if (r == CAMPUS_AUTH_SUCCESS) {
    Serial.println(F("CAMPUS_AUTH_PASS"));
    _authPolicy.noteSuccess(millis());
    _autoAuth.markAuthSuccess((uint32_t)WiFi.localIP());
    _authInProgress = false;
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

  // Hard blocks: a rejected password must never be replayed automatically —
  // that is how a campus account gets locked out. Latches until `campus unblock`.
  if (r == CAMPUS_AUTH_BAD_CREDENTIALS || r == CAMPUS_AUTH_WRONG_DOMAIN ||
      r == CAMPUS_AUTH_TLS_PIN_MISMATCH) {
    _authPolicy.noteHardFailure(millis());
    _authInProgress = false;
    enterState(WIFI_BLOCKED);
    return;
  }

  // Retryable class (timeout, transient server/portal error). The policy owns
  // the wait; AUTH_READY re-evaluates it on every tick.
  _authPolicy.noteRetryableFailure(millis());
  _authInProgress = false;
  Serial.print(F("AUTH_BACKOFF ms="));
  Serial.print(CampusAuthPolicy::backoffMs(_authPolicy.failStreak()));
  Serial.print(F(" fail_streak="));
  Serial.println(_authPolicy.failStreak());

#if ENABLE_AUTO_CAMPUS_AUTH
  // Unattended build: keep trying, paced by the policy (and capped by the
  // hourly quota, which eventually parks the device until the window rolls).
  enterState(WIFI_AUTH_READY);
#else
  // Manual build: preserve the historical "initial + 2 retries then BLOCKED"
  // behaviour. `campus unblock` (or a power cycle) is the way out.
  if (_authPolicy.failStreak() <= MAX_AUTH_RETRIES) {
    Serial.print(F("AUTH_RETRY n="));
    Serial.println(_authPolicy.failStreak() + 1);
    _authRequested = true;
    enterState(WIFI_AUTH_READY);
  } else {
    Serial.println(F("AUTH_RETRY_EXHAUSTED"));
    _authPolicy.noteHardFailure(millis());
    enterState(WIFI_BLOCKED);
  }
#endif
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
  // Rule 10: if Wi-Fi is associated but portal detection is not yet determined,
  // trigger detection first instead of silently waiting.
  if (_state == WIFI_DHCP_WAIT) {
    Serial.println(F("PORTAL_NOT_READY trigger detect"));
    enterState(WIFI_PORTAL_CHECK);
    return;
  }
  // Protected, single request. The actual login runs in update() (AUTH_READY ->
  // AUTHENTICATING). An explicit operator command is also the sanctioned way to
  // clear a latched hard block: the human is asserting the credentials changed.
  if (_authPolicy.hardBlocked()) {
    Serial.println(F("AUTH_HARD_BLOCK_CLEARED_BY_OPERATOR"));
    _authPolicy.clearHardBlock();
    if (_state == WIFI_BLOCKED) enterState(WIFI_AUTH_READY);
  }
  _authBlockedReported = false;
  _lastGateReported = 0xFF;
  _authRequested = true;
  Serial.println(F("CAMPUS_LOGIN_REQUESTED"));
}

void WifiManager::campusUnblock() {
  _authPolicy.clearHardBlock();
  _authBlockedReported = false;
  _lastGateReported = 0xFF;
  Serial.println(F("AUTH_HARD_BLOCK_CLEARED"));
  if (_state == WIFI_BLOCKED) {
    // Re-enter the pipeline from portal detection rather than jumping straight
    // to a login: the network may look completely different by now.
    enterState(WIFI_PORTAL_CHECK);
  }
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

CampusAuthResult WifiManager::executeLogin() {
  if (!CampusCredentials::ready()) return CAMPUS_AUTH_UNKNOWN_RESPONSE;
  if (!_auth.tlsPinValid())         return CAMPUS_AUTH_TLS_PIN_MISMATCH;
  _tlsOk = true;
  Serial.println(F("CAMPUS_AUTH_START"));
  return _auth.login(localIp());
}
#endif // ENABLE_CAMPUS_AUTH

// Delegates to the shared PortalDetector module (no credentials sent).
void WifiManager::doPortalDetect() {
  PortalResult res;
  _portalDetected = PortalDetector::detect(res);   // prints CAPTIVE_PORTAL_DETECTED=YES/HOST/AC_ID
  _portalHost = res.portalHost;
  _portalUrl  = res.portalUrl;
  _acId       = res.acId;
}

// ---------------------------------------------------------------------------
// ONE internet-verification round: timestamp-scheduled, no delay().
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
#if ENABLE_CAMPUS_AUTH
      // No-cred gate: honest blocker printed ONCE, then periodic backoff.
      if (!CampusCredentials::ready() && !_authBlockedReported) {
        Serial.println(F("CAMPUS_CREDS_READY=NO"));
        Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
        _authBlockedReported = true;
      }
#endif
      enterState(WIFI_BACKOFF);
      schedulePortalBackoff();
    }
    return;
  }
  _nextVerifyMs = millis() + VERIFY_GAP_MS;   // schedule next independent round
}

// True only when a NON-EMPTY portal host is configured AND the body mentions it.
// The sizeof() guard matters: with campus auth disabled CAMPUS_PORTAL_HOST is "",
// and String::indexOf("") returns 0 (>= 0), which would fake a captive portal on
// every probe. Compile-time short-circuit keeps the literal out of the binary too.
static bool bodyMentionsConfiguredPortalHost(const String& body) {
  if (sizeof(CAMPUS_PORTAL_HOST) <= 1) return false;
  return body.indexOf(F(CAMPUS_PORTAL_HOST)) >= 0;
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
        bodyMentionsConfiguredPortalHost(body) ||
        (body.indexOf(F("srun_portal")) >= 0) ||
        (body.indexOf(F("index_8.html")) >= 0);
    ok = !intercepted && (code == 200);
  }
  http.end();
  logNetOp("probe_internet", t0, t1);
  return ok;
}

void WifiManager::update() {
  const uint32_t now = millis();

  // Rule 3: link-loss guard (except DISCONNECTED/ASSOCIATING/BLOCKED).
  if (_state != WIFI_DISCONNECTED && _state != WIFI_ASSOCIATING && _state != WIFI_BLOCKED) {
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println(F("WIFI_LINK_LOST re-associate"));
#if ENABLE_CAMPUS_AUTH
      // Task §十三.5/6: the old auth cycle is stale after a drop; re-association
      // must be allowed to re-detect and re-authenticate.
      _autoAuth.onLinkReassociated();
      Serial.print(F("AUTO_CAMPUS_AUTH_EPOCH_INVALIDATED reason=LINK_LOST epoch="));
      Serial.println(_autoAuth.epoch());
#endif
      connect();   // -> ASSOCIATING
      return;
    }
    // Rule 4: DHCP IP change -> re-detect portal.
    String ip = localIp();
    if (ip != _lastLocalIp) {
      _lastLocalIp = ip;
#if ENABLE_CAMPUS_AUTH
      // Task §十三.7: a new lease invalidates the old authenticated context.
      _autoAuth.onDhcpIpChanged((uint32_t)WiFi.localIP());
      Serial.print(F("AUTO_CAMPUS_AUTH_EPOCH_INVALIDATED reason=DHCP_IP_CHANGED epoch="));
      Serial.println(_autoAuth.epoch());
#endif
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
#if ENABLE_CAMPUS_AUTH
        // Fresh association: the previous cycle (if any) must not block a new
        // portal detection + authentication decision.
        _autoAuth.onLinkReassociated();
#endif
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
#if ENABLE_CAMPUS_AUTH
        // Task §十三.1/8: each portal detection cycle may trigger at most one
        // FIRST attempt; a re-detected portal opens a new cycle.
        _autoAuth.beginEpoch();
        Serial.print(F("AUTO_CAMPUS_AUTH_EPOCH="));
        Serial.print(_autoAuth.epoch());
        Serial.print(F(" portal_gen="));
        Serial.println(_autoAuth.portalGeneration());
#endif
        enterState(WIFI_AUTH_READY);
      } else if (now - _stateEnterMs > 500) {
        // No captive portal detected - verify internet before going online
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
#if ENABLE_CAMPUS_AUTH
      serviceAuthReady();
#else
      // This build has no authenticator. Parking here forever (the pre-v1.0.0
      // behaviour) made the device look associated while it could never reach
      // the internet, and nothing ever re-evaluated the situation. Report once,
      // then re-probe on a slow timer so an externally cleared portal is picked
      // up without a reboot.
      if (!_noAuthSupportReported) {
        Serial.println(F("CAPTIVE_PORTAL_DETECTED_BUT_AUTH_UNSUPPORTED_BY_BUILD"));
        Serial.println(F("HINT rebuild with -DENABLE_CAMPUS_AUTH=1 or clear the portal externally"));
        _noAuthSupportReported = true;
      }
      enterState(WIFI_BACKOFF);
      scheduleNoAuthBackoff();
#endif
      break;

#if ENABLE_CAMPUS_AUTH
    case WIFI_AUTHENTICATING:
      doAuth();
      break;
#endif

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
          _failStreak = 0;   // Rule 5: success resets streak
          Serial.println(F("INTERNET_CHECK_OK"));
        }
      }
      break;

    case WIFI_BACKOFF:
      // Both backoff reasons resolve the same way — re-detect from a known
      // state. Authentication pacing is no longer routed through BACKOFF.
      if (now >= _nextRetryMs) {
        if (WiFi.status() == WL_CONNECTED) enterState(WIFI_PORTAL_CHECK);
        else connect();    // re-associate
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
