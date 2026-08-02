[简体中文](../中文/安全模型.md) | **English**

# Security Model

Threat model, controls, and the safe-by-default posture of the public
repository.

## 1. What This Repository Contains

The public repository contains **source code only**. It does not contain, and
has never contained in its published history:

- Wi-Fi credentials, MQTT passwords, or web login passwords
- TLS private keys, certificate authorities, or issued certificates
- Real infrared frame data for any specific air-conditioner model
- Databases, session stores, or operational logs
- Production hostnames, IP addresses, or operator identity

Documentation and examples use reserved placeholder values
(`example.com`, `203.0.113.0/24`, `CHANGE_ME`) as defined by RFC 2606 and
RFC 5737.

CI enforces part of this automatically: the `repo-hygiene` job in
`.github/workflows/ci.yml` fails the build if `.pem`, `.key`, `.db`, or
`.sqlite` files are tracked, and the `firmware-ci` job asserts that
the canonical `firmware/shared/RemoteACCore/src/config/cloud_secrets.h` is not committed and both deprecated paths (`firmware/agent-platformio/include/cloud_secrets.h` and `firmware/shared/RemoteACCore/src/cloud_secrets.h`) are absent.

## 2. Assets and Threat Actors

| Asset | Impact if compromised |
|-------|----------------------|
| MQTT device credentials | Attacker can forge telemetry, ACK commands falsely |
| MQTT backend credentials | Attacker can actuate the air conditioner |
| Owner web password | Full control including real IR transmission |
| Session cookie | Impersonation for the session lifetime |
| TLS private key | Broker impersonation, traffic interception |
| IR frame data | Reveals appliance model; enables replay by a co-located attacker |

| Actor | Capability assumed |
|-------|-------------------|
| Network observer | Can see traffic between device, broker, and browser |
| Internet scanner | Can reach any port you expose |
| Co-located attacker | Physical IR line of sight, physical access to the board |
| Malicious guest | Holds valid guest credentials |

Explicitly **out of scope**: a physically compromised ESP8266 (flash contents
are readable by anyone holding the board), and IR replay by someone already
inside the room.

## 3. Authentication and Roles

Two roles, defined in `cloud/backend/src/auth.ts`:

| Role | Capability |
|------|-----------|
| `guest` | Read status and telemetry; limited or no actuation depending on `ACCESS_MODE` |
| `owner` | Full control, including real IR when the corresponding switches are enabled |

Password storage uses **scrypt** (`scryptVerify`). A legacy `bcryptjs` path
exists solely to migrate historical hashes and should be considered
deprecated. Passwords are stored as `salt:hash`; plaintext is never persisted.

`WEB_USER` and `WEB_PASSWORD` are the single Owner credential. Real IR still
requires an Owner session, valid Origin and CSRF checks, explicit
`REAL_IR_PRODUCTION_CONTROL_ENABLED`, an allowed state, and device-side policy.
Legacy `IR_OWNER_*` variables are ignored and cannot grant authorization.

### Trusted devices

An owner may mark a browser as trusted, producing a long-lived session
(`sessions.trusted_label`, TTL `TRUSTED_OWNER_SESSION_TTL_DAYS`). Each trusted
session records an `owner_password_fingerprint`, derived from the current
owner credentials. Rotating the owner password changes the fingerprint and
**invalidates every existing trusted session** — the intended behaviour after
a suspected compromise.

The frontend treats `role === 'owner' && trusted === true` as the gate for
privileged UI (`App.vue`).

## 4. Web-Tier Controls

| Control | Implementation |
|---------|----------------|
| Origin allow-list | `requireOrigin` guard against `ALLOWED_ORIGINS` |
| CSRF | Per-session token compared with `crypto.timingSafeEqual` in `validateCsrf` |
| Session cookies | Signed with `SESSION_SECRET`; TTL `SESSION_TTL_MIN` (default 480 min) |
| Rate limiting | `@fastify/rate-limit`, 100 requests/minute |
| Uniform deny envelope | `reply_utils.deny()` |

CSRF comparison is constant-time by construction; do not replace it with `===`.

### Deny error codes

Rejections return a machine-readable `errorCode` so the UI can render precise
guidance instead of a generic failure:

