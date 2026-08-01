**English** | [简体中文](../中文/维护者发布流程.md)

# Maintainer Release Process

This document is for repository maintainers. It defines the end-to-end flow
from commit to a v1.2.x release.

## Pre-release checks

- Create the release-prep branch (`release/vX.Y.Z`) from a clean `main`.
- Pass locally: `tools/test-all.ps1`, `tools/build-all.ps1`, and
  `check-doc-parity.py` / `check-doc-links.py` / `check-doc-language-links.py` /
  `check-public-docs.py` / `check-version.py` / `check-pcb-release.py`.
- Bilingual docs must be updated in pairs (`docs/中文/` ↔ `docs/English/`) and
  `docs/doc-map.json` refreshed.
- Run the secret/private-key/database/real-IR exclusion scan; the public tree
  must show 0 hits.

## Versioning and tags

- The root `VERSION` file is the single source of truth; `check-version.py`
  validates every version file dynamically.
- The software version (vX.Y.Z) and the PCB revision (Rev x.y.z) are
  independent.
- On release, create an **annotated tag** (e.g. `v1.2.1`) and push only that
  tag — never `git push --tags`.
- **Tags are immutable once pushed.** Fix issues in a new patch release.

## Release asset rules

- **Never silently replace a published asset.** If an asset is wrong after the
  release, publish a patch release (v1.2.1 → v1.2.2) and add a bilingual
  "superseded" notice at the top of the old release body.
- After tagging, **re-download every asset** (including GitHub's auto source
  zip/tar.gz) and verify each SHA-256 before announcing.
- Manufacturing packages use deterministic packaging
  (`tools/package-pcb-release.py`); the same commit must produce the same ZIP
  twice.
- `SHA256SUMS.txt` lists all release assets and ships with the release.
- Release bodies must be curated by a human; auto-generated drafts are only a
  starting point.

## PCB publishing

- The manufacturing package contains only `gerber/`, `drill/`,
  `test/FlyingProbeTesting.json`, `manufacturing-manifest.md`, and
  `PCB下单必读.txt`.
- The EasyEDA source stays in the tagged source tree and is not part of the
  manufacturing ZIP by default.
- Hashes inside the package must match `manufacturing-manifest.md` and both
  must be computed over Git-controlled bytes (immune to line-ending settings).
- See [hardware-release-process](./hardware-release-process.md).

## Forbidden

- Never put `Private/`, `Evidence/`, `Archives/`, `Deliverables/`, or
  production data into the public repository.
- Never publish production servers, domains, MQTT credentials, or real IR
  frames.
- Never rewrite pushed history or move published tags.

## Related documents

- [versioning](./versioning.md)
- [hardware-release-process](./hardware-release-process.md)
- 简体中文: [维护者发布流程](../中文/维护者发布流程.md)、
  [版本管理](../中文/版本管理.md)、[PCB 发布流程](../中文/PCB发布流程.md)
