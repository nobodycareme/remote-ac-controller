/* srun-c ESP8266 HTTPS adapter with certificate pinning.
 *
 * Vendored from 45gfg9/srun-c @1881da8fa98e52041fb92f38888b3d5eb4789f7a.
 * Upstream file: platform/esp8266_arduino_http.cpp (used setInsecure()).
 *
 * PROJECT MODIFICATION (the only deviation from upstream for ESP8266):
 *   - Use BearSSL WiFiClientSecure::setFingerprint(CAMPUS_CERT_SHA1) instead of
 *     setInsecure() for ALL credential-bearing requests (get_challenge + login).
 *   - NO fallback to setInsecure(). If the pinned leaf certificate does not
 *     match, the TLS handshake fails and credentials are never transmitted.
 *   - The insecure (setInsecure) path is intentionally NOT compiled: the
 *     portal-only probe that needs no credentials lives in wifi_manager.cpp
 *     and is clearly marked INSECURE_PROBE_ONLY (it never touches challenge/login).
 *
 * See docs/03_协议与接口/TLS证书固定与更新.md for rationale and rotation.
 */
#if ARDUINO && ESP8266 && !defined(SRUN_C_VECTOR_TEST)

#include "compat.h"

#include <cstring>
#include <memory>
#include <WiFiClientSecure.h>
#include <ESP8266HTTPClient.h>
#include "config/campus_tls_pin.h"

// Captured last portal (srun_portal) response body, for result classification
// by the campus auth wrapper. Written only for srun_portal requests.
#define CAMPUS_PORTAL_BODY_MAX 320
char campus_last_portal_body[CAMPUS_PORTAL_BODY_MAX] = {0};

using client_req_func = char *(HTTPClient &client);

static char *request(const_srun_handle handle, const char *url, client_req_func func) {
  std::unique_ptr<WiFiClient> pclient;
  HTTPClient http;

  if (strncmp(url, "https://", 8) == 0) {
    auto psecure = new WiFiClientSecure;
    pclient.reset(psecure);
    // Certificate pinning ONLY. Never setInsecure() for credential-bearing paths.
    psecure->setFingerprint(CAMPUS_CERT_SHA1);
  } else {
    pclient.reset(new WiFiClient);
  }
  http.begin(*pclient, url);

  char *response = func(http);

  // Capture portal body for classification (best-effort, bounded).
  if (response != NULL && strstr(url, "/cgi-bin/srun_portal") != NULL) {
    strncpy(campus_last_portal_body, response, CAMPUS_PORTAL_BODY_MAX - 1);
    campus_last_portal_body[CAMPUS_PORTAL_BODY_MAX - 1] = '\0';
  }

  http.end();
  return response;
}

char *request_get_body(const_srun_handle handle, const char *url) {
  return request(handle, url, [](HTTPClient &client) -> char * {
    int httpCode = client.GET();
    if (httpCode > 0) {
      String payload = client.getString();
      return strdup(payload.c_str());
    }
    return nullptr;
  });
}

char *request_get_location(const_srun_handle handle, const char *url) {
  return request(handle, url, [](HTTPClient &client) -> char * {
    int httpCode = client.GET();
    if (httpCode >= 300 && httpCode < 400) {
      String location = client.getLocation();
      if (!location.isEmpty()) {
        return strdup(location.c_str());
      }
    }
    return nullptr;
  });
}

#endif
