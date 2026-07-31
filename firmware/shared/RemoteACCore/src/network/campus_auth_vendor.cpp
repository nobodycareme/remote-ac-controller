#include "config/feature_gates.h"
// NOTE (v1.0.0): this unit used to carry a second guard,
// `#if !defined(ENABLE_CLOUD) || ENABLE_CLOUD`, which silently emptied the
// whole translation unit for a campus-auth-only build (ENABLE_CAMPUS_AUTH=1,
// ENABLE_CLOUD=0) and produced undefined references at link time. Campus
// authentication does not depend on MQTT and is no longer gated on it.
#if ENABLE_CAMPUS_AUTH
// ============================================================
// campus_auth_vendor.cpp - wrapper around vendored srun-c (see header)
// v0.3.5: +HTTP metadata diagnostics, JSONP handling, precise error stages
// ============================================================
#include "network/campus_auth_vendor.h"
#include "network/net_telemetry.h"
#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <cstring>
#include <cctype>

// Extern from vendored srun-c HTTP adapter — only body capture, no metadata struct
extern char campus_last_portal_body[];

// ---- Helpers ----------------------------------------------------------------
static void stripBomAndWs(String &s) {
  if (s.length() >= 3 && (unsigned char)s[0] == 0xEF && (unsigned char)s[1] == 0xBB && (unsigned char)s[2] == 0xBF)
    s = s.substring(3);
  while (s.length() && isspace((unsigned char)s[0])) s = s.substring(1);
  while (s.length() && isspace((unsigned char)s[s.length()-1])) s.remove(s.length()-1);
}
static String extractJsonObj(const String &raw) {
  String s = raw; stripBomAndWs(s);
  int start = s.indexOf('{'); if (start < 0) return "";
  int depth = 0;
  for (unsigned i = start; i < s.length(); i++) {
    if (s[i] == '{') depth++; else if (s[i] == '}') { depth--; if (!depth) return s.substring(start, i+1); }
  }
  return "";
}

// Print a sanitized preview: replace sensitive values with [MASKED]
static void printSanitizedPreview(const char* label, const char* body, size_t maxLen=160) {
  String copy(body);
  // Replace known credential-related patterns with [MASKED]
  const char* keys[] = {"username","password","challenge","token","info","chksum","client_ip","online_ip","callback","st"};
  for (auto& k : keys) {
    String pat = String("\"") + k + "\"";
    int pos = 0;
    while ((pos = copy.indexOf(pat, pos)) >= 0) {
      int valStart = copy.indexOf(':', pos) + 1;
      if (valStart <= pos) break;
      while (valStart < (int)copy.length() && (copy[valStart] == ' ' || copy[valStart] == '"')) valStart++;
      int valEnd = copy.indexOf('"', valStart);
      if (valEnd < 0) valEnd = copy.indexOf(',', valStart);
      if (valEnd < 0) valEnd = copy.indexOf('}', valStart);
      if (valEnd < 0) valEnd = copy.length();
      copy = copy.substring(0, valStart) + "[MASKED]" + copy.substring(valEnd);
      pos = valStart + 9;
    }
  }
  if (copy.length() > maxLen) copy = copy.substring(0, maxLen) + "...";
  Serial.print(label); Serial.println(copy);
}

// ---- TLS pre-flight ---------------------------------------------------------
bool CampusAuthVendor::tlsPinValid() {
  if (strlen(CAMPUS_CERT_SHA1) < 40) return false;
  unsigned long t0 = millis();
  BearSSL::WiFiClientSecure client;
  client.setFingerprint(CAMPUS_CERT_SHA1);
  client.setTimeout(8000);
  const bool connected = client.connect(CAMPUS_PORTAL_HOST, 443);
  const int err = client.getLastSSLError();
  client.stop();
  unsigned long t1 = millis();
  logNetOp("tls_pin_check", t0, t1);
  return connected && (err == 0);
}

