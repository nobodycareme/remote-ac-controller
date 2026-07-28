// ============================================================
// hardware_config.h - Single source of truth for all hardware pins
// Board: NodeMCU ESP8266 (ESP-12E) | PlatformIO board ID: nodemcuv2
//
// This file centralises every physical pin assignment for the project.
// Modules must include this header (directly or via board_pins.h) instead
// of hard-coding GPIO numbers.
// ============================================================
#pragma once
#include <Arduino.h>

// ---------------------------------------------------------------------------
// DHT11 temperature / humidity sensor (single-wire)
//   DHT11 VCC  -> NodeMCU 3V3
//   DHT11 DATA -> NodeMCU D1 / GPIO5      <-- current official wiring (verified-stable)
//   DHT11 GND  -> NodeMCU GND
// Root-cause note: the original DHT11 failure was primarily caused by defects in
// the custom dht_service/rawTrace test method. Whether D2/GPIO4 has an independent
// anomaly was NOT validated with a single-variable Adafruit test. The current
// official scheme uses the already-verified-stable Adafruit DHT 1.4.7 + D1/GPIO5.
// Do not change the wiring to re-test GPIO4 unless the user explicitly asks.
// ---------------------------------------------------------------------------
constexpr uint8_t DHT11_DATA_PIN = D1;   // D1 == GPIO5

// ---------------------------------------------------------------------------
// ZJ-IR-V2 IR learn / emit module (SoftwareSerial, TTL, lazy-open)
//   Module VCC -> NodeMCU 3V3
//   Module GND -> NodeMCU GND
//   Module TXD -> NodeMCU D5 / GPIO14   (MCU RX)
//   Module RXD -> NodeMCU D6 / GPIO12   (MCU TX)
// NOTE: SoftwareSerial constructor order is (RX, TX).
// ---------------------------------------------------------------------------
constexpr uint8_t IR_UART_RX_PIN = D5;   // GPIO14 (module TXD -> MCU RX)
constexpr uint8_t IR_UART_TX_PIN = D6;   // GPIO12 (MCU TX -> module RXD)

// ---------------------------------------------------------------------------
// Pins intentionally AVOIDED
//   GPIO6..GPIO11 -> on-board Flash, never use.
//   D3/GPIO0, D4/GPIO2, D8/GPIO15 -> boot-strapping pins, avoid.
// ---------------------------------------------------------------------------
