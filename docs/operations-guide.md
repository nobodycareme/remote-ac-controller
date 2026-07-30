# Operations Guide

Day-2 operations for a running deployment: health checks, logs, database
maintenance, certificate renewal, incident response, and upgrades.

This guide assumes the system is already installed as described in
[`deployment.md`](./deployment.md). For memory- and disk-constrained hosts, read
[`resource-constrained-deployment.md`](./resource-constrained-deployment.md)
alongside this document.

> **Scope note.** This guide contains no deployment-specific host names,
> credentials, or IP addresses. Every example uses placeholders such as
> `ac.example.com` and `/opt/remote-ac-cloud`. Substitute your own values.

---

## 1. Service Topology Recap

| Component | Default listen | Managed by |
|---|---|---|
| Backend (Fastify) | `127.0.0.1:3100` | systemd unit `remote-ac-backend`, or Docker Compose service `backend` |
| MQTT broker (Mosquitto) | `8883` (TLS), `1883` (internal only) | `mosquitto.service`, or Compose service `broker` |
| Reverse proxy (TLS termination / SNI routing) | `443` | Operator-provided (nginx, Caddy, …) |
| Device (ESP8266) | outbound only | Firmware |

The backend deliberately binds to loopback in the systemd profile
(`HOST=127.0.0.1`). All public exposure is the reverse proxy's responsibility.

---

## 2. Health Checks

Three unauthenticated endpoints are exposed for liveness and readiness probes.

| Endpoint | Purpose | Healthy response |
|---|---|---|
| `GET /api/health` | Process liveness | `{"status":"ok","uptime":<seconds>}` |
| `GET /api/ready` | Readiness incl. DB probe (`SELECT 1`) | `{"status":"ready","db":"ok"}` |
| `GET /api/version` | Deployed artifact identity | `{"version":"1.0.0","node":"v24.x.x"}` |

```bash
curl -fsS http://127.0.0.1:3100/api/health
curl -fsS http://127.0.0.1:3100/api/ready
curl -fsS http://127.0.0.1:3100/api/version
```

Recommended probe policy:

- **Liveness** — `/api/health`, 10 s interval, 3 failures before restart.
- **Readiness** — `/api/ready`, 30 s interval. A `not_ready` result means the
  SQLite file is missing, locked, or unreadable; restarting rarely helps —
  check the filesystem and `DB_PATH` first.

`APP_VERSION` may be set at deploy time (Git tag, CI build id) so that
`/api/version` reports the exact artifact rather than the source constant.

### 2.1 Deep Health via the Dashboard API

`GET /api/dashboard` (**authenticated**) is the authoritative operational view.
Fields worth alerting on:

| Field | Meaning | Alert condition |
|---|---|---|
| `online` | Trusted liveness verdict | `false` for > 5 min |
| `liveness_reason` | Why the verdict was reached | `device_offline`, `telemetry_stale` |
| `data_freshness` | Age classification of latest telemetry | `stale` / `offline` |
| `last_telemetry_at` | Timestamp of newest sample | age > `offline_threshold_ms` |
| `mqtt_backend_connected` | Backend↔broker link | `false` |
| `mqtt_reconnect_attempt_count` | Cumulative reconnect attempts | rapid growth (flapping) |
| `availability` | Raw retained LWT value | see caution below |

> **Caution — do not alert on `availability` alone.** The broker retains the
> device's last-will/birth message, so a device that vanished without a clean
> disconnect can keep reporting `online` indefinitely. The backend therefore
> derives liveness from telemetry freshness, and `availability` is exposed only
> as a hint (`availability_hint`). Use `online` / `liveness_reason` for alerts.

### 2.2 No Metrics Endpoint

There is **no** `/metrics` (Prometheus) endpoint in this release. If you need
time-series monitoring, the pragmatic options are:

1. Scrape `/api/dashboard` with an authenticated exporter script and translate
   the fields above into metrics.
2. Ship the structured JSON logs (§3) into a log-based metrics pipeline.

---

## 3. Logs

The backend uses a small purpose-built logger (`cloud/backend/src/logger.ts`),
not pino or winston. Characteristics:

- **Format** — one JSON object per line: `{"ts":…,"level":…,"msg":…,"meta":{…}}`.
- **Destination** — `stdout` for `info`, `stderr` for `warn`/`error`. Under
  systemd this lands in the journal; under Docker in the container log.
- **Redaction** — keys matching a sensitive set (password, session, cookie,
  token, secret, …) are recursively replaced before serialization. Do not defeat
  this by logging whole request bodies in custom patches.
- **Request logging** — Fastify's own logger is disabled (`logger: false`).
  There is no per-request access log. If you need one, put it in the reverse
  proxy, where it belongs.
