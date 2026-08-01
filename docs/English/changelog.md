[简体中文](../中文/更新日志.md) | **English**

# Changelog

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
