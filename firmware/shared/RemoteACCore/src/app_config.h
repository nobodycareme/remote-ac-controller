// ============================================================
// app_config.h - Firmware configuration constants
// ============================================================
#pragma once

// Compile-time feature switches (defaults, dependency rules, illegal-combo
// diagnostics). Must be first: everything below and every consumer of this
// header may test ENABLE_* macros.
#include "config/feature_gates.h"

// Firmware version (printed at boot, used by `version` CLI command)
#define FIRMWARE_VERSION "v1.2.1"

// USB debug serial baud rate (NOT the IR module baud rate)
#define USB_SERIAL_BAUD 115200

// DHT11 sample interval. The Adafruit DHT library enforces a 2s minimum
// (MIN_INTERVAL); use 2.5s to stay safely above the cache boundary.
#define DHT_READ_INTERVAL_MS 2500U

// Max characters for a single CLI input line (hard cap, no growth).
// IR Learning Studio session ids include a timestamp plus a full codeId.
#define CLI_LINE_MAX 192U

// IR module addresses (v0.4.0 — separated per manufacturer spec):
//   IR_MODULE_ADDRESS   = 0x00  — confirmed module address (downlink for mutating commands)
//   IR_BROADCAST_ADDRESS = 0xFF  — broadcast address (read-only discovery/diagnostics only)
// Rule: mutating commands (learn/send/set-addr/reset) MUST use IR_MODULE_ADDRESS.
//       Read-only probes (get-baud/get-addr) MAY use IR_BROADCAST_ADDRESS.
#define IR_MODULE_ADDRESS    0x00
#define IR_BROADCAST_ADDRESS 0xFF

// IR module default baud rate. Changed 2026-07-21 to 19200 per user decision
// "option A" (drop from 115200) to eliminate SoftwareSerial bit-errors under
// ESP8266 WiFi RF contention. Rollback: `ir setbaud 4` at runtime, or reflash a
// 115200 build. Persistence across power-cycle verified by GET_BAUD after reboot.
#define IR_DEFAULT_BAUD 19200UL

// Allowed internal code indices (spec: 0..6).
#define IR_GROUP_MIN 0
#define IR_GROUP_MAX 6

// IR frame constants (from manufacturer protocol / Arduino_Nano_IrStudy.ino)
#define IR_FRAME_HEADER 0x68
#define IR_FRAME_TAIL   0x16

// IR operation timeout (milliseconds) when waiting for a module reply.
#define IR_REPLY_TIMEOUT_MS 3000UL
