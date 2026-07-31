// config.example.h — Arduino IDE / arduino-cli VALUE template
//
// Copy this file to config.h and fill in your environment.
// config.h is git-ignored — NEVER commit real credentials.
//
// NOTE: This file holds ONLY runtime values (SSID, broker, TLS, IR pins, etc.).
// The compile-time feature switches (ENABLE_*) live in the global
// Remote_AC_Controller.ino.globals.h header (see
// Remote_AC_Controller.ino.globals.example.h). Keep them separate.

#pragma once

// ---- Wi-Fi ----
// Campus network SSID (set empty string to skip auto-connect)
#define CAMPUS_SSID          ""

// ---- Campus Authentication (srun) ----
// Credentials are consumed only when ENABLE_CONTROLLED_LIVE_AUTH=1 (set in the
// globals header) AND a campus_secrets.h exists. Copy
// config/campus_secrets.example.h -> config/campus_secrets.h and fill these in
// there; this template value is ignored by the public build's credential gate.
#define CAMPUS_USERNAME      ""
#define CAMPUS_PASSWORD      ""

// ---- Cloud (MQTT) ----
// Broker host/port (used when ENABLE_CLOUD=1 in the globals header)
#define MQTT_BROKER_HOST     "your-broker.example.com"
#define MQTT_BROKER_PORT     8883
#define MQTT_DEVICE_ID       "bedroom-ac-01"
#define MQTT_USERNAME        "bedroom-ac-01"
#define MQTT_PASSWORD        "change-me"

// TLS: PEM CA certificate or SHA-1 fingerprint (40 hex chars)
#define MQTT_CA_CERT         ""
#define MQTT_TLS_FINGERPRINT ""

// ---- IR Module (private IR codes) ----
// Set ENABLE_IR_MUTATING_COMMANDS=1 in the globals header only if you have
// private IR code data (ir_code_registry.h). No value to set here.
