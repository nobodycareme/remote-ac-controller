# Third-Party Notices

This file aggregates third-party license information for components used by the
Remote AC Controller project. The project itself is licensed under the
Apache License, Version 2.0. Third-party components retain their own licenses
as noted below. This list is maintained as part of the open-source release
review; verify exact versions against each subsystem's dependency manifests
(`firmware/platformio.ini`, `cloud/backend/package.json`,
`cloud/frontend/package.json`) before redistribution.

## Firmware (PlatformIO / Arduino)

| Component | Role | License |
|-----------|------|---------|
| ArduinoJson | JSON (de)serialization | MIT |
| Adafruit Unified Sensor | Sensor abstraction | BSD-3-Clause |
| DHT sensor library (Adafruit) | DHT11/DHT22 read | MIT |
| ESP8266 Arduino Core / PlatformIO espressif8266 | MCU platform | LGPL-2.1 / various |
| BearSSL (ESP8266) | TLS | BSD-3-Clause (from ESP8266 core) |
| IR libraries used for learning/transmit | IR encode/decode | Check per-library (commonly MIT/GPL) |

> Maintainers must confirm the exact IR library license (MIT vs GPL) before
> publishing IR-related code; GPL dependencies must not be statically required
> for the default open-source build.

## Cloud Backend (Node.js)

| Component | Role | License |
|-----------|------|---------|
| Fastify | HTTP server | MIT |
| MQTT.js | MQTT client | MIT |
| node:sqlite (Node 22+) | Embedded database | MIT (Node.js) |
| Vitest | Testing | MIT |
| TypeScript | Language/type-check | Apache-2.0 |
| Vue 3 | Frontend framework | MIT |
| Vite | Frontend build | MIT |

## Frontend (Vue 3)

| Component | Role | License |
|-----------|------|---------|
| Vue 3 | UI framework | MIT |
| TypeScript | Language | Apache-2.0 |
| Vite | Bundler | MIT |
| ECharts (if bundled) | Charts | Apache-2.0 / BSD |
| Various UI/util libraries | UI primitives | MIT (per dependency) |

## Assets

- Icons/symbols, SVG, fonts, and images included in the repository must carry
  their own license or be original. Any asset without a clear license is
  excluded from the public release.
- Contributor Covenant text in `CODE_OF_CONDUCT.md` is licensed CC-BY-4.0.

## Notes

- No third-party component in this repository is relicensed as Apache-2.0
  original work; each retains its stated license.
- If any dependency's license is incompatible with an open-source distribution
  goal (e.g., GPL with static-linking implications), it must be removed or
  replaced prior to release.
