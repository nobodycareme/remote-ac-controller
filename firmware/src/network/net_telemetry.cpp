// ============================================================
// net_telemetry.cpp - shared network-operation telemetry (see header).
// ============================================================
#include "network/net_telemetry.h"
#include <umm_malloc/umm_heap_select.h>

void logNetOp(const char* name, unsigned long t0, unsigned long t1) {
  uint32_t freeHeap = ESP.getFreeHeap();
  uint32_t maxBlock = ESP.getMaxFreeBlockSize();
  uint32_t frag = ESP.getHeapFragmentation();
  // 三.3: record begin/end timestamp, duration, free heap, max free block,
  // and heap fragmentation rate for EVERY HTTP/TLS request.
  Serial.print(F("NET_OP "));
  Serial.print(name);
  Serial.print(F(" begin_ms="));
  Serial.print(t0);
  Serial.print(F(" end_ms="));
  Serial.print(t1);
  Serial.print(F(" dur_ms="));
  Serial.print(t1 - t0);
  Serial.print(F(" free_heap="));
  Serial.print(freeHeap);
  Serial.print(F(" max_block="));
  Serial.print(maxBlock);
  Serial.print(F(" heap_frag_pct="));
  Serial.println(frag);
}
