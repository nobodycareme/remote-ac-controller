#pragma once
/*
 * cloud_secret_validation.h - PURE, host-testable local cloud credential rules.
 *
 * v1.2.4: the SAME rules are enforced (a) at build time by
 * tools/validate-cloud-secrets.py, (b) at runtime by
 * CloudCredentials::available()/validate(), and (c) by the host tests.
 * This header is the authoritative spec for those rules; the Python
 * validator mirrors it and a contract test keeps the two in agreement.
 *
 * The rules here are the MINIMUM safety floor: they reject empty/placeholder/
 * malformed values and demand TLS material, but never print a secret.
 */

// Non-sensitive error codes (safe to print/log).
enum CloudValidationCode {
  CLOUD_VALID_OK = 0,
  CLOUD_ERR_HOST_EMPTY,
  CLOUD_ERR_HOST_PLACEHOLDER,   // template/example/invalid domain or scheme
  CLOUD_ERR_PORT,               // out of 1..65535
  CLOUD_ERR_DEVICE_ID,          // empty / template value / bad charset
  CLOUD_ERR_AUTH,               // empty or template username/password
  CLOUD_ERR_TLS                 // neither a valid CA cert nor a valid fingerprint
};

struct CloudCredentialValidation {
  bool ok = false;
  CloudValidationCode code = CLOUD_VALID_OK;
};

// Placeholder/example strings that must never be treated as usable values.
// (kept as a simple helper used by the host contract tests)
static bool cloudHasTemplatePrefix(const char* v, const char* prefix) {
  if (!v || !prefix) return false;
  int i = 0;
  while (prefix[i]) {
    if (v[i] == '\0') return false;
    if (v[i] != prefix[i]) return false;
    ++i;
  }
  return true;
}

inline bool cloudHostValid(const char* host) {
  if (!host || !*host) return false;
  const char* lo = host;
  (void)lo;
  // reject scheme prefixes (http:// https://)
  if (cloudHasTemplatePrefix(host, "https://")) return false;
  if (cloudHasTemplatePrefix(host, "http://")) return false;
  // whitespace is invalid in a hostname
  for (const char* c = host; *c; ++c) {
    if (*c == ' ' || *c == '\t') return false;
  }
  // template families
  if (cloudHasTemplatePrefix(host, "your-")) return false;
  if (cloudHasTemplatePrefix(host, "change-")) return false;
  if (cloudHasTemplatePrefix(host, "placeholder")) return false;
  if (cloudHasTemplatePrefix(host, "example.")) return false;
  if (cloudHasTemplatePrefix(host, "invalid")) return false;
  // ".invalid" TLD (test-only)
  int len = 0; const char* c = host;
  while (*c) { ++len; ++c; }
  if (len >= 8 && host[len-8] == '.' && cloudHasTemplatePrefix(host + len - 7, "invalid")) return false;
  // "example.com" or subdomains (len >= 12 includes the leading dot)
  if (len >= 12 && host[len-12] == '.' && cloudHasTemplatePrefix(host + len - 11, "example.com")) return false;
  // "example.org" and other example TLDs
  if (len >= 12 && host[len-12] == '.' && cloudHasTemplatePrefix(host + len - 11, "example.org")) return false;
  return true;
}

inline bool cloudPortValid(int port) {
  return port >= 1 && port <= 65535;
}

