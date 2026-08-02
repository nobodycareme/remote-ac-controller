[简体中文](../中文/更新日志.md) | **English**

# Changelog

## [1.2.5] - 2026-08-02

### Fixed

- **MQTT TLS fingerprints are now applied at runtime**: `MqttClientWrapper::begin()` derives a single TLS identity plan (`MqttTlsPlan`) and applies it through an injectable adapter to the BearSSL client — when only a valid fingerprint is configured, `setFingerprint()` is actually called instead of leaving `tls_fingerprint` unused.
- **CA priority, fingerprint fallback**: when both a valid CA and a valid fingerprint are present, only the CA is used (`setTrustAnchors`); the SHA-1 fingerprint (`setFingerprint`) is used only when no valid CA exists; if neither is present `begin()` returns false and the cloud state machine is not entered, with a non-sensitive code (`TLS_MATERIAL_MISSING` / `TLS_FINGERPRINT_INVALID`).
- **SSIDs containing spaces are no longer rejected**: the build-time Python validator no longer uses `" " not in ssid`; `Home WiFi`, `Lab Network 2` and similar names are valid.
- **Unified 32-byte SSID contract**: a single C++ rule (`wifi_ssid_validation.h`, 1-32 UTF-8 bytes, control characters/all-space/template values rejected) is mirrored by the Python build-time validator and enforced for `wifi connect <ssid>` at runtime.
- **Python/C++ SSID rule parity test**: both languages consume the same shared test vectors and return identical valid/errorCode results.

### Notes

- Cloud API, database, MQTT message format, and the PCB are unchanged; PCB stays Rev 1.0.1.
- Prefer a CA certificate for long-term deployments; a fingerprint pins the current server certificate and must be updated when the certificate rotates.

## [1.2.4] - 2026-08-02

### Fixed

- **Local-WPA boot SSID state**: a connection-source model was introduced (compiled local WPA / campus open SSID / runtime open SSID / none); after boot, `wifi status` and the boot log show the actual SSID that was used.
- **`wifi connect <ssid>` no longer overridden by local WPA**: an explicit open SSID keeps its own source and is never silently replaced by the compiled local credentials; `wifi connect` (no arguments) restores the local WPA configuration.
- **Real association-path host integration tests**: an injectable station adapter and a production association controller let host tests execute the real connection function.
- **Unmodified cloud secret templates are rejected**: build-time and runtime content validation reject template hosts, invalid ports, template device IDs/credentials, and missing TLS material.
- **Stricter TLS configuration validation**: local cloud configs must provide at least one valid CA certificate or TLS fingerprint.

### Notes

- Firmware, cloud API, and database format are unchanged; PCB stays Rev 1.0.1.

## [1.2.3] - 2026-08-02

### Fixed

- **Boot-time network policy for credentials-free public builds**: `WIFI_AUTOCONNECT_ON_BOOT` is no longer triggered by `ENABLE_CLOUD` alone. Compiling the cloud module provides no SSID and no connection identity, so `public` and `public-cloud-example` no longer auto-associate at boot.
- **Empty-SSID hard guard**: when no SSID is configured the firmware prints `WIFI_CONNECT_SKIPPED reason=SSID_NOT_CONFIGURED` and calls no `WiFi.begin()` overload, staying disconnected; a missing local WPA password is skipped the same way.
- **local-wifi-cloud semantics fixed**: the profile now enables `ENABLE_CLOUD_CREDENTIALS=1` and requires the local `cloud_secrets.h`; the build stops when either `wifi_secrets.h` or `cloud_secrets.h` is missing instead of falling back to a credentials-free example.
- **Documentation corrections**: the READMEs no longer claim firmware-only phone control, a simulated device, freely swappable components, or that any ESP8266 board runs unmodified; the first-time setup guide uses the real `Remote_AC_Controller.ino.globals.h` filename; the Xidian campus guide states the real capabilities of `local-campus-example` (`ENABLE_AUTO_CAMPUS_AUTH=0`, no real credentials, no automatic login).

### Notes

- Firmware, cloud API, and database format are unchanged; PCB stays Rev 1.0.1.

## [1.2.2] - 2026-08-02

### Added

- **Home/lab WPA or WPA2 Wi-Fi configuration**: new
  `firmware/shared/RemoteACCore/src/config/wifi_secrets.example.h` placeholder
  template with `ENABLE_WIFI_CREDENTIALS` / `ENABLE_AUTO_WIFI_CONNECT` feature
  gates; the no-argument `wifi connect` serial command uses the compiled-in
  local credentials; `local-wifi` / `local-wifi-cloud` PlatformIO profiles are
  wired into `dev.ps1` and build-verified. Passwords never appear in serial
  logs, build flags, CI environments, or README examples.
- **First-time setup guides (bilingual)**: `docs/中文/首次配置.md` /
  `docs/English/first-time-setup.md`, covering home Wi-Fi, Xidian campus
  network, and offline modes.
