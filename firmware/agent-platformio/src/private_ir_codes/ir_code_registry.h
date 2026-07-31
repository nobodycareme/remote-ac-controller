// Private IR code lookup table.
// Maps a short codeId (sent by the web/backend) to a generated PROGMEM 22H frame.
// Only compiled when ENABLE_IR_MUTATING_COMMANDS=1 (private / ir-lab build).
#pragma once
#include "config/feature_gates.h"

#include <Arduino.h>

struct PrivateIrCode {
  const char*  codeId;       // short action id (e.g. hisense_cool_24_..._v1)
  const uint8_t* frame;      // PROGMEM: COMPLETE 22H frame (68..16)
  uint16_t     len;          // total frame length
  const char*  sha256;       // source SHA256 (audit)
  const char*  description;  // human-readable
  // v0.5.0 AC state metadata (2026-07-28 integration round)
  const char*  mode;         // cool / dry / heat / off / unknown
  int16_t      temperature;  // target temperature (0 = n/a)
  const char*  fan;          // auto / turbo / quiet / silent / unknown
  bool         swingVertical;
  bool         swingHorizontal;
  bool         powerOn;
  bool         enabled;      // per-state kill switch (compile-time default true)
};

#if ENABLE_IR_MUTATING_COMMANDS
// Find a code by its short id. Returns nullptr if unknown.
const PrivateIrCode* findPrivateIrCode(const char* codeId);
uint8_t privateIrCodeCount();
const PrivateIrCode* privateIrCodeAt(uint8_t i);
#endif
