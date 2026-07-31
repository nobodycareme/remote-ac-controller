// Remote_AC_Controller.ino
// Thin entry point for Arduino IDE builds.
// All business logic lives in the RemoteACCore shared library.
//
// Before compiling:
// 1. Install the RemoteACCore library (see README.md)
// 2. Copy config.example.h -> config.h and fill in your settings
// 3. (Optional, for custom feature switches) copy
//    Remote_AC_Controller.ino.globals.example.h -> Remote_AC_Controller.ino.globals.h
//    and point sketch.yaml's compile.extra_flags at your globals.h. The committed
//    .example.h already has safe public defaults, so this step can be skipped.
// 4. Install required dependencies via Library Manager:
//    - DHT sensor library by Adafruit
//    - Adafruit Unified Sensor
//    - ArduinoJson by Benoit Blanchon
//    - PubSubClient by Nick O'Leary
//    - Crypto by Rhys Weatherley (for SHA256/BLAKE2s)

#include "RemoteACApp.h"

void setup() {
  appSetup();
}

void loop() {
  appLoop();
}
