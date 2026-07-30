# Remote AC Controller — Release Handoff & Recovery Guide

> **Status: SAFE-TO-RELEASE (LOCAL) — server-independent preparation is complete. NOT published.**
> Production rotation is pending; all publish/rotation gates are intentionally closed.

This document is the authoritative handoff for taking the sanitized monorepo from its
current local state to a public GitHub release. It records the verification evidence,
the explicit "not done" list, and the exact 11-step continuation sequence to run **after**
production credentials/servers are rotated.

---

## 0. TL;DR

- The monorepo is **fully sanitized**: working tree + all 28 commits + every git object
  were scanned and contain **zero** residual sensitive strings.
- All **server-independent** preparation is DONE: documentation set, portability/leak
  fixes, and the Round-7 full-history rewrite (`git filter-repo`).
- All **server-dependent / publish** actions (GitHub repo, `v1.0.0` tag, Release,
  production credential & TLS rotation) are **NOT performed** and are gated behind the
  production-rotation step.
- Local verification: **164 tests pass** (backend 78 + frontend 86), both `tsc --noEmit`
  checks pass.

---

## 1. Status Dashboard

| Field | Value | Meaning |
|---|---|---|
| `PRODUCTION_SERVER_REACHABLE` | **False** | Production host not touched / not verified this session |
| `PUBLIC_PUSH_ALLOWED` | **False** | No public repository created or pushed |
| `GITHUB_PUSH_PASS` | **False** | No push performed |
| `HISTORY_SANITIZED` | **True** | Verified: 0 residual across all git objects |
| `WORKING_TREE_SANITIZED` | **True** | Verified: 0 residual in working tree |
| `MONOREPO_LOCAL_TEST_PASS` | **True** | 164 tests pass (backend 78 + frontend 86) |
| `MONOREPO_LOCAL_BUILD_PASS` | **Partial** | Backend `tsc` OK; frontend `vite build` deferred (off-machine); firmware build deferred (no PlatformIO) |
| `V1_0_0_TAG_CREATED` | **False** | Forbidden by gate |
| `GITHUB_REPO_CREATED` | **False** | Forbidden by gate |
| `PRODUCTION_ROTATION_DONE` | **False** | Pending |
| `ROUND_7_HISTORY_REWRITE` | **True** | `git filter-repo` applied and verified |

---

## 2. What was completed (server-independent)

### 2.1 Documentation (12 documents)
`README.md` (zh), `README_EN.md` (en), `docs/architecture.md`, `docs/deployment.md`,
`docs/hardware.md`, `docs/ir-learning.md`, `docs/mqtt-protocol.md`,
`docs/operations-guide.md`, `docs/resource-constrained-deployment.md`,
`docs/scheduling.md`, `docs/security-model.md`, `docs/temperature-automation.md`,
`docs/troubleshooting.md`, `docs/wiring.md`, plus `hardware/README.md`.

### 2.2 Portability & leak fixes (working tree)
- `cloud/backend/Dockerfile`: `node:20-slim` → `node:24-slim` (node:sqlite requires Node ≥ 22.5).
- `cloud/backend/package.json` & `cloud/frontend/package.json`: version `0.4.0` → `1.0.0`.
- `cloud/backend/src/index.ts`: `/api/version` now reads `APP_VERSION` (default `1.0.0`).
- `cloud/tools/cert-monitor.sh`: hardcoded hosts removed → `WEB_HOST`/`WEB_PORT`/`MQTT_HOST`/`MQTT_PORT` env-driven.
- All firmware tooling: the hard-coded absolute project path and Windows user name
  replaced by `IR_PROJECT_ROOT` / `IR_DATA_ROOT` / `IR_PYTHON` env vars or `__file__`-relative derivation.
- `firmware/tools/desensitize_artifacts.py`: user/MAC masking made opt-in via `DESENSITIZE_USER` / `DESENSITIZE_MAC`.
- `firmware/tools/ir_capture_studio/user_settings.json` deleted; `firmware/.gitignore` now ignores `tools/**/user_settings.json`.

### 2.3 Round-7 full-history rewrite (the key sanitization step)
`git filter-repo --replace-text` was applied to **all 28 commits**. Replacements:

| Original (leak) | Replacement |
|---|---|
| `<windows-user>` (Windows user) | `user` |
| `<original-project-path>` | `C:/example/remote-ac` |
| `<device-mac>` (device MAC) | `XX:XX:XX:XX:XX:XX` |
| `<device-mac>` (uppercase) | `XX:XX:XX:XX:XX:XX` |

Author identity was already generic (`Zhang Mingyang <nobodycareme@users.noreply.github.com>`)
and was left untouched. Component tags `cloud-v1.0.0` and `firmware-v1.0.0` were rewritten
along with history (these are component tags, **not** the monorepo `v1.0.0` release tag).

---

## 3. Sanitization evidence

**Working tree** (grep, excludes `.git`/`node_modules`/`__pycache__`): 0 hits for
  the Windows user name, the absolute project path, production domains, production IPs,
  the owner name, the university name, the project display name, and the device MAC.

**Full history** (`git grep` over `$(git rev-list --all)`): 0 hits for every pattern above.

**Every object** (`git cat-file --batch-all-objects --batch | grep`): 0 hits for
  the Windows user name, the absolute project path, or either case of the device MAC.