- **Log level** — there is no `LOG_LEVEL` environment variable in this release;
  levels are emitted unconditionally. Filter downstream.

Reading logs:

```bash
# systemd
journalctl -u remote-ac-backend -f --output=cat
journalctl -u remote-ac-backend --since "1 hour ago" | grep '"level":"error"'

# Docker Compose
docker compose logs -f backend
docker compose logs --since 1h broker
```

Useful filters:

```bash
# MQTT bridge lifecycle
journalctl -u remote-ac-backend --since today --output=cat | grep -i mqtt

# Command dispatch and ACK correlation (search by requestId)
journalctl -u remote-ac-backend --output=cat | grep '<request-id>'
```

---

## 4. Database Operations

The backend uses the built-in `node:sqlite` module — no native compilation, no
external database server.

| Property | Value |
|---|---|
| Path | `DB_PATH` env var (default `./data/app.db`; systemd `/opt/remote-ac-cloud/data/app.db`; Compose `/data/app.db`) |
| Journal mode | WAL (`PRAGMA journal_mode = WAL`) |
| Foreign keys | ON |
| Busy timeout | 5000 ms |

### 4.1 Schema and Migrations

All schema work happens inside `initDb()` at startup:

1. `CREATE TABLE IF NOT EXISTS` for every table.
2. Idempotent `ALTER TABLE … ADD COLUMN` guards for columns added after the
   initial schema (idempotency keys, IR code ids, session roles, liveness
   columns, MQTT counters, IR telemetry fields).

A `schema_migrations` table is declared but is **not** currently used as a
version ledger — migrations are made safe by idempotency, not by version
tracking. Consequence for operators: **starting a newer backend against an
older database is safe and self-migrating; starting an older backend against a
newer database is not tested and may fail on unknown columns.** Always back up
before a downgrade.

Tables: `schema_migrations`, `users`, `sessions`, `devices`, `telemetry`,
`telemetry_minute`, `device_state`, `commands`, `ir_debug_sessions`,
`ir_debug_commands`, `events`, `weather_cache`, `ac_states`, `ac_schedules`,
`ac_temperature_rules`, `ac_automation_executions`.

### 4.2 Retention

An hourly job (`retentionCleanup()`, `setInterval(3600_000)`) prunes:

| Data | Retention |
|---|---|
| `telemetry` | 7 days |
| `events`, `commands` | 180 days |

`telemetry_minute` holds the downsampled series used by the trend chart and is
not pruned by this job — it is small by construction (one row per minute).

### 4.3 Backup

**No backup script ships with this repository.** Backups are the operator's
responsibility. With WAL enabled, do not simply copy `app.db` while the service
is running — the copy may miss committed data still in the `-wal` file.

Recommended online backup (no downtime):

```bash
DB=/opt/remote-ac-cloud/data/app.db
OUT=/var/backups/remote-ac/app-$(date +%Y%m%d-%H%M%S).db
mkdir -p "$(dirname "$OUT")"
sqlite3 "$DB" ".backup '$OUT'"
sqlite3 "$OUT" "PRAGMA integrity_check;"
gzip -9 "$OUT"
```

If `sqlite3` is not installed, take a cold backup instead:

```bash
systemctl stop remote-ac-backend
cp -a /opt/remote-ac-cloud/data/app.db{,-wal,-shm} /var/backups/remote-ac/ 2>/dev/null
systemctl start remote-ac-backend
```

Copy the `-wal` and `-shm` files together with the main database, or the copy
may be inconsistent.

Restore:

```bash
systemctl stop remote-ac-backend
gunzip -c app-<timestamp>.db.gz > /opt/remote-ac-cloud/data/app.db
rm -f /opt/remote-ac-cloud/data/app.db-wal /opt/remote-ac-cloud/data/app.db-shm
chown <service-user>: /opt/remote-ac-cloud/data/app.db
systemctl start remote-ac-backend
curl -fsS http://127.0.0.1:3100/api/ready
```

Schedule daily backups with a systemd timer or cron, and verify at least one
restore per quarter. An untested backup is a hypothesis, not a backup.

---

## 5. Secrets Management

Secrets live in a single operator-owned file that is **never** committed:

```
<install-root>/deploy/secrets.env      # referenced by systemd and Compose
```

Start from [`cloud/deploy/secrets.env.example`](../cloud/deploy/secrets.env.example).
Required entries include the two MQTT accounts (`MQTT_USERNAME` /
`MQTT_PASSWORD` for the backend, `MQTT_DEVICE_USERNAME` /
`MQTT_DEVICE_PASSWORD` for the device), `SESSION_SECRET`, `WEB_PASSWORD`, and
optionally `IR_OWNER_PASSWORD`.

Hygiene rules:

