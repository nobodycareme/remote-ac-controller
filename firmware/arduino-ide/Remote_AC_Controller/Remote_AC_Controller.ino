// Remote_AC_Controller.ino
// Thin entry point for Arduino IDE builds.
// All business logic lives in the RemoteACCore shared library.
//
// Before compiling:
// 1. Install the RemoteACCore library (see README.md)
// 2. Install dependencies via Library Manager:
//    - DHT sensor library by Adafruit   (always)
//    - Adafruit Unified Sensor          (always, DHT dependency)
//    - ArduinoJson by Benoit Blanchon   (only with ENABLE_CAMPUS_AUTH=1)
//    - PubSubClient by Nick O'Leary     (only with ENABLE_CLOUD=1)
//    Do NOT install a "Crypto" library: Crypto.h / base64.h ship with the
//    ESP8266 core and are referenced only under ENABLE_IR_LAB_LEARNING_COMMANDS.
// 3. (Optional, for custom feature switches) copy
//    Remote_AC_Controller.ino.globals.example.h -> Remote_AC_Controller.ino.globals.h
//    The ESP8266 core force-includes that file into every compilation unit
//    automatically — no `-include` flag and no sketch.yaml editing needed. The
//    committed .example.h already has safe public defaults, so you can skip this
//    step for a basic Wi-Fi build.
//    globals.h is the ONLY place that reaches every compilation unit; a header
//    #included from this .ino would not affect the library's own .cpp files.
// 4. Runtime values are NOT set in this sketch folder:
//    - Wi-Fi SSID   -> `wifi connect <ssid>` over serial (no auto-connect)
//    - Campus portal-> the profile selected by CAMPUS_PROFILE_HEADER
//    - MQTT broker  -> cloud_secrets.h (git-ignored, see README.md)

#include "RemoteACApp.h"

void setup() {
  appSetup();
}

void loop() {
  appLoop();
}
