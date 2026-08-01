**English** | [简体中文](../中文/版本管理.md)

# Versioning

## Version scheme

- **Software version**: `vX.Y.Z` (Semantic Versioning), driven by the root
  `VERSION` file, covering firmware, backend, frontend, and docs.
- **PCB revision**: `Rev x.y.z`, independent of the software version, recorded
  in `hardware/pcb/REVISION`.

The two are independent: a PCB revision change does not require a software
version change and vice versa.

## Changing the software version

- After editing the root `VERSION`, update in sync:
  - `cloud/VERSION`, `firmware/agent-platformio/VERSION`
  - `cloud/backend/package.json` and `package-lock.json`
  - `cloud/frontend/package.json` and `package-lock.json`
  - `FIRMWARE_VERSION` in
    `firmware/shared/RemoteACCore/src/app_config.h`
  - the `version` field in `docs/doc-map.json`
- `tools/check-version.py` reads the root `VERSION` dynamically, validates all
  of the above, and asserts the startup banner never shows a double `v`.

## Startup banner convention

- Firmware constant: `#define FIRMWARE_VERSION "vX.Y.Z"` (with the `v` prefix).
- The banner prefix has no `v`: `Remote AC Controller  firmware `, which
  combined with the constant renders `firmware vX.Y.Z`.
- The `version` command and telemetry output `vX.Y.Z` directly (single `v`).

## Tags and immutability

- Releases use an **annotated tag** (`vX.Y.Z`); push only that tag.
- Tags are immutable: no moving, rewriting, or delete-and-recreate.
- After a release, fix issues in a patch release — never touch the published
  tag.

## PCB revision changes

- See [hardware-release-process](./hardware-release-process.md); the revision
  is recorded in `hardware/pcb/REVISION` and `hardware/pcb/CHANGELOG.md`.

## Related documents

- [maintainer-release-process](./maintainer-release-process.md)
- 简体中文: [版本管理](../中文/版本管理.md)、
  [维护者发布流程](../中文/维护者发布流程.md)
