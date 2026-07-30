[简体中文](./resource-constrained-deployment.md) | **English**

# Resource-Constrained Deployment

How to run this system on a small VPS — the 1–2 GB RAM, 1–2 vCPU class of host
that also runs other services. This document exists because the default
"just build it on the server" workflow **will** take such a host down.

Read [`deployment.md`](./deployment_EN.md) first for the installation itself; this
document covers only the constraints and the workarounds.

---

## 1. Why This Deserves Its Own Document

The runtime footprint of this system is genuinely small. The **build** footprint
is not. Concretely:

| Phase | Peak RSS (approx.) | Notes |
|---|---|---|
| Backend runtime | 90–160 MB | Capped at 192 MB heap by `--max-old-space-size` |
| Broker runtime | 10–30 MB | Compose limit 64 MB |
| `tsc` compile (backend) | 300–500 MB | Transient, but concurrent with everything else |
| `vite build` (frontend) | 700 MB – 1.4 GB | Dominated by bundling and minification |
| `npm ci` (either package) | 200–400 MB + heavy I/O | Also several hundred MB of disk churn |

On a host with ~1.6 GB total RAM and other services already resident, a
front-end build can consume the remaining headroom, push the machine into swap,
and make it unresponsive for tens of minutes — long enough to look like an
outage. The kernel OOM killer may then terminate the wrong process.

**Rule: never run `tsc`, `vite build`, or `npm ci` on a constrained production
host.** Build elsewhere; ship the output.

---

## 2. What Is Already Optimised

Some of the hard work is done, and it is worth knowing so you do not undo it.

**No native compilation anywhere.** The backend deliberately avoids every
dependency that requires `node-gyp` or a prebuilt binary:

- Persistence uses the built-in `node:sqlite` module rather than
  `better-sqlite3` or `sqlite3` — no toolchain, no build step, no glibc
  surprises.
- Password hashing uses `bcryptjs` (pure JavaScript) rather than `bcrypt`.
- The full dependency set — `fastify`, `@fastify/{cookie,rate-limit,websocket,static}`,
  `mqtt`, `bcryptjs`, `zod`, `uuid` — resolves with zero native modules.

The practical payoff: `npm ci --omit=dev` on the server, if you ever must run
it, needs no compiler, no Python, and no `build-essential`. Do not introduce a
native dependency casually; it changes the deployment story entirely.

> **Requirement.** `node:sqlite` needs **Node 22.5 or newer**; Node 24 is what
> CI validates and what the Dockerfile uses. On Node 20 the process fails at
> import with `ERR_UNKNOWN_BUILTIN_MODULE: node:sqlite`.

**Memory ceilings are pre-configured.** Both deployment profiles cap the
backend:

| Setting | systemd unit | Docker Compose |
|---|---|---|
| Node heap | `NODE_OPTIONS=--max-old-space-size=192` | same |
| Container/service memory | `MemoryHigh=256M`, `MemoryMax=384M` | `limits.memory: 256M` |
| Task/PID cap | `TasksMax=64` | `pids: 100` |
| Broker memory | — | `limits.memory: 64M`, `cpus: 0.5` |

`MemoryHigh` throttles before `MemoryMax` kills, which turns a hard OOM into
observable slowness. Keep both.

**Retention is bounded.** Telemetry is pruned after 7 days and
commands/events after 180 days by an hourly job, so the database stays in the
tens of megabytes rather than growing without limit.

---

## 3. Build Off-Host, Ship Artifacts

The supported workflow for a constrained host:

```
Developer machine / CI          Production host
────────────────────────        ─────────────────────
npm ci                          (nothing)
npm run build       ──────▶     rsync dist/  → /opt/…/backend/dist
npm run build (fe)  ──────▶     rsync dist/  → /opt/…/frontend/dist
                                systemctl restart remote-ac-backend
```

Practical guidance:

1. **Build both packages locally**, from a clean tree, and record the commit
   you built from. A build that cannot be traced to a commit cannot be rolled
   back with confidence.
2. **Verify integrity across the wire.** Compute `sha256sum` over the artifact
   on both ends and compare before restarting anything. Silent truncation
   during transfer is a real failure mode on flaky links.
3. **Ship `dist/` only** — not `node_modules`, not sources. Runtime
   dependencies are installed once on the server with `npm ci --omit=dev` and
   changed only when `package-lock.json` changes.
4. **Swap atomically.** Upload to a staging directory, then rename into place,
   then restart. A half-uploaded `dist/` served to users is worse than downtime.

If you must build on the server despite the warnings, at minimum stop the
backend first, ensure swap exists, and constrain the build:

```bash
systemctl stop remote-ac-backend
NODE_OPTIONS=--max-old-space-size=512 npm run build   # will be slow
systemctl start remote-ac-backend
```

This trades wall-clock time for survivability. It is a fallback, not a plan.

---

## 4. Frontend Bundle Size

The frontend is the heaviest artifact, for one identifiable reason: the trend
chart imports the charting library in full —

```ts
import * as echarts from 'echarts'   // pulls the entire library
```

and `vite.config.ts` sets no `manualChunks` (only
`chunkSizeWarningLimit: 1200`). The result is a single large JavaScript chunk in
the megabyte range. This works, but it costs build memory, build time, and
first-load bandwidth.

