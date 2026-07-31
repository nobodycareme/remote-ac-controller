#pragma once
/*
 * feature_gates.h — single authoritative source for every compile-time feature
 * switch used by RemoteACCore.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Before v1.0.0 the ENABLE_* macros were "defined somewhere, maybe". A missing
 * -D silently evaluated to 0 inside `#if`, so a typo disabled a whole subsystem
 * without a single warning, and Wi-Fi / campus authentication were accidentally
 * chained to ENABLE_CLOUD (MQTT). This header makes every switch explicit,
 * normalises defaults, encodes the dependency rules, and turns illegal
 * combinations into hard `#error`s.
 *
 * INCLUDE ORDER RULE
 * ------------------
 * Every translation unit that tests an ENABLE_* macro MUST include this header
 * (directly or transitively) BEFORE the first `#if`. Public headers of this
 * library include it as their first line.
 *
 * LAYERING (independent axes — deliberately NOT nested)
 * ----------------------------------------------------
 *   ENABLE_WIFI            Station-mode Wi-Fi + the WifiManager state machine.
 *   ENABLE_CAMPUS_AUTH     srun captive-portal authentication. Requires Wi-Fi.
 *                          Does NOT require, and never implies, ENABLE_CLOUD:
 *                          a device may authenticate to a campus network and
 *                          never speak MQTT.
 *   ENABLE_AUTO_CAMPUS_AUTH  Unattended (re)authentication driven by the state
 *                          machine instead of an operator CLI command.
 *                          Requires ENABLE_CAMPUS_AUTH.
 *   ENABLE_CLOUD           MQTT connectivity state machine + telemetry +
 *                          remote command service. Requires Wi-Fi.
 *   ENABLE_CLOUD_CREDENTIALS  Compile cloud_secrets.h into the image.
 *                          Requires ENABLE_CLOUD.
 *   ENABLE_CONTROLLED_LIVE_AUTH  Allows real campus credentials to be compiled
 *                          in and a real login to be attempted. Requires
 *                          ENABLE_CAMPUS_AUTH. OFF in every public build.
 *   ENABLE_IR_MUTATING_COMMANDS   Real IR emission (private code registry).
 *   ENABLE_IR_LAB_LEARNING_COMMANDS  Capture-only IR lab CLI. Requires
 *                          ENABLE_IR_MUTATING_COMMANDS.
 *
 * SAFE DEFAULTS
 * -------------
 * Everything that can transmit, authenticate, or embed a secret defaults to 0.
 * A build with no -D flags at all is a local, offline, read-only build.
 */

// ---------------------------------------------------------------------------
// 1. Defaults
// ---------------------------------------------------------------------------
// PlatformIO passes a bare `-DENABLE_WIFI` (no value). A bare -D expands to 1,
// so `#if ENABLE_WIFI` is well-formed in both spellings.

#ifndef ENABLE_WIFI
#define ENABLE_WIFI 0
#endif

#ifndef ENABLE_CAMPUS_AUTH
#define ENABLE_CAMPUS_AUTH 0
#endif

#ifndef ENABLE_AUTO_CAMPUS_AUTH
#define ENABLE_AUTO_CAMPUS_AUTH 0
#endif

#ifndef ENABLE_CLOUD
#define ENABLE_CLOUD 0
#endif

#ifndef ENABLE_CLOUD_CREDENTIALS
#define ENABLE_CLOUD_CREDENTIALS 0
#endif

#ifndef ENABLE_CONTROLLED_LIVE_AUTH
#define ENABLE_CONTROLLED_LIVE_AUTH 0
#endif

#ifndef ENABLE_IR_MUTATING_COMMANDS
#define ENABLE_IR_MUTATING_COMMANDS 0
#endif

#ifndef ENABLE_IR_LAB_LEARNING_COMMANDS
#define ENABLE_IR_LAB_LEARNING_COMMANDS 0
#endif

// ---------------------------------------------------------------------------
// 2. Dependency rules
// ---------------------------------------------------------------------------
// These are reported as errors rather than silently "fixed" by promoting the
// missing switch: a build whose flags do not say what it does is exactly the
// failure mode this header was written to remove.

