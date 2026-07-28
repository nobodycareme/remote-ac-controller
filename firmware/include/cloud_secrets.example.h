#pragma once
/*
 * cloud_secrets.example.h — template for MQTT broker credentials
 *
 * Copy this file to include/cloud_secrets.h and fill in real values.
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
#define MQTT_CA_CERT         ""

// TLS certificate fingerprint (SHA-1, 40 hex chars, colons optional)
// Leave empty when using CA validation above.
#define MQTT_TLS_FINGERPRINT ""
