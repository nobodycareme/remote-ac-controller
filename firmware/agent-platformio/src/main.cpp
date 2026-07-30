// agent-platformio/src/main.cpp
// Thin entry point for PlatformIO / CLI builds.
// All business logic lives in firmware/shared/RemoteACCore/.
#include <Arduino.h>
#include "RemoteACApp.h"

void setup() { appSetup(); }
void loop()  { appLoop(); }
