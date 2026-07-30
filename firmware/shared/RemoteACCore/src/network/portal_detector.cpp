// ============================================================
// portal_detector.cpp - reusable captive-portal detection (see header).
// Single source of truth for portal detection used by wifi_manager.
// ============================================================
#include "network/portal_detector.h"
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <cctype>

// Plain-HTTP probe targets (an open/unauthenticated network intercepts HTTP).
// At least two targets are used so a single-site anomaly cannot mask the result.
const char* PortalDetector::kTargets[] = {
  "http://www.baidu.com/",
  "http://connect.rom.miui.com/generate_204",
  "http://www.msftncsi.com/ncsi.txt",
};
const char* PortalDetector::kLabels[] = { "baidu", "miui_204", "msft_ncsi" };
int         PortalDetector::kNTargets = 3;

String PortalDetector::sanitizeLocation(const String& loc) {
  int q = loc.indexOf('?');
  if (q >= 0) return loc.substring(0, q);   // strip query (may carry tokens)
  return loc;
}

String PortalDetector::hostOf(const String& url) {
  int start = url.startsWith("http://") ? 7 : (url.startsWith("https://") ? 8 : 0);
  int end = url.indexOf('/', start);
  if (end < 0) end = url.length();
  return url.substring(start, end);
}

String PortalDetector::extractAcId(const String& url, const String& body) {
  // 1) from URL query: ac_id=8
  int q = url.indexOf("ac_id=");
  if (q >= 0) {
    int s = q + 6;
    int e = url.indexOf('&', s);
    String v = (e > 0) ? url.substring(s, e) : url.substring(s);
    v.trim();
    if (v.length() && v.indexOf(' ') < 0) return v;
  }
  // 2) from page body: find ac_id then the first digit run
  int idx = body.indexOf("ac_id");
  if (idx >= 0) {
    String near = body.substring(idx, idx + 60);
    for (int i = 0; i < (int)near.length(); i++) {
      if (isdigit((unsigned char)near.charAt(i))) {
        int j = i;
        while (j < (int)near.length() && isdigit((unsigned char)near.charAt(j))) j++;
        return near.substring(i, j);
      }
    }
  }
  return "";
}

String PortalDetector::fetchAcIdHttpOnly(const String& url) {
  Serial.println(F("HTTP_PROBE_ONLY ac_id_forensics (no credentials)"));
  String httpUrl = url;
  if (httpUrl.startsWith("https://")) {
    httpUrl = String("http://") + httpUrl.substring(8);
  }
  WiFiClient s;
  s.setTimeout(8000);
  HTTPClient http;
  http.begin(s, httpUrl);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  http.setTimeout(10000);
  int code = http.GET();
  String body = http.getString();
  http.end();
  if (code > 0) return extractAcId(url, body);
  return "";
}

// Detect a campus captive-portal marker inside a 200 body.
// Multiple INDEPENDENT markers joined by OR — never the brittle
// "must contain BOTH portal.campus.example.edu AND srun_portal" condition (task 一.4).
// The real Xidian captive portal returns HTTP 200 (NOT a 3xx) with a
// <meta http-equiv="refresh" ... url=srun_portal_pc?ac_id=8> page that does
// NOT literally contain "portal.campus.example.edu", so that single-string test failed.
static bool bodyHasCaptiveMarker(const String& body) {
  // meta-refresh to a campus login (the real Xidian intercept shape).
  int mi = body.indexOf(F("http-equiv=\"refresh\""));
  if (mi >= 0) {
    int ci = body.indexOf(F("content="), mi);
    if (ci >= 0) {
      int q1 = body.indexOf('"', ci);
      int q2 = (q1 >= 0) ? body.indexOf('"', q1 + 1) : -1;
      if (q1 >= 0 && q2 > q1) {
        String c = body.substring(q1 + 1, q2);
        if (c.indexOf(F("srun_portal")) >= 0 || c.indexOf(F("portal.campus.example.edu")) >= 0 ||
            c.indexOf(F("ac_id="))      >= 0 || c.indexOf(F("index_8")) >= 0) {
          return true;
        }
      }
    }
  }
  // Auto-submit form action pointing at the campus portal host.
  if (body.indexOf(F("action=\"https://portal.campus.example.edu")) >= 0) return true;
  if (body.indexOf(F("action=\"http://portal.campus.example.edu"))  >= 0) return true;
  // Well-known campus portal tokens / hostnames (each independent).
  if (body.indexOf(F("srun_portal"))     >= 0) return true;
  if (body.indexOf(F("portal.campus.example.edu")) >= 0) return true;
  if (body.indexOf(F("index_8.html"))    >= 0) return true;
  if (body.indexOf(F("\xe6\xa0\xa1\xe5\x9b\xad\xe7\xbd\x91")) >= 0) return true; // 校园网
  return false;
}

