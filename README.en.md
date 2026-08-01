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
<p align="center">Control an ordinary air conditioner from your phone with an ESP8266, an IR module, and a web page.</p>

<p align="center">
  <a href="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml"><img src="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/nobodycareme/remote-ac-controller/releases"><img src="https://img.shields.io/github/v/release/nobodycareme/remote-ac-controller" alt="Latest Release" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
</p>

---

## Overview

Remote AC Controller is an ESP8266-based air conditioner remote control project. The device controls the AC through infrared and reports temperature, humidity, and device status to a web page. The repository includes firmware, cloud services, PCB files, and an IR learning tool.

With a NodeMCU board, an IR transmitter, and a small temperature/humidity sensor, you can build the whole system. The IR codes are learned from your own remote, so it works with most infrared-controlled air conditioners.

The project is designed for everyday use: the web UI works on phones, and you can deploy it on a LAN or on a public server. The firmware supports home Wi-Fi and optional campus network access to fit different environments.

## Interface preview

<p align="center">
  <img src="./docs/assets/screenshots/dashboard-desktop.png" alt="Desktop control interface" width="820" />
</p>

<p align="center">
  <img src="./docs/assets/screenshots/dashboard-mobile.png" alt="Mobile control interface" width="320" />
</p>

Desktop and mobile use the same responsive page; the data in the screenshots is demo data shown for layout illustration only.

## Features

- Control AC power, mode, and common states from the phone web page;
- DHT11 temperature and humidity monitoring;
- Scheduled tasks and temperature-based automation;
- ESP8266 communicates with the cloud over MQTT;
- Supports home WPA/WPA2 Wi-Fi and optional Srun campus network auth;
- IR learning tool to capture data from your own remote.

Phone web control requires the frontend, backend, MQTT broker, and ESP8266 firmware running together. The firmware can also be used standalone for serial interaction, sensor reading, and IR hardware debugging. The parts can be developed and deployed separately; when replacing the frontend, backend, broker, or firmware, keep the existing API and MQTT protocol compatible.

## Quick start

| Goal | Start here |
|---|---|
| Home or lab Wi-Fi | [First-time setup](./docs/English/first-time-setup.md) |
| Xidian campus network | [Xidian campus authentication](./docs/English/xidian-campus-network-authentication.md) |
| Build the ESP8266 firmware | [PlatformIO firmware guide](./firmware/agent-platformio/README.en.md) |
| Use Arduino IDE | [Arduino IDE guide](./docs/English/arduino-ide-guide.md) |
| Deploy your own server | [Deployment guide](./docs/English/deployment.md) |
| Learn your own remote | [IR learning guide](./docs/English/ir-learning.md) |
| Manufacture the PCB | [PCB documentation](./hardware/pcb/README.en.md) |

A minimal public build:

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile public
```

This is a credentials-free public build, not an offline build: the firmware still compiles the Wi-Fi and cloud modules, just without real credentials, and it does not auto-connect at boot.

To set up local credentials for a home router or the Xidian campus network and to flash the firmware, start with the [first-time setup guide](./docs/English/first-time-setup.md). To check that your toolchain works, run the command above — no credential files are needed.

## System layout

```
Phone web page → Cloud → MQTT → ESP8266 → IR → AC
```

The server uses Fastify, the frontend uses Vue 3, and the device is a NodeMCU ESP8266.

The repository is organized by directory: `firmware/` holds the ESP8266 firmware (PlatformIO and Arduino IDE workflows), `cloud/` holds the backend and web frontend, `hardware/` holds the PCB files, and `tools/` holds the IR learning tool and helper scripts. The parts communicate over the MQTT message protocol, documented in [MQTT protocol](./docs/English/mqtt-protocol.md).

The backend, web frontend, and firmware can be started and debugged separately; complete phone control needs all three plus an MQTT broker. The firmware supports several network access methods — see the [first-time setup guide](./docs/English/first-time-setup.md).

## Hardware

- Board: NodeMCU ESP8266
- Temperature/humidity: DHT11
- IR module: ZJ-IR-V2
- PCB: Rev 1.0.1

The project has been developed and validated on NodeMCU ESP8266, DHT11, and ZJ-IR-V2. When using other ESP8266 boards or IR modules, re-check the pin mapping, voltage levels, and communication protocol.

The public repository does not ship real AC IR codes, and no validated BOM or pick-and-place files are provided. Use the [IR learning guide](./docs/English/ir-learning.md) to capture data from your own remote, then follow the [first-time setup guide](./docs/English/first-time-setup.md) to flash it.

## Documentation

| Understand the project | Use and configure | Maintain and troubleshoot |
|---|---|---|
| [Architecture](./docs/English/architecture.md) | [First-time setup](./docs/English/first-time-setup.md) | [Operations guide](./docs/English/operations-guide.md) |
| [Security model](./docs/English/security-model.md) | [Arduino IDE guide](./docs/English/arduino-ide-guide.md) | [Troubleshooting](./docs/English/troubleshooting.md) |
| [MQTT protocol](./docs/English/mqtt-protocol.md) | [Deployment guide](./docs/English/deployment.md) | [Backup and recovery](./docs/English/backup-and-recovery.md) |
| [Changelog](./docs/English/changelog.md) | [IR learning](./docs/English/ir-learning.md) | [Security policy](./docs/English/security.md) |

Chinese documentation is available from the [简体中文文档导航](./docs/中文/文档导航.md).

All documents are provided in both Chinese and English with the same structure, so you can switch languages side by side. If a topic is not listed in the table, check the [documentation index](./docs/English/documentation-index.md).

## Contributing and support

Issues and pull requests are welcome — please read the [contributing guide](./docs/English/contributing.md) first. If you find a problem, describing what you did and the environment helps maintainers fix it faster. Security vulnerabilities should be reported through GitHub Private Vulnerability Reporting; see the [security policy](./docs/English/security.md). For usage questions, check the [documentation index](./docs/English/documentation-index.md) or open an [Issue](https://github.com/nobodycareme/remote-ac-controller/issues).

The project is licensed under the [Apache License 2.0](./LICENSE); third-party component licenses are listed in the [third-party notices](./docs/English/third-party-notices.md). All code and docs are maintained in this repository; release notes are in the [changelog](./docs/English/changelog.md) and [GitHub Releases](https://github.com/nobodycareme/remote-ac-controller/releases).
