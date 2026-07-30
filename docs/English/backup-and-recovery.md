[简体中文](../中文/备份与恢复.md) | **English**

# Backup and Recovery

This document describes general backup and recovery practices for the public
Remote AC Controller repository. It replaces an earlier internal handoff guide
and retains only content useful to self-hosters, without exposing any production
identifiers.

> This document does not cover any production server, production credentials,
> internal release gates, or incident timelines. All examples use placeholder
> values (e.g. `example.com`, `203.0.113.0/24`, `C:/example/remote-ac`).

## 1. What to back up

| Category | Description | Sensitivity |
|----------|-------------|-------------|
| Source repository bundle | A self-contained Git snapshot (`git bundle` or a mirror with all refs) to restore source when the remote is unreachable | Low (public source) |
| Database | The `node:sqlite` database file used by the cloud backend and its dump | High (device/session metadata) |
| Configuration | Self-hosted `.env`, TLS certificates, MQTT ACLs, reverse-proxy config | High (contains secrets) |
| IR code library | IR learning files you captured for your own AC model | Medium (only valid for your devices) |

## 2. Source repository bundle backup

```bash
# From the repository root, produce a self-contained bundle
git bundle create remote-ac-backup.bundle --all
# Verify the bundle can be cloned normally
git clone ./remote-ac-backup.bundle /tmp/verify-clone
```

Recommendation: store bundles on offline or off-site media; regenerate regularly to include new commits.

## 3. Safe database backup

The cloud backend uses the built-in `node:sqlite`. Back it up through the
application's export interface, or copy the database file during a downtime
window:

```bash
# Example: copy the database during a maintenance shutdown (placeholder path)
cp C:/example/remote-ac/cloud/backend/data/app.db C:/example/remote-ac/backup/app.db.$(date +%F)
```

- Back up while the backend is stopped or read-only, to avoid a half-written file.
- Database backups contain device and session metadata; **store them encrypted**
  and never commit them to Git.

## 4. Configuration backup

- Back up the real `.env` (not `.env.example`) separately and **never** commit it to Git.
- Archive TLS certificates (`fullchain.pem`, `privkey.pem`) and MQTT credentials separately, encrypted.
- Use access controls for config backups that differ from those for source code.

## 5. Recovery procedure

1. **Restore source**: `git clone ./remote-ac-backup.bundle ./restored` or `git clone <remote-url>`.
2. **Restore dependencies**: run `npm ci` in `cloud/backend` and `cloud/frontend`.
3. **Restore database**: stop the backend, overwrite the database path with the backup, confirm it is not truncated.
4. **Restore configuration**: place the backed-up `.env`, certificates, and ACLs back, and check file permissions.
5. **Smoke test**: start the backend, call `/api/health`, and confirm a healthy response.

## 6. Rollback principles

- Database migrations rely on idempotent `ALTER TABLE` for forward compatibility;
  **downgrade is not validated** — always back up the database before downgrading.
- Prefer `git` historical commits or published tags for code rollback; avoid
  hand-editing files on the live system.
- After any rollback, re-run the smoke test from section 5.

## 7. How to verify recovery

- **Source integrity**: `git fsck --full` reports no errors; `git log --oneline -1` matches the backup.
- **Database usable**: backend starts without `ERR_UNKNOWN_BUILTIN_MODULE` or DB-open errors; `/api/health` returns 200.
- **Config effective**: backend logs show it bound to the expected address (e.g. `localhost` or your internal address); TLS handshake succeeds.
- **Functional check**: read device telemetry once or send a test command to confirm the end-to-end path works.

## 8. Related documents

- [Operations guide](./operations-guide.md)
- [Deployment](./deployment.md)
- [Security model](./security-model.md)
