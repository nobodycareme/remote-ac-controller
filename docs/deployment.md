# Deployment

Taking the system from a clone to a working installation.

Read [`security-model.md`](./security-model.md) first. Deploying this with
default credentials on a public address is not safe.

## 1. Prerequisites

| Component | Requirement |
|-----------|-------------|
| Server | Linux, 1 vCPU / 1 GB RAM minimum (see [`resource-constrained-deployment.md`](./resource-constrained-deployment.md)) |
| Node.js | 24.x (22+ required for built-in `node:sqlite`) |
| MQTT broker | Mosquitto 2.x |
| Reverse proxy | Nginx, Caddy, or equivalent, with TLS |
| Build machine | Any host with Node.js and PlatformIO |
| Domain | One hostname for the web app, one for MQTT (may share an IP) |

A **separate build machine is strongly recommended**. Compiling TypeScript and
bundling the frontend on a 1 GB server is a known way to make it unresponsive.

## 2. Topology

```
Internet
   │
   ├── 443 ──▶ Reverse proxy (TLS) ──▶ 127.0.0.1:3100  backend
   │
   └── 8883 ─▶ Mosquitto TLS listener ──▶ device
                    │
                    └── 1883 (loopback / container network only) ──▶ backend
```

Two invariants:

- The backend binds to `127.0.0.1` and is never published directly.
- The broker's plaintext listener is reachable only from the backend, never
  from the network.

## 3. Certificates

Two independent certificate needs.

### 3.1 Web (browser-facing)

Any publicly trusted certificate. With certbot:

```bash
certbot certonly --standalone -d ac.example.com
```

### 3.2 MQTT (device-facing)

The ESP8266 validates the broker certificate against a CA you control. A
private CA is appropriate here — the device pins it, so public trust is not
required.

```bash
# Private CA (keep ca.key offline; it never goes on the server)
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -out ca.crt -subj "/CN=Remote AC Private CA"

# Broker certificate
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
  -subj "/CN=mqtt.example.com"

# SAN is mandatory — CN alone is ignored by modern TLS stacks.
cat > san.cnf <<'EOF'
subjectAltName = DNS:mqtt.example.com
EOF

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 825 -sha256 -extfile san.cnf
```

> **The SAN extension is not optional.** A certificate without a matching SAN
> produces BearSSL error code 56 on the device. See
> [`troubleshooting.md`](./troubleshooting.md).

Place `ca.crt`, `server.crt`, `server.key` in `cloud/broker/certs/`. The
`.gitignore` rules exclude them.

## 4. Broker Configuration

`cloud/broker/config/mosquitto.conf` already encodes the required posture:

```
allow_anonymous false
password_file /mosquitto/run/passwordfile
acl_file /mosquitto/acl/aclfile

listener 1883          # internal only — never published
listener 8883          # TLS, public
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
```

Update `cloud/broker/acl/aclfile` for your `DEVICE_ID` if it is not the
default. Every topic is listed explicitly; Mosquitto denies anything not
granted.

## 5. Secrets

```bash
cd cloud/deploy
cp secrets.env.example secrets.env
```

Fill in:

| Variable | How to produce it |
|----------|------------------|
| `MQTT_DEVICE_PASSWORD` | `node -e "console.log(require('crypto').randomBytes(24).toString('base64url'))"` |
| `MQTT_PASSWORD` | Same, different value |
| `SESSION_SECRET` | `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` |
| `WEB_PASSWORD` | scrypt hash, `salt:hash` form |
| `IR_OWNER_PASSWORD` | scrypt hash, different from `WEB_PASSWORD` |

`secrets.env` is git-ignored. Verify with `git check-ignore -v` before your
first commit.

## 6. Deploying with Docker Compose

The simplest path. From `cloud/`:

```bash
docker compose up -d
```

This starts:

| Service | Memory cap | Ports |
|---------|-----------|-------|
| `broker` (Mosquitto 2.1.3, digest-pinned) | 64 MB | `8883` published |
| `backend` | 256 MB | `127.0.0.1:3100` only |

Both have health checks and capped JSON log rotation (10 MB × 3).

The broker provisions its password file from `secrets.env` on first start.
To rotate credentials later, update `secrets.env` and recreate the broker
container so the password file is rebuilt.