// Pure classifier: no network. Returns true if a campus captive portal is seen.
bool PortalDetector::classifyResponse(int httpCode, const String& location,
                                      const String& /*contentType*/, const String& body,
                                      PortalResult& out) {
  out = PortalResult();
  out.portalHost = String(CAMPUS_PORTAL_HOST);

  if (httpCode == 204) {
    out.method = 3;                       // already online
    return false;
  }
  if (httpCode >= 300 && httpCode < 400 && location.length() > 0) {
    out.method = 1;
    out.captive = true;
    out.portalUrl = sanitizeLocation(location);
    out.acId = extractAcId(location, body);
    return true;
  }
  if (httpCode == 200 && bodyHasCaptiveMarker(body)) {
    out.method = 2;
    out.captive = true;
    // Parse the auto-submit form action only when it points at the campus
    // portal (desensitized; query strings are stripped before logging).
    int a = body.indexOf(F("action=\""));
    if (a >= 0) {
      int ae = body.indexOf('"', a + 8);
      if (ae > a) {
        String act = body.substring(a + 8, ae);
        if (act.indexOf(F("srun_portal")) >= 0 || act.indexOf(F("portal.campus.example.edu")) >= 0 ||
            act.indexOf(F("index_8")) >= 0) {
          out.portalUrl = sanitizeLocation(act);
        }
      }
    }
    if (out.portalUrl.length() == 0) {
      out.portalUrl = String(F("https://")) + CAMPUS_PORTAL_HOST + F("/index_8.html");
    }
    // Prefer ac_id extracted from the body (covers meta-refresh to
    // srun_portal_pc?ac_id=8 where the portal host is NOT in the body).
    out.acId = extractAcId("", body);
    if (out.acId.length() == 0) out.acId = extractAcId(out.portalUrl, body);
    return true;
  }
  return false;                          // plain 200 / failure -> not captive
}

bool PortalDetector::detect(PortalResult& out) {
  out = PortalResult();
  out.portalHost = String(CAMPUS_PORTAL_HOST);
  bool captive = false;
  PortalResult best;

  Serial.println(F("PORTAL_DETECT_START"));
  for (int i = 0; i < kNTargets; i++) {
    Serial.print(F("PORTAL_PROBE_TARGET label="));
    Serial.print(kLabels[i]);
    Serial.print(F(" host="));
    Serial.println(hostOf(kTargets[i]));

    WiFiClient client;
    HTTPClient http;
    http.begin(client, kTargets[i]);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);  // capture, don't follow
    http.setTimeout(8000);
    int code = http.GET();
    String loc = sanitizeLocation(http.getLocation());
    String ct  = http.header("Content-Type");
    String body = http.getString();
    http.end();

    Serial.print(F("  HTTP_CODE="));
    Serial.println(code);
    if (loc.length()) { Serial.print(F("  LOCATION=")); Serial.println(loc); }
    if (ct.length())  { Serial.print(F("  CONTENT_TYPE=")); Serial.println(ct); }

    PortalResult r;
    if (classifyResponse(code, loc, ct, body, r)) {
      captive = true;
      best = r;
    }
    yield();
  }

  if (captive) out = best;

  // ac_id forensics only if not already extracted.
  if (captive && out.acId.length() == 0) {
    String url = out.portalUrl.length()
        ? out.portalUrl
        : String("https://") + CAMPUS_PORTAL_HOST + "/index_8.html";
    out.acId = fetchAcIdHttpOnly(url);
  }

  Serial.println(F("PORTAL_DETECT_RESULT captive=") + String(captive ? "YES" : "NO"));
  if (captive) {
    out.portalUrl = sanitizeLocation(out.portalUrl);
    Serial.println(F("CAPTIVE_PORTAL_DETECTED=YES"));
    Serial.print(F("PORTAL_HOST="));
    Serial.println(out.portalHost);
    if (out.acId.length()) { Serial.print(F("AC_ID=")); Serial.println(out.acId); }
    if (out.portalUrl.length()) { Serial.print(F("PORTAL_LOGIN_URL=")); Serial.println(out.portalUrl); }
  } else {
    Serial.println(F("CAPTIVE_PORTAL_DETECTED=NO"));
  }
  return captive;
}

