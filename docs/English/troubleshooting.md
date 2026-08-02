[简体中文](../中文/故障排查.md) | **English**

# Troubleshooting

Symptom-first diagnostics. Each section states the observable symptom, the
likely causes in order of probability, and how to discriminate between them.

## 1. Diagnostic Order

Work from the device outward. Most "the app is broken" reports resolve to a
device or credential problem two layers down.

```
1. Is the device powered and sensing?        → serial monitor
2. Is it associated with Wi-Fi?              → `wifi status`
3. Is the TLS MQTT session up?               → telemetry counters
4. Is the backend receiving telemetry?       → dashboard / API
5. Is the browser authorised?                → error code in the response
```

## 2. Build and Flash

### `dev.ps1 status` reports no serial port

| Cause | Discriminator |
|-------|--------------|
| Charge-only USB cable | The board does not appear in Device Manager at all |
| Missing USB-UART driver | Appears as an unknown device |
| Board not powered | No power LED |

Install the driver matching your bridge chip (CH9102/CH340, CP210x, or FTDI).
The tooling enumerates ports dynamically, so there is no port number to
configure; use `-Port` only to override auto-detection.

### Toolchain errors mentioning archiver or path failures

The Xtensa toolchain is intolerant of unusual build paths. Symptoms include
archiver failures and truncated object paths.

Remedies, in order:

1. Build from a path with only ASCII characters and no spaces.
2. Keep the path short — deep nesting can exceed platform path limits.
3. On Windows, map a short virtual drive to the repository root and build from
   there.

### The build stalls indefinitely

Usually a stale PlatformIO core lock left by a killed process. Terminate any
lingering `pio` processes and remove the lock files under the PlatformIO core
directory, then retry.

Also check for a proxy environment variable pointing at a dead proxy — package
resolution will hang rather than fail. Clear `HTTP_PROXY`/`HTTPS_PROXY` for
the build, or set `NO_PROXY=*`.

### Upload times out

A full upload takes roughly two and a half minutes. Tooling with a shorter
timeout will kill it mid-write and report a missing binary. Allow at least
480 seconds.

## 3. Sensor

### Temperature reads `nan` or `sensor_ok` is false every cycle

| Cause | Check |
|-------|-------|
| DATA on the wrong pin | Must be D1 / GPIO5 |
| Missing pull-up | Bare 4-pin DHT11 needs 4.7 kΩ to 3V3 |
| Powered from 5 V | Must be 3V3 |
| Wrong library | Must be Adafruit DHT 1.4.7 + Unified Sensor 1.1.15 |

Substituting a different DHT library produces exactly this symptom on this
pin/timing combination. Do not change the library.

### Readings are plausible but drift high

The sensor is picking up the ESP8266's own heat, or sits in the AC's airflow.
See [`temperature-automation.md`](./temperature-automation.md) §10 — no amount
of threshold tuning compensates for placement.

## 4. Infrared

### `ir probe` returns nothing

Almost always the UART lines are not crossed. Module TXD → MCU D5/GPIO14;
module RXD → MCU D6/GPIO12. Straight-through wiring gives a module that looks
dead.

### Capture length or digest differs between attempts

Ambient infrared contamination — sunlight, fluorescent or LED lighting, or
another remote. Reduce ambient IR, hold the remote 3–10 cm from the black
receiver element, and repeat until three captures agree. Never register a
frame you have not reproduced.

### Capture succeeds but replay does nothing

| Cause | Check |
|-------|-------|
| Emitter not aimed at the AC | Clear element, line of sight |
| Out of range | Verify within 1 m first |
| AC already in that state | Most units give no feedback for a no-op |
| Frame needs staged transfer | Try `ir stage send` |
| Insufficient supply current | Works close, fails at distance — see [`hardware.md`](./hardware.md) §4 |

### Acknowledgement status decoder

| Status | Meaning | Action |
|--------|---------|--------|
| `blocked_by_ir_policy` / `real_ir_control_disabled` | Command round-trip completed, no IR sent | Expected while real IR is disabled |
| `blocked_by_ir_policy` | Firmware policy gate refused | Check firmware IR configuration |
| `ir_state_disabled` | State's `enabled` flag is false | Enable it in the catalogue |
| `ir_unknown_code` | Code not in the firmware registry | Regenerate the registry and reflash |
| `ir_module_busy` | Module mid-operation | Reduce command rate |
| `ir_execute_failed` | Transmission failed | Check power and wiring |
| `expired` | Arrived after `expires_at` | Latency or a device clock problem |
| `duplicate` | Seen within the 30 s exec cache | Usually benign |

## 5. Connectivity

### Device never reaches online

Read the telemetry counters — they discriminate the failure mode precisely:

| Observation | Interpretation |
|-------------|---------------|
| `wifi_reconnect_count` climbing | Wi-Fi association problem, not MQTT |
| Wi-Fi stable, `mqtt_reconnect_attempt_count` climbing, success flat | TLS or authentication failure |
| `mqtt_publish_fail_count` climbing | Connected, but ACL denies the topic |

### TLS handshake fails

