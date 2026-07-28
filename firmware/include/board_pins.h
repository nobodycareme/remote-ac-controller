// ============================================================
// board_pins.h - Backward-compatible pin aliases
//
// Pin definitions are now centralised in config/hardware_config.h.
// This header remains as a thin compatibility shim so existing modules
// (ir_module.*) that reference the legacy names keep compiling.
// New code should include "config/hardware_config.h" directly.
// ============================================================
#pragma once
#include "config/hardware_config.h"

// ----- Legacy aliases (map old names to the centralised config) -----
constexpr uint8_t DHT_PIN   = DHT11_DATA_PIN;  // D1 / GPIO5 (official DHT11 data pin)
constexpr uint8_t IR_RX_PIN = IR_UART_RX_PIN;  // D5 / GPIO14 (module TXD -> MCU RX)
constexpr uint8_t IR_TX_PIN = IR_UART_TX_PIN;  // D6 / GPIO12 (MCU TX -> module RXD)