// ---- Embedded desensitized fixture unit tests (no network) ----
struct Fixture {
  int    code;
  const char* location;
  const char* body;
  bool   expectCaptive;
  const char* expectAcId;   // "" if none expected
};

bool PortalDetector::unitTest() {
  Serial.println(F("PORTAL_UNITTEST_START"));
  Fixture fx[] = {
    // 1) 3xx redirect to campus portal gateway with ac_id in query
    { 302, "http://10.254.0.1/srun_portal.php?ac_id=8&url=http://www.baidu.com/", "", true, "8" },
    // 2) 200 transparent-intercept page with auto-submit form to portal.campus.example.edu
    { 200, "",
      "<html><body><form action=\"https://portal.campus.example.edu/srun_portal.php\" method=\"post\">"
      "<input type=\"hidden\" name=\"ac_id\" value=\"8\"></form></body></html>", true, "8" },
    // 2b) 200 transparent-intercept with META-REFRESH to srun_portal_pc?ac_id=8
    //     (THE real Xidian captive-portal shape; body has NO literal
    //      portal.campus.example.edu — only "srun_portal_pc?ac_id=8"). This is the case
    //     the old single-string test missed (task 一.1 / 一.6).
    { 200, "",
      "<!DOCTYPE html><html><head><meta http-equiv=\"Content-Type\" "
      "content=\"text/html; charset=utf-8\"/>"
      "<meta http-equiv=\"refresh\" content=\"0;url=srun_portal_pc?ac_id=8&amp;theme=pro\">"
      "</head><body></body></html>", true, "8" },
    // 3) already-online (204)
    { 204, "", "", false, "" },
    // 4) normal 200 page (no campus marker)
    { 200, "", "<html><body>example content, not a portal</body></html>", false, "" },
    // 5) network failure (GET returns <= 0)
    { -1, "", "", false, "" },
  };
  int n = sizeof(fx) / sizeof(fx[0]);
  bool allOk = true;
  for (int i = 0; i < n; i++) {
    PortalResult r;
    bool got = classifyResponse(fx[i].code, fx[i].location, "", fx[i].body, r);
    bool acOk = (String(fx[i].expectAcId) == r.acId);
    bool pass = (got == fx[i].expectCaptive) && acOk;
    allOk = allOk && pass;
    Serial.print(F("  FIXTURE["));
    Serial.print(i);
    Serial.print(F("] captive="));
    Serial.print(got ? "YES" : "NO");
    Serial.print(F(" acId="));
    Serial.print(r.acId);
    Serial.print(F(" expect_captive="));
    Serial.print(fx[i].expectCaptive ? "YES" : "NO");
    Serial.print(F(" expect_acId="));
    Serial.print(fx[i].expectAcId);
    Serial.println(pass ? F(" => PASS") : F(" => FAIL"));
  }
  Serial.println(allOk ? F("PORTAL_UNITTEST_PASS") : F("PORTAL_UNITTEST_FAIL"));
  return allOk;
}