`ORIGIN_DENIED`, `UNAUTHORIZED`, `CSRF_INVALID`, `OWNER_REQUIRED`,
`SESSION_EXPIRED`, `REAL_IR_DISABLED`, `DEVICE_OFFLINE`,
`IDEMPOTENCY_KEY_PAYLOAD_MISMATCH`, `IDEMPOTENCY_REPLAY`,
`INVALID_CREDENTIALS`, `TOO_MANY_REQUESTS`.

## 5. Infrared Kill Switches

Physical actuation is the highest-consequence action in the system, so it is
gated by layered switches. **All default to `false`.**

| Variable | Purpose |
|----------|---------|
| `WEB_REAL_IR_ENABLED` | Master switch for the debug/experiment path |
| `REAL_IR_PRODUCTION_CONTROL_ENABLED` | Master switch for normal production control |
| `REAL_IR_DEBUG_MODE` | Enables the constrained debug session mechanism |
| `REAL_IR_DEBUG_EXPIRES_AT` | Absolute expiry for a debug window |
| `REAL_IR_DEBUG_ALLOWED_CODE_ID` | Restricts debug to a single code |
| `REAL_IR_DEBUG_ALLOWED_SHA256` | Restricts debug to a single frame digest |
| `REAL_IR_DEBUG_ALLOWED_LENGTH` | Restricts debug to a single frame length |
| `REAL_IR_DEBUG_MAX_TOTAL_COMMANDS` | Hard cap on transmissions in a window |
| `REAL_IR_DEBUG_COOLDOWN_SECONDS` | Minimum interval between transmissions |
| `REAL_IR_DEBUG_COMMAND_TTL_SECONDS` | Per-command expiry |
| `REAL_IR_DEBUG_SESSION_TTL_SECONDS` | Debug session lifetime |

Two implementation rules that must not be relaxed:

1. **Strict boolean parsing.** Only the exact strings `"true"` and `"1"` are
   truthy. A permissive coercion (for example `z.coerce.boolean()`) treats any
   non-empty string — including `"false"` — as true, which would silently arm
   the system. This is a known trap; the strict parser is deliberate.
2. **Single dispatch point.** Every real IR emission passes through
   `dispatchIrAction()` in `firmware/src/cloud/command_service.cpp`. Legacy
   `set_power` / `set_temperature` commands are always acknowledged as
   `blocked_by_ir_policy` with reason `real_ir_control_disabled` and never
   transmit while real IR is disabled. Do not add a second dispatch path.

## 6. Transport Security

- **Browser ↔ backend:** HTTPS, terminated by the reverse proxy. The backend
  itself binds to `127.0.0.1` and is never exposed directly.
- **Backend ↔ broker:** MQTT over TLS. The broker should listen on loopback
  only, with external access mediated by a TLS-terminating stream proxy.
- **Device ↔ broker:** MQTT over TLS with CA validation on the device
  (`setTrustAnchors`). When no valid CA is present, a SHA-1 server-certificate
  fingerprint is used instead (`setFingerprint`, 40 hex characters, colons
  optional); the fingerprint pins the current server certificate and must be
  updated when the certificate rotates. If neither is present, initialization
  is refused (`TLS_MATERIAL_MISSING`).

BearSSL error interpretation on the ESP8266:

| Symptom | Interpretation |
|---------|---------------|
| `bearssl_code = 0`, free heap < ~28 KB | Heap exhaustion, not a certificate fault |
| `bearssl_code = 56` | Subject Alternative Name mismatch |

Do not "fix" a code-0 failure by disabling certificate validation.

## 7. Broker Authorisation

See [`mqtt-protocol.md`](./mqtt-protocol.md) §2. The essential property is that
the device account has **no write access** to `commands/set`, so a compromised
device cannot actuate itself or any peer.

## 8. Operator Responsibilities

Self-hosters must provide:

1. A unique `SESSION_SECRET` with high entropy.
2. The Owner password, stored as scrypt `salt:hash`.
3. MQTT credentials, distinct per account, plus matching ACL entries.
4. A TLS certificate chain and a private CA (or a public CA) for MQTT.
5. Their own IR frame data, captured from their own remote control.

Recommended hardening:

- Expose only the reverse proxy; bind the backend and broker to loopback.
- Keep both IR kill switches disabled until control has been verified in a
  simulated path.
- Rotate the owner password after any suspected exposure — this invalidates
  trusted sessions.
- Retain the deny-envelope error codes in logs for incident analysis.

## 9. Reporting Vulnerabilities

See [`SECURITY.md`](./security.md) in the repository root. Please do not open
a public issue for security-relevant defects.