`git count-objects`: `count 0, size 0, size-garbage 0`. The pre-rewrite merge commit
`eef75f8…` is now unreachable (`git cat-file` → "could not get object info").

---

## 4. What is explicitly NOT done (rotation-gated, by decision q-0)

- No GitHub repository created or pushed (`nobodycareme/remote-ac-controller` not created).
- No `v1.0.0` tag and no GitHub Release.
- No production MQTT broker leaf-cert rotation (no `ca.key` access).
- No `WEB_PASSWORD` / `IR_OWNER_PASSWORD` rotation (scrypt + fingerprint unchanged).
- Production server, certificates, and broker left untouched.
- Frontend `vite build` not executed locally (per `resource-constrained-deployment.md`,
  builds must run off-machine on a builder with ≥1 GB RAM).
- Firmware build not executed (no PlatformIO Core in this environment).

---

## 5. Post-rotation continuation (11 steps)

Run these **only after** production access is restored and credentials are rotated.

1. **Confirm reachability** of the production host (direct IP + Tailscale internal IP). Do not proceed if unreachable.
2. **Rotate MQTT broker leaf certificate** using `ca.key` (kept only on `broker/certs/`). Restart the broker.
3. **Rotate `WEB_PASSWORD` + `IR_OWNER_PASSWORD`** (scrypt store); the session fingerprint (`sha256(WEB_PASSWORD|IR_OWNER_PASSWORD)`) is recomputed, invalidating old sessions.
4. **Re-run the full sensitive scan** on the production host and on this repo; it must return **0**. Re-verify the bundle (Section 8).
5. **Create the GitHub repo** `nobodycareme/remote-ac-controller` (public).
6. **Push** all branches and tags (`cloud-v1.0.0`, `firmware-v1.0.0`).
7. **Run CI** (`.github/workflows/ci.yml`); it must pass. It runs the same vitest suites verified locally in Section 6.
8. **Create the `v1.0.0` tag + GitHub Release**; attach the SHA256-verified bundle from Section 8.
9. **Production smoke test**: confirm `device_offline` is the source of truth (the `last_seen`/retained-availability path can falsely show "online" while offline); confirm real IR control is gated by `REAL_IR_PRODUCTION_CONTROL_ENABLED`.
10. **Final doc pass**: confirm `example.com` placeholders, no secrets, and that published docs match the repo.
11. **Securely delete** the pre-rewrite backup (it contains the un-sanitized history) and archive this guide with the release.

---

## 6. Local verification performed (reproducible)

| Scope | Command | Result |
|---|---|---|
| Backend install | `cd cloud/backend && npm ci` | ✓ 175 packages |
| Backend types | `npx tsc --noEmit` | ✓ clean |
| Backend tests | `npm test` (vitest) | ✓ **78/78** (process does not self-exit — run under `timeout`; tests are green) |
| Frontend install | `cd cloud/frontend && npm ci` | ✓ |
| Frontend types | `npx tsc --noEmit` | ✓ clean |
| Frontend tests | `npm test` (vitest) | ✓ **86/86** (clean exit) |
| Firmware | `tools/dev.ps1 …` | deferred — no PlatformIO Core / `pwsh` in this environment |
| Frontend build | `npm run build` (vite) | deferred — off-machine per `resource-constrained-deployment.md` |

> **CI note:** the backend vitest suite completes all 78 tests but leaves an open handle
> (DB/MQTT client) so the process does not terminate. Wrap it with a timeout
> (e.g. `timeout 160 npm test`) in CI, or add explicit teardown/`process.exit(0)`.

---

## 7. Known limitations & risks

- **npm audit:** backend reports 16 transitive vulnerabilities (4 moderate, 11 high, 1 critical). Review and pin before public release.
- **Dashboard online/offline:** retained MQTT availability can make a device appear "online" while offline; `device_offline` is the authoritative signal.
- **Frontend bundle:** `echarts` is imported in full (~1.15 MB). Consider on-demand import + `manualChunks` + `chunkSizeWarningLimit` (see `resource-constrained-deployment.md`).
- **Observability:** no `/metrics` endpoint; no automated DB backup script (manual `sqlite3 .backup` steps in `docs/operations-guide.md`).
- **Model:** single-device design; no multi-tenant isolation.
- **Frontend build / firmware build** were not executed here (environment + off-machine policy).

---

## 8. Bundle & checksum (external artifact)

The clean repository is exported as a git bundle (all commits + tags), produced **after** the
final commit below. Its integrity is captured by the companion checksum file.

- Bundle: `remote-ac-controller.clean.bundle`
- Checksum: `remote-ac-controller.clean.bundle.sha256` (SHA-256 of the bundle)
- Reproduce: `git bundle create remote-ac-controller.clean.bundle --all`

> The SHA-256 value is recorded in `remote-ac-controller.clean.bundle.sha256` (alongside the
> bundle) and in the release handoff message. It is intentionally kept **outside** the repo
> bundle to avoid a self-referential checksum.

---

## 9. Recovery

If the working copy is lost, restore from the clean bundle:
```bash
git clone remote-ac-controller.clean.bundle remote-ac-controller
cd remote-ac-controller
git verify-commit HEAD   # optional integrity check
```
If the pre-rewrite backup is still present and must be destroyed (it contains sensitive
history), delete it with a secure delete and verify the sensitive scan returns 0 on the
clean bundle only.
