// Private IR code lookup table.
// Raw frames are generated into gitignored source by IR Learning Studio.
#include "private_ir_codes/ir_code_registry.h"

#if ENABLE_IR_MUTATING_COMMANDS
#include "private_ir_codes/generated/ir_library_generated.inc"

const PrivateIrCode* findPrivateIrCode(const char* codeId) {
  if (!codeId) return nullptr;
  for (uint8_t i = 0; i < kPrivateIrCodeCount; i++) {
    if (strcmp(kPrivateIrCodes[i].codeId, codeId) == 0) return &kPrivateIrCodes[i];
  }
  return nullptr;
}

uint8_t privateIrCodeCount() {
  return kPrivateIrCodeCount;
}

const PrivateIrCode* privateIrCodeAt(uint8_t i) {
  return (i < privateIrCodeCount()) ? &kPrivateIrCodes[i] : nullptr;
}
#endif
