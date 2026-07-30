[简体中文](./README.md) | **English**

# Remote AC Controller

**English** | [简体中文](./README.md)

A full-stack, open-source system to control an air conditioner remotely from a
phone web app, through a cloud backend, over MQTT, down to an ESP8266 that
drives the AC via learned infrared (IR) signals.

> **Status:** public pre-release on main; v1.0.0 has not been released yet.
> **License:** [Apache License 2.0](./LICENSE)

---

## What It Does

```
Phone Web App ──▶ Cloud Backend ──▶ MQTT (TLS) ──▶ ESP8266 ──▶ IR ──▶ Air Conditioner
                    │
                    ├─ Scheduling (timers)
                    ├─ Temperature Automation (DHT11 + rules)
                    ├─ Weather-aware behavior
                    ├─ Owner / Guest & trusted-device model
                    └─ Dashboard, telemetry, command ACK
```

- **Phone web app** — responsive Vue 3 UI for status, control, schedules,
  automation, and device management.
- **Cloud backend** — Fastify + MQTT bridge, scheduling engine, temperature
  automation, weather integration, Owner/Guest auth, trusted-device model,
  telemetry, and a dashboard API. Uses an embedded `node:sqlite` database.
- **MQTT** — TLS-secured broker (Mosquitto) connecting the cloud backend and
  the device.
- **ESP8266 firmware** — NodeMCU/ESP8266 with DHT11 temperature/humidity
  sensing, IR learning + transmission, secure MQTT client, and an 11-state AC
  control model.
- **Infrared** — learns and replays AC IR codes; supports 11 discrete AC
  states plus temperature setpoints.

## Key Features

- 11 air-conditioner states (on/off, mode, fan, swing, sleep, turbo, eco,
  dry, health, display, timer) with per-state enable flags.
- Temperature & humidity monitoring (DHT11 on GPIO5).
- Scheduling and temperature-based automation.
- Owner / Guest accounts with a trusted-device model and persistent trusted
  sessions.
- Responsive, cross-device web UI (desktop and mobile).
- Secure-by-default: TLS MQTT, scoped credentials, no real secrets in the
  public repo.

## Repository Layout

This is a **Monorepo** combining two previously separate projects (firmware
and cloud) into one published Git history.

```
remote-ac-controller/
├─ firmware/      # ESP8266 firmware (PlatformIO)
│  ├─ src/  include/  lib/  test/  tools/  platformio.ini  README.md
├─ cloud/        # Backend + frontend + broker + deploy + tools
│  ├─ backend/  frontend/  broker/  deploy/  tools/  README.md
├─ docs/         # Architecture, hardware, IR, MQTT, security, ops, backup (13 documents)
├─ hardware/     # Public BOM / wiring summary / what is not published
├─ tools/        # test-all.ps1, build-all.ps1
├─ .github/      # CI workflows
├─ LICENSE  NOTICE  THIRD_PARTY_NOTICES.md
├─ README.md (中文)  README_EN.md (English)
└─ CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md  SUPPORT.md  CHANGELOG.md
```

No Git submodules are used; a single `git clone` yields the complete firmware
and cloud source.

## Quick Start (Safe / Non-Production)

The public repository defaults to **non-production** behavior.

### Firmware

```powershell
cd firmware
# Build/test using the provided entry point (do NOT call pio directly):
./tools/dev.ps1 test
./tools/dev.ps1 verify
# Build a public profile:
./tools/dev.ps1 build <public-profile>
```

The public firmware profile does **not** embed production Wi-Fi, MQTT
credentials, or real IR data, and does not transmit real IR by default.

### Cloud

```bash
cd cloud/backend && npm ci && npm test
cd cloud/frontend && npm ci && npm test && npm run build
```

The default cloud configuration binds to `localhost`, uses `example.com`
placeholders, an empty/test database, a local test MQTT address, IR disabled,
and automation disabled. Operators supply their own cookie/session signing key.

### Unified Validation

From the repository root:

```powershell
./tools/test-all.ps1
./tools/build-all.ps1
```

## Security & Safe Defaults

- **No production secrets** are included: no Wi-Fi/MQTT passwords, no TLS
  private keys, no real IR data, no databases, no production environment files.
- Public firmware/cloud defaults are non-production safe (see
  [`SECURITY.md`](./SECURITY_EN.md)).
- Self-hosters must provision their own MQTT credentials, TLS certificates,
  and IR codes.
- See [`docs/security-model.md`](./docs/security-model_EN.md) for the threat
  model and [`docs/deployment.md`](./docs/deployment_EN.md) for hardening.

## Requirements

| Component | Requirement |
|---|---|
| Node.js | **≥ 22.5**, 24 recommended — the backend uses the built-in `node:sqlite` module, which does not exist on Node 20 |
| Toolchain | None. No dependency requires native compilation (`node:sqlite`, `bcryptjs`) |
| Board | NodeMCU / ESP8266 (ESP-12E/F), PlatformIO |
| Host | 1 GB RAM is workable if you build off-host — see [`docs/resource-constrained-deployment.md`](./docs/resource-constrained-deployment_EN.md) |

## Documentation

[`docs/`](./docs) — thirteen documents, grouped by what you are trying to do:

| Getting it working | Understanding it | Running it |
|---|---|---|
| [`hardware.md`](./docs/hardware_EN.md) | [`architecture.md`](./docs/architecture_EN.md) | [`deployment.md`](./docs/deployment_EN.md) |
| [`wiring.md`](./docs/wiring_EN.md) | [`mqtt-protocol.md`](./docs/mqtt-protocol_EN.md) | [`operations-guide.md`](./docs/operations-guide_EN.md) |
| [`ir-learning.md`](./docs/ir-learning_EN.md) | [`security-model.md`](./docs/security-model_EN.md) | [`resource-constrained-deployment.md`](./docs/resource-constrained-deployment_EN.md) |
| | [`scheduling.md`](./docs/scheduling_EN.md) · [`temperature-automation.md`](./docs/temperature-automation_EN.md) | [`troubleshooting.md`](./docs/troubleshooting_EN.md) · [`backup-and-recovery.md`](./docs/backup-and-recovery_EN.md) |

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING_EN.md). Contributions are licensed under
Apache-2.0.

## License

[Apache License 2.0](./LICENSE). A non-authoritative Chinese translation is
available in [`LICENSE_ZH.md`](./LICENSE_ZH.md). Third-party licenses are
aggregated in [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES_EN.md).

## Known Limitations

- Real IR codes for specific AC models are not included (operators supply
  their own).
- The public release is source-only; production deployment (TLS, MQTT ACLs,
  secrets) is the operator's responsibility.
- Some hardware/PCB artifacts may be omitted if they cannot be published under
  compatible licenses.
- Backup and recovery guidance is in
  [`docs/backup-and-recovery.md`](./docs/backup-and-recovery_EN.md).
