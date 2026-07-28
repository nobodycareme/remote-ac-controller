#pragma once
/*
 * cloud_credentials.h — isolated MQTT credential interface
 *
 * Gates all cloud secrets behind ENABLE_CLOUD_CREDENTIALS:
 *   0 (Public)  — never includes cloud_secrets.h; returns empty credentials;
 *                 cloud code compiles but MQTT connect() safely fails at runtime.
 *   1 (Private) — #includes "cloud_secrets.h" and returns real credentials;
 *                 #error if cloud_secrets.h is missing.
 *
 * This header is the ONLY file permitted to include cloud_secrets.h.
 * No other source file in this project may include cloud_secrets.h directly.
 */
#include <Arduino.h>

namespace CloudCredentials {

    // True only when ENABLE_CLOUD_CREDENTIALS=1 and cloud_secrets.h was loaded.
    bool available();

    // MQTT broker connection parameters.
    const char* host();
    uint16_t    port();
    const char* username();
    const char* password();
    const char* deviceId();      // MQTT client ID

    // TLS CA certificate (PEM string). Empty in Public builds.
    const char* caCert();

    // Optional TLS fingerprint (SHA1 hex). Empty if unused.
    const char* tlsFingerprint();

} // namespace CloudCredentials