## 7. Deploying Without Docker

Appropriate when memory is tight — see
[`resource-constrained-deployment.md`](./resource-constrained-deployment.md).

**Build on your workstation, not the server:**

```bash
cd cloud/backend  && npm ci && npx tsc --noEmit && npm run build
cd ../frontend    && npm ci && npm test && npm run build
```

Transfer only the build output plus production dependencies. Then install the
unit file:

```bash
cp cloud/deploy/remote-ac-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now remote-ac-backend
```

The unit assumes `/opt/remote-ac-cloud`; adjust `WorkingDirectory`, `DB_PATH`,
`ReadWritePaths` and `ReadOnlyPaths` if you deploy elsewhere. It already sets
`MemoryMax=384M`, `NoNewPrivileges`, `ProtectSystem=strict` and
`ProtectHome=yes`.

## 8. Reverse Proxy

Nginx, terminating TLS and forwarding to the loopback backend:

```nginx
server {
    listen 443 ssl http2;
    server_name ac.example.com;

    ssl_certificate     /etc/letsencrypt/live/ac.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ac.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3100;
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;   # WebSocket
        proxy_set_header Connection "upgrade";
        proxy_set_header Host       $host;
        proxy_set_header X-Real-IP  $remote_addr;
    }
}
```

The `Upgrade`/`Connection` headers are required — without them live telemetry
silently stops updating while the rest of the UI appears fine.

`PUBLIC_BASE_URL` and `ALLOWED_ORIGINS` must match this hostname **exactly**,
including scheme and with no trailing slash. A mismatch produces
`ORIGIN_DENIED` on every write.

## 9. Firmware Provisioning

On your build machine:

```bash
cd firmware
cp include/secrets.example.h include/secrets.h
cp include/config.example.h  include/config_local.h
```

Fill in Wi-Fi credentials, MQTT host and account, and embed the CA
certificate. Both files are git-ignored, and CI fails if they are ever
committed.

```powershell
./tools/dev.ps1 verify
./tools/dev.ps1 build
./tools/dev.ps1 upload
./tools/dev.ps1 monitor
```

The port is detected automatically; override with `-Port` if needed.

## 10. Bring-Up Sequence

Verify in this order. Do not skip ahead — each step depends on the previous.

1. **Broker reachable.** `mosquitto_sub` with the backend credentials over TLS
   receives messages. Wrong credentials must be rejected.
2. **Backend healthy.** `GET /api/health` returns 200 on loopback.
3. **Proxy correct.** The web app loads over HTTPS and the WebSocket connects.
4. **Device online.** Telemetry appears; the dashboard shows `online`.
5. **Mock command round-trip.** Issue a command with IR still disabled; expect
   an `accepted_mock` acknowledgement. This proves the whole path works
   without touching hardware.
6. **Enable debug IR.** Set `WEB_REAL_IR_ENABLED=true`, configure the
   allow-list triple, keep `REAL_IR_DEBUG_MAX_TOTAL_COMMANDS` low. Confirm one
   physical actuation.
7. **Enable production IR.** Set `REAL_IR_PRODUCTION_CONTROL_ENABLED=true`.
8. **Enable automation.** Only now create schedules and the temperature rule.

## 11. Backups

The single stateful artifact is the SQLite database at `DB_PATH`. It holds
sessions, telemetry history, schedules, automation rules, and the state
catalogue.

```bash
sqlite3 /opt/remote-ac-cloud/data/app.db ".backup '/backup/app-$(date +%F).db'"
```

Use `.backup` rather than `cp` — copying a live SQLite file can capture a torn
write. Back up before every upgrade and before any credential rotation.

Certificates and `secrets.env` should be backed up separately, encrypted, and
must never enter the repository.

## 12. Upgrading

1. Back up the database.
2. Build on the workstation; run `./tools/test-all.ps1` and confirm `PASS`.
3. Transfer artifacts; restart the service.
4. Verify `/api/health`, then that telemetry resumes.
5. Reflash firmware only if the firmware changed — it is independently
   versioned.

Database migrations run automatically on start and are forward-only. There is
no automatic downgrade: to roll back, restore the database backup as well as
the code.
