#pragma once
/*
 * cloud_secrets.example.h — template for MQTT broker credentials
 *
 * Copy this file to cloud_secrets.h in this same config directory and fill in
 * real values. PlatformIO and Arduino IDE share this one canonical local file.
 * cloud_secrets.h is git-ignored — NEVER commit real credentials.
 */

// MQTT Broker connection
#define MQTT_BROKER_HOST     "your-broker.example.com"
#define MQTT_BROKER_PORT     8883

// Device identity (never use full MAC as public device id)
#define MQTT_DEVICE_ID       "bedroom-ac-01"

// MQTT authentication
#define MQTT_USERNAME        "bedroom-ac-01"
#define MQTT_PASSWORD        "change-me"

// Project private CA certificate (PEM). Embed the CA that signed the broker cert.
// ESP8266 validates the broker cert against this CA (no setInsecure).
// v1.2.5: the CA certificate takes PRIORITY — when a valid CA is present the
// firmware uses setTrustAnchors() and ignores the fingerprint below.
#define MQTT_CA_CERT         ""

// TLS certificate fingerprint (SHA-1, 40 hex chars, colons optional).
// v1.2.5: used ONLY when no valid CA certificate is configured above
// (setFingerprint). It pins the CURRENT server certificate, so it must be
// updated whenever the broker certificate rotates. Recommended for long-term
// deployments: use the CA certificate above instead.
#define MQTT_TLS_FINGERPRINT ""
