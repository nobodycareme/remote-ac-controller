#pragma once
/*
 * Remote_AC_Controller.ino.globals.example.h — GLOBAL FEATURE-SWITCH HEADER.
 *
 * This is the ESP8266 core "Global Build Options" file. The ESP8266 platform
 * (arduino-esp8266 >= 2.5) automatically force-includes
 *   <sketch>.ino.globals.h
 * into EVERY compilation unit via its prebuild step (mkbuildoptglobals.py),
 * with NO `-include` flag, NO sketch.yaml build flags, and NO editing of
 * sketch.yaml required. You never `#include` this file yourself.
 *
 * USAGE
 * ------
 *   1. cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
 *      (Remote_AC_Controller.ino.globals.h is git-ignored)
 *   2. edit the switches below for your build
 *   3. compile:  arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 .
 *
 * This committed .example.h has safe public defaults (everything that can
 * transmit, authenticate, or embed a secret is 0), so a fresh clone compiles.
 *
 * CAMPUS AUTH NOTE
 * -----------------
 * Enable campus auth ONLY after copying a profile and pointing at it:
 *   #define CAMPUS_PROFILE_HEADER "profiles/xidian.h"          // your copy
 *   #define CAMPUS_PROFILE_HEADER "profiles/generic_srun.h"    // your copy
 * The build will #error if ENABLE_CAMPUS_AUTH=1 but no profile is selected —
 * it never silently targets an unspecified campus portal.
 * Your username/password stay in the git-ignored campus_secrets.h and are only
 * compiled when you also set ENABLE_CONTROLLED_LIVE_AUTH=1 locally.
 *
 * SAFE DEFAULTS
 * -------------
 * Wi-Fi is on so a basic build links; cloud, campus auth, IR emission and live
 * auth are all 0.
 */
#ifndef REMOTE_AC_CONTROLLER_INO_GLOBALS_H
#define REMOTE_AC_CONTROLLER_INO_GLOBALS_H

// ---- Network feature switches (see config/feature_gates.h for the rules) ----
// Each is #ifndef-guarded so a -D flag on the command line still overrides it.
#ifndef ENABLE_WIFI
#define ENABLE_WIFI                     1
#endif
#ifndef ENABLE_CAMPUS_AUTH
#define ENABLE_CAMPUS_AUTH              0
#endif
#ifndef ENABLE_AUTO_CAMPUS_AUTH
#define ENABLE_AUTO_CAMPUS_AUTH         0
#endif
#ifndef ENABLE_CLOUD
#define ENABLE_CLOUD                    0
#endif
#ifndef ENABLE_CLOUD_CREDENTIALS
#define ENABLE_CLOUD_CREDENTIALS        0
#endif
#ifndef ENABLE_CONTROLLED_LIVE_AUTH
#define ENABLE_CONTROLLED_LIVE_AUTH     0
#endif
#ifndef ENABLE_IR_MUTATING_COMMANDS
#define ENABLE_IR_MUTATING_COMMANDS     0
#endif
#ifndef ENABLE_IR_LAB_LEARNING_COMMANDS
#define ENABLE_IR_LAB_LEARNING_COMMANDS 0
#endif

// ---- Optional: select a campus profile (required when ENABLE_CAMPUS_AUTH=1) ----
// Copy the matching *.example.h to a non-example name (git-ignored) and point
// here, e.g.:
//   #define CAMPUS_PROFILE_HEADER "profiles/xidian.h"
//   #define CAMPUS_PROFILE_HEADER "profiles/generic_srun.h"

#endif // REMOTE_AC_CONTROLLER_INO_GLOBALS_H