// ---- Login (with stage-level diagnostics) -----------------------------------
CampusAuthResult CampusAuthVendor::login(const String& localIp) {
  // === BUSINESS-LAYER FINAL GATE (v0.4.0) ===
  // Even if CLI misses its own check, the deepest layer MUST refuse.
  #if !ENABLE_CONTROLLED_LIVE_AUTH
    _last = CAMPUS_AUTH_BLOCKED_NEEDS_CREDS;
    Serial.println(F("LIVE_AUTH_BLOCKED_BY_BUILD_POLICY"));
    return _last;
  #endif

  if (!CampusCredentials::ready()) { _last = CAMPUS_AUTH_BLOCKED_NEEDS_CREDS; return _last; }
  if (!tlsPinValid()) { _last = CAMPUS_AUTH_TLS_PIN_MISMATCH; return _last; }
  campus_last_portal_body[0] = '\0';
  Serial.println(F("SRUN_REQUEST_CONFIG_PASS=True"));

  srun_config cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.base_url  = "https://" CAMPUS_PORTAL_HOST;
  cfg.username  = CampusCredentials::username();
  cfg.password  = CampusCredentials::password();
  cfg.ip        = localIp.c_str();
  cfg.ac_id     = CAMPUS_AC_ID;
  cfg.verbosity = SRUN_VERBOSITY_SILENT;

  srun_handle h = srun_create(&cfg);
  if (!h) { _last = CAMPUS_AUTH_OUT_OF_MEMORY; return _last; }
  unsigned long t0 = millis();
  const int r = srun_login(h);
  unsigned long t1 = millis();
  logNetOp("srun_login", t0, t1);
  Serial.print(F("SRUN_LOGIN_RET=")); Serial.println(r);

  // --- Response body diagnostics ---
  const char *body = campus_last_portal_body;
  int bodyLen = body ? strlen(body) : 0;
  Serial.print(F("RESPONSE_BODY_LEN=")); Serial.println(bodyLen);

  if (!body || !body[0]) {
    _last = CAMPUS_AUTH_CHALLENGE_EMPTY_BODY;
    return _last;
  }

  // Try JSONP extraction if needed (body doesn't start with {)
  String jsonBody(body);
  if (bodyLen > 0 && body[0] != '{') {
    String extracted = extractJsonObj(String(body));
    if (extracted.length()) { jsonBody = extracted; }
  }

  // Print sanitized preview
  printSanitizedPreview("SANITIZED_PREVIEW=", jsonBody.c_str(), 160);

  DynamicJsonDocument doc(1024);
  DeserializationError jsonErr = deserializeJson(doc, jsonBody);
  if (jsonErr) {
    Serial.print(F("ARDUINOJSON_ERROR=")); Serial.println(jsonErr.c_str());
    // Check if response looks like HTML
    if (body && (strstr(body, "<html") || strstr(body, "<HTML")))
      { _last = CAMPUS_AUTH_UNKNOWN_RESPONSE; Serial.println(F("PORTAL_RESPONSE_HTML")); }
    else
      { _last = CAMPUS_AUTH_UNKNOWN_RESPONSE; Serial.println(F("PORTAL_RESPONSE_SCHEMA_UNKNOWN")); }
    return _last;
  }

  // Extract fields (tolerant: all optional except error)
  const char* error      = doc["error"] | "";
  int ecode               = doc["ecode"] | -1;
  const char* error_msg  = doc["error_msg"] | "";
  const char* res        = doc["res"] | "";
  const char* suc_msg    = doc["suc_msg"] | "";

  _lastErrMsg = error_msg;
  _lastSucMsg = suc_msg;

  bool hasError    = doc.containsKey("error");
  bool hasEcode    = doc.containsKey("ecode");
  bool hasErrorMsg = doc.containsKey("error_msg");

  Serial.print(F("RESPONSE_ERROR_FIELD_PRESENT="));  Serial.println(hasError ? "YES" : "NO");
  Serial.print(F("RESPONSE_ECODE_FIELD_PRESENT="));  Serial.println(hasEcode ? "YES" : "NO");
  Serial.print(F("RESPONSE_ERROR_MSG_FIELD_PRESENT=")); Serial.println(hasErrorMsg ? "YES" : "NO");

  if (!hasError) {
    _last = CAMPUS_AUTH_UNKNOWN_RESPONSE;
    Serial.println(F("PORTAL_RESPONSE_SCHEMA_UNKNOWN"));
    if (res[0] && strcmp(res, "ok") == 0) {
      Serial.println(F("PORTAL_AUTH_OK_BY_RES_FIELD"));
      _last = CAMPUS_AUTH_SUCCESS;
    }
    return _last;
  }

  if (error[0]) { Serial.print(F("RESPONSE_ERROR_VALUE=")); Serial.println(error); }
  if (ecode >= 0) { Serial.print(F("RESPONSE_ECODE_VALUE=")); Serial.println(ecode); }
  if (error_msg[0]) { Serial.print(F("RESPONSE_ERROR_MSG_VALUE=")); Serial.println(error_msg); }

  if (strcmp(error, "ok") == 0 || strcmp(res, "ok") == 0) {
    _last = CAMPUS_AUTH_SUCCESS;
    Serial.println(F("PORTAL_AUTH_OK"));
    return _last;
  }

  // Xidian Srun non-standard response (2026-07-18 verified):
  // Server returns error="login_error" with error_msg="Authentication success,Welcome!"
  // This is a confirmed successful login — the captive portal disappears afterward.
  // Whitelist approach: only exact error_msg matches accepted, not arbitrary strstr.
  if (strcmp(error, "login_error") == 0) {
    // Trim trailing comma from error_msg (server may append punctuation)
    String msg(error_msg);
    while (msg.length() && (msg[msg.length()-1] == ',' || msg[msg.length()-1] == '.' || msg[msg.length()-1] == '!'))
      msg.remove(msg.length()-1);
    const char* knownSuccess[] = {
      "Authentication success,Welcome",
      "Authentication success Welcome",
      "login_ok",
    };
    for (auto& s : knownSuccess) {
      if (strcmp(msg.c_str(), s) == 0) {
        _last = CAMPUS_AUTH_SUCCESS;
        Serial.println(F("PORTAL_AUTH_OK_BY_LOGIN_ERROR_WHITELIST"));
        return _last;
      }
    }
    // Exact match not found — record for analysis but don't guess
    Serial.print(F("CAMPUS_UNMATCHED_LOGIN_ERROR_MSG=")); Serial.println(error_msg);
  }

  // Precise error classification
  Serial.print(F("PORTAL_AUTH_REJECTED error=")); Serial.println(error);
  _last = mapResponse(jsonBody.c_str(), r);
  return _last;
}