#if ENABLE_CAMPUS_AUTH && !ENABLE_WIFI
#error "feature_gates: ENABLE_CAMPUS_AUTH=1 requires ENABLE_WIFI=1 (campus authentication runs on the Wi-Fi state machine)."
#endif

#if ENABLE_AUTO_CAMPUS_AUTH && !ENABLE_CAMPUS_AUTH
#error "feature_gates: ENABLE_AUTO_CAMPUS_AUTH=1 requires ENABLE_CAMPUS_AUTH=1 (there is no authenticator to drive)."
#endif

// Unattended authentication must never run against placeholder credentials or
// a public build: AUTO_CAMPUS_AUTH is only meaningful when real credentials may
// be compiled in (ENABLE_CONTROLLED_LIVE_AUTH). A public build that flips
// ENABLE_AUTO_CAMPUS_AUTH by accident must fail loudly instead of looping
// against CampusCredentials::ready()==false forever.
#if ENABLE_AUTO_CAMPUS_AUTH && !ENABLE_CONTROLLED_LIVE_AUTH
#error "feature_gates: ENABLE_AUTO_CAMPUS_AUTH=1 requires ENABLE_CONTROLLED_LIVE_AUTH=1 (unattended auth must never target placeholder credentials; set it in a PRIVATE build only)."
#endif

#if ENABLE_CLOUD && !ENABLE_WIFI
#error "feature_gates: ENABLE_CLOUD=1 requires ENABLE_WIFI=1 (MQTT needs a station-mode link)."
#endif

#if ENABLE_CLOUD_CREDENTIALS && !ENABLE_CLOUD
#error "feature_gates: ENABLE_CLOUD_CREDENTIALS=1 requires ENABLE_CLOUD=1 (nothing would consume the secrets)."
#endif

#if ENABLE_CONTROLLED_LIVE_AUTH && !ENABLE_CAMPUS_AUTH
#error "feature_gates: ENABLE_CONTROLLED_LIVE_AUTH=1 requires ENABLE_CAMPUS_AUTH=1 (live auth has no code path otherwise)."
#endif

#if ENABLE_IR_LAB_LEARNING_COMMANDS && !ENABLE_IR_MUTATING_COMMANDS
#error "feature_gates: ENABLE_IR_LAB_LEARNING_COMMANDS=1 requires ENABLE_IR_MUTATING_COMMANDS=1 (the lab CLI drives the IR module)."
#endif

// ---------------------------------------------------------------------------
// 3. Derived convenience predicates
// ---------------------------------------------------------------------------
// `ENABLE_NETWORK_STACK` is true whenever the WifiManager instance must exist.
// It intentionally does NOT mention ENABLE_CLOUD: cloud is one consumer of the
// network stack, not its owner.
#define ENABLE_NETWORK_STACK (ENABLE_WIFI)

// True when the firmware may perform an unattended login without an operator
// typing `campus login`. Used by WifiManager and reported by `campus status`.
#define CAMPUS_AUTH_IS_AUTOMATIC (ENABLE_CAMPUS_AUTH && ENABLE_AUTO_CAMPUS_AUTH)

// Boot-time association policy. The project's default philosophy is
// offline-first: the radio stays idle until an operator issues `wifi connect`.
// Two features legitimately need the link up without an operator present:
//   - ENABLE_CLOUD              a remotely controllable device must dial home;
//   - ENABLE_AUTO_CAMPUS_AUTH   unattended re-auth after a power cut is the
//                               entire point of the feature.
// Any other build keeps the manual behaviour.
#define WIFI_AUTOCONNECT_ON_BOOT (ENABLE_WIFI && (ENABLE_CLOUD || ENABLE_AUTO_CAMPUS_AUTH))

// ---------------------------------------------------------------------------
// 4. Human-readable build profile string (printed at boot)
// ---------------------------------------------------------------------------
#if ENABLE_CLOUD
#  define BUILD_PROFILE_NET "cloud"
#elif ENABLE_CAMPUS_AUTH
#  define BUILD_PROFILE_NET "campus"
#elif ENABLE_WIFI
#  define BUILD_PROFILE_NET "wifi"
#else
#  define BUILD_PROFILE_NET "offline"
#endif
