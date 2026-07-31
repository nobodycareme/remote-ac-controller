[简体中文](../中文/更新日志.md) | **English**

# Changelog

## [1.2.0] - 2026-08-01

Canonical monorepo consolidation release.

- Single authoritative monorepo established; the two split repositories are
  retained only as private archived records (histories not merged; zero secret
  leakage).
- Production-grade automatic Xidian campus authentication: authEpoch cycle
  model + policy backoff/quota/hard-block + compile-time feature-gate
  dependency constraints; recovery on Wi-Fi drop, DHCP change and portal
  re-appearance; 30/60/120s backoff ladder.
- Host tests: CampusAuthPolicy / feature gates / auth epoch / campus profiles.
- Cloud security consolidation (backend_verify.js credentials come only from
  the environment).
- Complete bilingual documentation paths (24 doc-map pairs + three checkers).
- Unified CI (11 jobs) + unified version v1.2.0 + BOM/mojibake cleanup.

All notable changes to this project are documented here. This repository
follows a Monorepo layout combining the ESP8266 firmware and the cloud
backend/frontend into a single published history.

## [1.0.0] - 2026-07-31

Initial public release.

### Added
- Initial public open-source release of the Remote AC Controller system.
- **Complete Monorepo**: firmware, cloud, frontend, docs in a single repo.
- **Dual firmware modes**: PlatformIO Agent automation + Arduino IDE manual, sharing one core codebase.
- **ESP8266 firmware**: DHT11 sensing, MQTT/TLS secure transport, 11-state IR AC control.
- **Cloud backend**: Fastify + MQTT bridge, scheduling engine, dual-threshold temperature automation, weather data caching, Owner/Guest auth model, trusted devices, telemetry logging.
- **Vue 3 frontend**: responsive cross-device UI, 11-state control panel, schedule & automation management.
- **PCB design files**: EasyEDA Pro source, Gerber manufacturing files, drill files, BOM, JLCPCB fabrication pack.
- **IR learning tool**: source code + Windows x64 EXE (CH9102 serial capture).
- **Complete bilingual docs**: 21 Chinese + 20 English documents.
- **GitHub Actions CI**: PlatformIO + Arduino CLI + Cloud + Repo Hygiene.
- Licensed under Apache License 2.0.

### Security
- No production credentials, private keys, real IR data, databases, or
  production environment files are included.
- Public firmware and cloud defaults are non-production safe.