// ---- Response classification ------------------------------------------------
CampusAuthResult CampusAuthVendor::mapResponse(const char* body, int srunRet) {
  if (srunRet == SRUNE_OK) return CAMPUS_AUTH_SUCCESS;
  if (!body || body[0] == '\0') {
    if (srunRet == SRUNE_NETWORK) return CAMPUS_AUTH_CHALLENGE_HTTP_FAIL;
    if (srunRet == SRUNE_SYSTEM)  return CAMPUS_AUTH_OUT_OF_MEMORY;
    return CAMPUS_AUTH_UNKNOWN_RESPONSE;
  }
  DynamicJsonDocument doc(512);
  DeserializationError err = deserializeJson(doc, body);
  if (err) { Serial.print(F("CLASSIFY_JSON_ERR=")); Serial.println(err.c_str()); return CAMPUS_AUTH_UNKNOWN_RESPONSE; }

  const char* error = doc["error"] | "";
  const char* res   = doc["res"] | "";
  const char* error_msg = doc["error_msg"] | "";
  const char* suc_msg   = doc["suc_msg"] | "";
  _lastErrMsg = error_msg;
  _lastSucMsg = suc_msg;

  if (strcmp(error, "ok") == 0 || strcmp(res, "ok") == 0) return CAMPUS_AUTH_SUCCESS;
  // Xidian non-standard success whitelist (2026-07-18 verified)
  if (strcmp(error, "login_error") == 0) {
    String msg(error_msg);
    while (msg.length() && (msg[msg.length()-1]==',' || msg[msg.length()-1]=='.' || msg[msg.length()-1]=='!'))
      msg.remove(msg.length()-1);
    const char* known[] = {"Authentication success,Welcome","Authentication success Welcome","login_ok"};
    for (auto& s : known) { if (strcmp(msg.c_str(), s) == 0) return CAMPUS_AUTH_SUCCESS; }
  }
  if (strstr(error, "password_error") || strstr(error, "username_error") ||
      strstr(error, "pwd_error") || strstr(error, "auth_error") ||
      (error_msg[0] && strstr(error_msg, "\u5bc6\u7801")))
    return CAMPUS_AUTH_BAD_CREDENTIALS;
  if (strstr(error, "domain_error") || strstr(error, "operator_error"))
    return CAMPUS_AUTH_WRONG_DOMAIN;
  if (strstr(error, "ac_id") || strstr(error, "ac_error"))
    return CAMPUS_AUTH_WRONG_AC_ID;
  if (strstr(error, "ip_error") || strstr(error, "ip is not") || strstr(error, "ip is wrong"))
    return CAMPUS_AUTH_IP_MISMATCH;
  if (strstr(error, "online_num") || strstr(error, "E2606") || strstr(error, "E2611"))
    return CAMPUS_AUTH_CONCURRENT_SESSION_LIMIT;
  if (strstr(error, "already_online") || strstr(error, "already online"))
    return CAMPUS_AUTH_CONCURRENT_SESSION_LIMIT;
  if (strstr(error, "portal_error") || strstr(error, "portal_timeout") || strstr(error, "format"))
    return CAMPUS_AUTH_PORTAL_FORMAT_CHANGED;
  if (strstr(error, "user_not_found") || strstr(error, "no such user"))
    return CAMPUS_AUTH_BAD_CREDENTIALS;
  if (strstr(error, "busy") || strstr(error, "server"))
    return CAMPUS_AUTH_UNKNOWN_RESPONSE;

  Serial.print(F("UNRECOGNIZED_ERROR=")); Serial.println(error);
  return CAMPUS_AUTH_UNKNOWN_RESPONSE;
}

