[简体中文](../中文/文档导航.md) | **English**

# Documentation Index

This page indexes all English technical documentation for Remote AC Controller. Every document carries a language switch at the top so you can jump to its Chinese counterpart; the Chinese index lives at [中文文档导航](../中文/文档导航.md).

Back to the repository root: [`README.md`](./README.md)

## Getting Started

- [Project overview and quick start](./README.md) — capabilities, architecture diagram, one-shot validation commands
- [Arduino IDE guide](./arduino-ide-guide.md) — build, upload, and debug the firmware with Arduino IDE 2.x
- [Deployment](./deployment.md) — full deployment flow for backend, frontend, and MQTT broker
- [Operations guide](./operations-guide.md) — routine checks, logs, certificate rotation, upgrades

## How It Works

- [Architecture](./architecture.md) — end-to-end components, data flow, and boundaries
- [Security model](./security-model.md) — roles, sessions, IR kill switches, threat surface
- [Xidian campus network authentication](./xidian-campus-network-authentication.md) — automatic Srun authentication on ESP8266 boot
- [Srun campus network porting guide](./srun-campus-network-porting-guide.md) — adapting to other Srun-based campuses

## Hardware and Wiring

- [Hardware](./hardware.md) — board, sensor, IR module, and PCB selection
- [Wiring](./wiring.md) — pin assignment and physical wiring

## IR Learning

- [IR learning](./ir-learning.md) — capture remote-control IR frames and load them into firmware

## Cloud and MQTT

- [MQTT protocol](./mqtt-protocol.md) — topic naming, payload structure, presence detection

## Automation

- [Scheduling](./scheduling.md) — weekly cron-style scheduled tasks
- [Temperature automation](./temperature-automation.md) — dual-threshold hysteresis control

## Deployment and Operations

- [Deployment](./deployment.md) — production deployment steps
- [Operations guide](./operations-guide.md) — runtime maintenance
- [Resource-constrained deployment](./resource-constrained-deployment.md) — build and runtime constraints on a 1 GB host

## Security

- [Security model](./security-model.md) — design-level security boundaries
- [Security policy](./security.md) — vulnerability reporting process and supported scope

## Troubleshooting

- [Troubleshooting](./troubleshooting.md) — common symptoms, diagnosis, and fixes

## Backup and Recovery

- [Backup and recovery](./backup-and-recovery.md) — database and configuration backup, restore, and drills

## Project and Community

- [Contributing](./contributing.md) — development workflow, commit conventions, required gates
- [Code of conduct](./code-of-conduct.md) — community behaviour standards
- [Support](./support.md) — support scope and help channels
- [Changelog](./changelog.md) — release history

## Licensing

- [Third-party notices](./third-party-notices.md) — licences and provenance of dependencies
- [Apache-2.0 licence](../../LICENSE) — authoritative English text (a Chinese reference translation is available at [Apache-2.0 许可证参考译文](../中文/Apache-2.0许可证参考译文.md))
