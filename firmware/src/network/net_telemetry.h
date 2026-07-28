#pragma once
/*
 * net_telemetry.h - shared network-operation telemetry printer.
 * Used by wifi_manager and campus_auth_vendor so every HTTP/TLS request is
 * wrapped with begin/end time + heap metrics (task 三.3). No allocations.
 */
#include <Arduino.h>

// Log one network/TLS operation with timing + heap metrics.
void logNetOp(const char* name, unsigned long t0, unsigned long t1);
