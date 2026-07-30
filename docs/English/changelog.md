[简体中文](../中文/更新日志.md) | **English**

# Changelog

All notable changes to this project are documented here. This repository
follows a Monorepo layout combining the ESP8266 firmware and the cloud
backend/frontend into a single published history.

> **Status:** public pre-release on `main`; `v1.0.0` has **not** been released yet.
> The entry below is planned as the first public `v1.0.0` release. It is only
> converted to `## [1.0.0] - <real release date>` once the `v1.0.0` tag and
> GitHub Release are actually created. Do not claim a release prematurely.

## [Unreleased]

Planned as the first public `v1.0.0` release.

### Added
- Initial public open-source release of the Remote AC Controller system.
- `firmware/`: ESP8266 (NodeMCU) firmware with DHT11 temperature/humidity
  sensing, IR learning and transmission, MQTT client with TLS, and 11-state
  air-conditioner control.
- `cloud/`: Fastify backend (MQTT bridge, scheduling, temperature automation,
  weather, dashboard API, Owner/Guest and trusted-device model), Vue 3
  responsive frontend, Mosquitto broker configuration, and deployment tooling.
- `docs/`: architecture, hardware, wiring, IR learning, MQTT protocol,
  security model, scheduling, temperature automation, deployment, and
  troubleshooting documentation.
- `tools/`: `test-all.ps1` and `build-all.ps1` for unified validation.
- `.github/workflows/ci.yml`: `firmware-ci` and `cloud-ci` jobs.
- Licensed under Apache License 2.0.

### Security
- No production credentials, private keys, real IR data, databases, or
  production environment files are included.
- Public firmware and cloud defaults are non-production safe.