Two distinct failures that are easy to confuse:

| Indicator | Cause | Fix |
|-----------|-------|-----|
| `bearssl_code = 0` **and** free heap < ~28 KB | Heap exhaustion | Reduce memory use elsewhere; keep `setBufferSizes(4096, 1024)` |
| `bearssl_code = 56` | Subject Alternative Name mismatch | Reissue the broker certificate with a correct SAN |

A code-0 failure is **not** a certificate problem. Do not disable certificate
validation to "fix" it — that converts a memory bug into a security hole.

### Publishes are rejected

The broker ACL grants topics explicitly. If `DEVICE_ID` differs from the ACL
entries, every publish is denied while the connection itself stays up. Make
`DEVICE_ID` in the firmware, the backend, and `aclfile` identical.

## 6. Backend

### Server exits immediately on start

Configuration is validated by Zod at startup and a failure is fatal by design.
The error names the offending variable. Compare against
`cloud/backend/.env.example`.

### `node:sqlite` is not available

Requires Node.js 22 or newer. On older versions the import fails outright.
Node 24 is the tested version.

### Health check passes but the UI shows nothing

Almost always the reverse proxy is not forwarding the WebSocket upgrade. Add
the `Upgrade` and `Connection` headers — see
[`deployment.md`](./deployment.md) §8. REST works, live updates do not, which
makes the UI look stale rather than broken.

### The server becomes unresponsive during a build

Do not build on a small server. Compiling TypeScript and bundling the frontend
can exhaust memory to the point of losing SSH access. Build on a workstation
and ship artifacts. See
[`resource-constrained-deployment.md`](./resource-constrained-deployment.md).

## 7. Web Application

Error codes are returned in a uniform deny envelope; read `errorCode` rather
than guessing from the HTTP status.

| `errorCode` | Meaning | Fix |
|-------------|---------|-----|
| `ORIGIN_DENIED` | Origin header does not match | `PUBLIC_BASE_URL`/`ALLOWED_ORIGINS` must match exactly, no trailing slash |
| `CSRF_INVALID` | Token missing or wrong | Reload the page; check cookie forwarding through the proxy |
| `UNAUTHORIZED` | No valid session | Log in |
| `SESSION_EXPIRED` | Session TTL elapsed | Log in again |
| `OWNER_REQUIRED` | Guest attempted a privileged action | Use an owner session |
| `REAL_IR_DISABLED` | Kill switch off | See [`security-model.md`](./security-model.md) §5 |
| `DEVICE_OFFLINE` | No recent telemetry | Diagnose the device first |
| `IDEMPOTENCY_KEY_PAYLOAD_MISMATCH` | Same key, different payload | Client bug — generate a fresh key |
| `TOO_MANY_REQUESTS` | Rate limit (100/min) | Back off |

### Owner login stopped working after a password change

Expected. Trusted sessions embed a fingerprint derived from the owner
credentials; rotating the password invalidates every trusted session. Log in
again and re-trust the device.

### Device shows online but is unplugged

If you observe this, check whether liveness is being derived from the retained
`availability` message rather than from telemetry recency. Retained messages
outlive the publisher, so they cannot be used as a liveness signal — the
backend classifies liveness from telemetry age instead. See
[`mqtt-protocol.md`](./mqtt-protocol.md) §5.

## 8. Automation

### A schedule did not fire

Read `ac_automation_executions` (`GET /api/ac/automation/executions`) before
anything else.

| Status | Meaning |
|--------|---------|
| `skipped_ir_disabled` | Production IR kill switch is off |
| `skipped_device_offline` | Device was offline at the scheduled minute |
| `skipped_state_unavailable` | `state_id` missing or disabled |
| No row at all | The schedule never matched — check `days_mask` (bit 0 = Monday) and `time_hhmm` |

Note that missed schedules are not replayed after downtime; this is
deliberate.

### Temperature automation does nothing

Read `last_eval_reason` on the rule row. Every evaluation writes it.

| Reason | Meaning |
|--------|---------|
| `insufficient_samples` | Fewer than 3 telemetry samples |
| `sensor_stale` | Newest sample older than `sensor_stale_s` |
| `in_deadband:<t>C` | Temperature is between the thresholds — normal |
| `already_on` / `already_off` | Already in the desired state |
| `min_interval_hold` | Rate limited |
| `manual_suppressed` | Within the manual override window (default 30 min) |
| `pending_confirm_<d>:1/2` | Waiting for the second agreeing evaluation |

### Automation cycles the AC too often

Widen the dead band (raise `on_threshold_c`, lower `off_threshold_c`) and
raise `min_interval_s`. Do not go below roughly 300 s for a real compressor.

## 9. Escalation

If a problem is not covered here:

1. Capture the serial log and the relevant telemetry counters.
2. Capture the deny envelope, including `errorCode` and `requestId`.
3. Note firmware version, Node version, and whether the kill switches are on.
4. Open an issue using the template in `.github/ISSUE_TEMPLATE/`.

**Redact before posting:** hostnames, IP addresses, credentials, certificates,
and captured IR frames.