inline bool cloudDeviceIdValid(const char* id) {
  if (!id || !*id) return false;
  // exact template values (a real user device may legitimately be bedroom-*)
  if (cloudHasTemplatePrefix(id, "bedroom-ac-01") &&
      id[11] == '\0') return false;
  if (cloudHasTemplatePrefix(id, "your-")) return false;
  // charset contract: [A-Za-z0-9_-]{3,64}
  int len = 0;
  for (const char* c = id; *c; ++c) {
    char ch = *c;
    if (!((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
          (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) return false;
    ++len;
  }
  return len >= 3 && len <= 64;
}

inline bool cloudAuthValid(const char* user, const char* pass) {
  if (!user || !*user) return false;
  if (!pass || !*pass) return false;
  // exact template values; a real user may legitimately use bedroom-*
  if (cloudHasTemplatePrefix(user, "bedroom-ac-01") && user[11] == '\0') return false;
  if (cloudHasTemplatePrefix(user, "your-")) return false;
  if (cloudHasTemplatePrefix(pass, "change-")) return false;
  if (cloudHasTemplatePrefix(pass, "your-")) return false;
  return true;
}

// Valid CA cert: contains BEGIN CERTIFICATE and END CERTIFICATE delimiters
// and is not placeholder text.
inline bool cloudCaCertValid(const char* caCert) {
  if (!caCert || !*caCert) return false;
  if (cloudHasTemplatePrefix(caCert, "your-") || cloudHasTemplatePrefix(caCert, "change-") ||
      cloudHasTemplatePrefix(caCert, "placeholder")) return false;
  // look for the PEM delimiters
  bool hasBegin = false, hasEnd = false;
  for (const char* c = caCert; *c; ++c) {
    if (!hasBegin && cloudHasTemplatePrefix(c, "BEGIN CERTIFICATE")) {
      hasBegin = true;
    }
    if (!hasEnd && cloudHasTemplatePrefix(c, "END CERTIFICATE")) {
      hasEnd = true;
    }
  }
  return hasBegin && hasEnd;
}

// Valid fingerprint: 40 hex chars when colons are removed, not all zeros,
// not the template empty string.
inline bool cloudFingerprintValid(const char* fp) {
  if (!fp || !*fp) return false;
  int hexCount = 0, nonzero = 0;
  for (const char* c = fp; *c; ++c) {
    char ch = *c;
    if (ch == ':' || ch == ' ') continue;
    if ((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F')) {
      ++hexCount;
      if (ch != '0') ++nonzero;
    } else {
      return false;   // non-hex character
    }
  }
  if (hexCount != 40) return false;
  return nonzero > 0;
}

inline bool cloudTlsValid(const char* caCert, const char* fingerprint) {
  return cloudCaCertValid(caCert) || cloudFingerprintValid(fingerprint);
}

inline CloudCredentialValidation validateCloudCredentials(const char* host,
                                                          int port,
                                                          const char* deviceId,
                                                          const char* user,
                                                          const char* pass,
                                                          const char* caCert,
                                                          const char* fingerprint) {
  CloudCredentialValidation v;
  if (!host || !*host)                     { v.code = CLOUD_ERR_HOST_EMPTY; return v; }
  if (!cloudHostValid(host))               { v.code = CLOUD_ERR_HOST_PLACEHOLDER; return v; }
  if (!cloudPortValid(port))               { v.code = CLOUD_ERR_PORT; return v; }
  if (!cloudDeviceIdValid(deviceId))       { v.code = CLOUD_ERR_DEVICE_ID; return v; }
  if (!cloudAuthValid(user, pass))         { v.code = CLOUD_ERR_AUTH; return v; }
  if (!cloudTlsValid(caCert, fingerprint)) { v.code = CLOUD_ERR_TLS; return v; }
  v.ok = true;
  v.code = CLOUD_VALID_OK;
  return v;
}

inline const char* cloudValidationCodeStr(CloudValidationCode c) {
  switch (c) {
    case CLOUD_VALID_OK:            return "OK";
    case CLOUD_ERR_HOST_EMPTY:      return "HOST_EMPTY";
    case CLOUD_ERR_HOST_PLACEHOLDER: return "HOST_PLACEHOLDER";
    case CLOUD_ERR_PORT:            return "PORT_INVALID";
    case CLOUD_ERR_DEVICE_ID:       return "DEVICE_ID_INVALID";
    case CLOUD_ERR_AUTH:            return "AUTH_INVALID";
    case CLOUD_ERR_TLS:             return "TLS_MATERIAL_MISSING";
  }
  return "UNKNOWN";
}
