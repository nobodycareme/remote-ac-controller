#pragma once
/*
 * mqtt_tls_policy.h — PURE, host-testable MQTT TLS identity selection.
 *
 * v1.2.5: MqttClientWrapper::begin() no longer pokes at the CA string
 * ad-hoc. A single MqttTlsPlan is derived from the incoming MqttConfig and
 * applied through an injectable MqttTlsAdapter. This header has NO Arduino /
 * ESP8266 dependency, so host tests compile it directly and exercise the
 * exact decision logic the firmware uses.
 *
 * Selection rules (authoritative, mirrored in the docs and tests):
 *   1. valid CA cert present            -> CA_CERT (setTrustAnchors only)
 *   2. no valid CA, valid fingerprint   -> FINGERPRINT_SHA1 (setFingerprint only)
 *   3. CA and fingerprint both valid    -> CA_CERT wins (documented priority)
 *   4. CA invalid, fingerprint valid    -> FINGERPRINT_SHA1
 *   5. CA valid, fingerprint invalid    -> CA_CERT
 *   6. neither valid                    -> valid=false (begin() returns false)
 *
 * NEVER: setInsecure(), plaintext MQTT fallback, continue after a failed
 * certificate check, auto-disable TLS validation.
 *
 * The plan deliberately contains NO MQTT password, username, device ID, or
 * the printable fingerprint string — only the 20-byte binary fingerprint.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "cloud/cloud_secret_validation.h"

enum MqttTlsMode {
  MQTT_TLS_MODE_NONE = 0,          // nothing usable (plan invalid)
  MQTT_TLS_MODE_CA_CERT,           // setTrustAnchors(X509List)
  MQTT_TLS_MODE_FINGERPRINT_SHA1   // setFingerprint(uint8_t[20])
};

struct MqttTlsPlan {
  bool valid = false;
  MqttTlsMode mode = MQTT_TLS_MODE_NONE;
  const char* caCert = nullptr;        // valid PEM (CA_CERT mode)
  uint8_t     fingerprint[20] = {0};   // binary SHA1 (FINGERPRINT_SHA1 mode)
  const char* reason = nullptr;        // non-sensitive rejection code
};

inline const char* mqttTlsModeLabel(MqttTlsMode m) {
  switch (m) {
    case MQTT_TLS_MODE_CA_CERT:          return "CA_CERT";
    case MQTT_TLS_MODE_FINGERPRINT_SHA1: return "FINGERPRINT_SHA1";
    case MQTT_TLS_MODE_NONE:
    default:                             return "NONE";
  }
}

/*
 * Parse a SHA1 certificate fingerprint into 20 bytes.
 *
 * Accepted input formats (exactly the formats the project template allows):
 *   F4BD59328E778CCBAD6EAE85865936FD0D2847F9        (40 continuous hex chars)
 *   F4:BD:59:32:...:28:47:F9                        (colon separated)
 *   whitespace-separated hex is also tolerated (legacy compatible).
 *
 * Rules:
 *   - separators are removed, then exactly 40 hex characters are required;
 *   - converted to 20 bytes;
 *   - non-hex characters are rejected;
 *   - an all-zero fingerprint is rejected;
 *   - the input string is NEVER copied into the output and the function
 *     never prints anything.
 */
inline bool parseSha1Fingerprint(const char* text, uint8_t output[20]) {
  if (!text || !output) return false;

  uint8_t bytes[20];
  int nibbleCount = 0;
  int nonzero = 0;
  uint8_t current = 0;

  for (const char* c = text; *c; ++c) {
    const char ch = *c;
    if (ch == ':' || ch == ' ') continue;   // allowed separators

    uint8_t v;
    if (ch >= '0' && ch <= '9')      v = (uint8_t)(ch - '0');
    else if (ch >= 'a' && ch <= 'f') v = (uint8_t)(10 + (ch - 'a'));
    else if (ch >= 'A' && ch <= 'F') v = (uint8_t)(10 + (ch - 'A'));
    else return false;                        // non-hex character

    if (nibbleCount >= 40) return false;      // more than 40 hex chars

    if ((nibbleCount & 1) == 0) {
      current = (uint8_t)(v << 4);
    } else {
      bytes[nibbleCount >> 1] = (uint8_t)(current | v);
    }
    if (v != 0) nonzero = 1;
    ++nibbleCount;
  }

  if (nibbleCount != 40) return false;        // must be exactly 40 hex chars
  if (!nonzero) return false;                 // all-zero rejected
  memcpy(output, bytes, 20);
  return true;
}

/*
 * Build the TLS identity plan from the incoming CA cert + fingerprint.
 * Uses the SAME content rules as the build-time validator
 * (cloud_secret_validation.h) — a single spec, three consumers.
 */
inline MqttTlsPlan makeMqttTlsPlan(const char* caCert, const char* fingerprint) {
  MqttTlsPlan plan;

  const bool caValid = cloudCaCertValid(caCert);

  if (caValid) {
    // Rules 1, 3, 5: CA always wins when it is valid.
    plan.valid = true;
    plan.mode = MQTT_TLS_MODE_CA_CERT;
    plan.caCert = caCert ? caCert : "";
    plan.reason = "OK";
    return plan;
  }

  // No valid CA: the fingerprint decides (rules 2, 4).
  const bool fpNonEmpty = (fingerprint && fingerprint[0] != '\0');
  if (!fpNonEmpty) {
    // Rule 6a: no CA AND no fingerprint at all -> material missing.
    plan.valid = false;
    plan.mode = MQTT_TLS_MODE_NONE;
    plan.reason = "TLS_MATERIAL_MISSING";
    return plan;
  }

  // A fingerprint string IS present but fails the format rules
  // (wrong length / non-hex / all-zero) -> distinct non-sensitive code.
  if (!cloudFingerprintValid(fingerprint)) {
    plan.valid = false;
    plan.mode = MQTT_TLS_MODE_NONE;
    plan.reason = "TLS_FINGERPRINT_INVALID";
    return plan;
  }

  if (!parseSha1Fingerprint(fingerprint, plan.fingerprint)) {
    plan.valid = false;
    plan.mode = MQTT_TLS_MODE_NONE;
    plan.reason = "TLS_FINGERPRINT_INVALID";
    return plan;
  }

  plan.caCert = nullptr;
  plan.valid = true;
  plan.mode = MQTT_TLS_MODE_FINGERPRINT_SHA1;
  plan.reason = "OK";
  return plan;
}
