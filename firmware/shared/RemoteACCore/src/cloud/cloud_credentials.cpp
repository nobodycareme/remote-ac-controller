// ============================================================
// cloud_credentials.cpp — MQTT credential provider
// ============================================================
#include "cloud/cloud_credentials.h"

#if ENABLE_CLOUD_CREDENTIALS
  // Private build: real credentials REQUIRED
  #if __has_include("cloud_secrets.h")
    #include "cloud_secrets.h"
  #else
    #error "ENABLE_CLOUD_CREDENTIALS=1 but cloud_secrets.h is missing. Create it from include/cloud_secrets.example.h"
  #endif
#endif

namespace CloudCredentials {

CloudCredentialValidation validate() {
#if ENABLE_CLOUD_CREDENTIALS
    // v1.2.4: same minimum rules as tools/validate-cloud-secrets.py. A config
    // copied from the example template verbatim is rejected here.
    return ::validateCloudCredentials(
        MQTT_BROKER_HOST, (int)MQTT_BROKER_PORT,
        MQTT_DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD,
        MQTT_CA_CERT, MQTT_TLS_FINGERPRINT);
#else
    CloudCredentialValidation v;
    v.ok = false;
    v.code = CLOUD_ERR_HOST_EMPTY;
    return v;
#endif
}

bool available() {
    return validate().ok;
}

const char* validationErrorCode() {
    return cloudValidationCodeStr(validate().code);
}

const char* host() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_BROKER_HOST;
#else
    return "";
#endif
}

uint16_t port() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_BROKER_PORT;
#else
    return 8883;
#endif
}

const char* username() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_USERNAME;
#else
    return "";
#endif
}

const char* password() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_PASSWORD;
#else
    return "";
#endif
}

const char* deviceId() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_DEVICE_ID;
#else
    return "bedroom-ac-01";
#endif
}

const char* caCert() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_CA_CERT;
#else
    return "";
#endif
}

const char* tlsFingerprint() {
#if ENABLE_CLOUD_CREDENTIALS
    return MQTT_TLS_FINGERPRINT;
#else
    return "";
#endif
}

} // namespace CloudCredentials
