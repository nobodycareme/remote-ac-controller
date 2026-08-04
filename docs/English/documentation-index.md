[简体中文](../中文/文档导航.md) | **English**

# Documentation index

Start with one of the reading paths below, or browse by topic. Each first-party document appears in one group only.

## Recommended paths

- **Home user**: use [Getting started](#getting-started) in this order: wiring, first-time setup, IR learning, and deployment.
- **Source validation only**: open [Getting started](#getting-started) for the PlatformIO firmware project, then the Cloud development environment.
- **Maintainer**: read [Understand the system](#understand-the-system) before the operations and release guides.

## Getting started

- [First-time setup](./first-time-setup.md) — configure networking, credentials, and firmware safety switches
- [Wiring](./wiring.md) — verify pins and physical connections
- [Arduino IDE guide](./arduino-ide-guide.md) — build and upload with Arduino IDE 2.x
- [PlatformIO firmware project](../../firmware/agent-platformio/README.en.md) — build the firmware with the public profile
- [Deployment](./deployment.md) — deploy the backend, frontend, and MQTT broker

## Understand the system

- [Architecture](./architecture.md) — components, data flow, and boundaries
- [MQTT protocol](./mqtt-protocol.md) — topics, messages, and presence state
- [Security model](./security-model.md) — identity, sessions, credentials, and IR safety boundaries
- [Hardware](./hardware.md) — verified components and PCB file scope

## Feature guides

- [IR learning](./ir-learning.md) — capture and validate data from your own remote
- [Scheduling](./scheduling.md) — configure recurring tasks
- [Temperature automation](./temperature-automation.md) — configure dual-threshold hysteresis
- [Xidian campus network authentication](./xidian-campus-network-authentication.md) — configure the currently verified Srun access flow
- [Srun campus network porting guide](./srun-campus-network-porting-guide.md) — adapt the implementation to another Srun deployment

## Maintain the project

- [Operations guide](./operations-guide.md) — routine checks, logs, certificate rotation, and upgrades
- [Troubleshooting](./troubleshooting.md) — diagnose common firmware and cloud problems
- [Backup and recovery](./backup-and-recovery.md) — backup, restore, and drills
- [Resource-constrained deployment](./resource-constrained-deployment.md) — control build resources on a 1 GB host
- [Versioning](./versioning.md) — distinguish software versions from PCB revisions
- [Hardware release process](./hardware-release-process.md) — package and verify manufacturing files
- [Maintainer release process](./maintainer-release-process.md) — prepare, verify, and publish a version

## Participate

- [Contributing](./contributing.md) — development workflow and submission requirements
- [Support](./support.md) — routes for usage questions, defects, and proposals
- [Security policy](./security.md) — report vulnerabilities privately
- [Code of conduct](./code-of-conduct.md) — community collaboration rules
- [Changelog](./changelog.md) — software release history
- [Third-party notices](./third-party-notices.md) — dependency licences and provenance
- [Apache License 2.0](../../LICENSE) — authoritative project licence
