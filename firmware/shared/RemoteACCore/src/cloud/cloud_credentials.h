#pragma once
#include "config/feature_gates.h"
#include "cloud/cloud_secret_validation.h"
/*
 * cloud_credentials.h — isolated MQTT credential interface
 *
 * Gates all cloud secrets behind ENABLE_CLOUD_CREDENTIALS:
 *   0 (Public)  — never includes cloud_secrets.h; returns empty credentials;
 *                 cloud code compiles but MQTT connect() safely fails at runtime.
 *   1 (Private) — #includes "cloud_secrets.h" and returns real credentials;
 *                 #error if cloud_secrets.h is missing.
 *
 * v1.2.4: available() no longer trusts a non-empty MQTT_BROKER_HOST. It runs
 * the same minimum safety rules as the build-time validator
 * (tools/validate-cloud-secrets.py) — placeholder hosts, invalid ports,
 * template device IDs/auth and missing TLS material are all rejected, so a
 * user who copies the example template verbatim gets a safe "skipped".
 *
 * This header is the ONLY file permitted to include cloud_secrets.h.
 * No other source file in this project may include cloud_secrets.h directly.
 */
#include <Arduino.h>

namespace CloudCredentials {

    // True only when ENABLE_CLOUD_CREDENTIALS=1 AND the local config passes
    // the v1.2.4 content validation (non-placeholder, complete, TLS present).
    bool available();

    // Full validation result (ok + non-sensitive error code).
    CloudCredentialValidation validate();

    // Short non-sensitive error code ("OK", "HOST_PLACEHOLDER", "PORT_INVALID",
    // "DEVICE_ID_INVALID", "AUTH_INVALID", "TLS_MATERIAL_MISSING", ...).
    const char* validationErrorCode();

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
