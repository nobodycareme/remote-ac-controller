#pragma once
/*
 * Remote_AC_Controller.ino.globals.example.h — GLOBAL FEATURE-SWITCH HEADER.
 *
 * This header is force-included for the whole translation unit via the ESP8266
 * core's `-include` mechanism (wired in sketch.yaml as
 * `compile.extra_flags: -include "Remote_AC_Controller.ino.globals.h"`).
 *
 * It defines ONLY the compile-time feature switches (ENABLE_*). It deliberately
 * does NOT hold any credentials or numeric tuning — those live in config.h
 * (copied from config.example.h) and config/campus_config.h / campus_secrets.h.
 *
 * HOW TO USE
 * ----------
 *   1. cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
 *   2. edit the switches below for your build
 *   3. edit sketch.yaml so extra_flags points at YOUR globals.h
 *
 * CI uses this committed .example.h directly (safe public defaults), so a fresh
 * clone always compiles.
 *
 * SAFE DEFAULTS
 * -------------
 * Everything that can transmit, authenticate, or embed a secret is 0.
 */
#ifndef REMOTE_AC_CONTROLLER_INO_GLOBALS_H
#define REMOTE_AC_CONTROLLER_INO_GLOBALS_H

// ---- Network feature switches (see config/feature_gates.h for the rules) ----
// All are #ifndef-guarded so a build can override any of them with a -D flag
// (e.g. CI passes -DENABLE_CLOUD=1 without editing this file).
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

// Optional: pick a campus profile by uncommenting one line. If left undefined,
// config/campus_config.h falls back to the Xidian example profile.
//   #define CAMPUS_PROFILE_HEADER "profiles/xidian.example.h"
//   #define CAMPUS_PROFILE_HEADER "profiles/generic_srun.example.h"

// ---- Pull in the user's numeric / credential values (git-ignored config.h) ----
// Conditional so a fresh clone / CI (where config.h does not exist) still
// compiles with the example values above.
#if __has_include("config.h")
#include "config.h"
#endif

#endif // REMOTE_AC_CONTROLLER_INO_GLOBALS_H
