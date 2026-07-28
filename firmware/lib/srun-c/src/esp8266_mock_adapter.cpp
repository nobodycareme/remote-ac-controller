/* srun-c ESP8266 MOCK HTTP adapter — used ONLY by the algorithm-verification
 * build (nodemcuv2_srun_c_vector, -DSRUN_C_VECTOR_TEST).
 *
 * It replaces the real TLS/HTTP adapter with a deterministic in-process mock
 * so the VENDORED srun.c + md.c + arduinojson.cpp algorithm is exercised
 * END-TO-END on real hardware WITHOUT any network and WITHOUT credentials:
 *   - get_challenge  -> returns a FIXED challenge token (deterministic).
 *   - srun_portal    -> captures the full request URL (which carries the
 *                       HMAC-MD5 password, the {SRBX1} info, and the SHA-1
 *                       chksum) and returns {"error":"ok"}.
 *
 * The crypto, the info-field JSON, the xEncode, the Srun-Base64 and the
 * checksum are ALL produced by the upstream vendored code. Only the transport
 * layer is mocked. This is the faithful "actually call vendored C" test.
 */
#if defined(SRUN_C_VECTOR_TEST)

#include "compat.h"
#include <cstring>
#include <cstdlib>

#define CAMPUS_PORTAL_BODY_MAX 320
char campus_last_portal_body[CAMPUS_PORTAL_BODY_MAX] = {0};

// Captured srun_portal request URL (set by request_get_body).
char* g_srun_captured_portal_url = nullptr;

// Fixed challenge response (deterministic token -> deterministic algorithm output).
static const char* kChallengeJson = "{\"challenge\":\"a1b2c3d4e5f6\",\"client_ip\":\"10.1.2.3\"}";
static const char* kPortalJson    = "{\"error\":\"ok\"}";

char* request_get_body(const_srun_handle handle, const char* url) {
  (void)handle;
  if (strstr(url, "/cgi-bin/get_challenge") != NULL) {
    return strdup(kChallengeJson);
  }
  if (strstr(url, "/cgi-bin/srun_portal") != NULL) {
    if (g_srun_captured_portal_url) free(g_srun_captured_portal_url);
    g_srun_captured_portal_url = strdup(url);   // capture for the test harness
    return strdup(kPortalJson);
  }
  return nullptr;
}

char* request_get_location(const_srun_handle handle, const char* url) {
  (void)handle;
  (void)url;
  return nullptr;
}

#endif  // SRUN_C_VECTOR_TEST
