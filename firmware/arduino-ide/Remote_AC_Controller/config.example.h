// config.example.h — Arduino IDE build configuration template
//
// Copy this file to config.h and adjust for your environment.
// config.h is git-ignored — NEVER commit real credentials.

#pragma once

// ---- Wi-Fi ----
// Campus network SSID (set empty string to skip auto-connect)
#define CAMPUS_SSID          ""

// ---- Campus Authentication ----
// Set to 1 to enable srun campus network authentication
#define ENABLE_CAMPUS_AUTH   0

// Campus login credentials (required when ENABLE_CAMPUS_AUTH=1)
#define CAMPUS_USERNAME      ""
#define CAMPUS_PASSWORD      ""

// ---- Cloud (MQTT) ----
// Set to 1 to enable MQTT cloud connectivity
#define ENABLE_CLOUD         0

// MQTT broker (required when ENABLE_CLOUD=1)
#define MQTT_BROKER_HOST     "your-broker.example.com"
#define MQTT_BROKER_PORT     8883
#define MQTT_DEVICE_ID       "bedroom-ac-01"
#define MQTT_USERNAME        "bedroom-ac-01"
#define MQTT_PASSWORD        "change-me"

// TLS: PEM CA certificate or SHA-1 fingerprint (40 hex chars)
#define MQTT_CA_CERT         ""
#define MQTT_TLS_FINGERPRINT ""

// ---- IR Module (private IR codes) ----
// Set to 1 only if you have private IR code data (ir_code_registry.h)
#define ENABLE_IR_MUTATING_COMMANDS 0