CampusAuthResult CampusAuthVendor::classify(int srunRet) {
  return mapResponse(campus_last_portal_body, srunRet);
}

// ---- Logout ------------------------------------------------------------------
CampusAuthResult CampusAuthVendor::logout() {
  // === BUSINESS-LAYER FINAL GATE (v0.4.0) ===
  #if !ENABLE_CONTROLLED_LIVE_AUTH
    _last = CAMPUS_AUTH_BLOCKED_NEEDS_CREDS;
    Serial.println(F("LIVE_AUTH_BLOCKED_BY_BUILD_POLICY"));
    return _last;
  #endif

  if (!CampusCredentials::ready()) { _last = CAMPUS_AUTH_BLOCKED_NEEDS_CREDS; return _last; }
  srun_config cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.base_url  = "https://" CAMPUS_PORTAL_HOST;
  cfg.username  = CampusCredentials::username();
  cfg.password  = CampusCredentials::password();
  cfg.verbosity = SRUN_VERBOSITY_SILENT;
  srun_handle h = srun_create(&cfg);
  if (!h) { _last = CAMPUS_AUTH_OUT_OF_MEMORY; return _last; }
  const int r = srun_logout(h);
  srun_cleanup(h);
  _last = (r == SRUNE_OK) ? CAMPUS_AUTH_SUCCESS : CAMPUS_AUTH_SERVER_REJECTED;
  return _last;
}