- `chmod 600` and root-owned (or service-user-owned). It is read at start only.
- The owner password is stored as a scrypt digest in `salt:hash` form, never in
  plaintext. See [`security-model.md`](./security-model.md).
- **Rotating `SESSION_SECRET`, `WEB_PASSWORD`, or `IR_OWNER_PASSWORD`
  invalidates all existing sessions**, including trusted devices. This is
  intentional and is the fastest way to evict every client.
- Back up `secrets.env` separately from the database, with stricter access
  control. Losing it means re-provisioning MQTT accounts and all sessions.

Rotation procedure:

```bash
cp -a deploy/secrets.env deploy/secrets.env.bak.$(date +%Y%m%d-%H%M%S)
# edit the value(s)
systemctl restart remote-ac-backend
curl -fsS http://127.0.0.1:3100/api/ready
# If an MQTT password changed, update the broker password file and the
# firmware/device credential in the same maintenance window.
```

MQTT credential rotation touches three places and must be done together:
`secrets.env` → broker password file (`mosquitto_passwd`) → device firmware
configuration. Rotating only one will silently break the link.

---

## 6. TLS Certificates

Two certificates are in play:

1. **Web certificate** for the browser-facing hostname — normally a public CA
   (ACME/Let's Encrypt). Renewal is handled by your ACME client; the reverse
   proxy reloads it.
2. **Broker certificate** for the MQTT endpoint — commonly a private CA, because
   the ESP8266 pins the CA. **The leaf must carry a Subject Alternative Name
   matching the hostname the firmware connects to**; a CN-only certificate will
   fail on BearSSL with error code `56`.

Monitoring is provided by `cloud/tools/cert-monitor.sh`, which performs
read-only TLS handshakes and exits non-zero as expiry approaches:

```bash
WEB_HOST=ac.example.com MQTT_HOST=mqtt.example.com \
  bash cloud/tools/cert-monitor.sh
# exit 0 = OK, 2 = inside WARN_DAYS (default 30), 3 = expired/unreachable/<CRIT_DAYS (14)
```

Run it daily from a timer and alert on a non-zero exit code. If the broker is
published behind a TLS-passthrough proxy on 443, set `MQTT_PORT=443` — SNI still
selects the broker certificate.

Broker certificate renewal checklist:

1. Issue a new leaf from the same private CA **with the correct SAN**.
2. Install the leaf and key where `mosquitto.conf` expects them.
3. Reload the broker (`systemctl reload mosquitto` or restart the container).
4. Confirm the device reconnects: watch `mqtt_reconnect_success_count` and
   `last_telemetry_at` on the dashboard.
5. **Only replace the CA certificate itself if the firmware's embedded CA is
   updated in the same window** — otherwise every device is locked out. Plan CA
   rotation as a firmware release, not a server task.

---

## 7. Real-IR Kill Switches

Real infrared transmission is gated by multiple independent switches, all
default-off. Strict string parsing is used — only `"true"` or `"1"` enables a
switch, so a stray `WEB_REAL_IR_ENABLED=false` cannot be coerced to true.

| Variable | Default | Effect |
|---|---|---|
| `WEB_REAL_IR_ENABLED` | `false` | Master switch for the web/debug real-IR path |
| `REAL_IR_PRODUCTION_CONTROL_ENABLED` | `false` | Master switch for owner-driven production control |
| `REAL_IR_DEBUG_MODE` | `false` | Opens the temporary no-login on-site debug window |
| `REAL_IR_DEBUG_EXPIRES_AT` | *(empty)* | Debug window expiry; empty means no expiry |
| `REAL_IR_DEBUG_ALLOWED_CODE_ID` | *(empty)* | Debug allow-list: code id |
| `REAL_IR_DEBUG_ALLOWED_CODE_SHA256` | *(empty)* | Debug allow-list: frame digest |
| `REAL_IR_DEBUG_ALLOWED_CODE_LENGTH` | `0` | Debug allow-list: frame length |
| `IR_OWNER_PASSWORD` | *(empty)* | Empty means no owner IR authorization is possible |

The debug transmit path additionally requires **all three** allow-list values to
be non-empty; otherwise it returns `DEBUG_CODE_CONFIG_INVALID`. Debug windows
are further limited by `REAL_IR_DEBUG_MAX_TOTAL_COMMANDS` (3),
`_COOLDOWN_SECONDS` (10), `_COMMAND_TTL_SECONDS` (30), and
`_SESSION_TTL_SECONDS` (3600).

### Emergency shutdown

```bash
bash cloud/tools/disable-real-ir-debug.sh /opt/remote-ac-cloud
```

The script backs up `secrets.env`, forces every real-IR switch to `false`,
clears the `ir_debug_sessions` / `ir_debug_commands` tables, and restarts the
service. Run it whenever a debug window is suspected to be open longer than
intended, or before handing the host to anyone else.

---

## 8. Routine Maintenance

| Cadence | Task |
|---|---|
| Daily (automated) | Certificate monitor; database backup; alert on `online=false` > 5 min |
| Weekly | Review `error`-level log lines; confirm retention job ran; check disk free |
| Monthly | Verify a backup restores into a scratch copy; review open kill switches; review `sessions` table for stale trusted devices |
| Quarterly | Dependency updates + `npm audit`; rehearse the rollback procedure; review MQTT ACL |
| Per firmware release | Re-verify the device reconnects and telemetry resumes; confirm CA/SAN assumptions still hold |

Disk usage grows mainly through the journal and the WAL file. If disk pressure
appears, check `journalctl --disk-usage` before suspecting the database — with
7-day telemetry retention the database is normally in the tens of megabytes.

---

## 9. Upgrade Procedure

The safe order is: **back up → build off-host → stop → swap → start → verify**.

```bash
# 1. Back up (see §4.3) and record the running version
curl -fsS http://127.0.0.1:3100/api/version

# 2. Build artifacts OFF the production host (see resource-constrained-deployment.md §3)
#    Then ship only dist/ output to the server.

# 3. Swap and restart
systemctl stop remote-ac-backend
#   replace backend/dist and frontend dist as appropriate
systemctl start remote-ac-backend

# 4. Verify
curl -fsS http://127.0.0.1:3100/api/ready
curl -fsS http://127.0.0.1:3100/api/version
journalctl -u remote-ac-backend --since "2 min ago" --output=cat | grep -i error
```

Then confirm end-to-end behaviour: log in, observe fresh telemetry, and send one
harmless command with real IR still disabled — the ACK path should report
`ACCEPTED_MOCK`.

Rollback is the same sequence with the previous artifact plus, if the schema
changed, a database restore. Because migrations only add columns, an
older-binary/newer-database combination is untested; restore the matching
backup rather than gambling on it.

---

## 10. Incident Playbooks

### 10.1 Device shows offline

1. `GET /api/dashboard` → read `liveness_reason` and `last_telemetry_at`.
2. `mqtt_backend_connected=false` → the backend cannot reach the broker: check
   the broker service, credentials, and TLS. Everything else is downstream.
3. Backend connected but no telemetry → the device is at fault: power, Wi-Fi,
   TLS handshake, or credentials. Check the serial console.
4. Handshake failures on the device: heap below ~28 KB with `bearssl_code=0`
   indicates memory exhaustion, **not** a certificate problem — do not start
   replacing certificates. `bearssl_code=56` is a genuine SAN mismatch.
5. Full decision tree: [`troubleshooting.md`](./troubleshooting.md).

### 10.2 Commands accepted but the AC does not react

Check, in order: real-IR kill switches (§7) — if disabled, ACKs are
`ACCEPTED_MOCK` by design and no IR is emitted; then the IR code registration;
then emitter aim and power. See [`ir-learning.md`](./ir-learning.md).

### 10.3 Backend restart loop

`journalctl -u remote-ac-backend -n 200 --output=cat`. Common causes:

- Missing or malformed `secrets.env` → configuration validation aborts startup.
- `DB_PATH` not writable → `initDb()` throws.
- Memory ceiling: the unit sets `MemoryMax=384M` and
  `NODE_OPTIONS=--max-old-space-size=192`. An OOM kill is visible as
  `systemd… Killed process`. See
  [`resource-constrained-deployment.md`](./resource-constrained-deployment.md).
- Node version too old: `node:sqlite` requires Node 22.5+ (24 recommended and
  what CI validates). `ERR_UNKNOWN_BUILTIN_MODULE: node:sqlite` means the
  runtime is too old.

### 10.4 Suspected compromise

1. Rotate `SESSION_SECRET` and `WEB_PASSWORD` → every session dies immediately.
2. Run `disable-real-ir-debug.sh` to close all real-IR paths.
3. Rotate both MQTT passwords (backend + device) and update the firmware
   credential.
4. Preserve `journalctl` output and the `events` table before pruning.
5. Review `sessions` for unexpected trusted devices; delete the rows.

---

## 11. What This Release Does Not Provide

Stated plainly so you can plan around it:

- No `/metrics` endpoint and no bundled dashboards.
- No backup script or scheduled backup — you must build this.
- No log level control and no access log in the application tier.
- No version-ledger migrations; downgrades are unverified.
- No multi-device fan-out: the deployment model is one backend per device id.
- No automated certificate renewal for the broker's private-CA leaf.

Each is a deliberate scope decision for a single-device, low-resource
deployment rather than an oversight — but they are real gaps if you scale up.