If bundle size matters for your deployment, two independent improvements:

**a) Import only the modules actually used.**

```ts
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);
```

This typically removes the large majority of the charting payload.

**b) Split vendor code so the browser can cache it independently.**

```ts
// vite.config.ts
build: {
  rollupOptions: {
    output: {
      manualChunks: { echarts: ['echarts'], vue: ['vue'] },
    },
  },
}
```

Neither change is applied in this release — they are left as deliberate,
verifiable improvements rather than untested edits to shipped code.

Serving-side mitigations that cost nothing: enable gzip or brotli on the
reverse proxy, and set long-lived `Cache-Control` on hashed asset filenames.
Compression alone typically cuts transferred size by roughly 70 % for
JavaScript.

---

## 5. Swap: Insurance, Not Capacity

On a 1–2 GB host, configure swap even though the steady-state workload does not
need it. Swap converts a hard OOM kill into degraded performance, which is
recoverable; an OOM kill of the broker or the backend is not graceful.

```bash
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Prefer RAM; use swap only under real pressure
sysctl -w vm.swappiness=10
```

Healthy steady state is **swap present, near-zero used**. Sustained swap usage
means the host is genuinely over-committed — reduce co-tenants or resize; do
not raise the Node heap limit to "fix" it.

---

## 6. Sizing Reference

| Host RAM | Verdict |
|---|---|
| 512 MB | Not recommended. Runtime alone may fit; any co-tenant or maintenance task will not. |
| 1 GB | Workable with off-host builds, 1 GB swap, and no heavyweight co-tenants. |
| 2 GB | Comfortable for runtime plus a reverse proxy and modest co-tenants. Builds still belong off-host. |
| 4 GB+ | On-host builds become viable, though off-host remains better practice. |

Disk: budget ~1 GB for the OS-independent footprint (Node runtime, `dist`
output, runtime `node_modules`, database, logs). The database is small; the
systemd journal is usually the larger consumer — cap it:

```bash
journalctl --vacuum-size=200M
# persistent: SystemMaxUse=200M in /etc/systemd/journald.conf
```

CPU: 1 vCPU is sufficient at runtime. The workload is I/O- and
timer-driven — an MQTT subscription, a 10-second automation scan, an hourly
retention job — not compute-bound.

---

## 7. Co-tenancy Rules

Small hosts usually run more than one thing. To keep this system a good
neighbour:

1. **Give every service an explicit memory cap.** An unbounded co-tenant makes
   this system's careful ceilings pointless — the OOM killer picks by badness
   score, not by importance.
2. **Bind the backend to loopback** (`HOST=127.0.0.1`, the systemd default) and
   let one reverse proxy own the public ports.
3. **Do not co-schedule maintenance.** Backups, certificate renewal, log
   rotation and any container image pulls should be spread across the night,
   not stacked at the same minute.
4. **Watch total commit, not per-process RSS.** `free -m` and
   `systemd-cgtop` tell you more than `top` sorted by memory.

---

## 8. Verification Checklist

After deploying to a constrained host, confirm all of the following:

```bash
# 1. Runtime is new enough for node:sqlite
node -e "require('node:sqlite'); console.log('sqlite ok', process.version)"

# 2. Service is up and ready
curl -fsS http://127.0.0.1:3100/api/health
curl -fsS http://127.0.0.1:3100/api/ready

# 3. Memory ceilings are actually in force
systemctl show remote-ac-backend -p MemoryMax -p MemoryHigh -p TasksMax
systemctl status remote-ac-backend | grep -i memory

# 4. Swap exists and is idle
free -m

# 5. Journal is capped
journalctl --disk-usage
```

Then leave it for 24 hours and re-check `free -m` and the backend's memory
usage. A stable RSS after a full day — including the hourly retention job and a
daily backup — is the signal that the sizing is right.

---

## 9. Symptoms and Causes

| Symptom | Likely cause | Action |
|---|---|---|
| Host unresponsive for many minutes during deploy | `vite build` or `tsc` run on-host | Build off-host (§3) |
| Backend killed and restarted under load | `MemoryMax` reached | Inspect for a leak before raising the cap; check co-tenants |
| `ERR_UNKNOWN_BUILTIN_MODULE: node:sqlite` | Node < 22.5 | Upgrade to Node 24 |
| `npm ci` fails with `ENOSPC` | Disk exhausted by journal/npm cache | `journalctl --vacuum-size`, `npm cache clean --force` |
| Sustained swap usage | Genuine over-commit | Remove co-tenants or resize; do not raise the heap limit |
| Slow first page load | Un-split, uncompressed frontend bundle | Enable gzip/brotli; consider §4 |
| Broker restart loop under Compose | 64 MB limit too tight with heavy retained state | Raise the broker limit modestly and investigate retained topics |

---

## 10. Summary

The runtime is cheap; the build is expensive. Keep builds off the production
host, keep every service's memory explicitly capped, keep swap present and
unused, and keep the dependency tree free of native modules. Those four
disciplines are what make a 1 GB host a reasonable home for this system rather
than a recurring incident.