// ---- Unit test ---------------------------------------------------------------
bool CampusAuthVendor::classifyUnitTest() {
  Serial.println(F("CLASSIFY_UNITTEST_START"));
  struct Fx { const char* body; int ret; CampusAuthResult expect; };
  Fx fx[] = {
    { "{\"error\":\"ok\",\"suc_msg\":\"login ok\"}",                                  SRUNE_OK,     CAMPUS_AUTH_SUCCESS },
    { "{\"error\":\"password_error\",\"error_msg\":\"\\u5bc6\\u7801\\u9519\\u8bef\"}", SRUNE_NETWORK, CAMPUS_AUTH_BAD_CREDENTIALS },
    { "{\"error\":\"username_error\"}",                                            SRUNE_NETWORK, CAMPUS_AUTH_BAD_CREDENTIALS },
    { "{\"error\":\"operator_error\"}",                                           SRUNE_NETWORK, CAMPUS_AUTH_WRONG_DOMAIN },
    { "{\"error\":\"ac_id error\"}",                                              SRUNE_NETWORK, CAMPUS_AUTH_WRONG_AC_ID },
    { "{\"error\":\"ip is not in the group\"}",                                   SRUNE_NETWORK, CAMPUS_AUTH_IP_MISMATCH },
    { "{\"error\":\"online_num_error\"}",                                         SRUNE_NETWORK, CAMPUS_AUTH_CONCURRENT_SESSION_LIMIT },
    { "{\"error\":\"some_unknown_error\"}",                                       SRUNE_NETWORK, CAMPUS_AUTH_UNKNOWN_RESPONSE },
    { "",                                                                         SRUNE_NETWORK, CAMPUS_AUTH_CHALLENGE_HTTP_FAIL },
  };
  int pass=0, total=sizeof(fx)/sizeof(fx[0]);
  for (int i=0; i<total; i++) {
    CampusAuthResult got = CampusAuthVendor().mapResponse(fx[i].body, fx[i].ret);
    bool ok = (got == fx[i].expect);
    Serial.print(ok ? F("TEST_PASS ") : F("TEST_FAIL "));
    Serial.println(i);
    if (ok) pass++;
  }
  Serial.print(F("CLASSIFY_TEST_PASS=")); Serial.print(pass);
  Serial.print(F("/")); Serial.println(total);
  return pass == total;
}

// ---- Result string -----------------------------------------------------------
const char* CampusAuthVendor::resultStr(CampusAuthResult r) {
  switch (r) {
    case CAMPUS_AUTH_SUCCESS:             return "SUCCESS";
    case CAMPUS_AUTH_BLOCKED_NEEDS_CREDS: return "BLOCKED_NEEDS_CREDS";
    case CAMPUS_AUTH_TLS_PIN_MISMATCH:    return "TLS_PIN_MISMATCH";
    case CAMPUS_AUTH_CHALLENGE_HTTP_FAIL: return "CHALLENGE_HTTP_FAIL";
    case CAMPUS_AUTH_CHALLENGE_EMPTY_BODY:return "CHALLENGE_EMPTY_BODY";
    case CAMPUS_AUTH_OUT_OF_MEMORY:       return "OUT_OF_MEMORY";
    case CAMPUS_AUTH_BAD_CREDENTIALS:     return "BAD_CREDENTIALS";
    case CAMPUS_AUTH_WRONG_DOMAIN:        return "WRONG_DOMAIN";
    case CAMPUS_AUTH_WRONG_AC_ID:         return "WRONG_AC_ID";
    case CAMPUS_AUTH_IP_MISMATCH:         return "IP_MISMATCH";
    case CAMPUS_AUTH_CONCURRENT_SESSION_LIMIT: return "SESSION_CONFLICT";
    case CAMPUS_AUTH_PORTAL_FORMAT_CHANGED:return "PORTAL_FORMAT_CHANGED";
    case CAMPUS_AUTH_TIMEOUT:             return "TIMEOUT";
    case CAMPUS_AUTH_SERVER_REJECTED:     return "SERVER_REJECTED";
    case CAMPUS_AUTH_UNKNOWN_RESPONSE:    return "UNKNOWN_RESPONSE";
    default: return "UNSET";
  }
}
#endif  // ENABLE_CAMPUS_AUTH
