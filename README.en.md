<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="./docs/English/documentation-index.md">Documentation</a> ·
  <a href="./README.md">简体中文</a>
</p>

<p align="center">
  <img src="./docs/assets/logo.svg" alt="Remote AC Controller" width="240" />
</p>

<h1 align="center">Remote AC Controller</h1>
<p align="center">Connect an ordinary IR air conditioner to a phone web UI with an ESP8266.</p>

<p align="center">
  <a href="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml"><img src="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/nobodycareme/remote-ac-controller/releases"><img src="https://img.shields.io/github/v/release/nobodycareme/remote-ac-controller" alt="Latest Release" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
</p>

## Overview

The project started with a practical goal: control an ordinary IR air conditioner from a NodeMCU, then document the firmware, web service, PCB, and IR learning workflow needed to build it from scratch.

## Interface preview

<table>
  <tr>
    <td width="70%"><img src="./docs/assets/screenshots/dashboard-desktop.png" alt="Desktop control interface" /></td>
    <td width="30%"><img src="./docs/assets/screenshots/dashboard-mobile.png" alt="Mobile control interface" /></td>
  </tr>
</table>

One responsive interface works on desktop and mobile. <sub>The screenshots contain demo data and show layout only.</sub>

## Core capabilities

- Control AC power, mode, and common states from a phone web page
- View DHT11 temperature, humidity, and device presence
- Run recurring scheduled tasks
- Use dual-threshold hysteresis to avoid rapid cycling
- Connect the ESP8266 and cloud through MQTT, with optional Srun campus access
- Learn IR codes from your own remote

## Quick start

| Goal | Next step |
|---|---|
| Validate the source | Run the public PlatformIO build below; no real credentials are needed. |
| Build a physical device | Follow [Wiring](./docs/English/wiring.md), [First-time setup](./docs/English/first-time-setup.md), and [IR learning](./docs/English/ir-learning.md), then flash the firmware. |
| Deploy full web control | Use the [Deployment guide](./docs/English/deployment.md) to configure the backend, frontend, and MQTT broker before connecting the device. |

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile public
```

The public profile still compiles the Wi-Fi and cloud modules, but it contains no real credentials and does not connect automatically at boot.

## System layout

```text
Phone web UI → Fastify backend → MQTT → ESP8266 → IR → AC
```

The Vue 3 frontend serves desktop and mobile clients. A NodeMCU ESP8266 reads the sensor and drives the IR module.

| Directory | Contents |
|---|---|
| `firmware/` | PlatformIO and Arduino IDE firmware projects |
| `cloud/` | Fastify backend, Vue 3 frontend, and deployment configuration |
| `hardware/` | Wiring, PCB sources, and manufacturing files |
| `tools/` | IR learning application and project maintenance scripts |
| `docs/` | English and Chinese user, design, and maintenance guides |

## Verified hardware

| Category | Model or revision |
|---|---|
| Board | NodeMCU ESP8266 |
| Temperature and humidity sensor | DHT11 |
| IR module | ZJ-IR-V2 |
| PCB | Rev 1.0.1 |

Other boards or IR modules require a fresh check of pins, voltage levels, and communication protocols.

## Documentation

| Getting started | Architecture and protocols | Maintenance | Participate |
|---|---|---|---|
| [First-time setup](./docs/English/first-time-setup.md) | [Architecture](./docs/English/architecture.md) | [Operations guide](./docs/English/operations-guide.md) | [Contributing](./CONTRIBUTING.md) |
| [Arduino IDE](./docs/English/arduino-ide-guide.md) | [MQTT protocol](./docs/English/mqtt-protocol.md) | [Troubleshooting](./docs/English/troubleshooting.md) | [Support](./SUPPORT.md) |
| [Deployment](./docs/English/deployment.md) | [Security model](./docs/English/security-model.md) | [Backup and recovery](./docs/English/backup-and-recovery.md) | [Security policy](./SECURITY.md) |

See the [English documentation index](./docs/English/documentation-index.md) for the complete list.

## Security and limits

<details>
<summary>Boundaries to review before building</summary>

- The public repository contains no real Wi-Fi, MQTT, or campus-network credentials.
- Real AC IR codes are not included; capture them from your own remote.
- Firmware safety policy restricts real IR transmission by default.
- Other boards and IR modules may need adaptation.
- The Windows IR learner executable is unsigned.
- PCB files do not include an unverified BOM or pick-and-place data.

</details>

## Contributing, support, and license

Read [Contributing](./CONTRIBUTING.md) before submitting a change. [Support](./SUPPORT.md) directs usage questions and defects; report vulnerabilities through GitHub Private Vulnerability Reporting rather than a public issue.

The project is licensed under [Apache License 2.0](./LICENSE). Dependency licences are listed in [Third-party notices](./docs/English/third-party-notices.md).