- **Windows CI IR learner gate**: new `ir-simple-learner-windows` job
  (`windows-latest` + Python 3.12) installing locked dependencies, running
  both IR unit test trees, 20 stability rounds, the official
  `build.ps1 -Clean`, EXE `--self-test`, SHA-256 computation, credential/real-IR
  scans, and uploading the EXE as a CI artifact.
- **Official build.ps1 (Python 3.12 + PyInstaller 6.21.0)**: native-process
  helper (System.Diagnostics.Process) fixes PowerShell 5.1 stderr
  misdetection; `requirements-lock.txt` is pinned and hash-verified;
  `--self-test` / `--version` write report files for the windowed EXE.
- **README interface previews**: desktop (1440×900) and mobile (390×844)
  control-interface screenshots built from the local frontend with synthetic
  demo data.

### Fixed

- IR learner state machine: the mutually-exclusive if/elif between
  `ir.learn.cancelled` and `State.EXITING` made the exit-completion branch
  unreachable, leaving the flow stuck in EXITING; after refactoring all 12
  unit tests pass and stay green for 20 consecutive rounds.
- IR learner preset-count assertion: the authoritative contract is 10 presets;
  the test now uses a single source of truth and adds a codeId-uniqueness
  check; both tool copies are enforced identical by
  `tools/check-ir-tool-parity.py`.
- v1.2.1 official build-chain issues: requirements-lock.txt pins
  PyInstaller 6.21.0 (matching the release build) and build.ps1 rebuilds the
  EXE from a clean environment through the locked dependencies.
- README navigation (Chinese uses Chinese-title anchors) and visible `.md`
  suffix link labels in both READMEs.
- Firmware documentation drift: removed stale `v0.4.0-cloud-foundation`
  version strings and outdated `campus_credentials.h` paths; versions are
  unified to v1.2.2.

### Security

- Wi-Fi credentials and campus credentials are strictly separated
  (`wifi_secrets.h` / `campus_secrets.h` are both git-ignored); no mode ever
  writes a password to logs.
- New compile-time `#error` guards for illegal flag combinations:
  `ENABLE_WIFI_CREDENTIALS` / `ENABLE_AUTO_WIFI_CONNECT` require
  `ENABLE_WIFI`; local Wi-Fi credentials and campus authentication are
  mutually exclusive.

### Known issues

- No validated BOM or pick-and-place files are provided.
- Real AC IR frames are not in the public repository; capture your own with
  the IR learning tool.
- v1.2.1's IR learner release flow did not fully pass the official build
  script and full unit tests; use v1.2.2 or newer (the v1.2.1 tag and assets
  are kept for historical audit).

## [1.2.1] - 2026-08-01

### Changed

- Bilingual READMEs re-architected for developers.
- Community files (CONTRIBUTING / SECURITY / SUPPORT) are now actionable
  guides instead of stub redirects.
- PCB revision is separated as Rev 1.0.1 (software release vs PCB design
  revision).

### Fixed

- Corrected PCB manufacturing files (Gerber, drill, flying-probe data, and
  EasyEDA project).
- Corrected the ESP32 misstatement in the PCB README (the board is a
  NodeMCU ESP8266 development board).
- Removed stale release links and non-existent BOM/coordinate claims from the
  READMEs.
- Fixed the double-"v" startup banner (now `firmware v1.2.1`).
- Fixed English README semantic links (Chinese entries point to Chinese docs,
  English entries to English docs).

### Security

- Manufacturing data is now published byte-for-byte (`.gitattributes` +
  deterministic packaging) so line-ending conversion can no longer drift the
  published hashes.

### Known issues

- A verified BOM or pick-and-place file is not provided.
- Real AC IR frames are not shipped in the public repository; capture your own
  with the IR learning tool.
- The v1.2.0 auto-generated source archives still contain the old PCB files;
  use v1.2.1 for PCB manufacturing.

No cloud API or database schema changes.

## [1.2.0] - 2026-08-01

First Monorepo unified release.

- Optional Xidian/Srun campus-network authentication (off by default; public
  builds contain no credentials).
- Disconnect and session recovery: automatic reconnection after Wi-Fi drop,
  IP change, or portal re-appearance.
- PlatformIO and Arduino IDE build verification.
- Complete bilingual documentation and unified CI.
- Monorepo unified publishing (firmware, cloud, PCB, tools, docs in one shot).

## [1.0.0] - 2026-07-31

Initial public release.

### Added

- ESP8266 firmware (PlatformIO and Arduino IDE workflows) with DHT11 sensing
  and MQTT/TLS transport.
- Cloud backend (Fastify + MQTT bridge) and Vue 3 frontend.
- IR learning tool (source + Windows EXE).
- Basic security model (dual-role, trusted sessions).
- Licensed under Apache License 2.0.
