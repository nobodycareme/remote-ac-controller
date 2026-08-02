[简体中文](../中文/MQTT协议.md) | **English**

# MQTT Protocol

The contract between the ESP8266 firmware and the cloud backend.

## 1. Topic Namespace

```
<TOPIC_PREFIX>/<DEVICE_ID>/<suffix>
```

| Setting | Default | Where |
|---------|---------|-------|
| `TOPIC_PREFIX` | `remote-ac/v1/devices` | `cloud/backend/src/config.ts` |
| `DEVICE_ID` | `bedroom-ac-01` | `cloud/backend/src/config.ts`, firmware config |

Concrete example: `remote-ac/v1/devices/bedroom-ac-01/telemetry`.

The `v1` segment is the protocol version. Breaking payload changes must bump
it rather than mutate existing fields in place.

| Suffix | Publisher | Subscriber | QoS | Retain |
|--------|-----------|-----------|-----|--------|
| `telemetry` | device | backend | 0 | no |
| `state` | device | backend | 0 | no |
| `availability` | device (+ LWT) | backend | 0 | **yes** |
| `commands/set` | backend | device | 0 (IR: **1**) | no |
| `commands/ack` | device | backend | 0 | no |

## 2. Broker ACL

Two accounts with strictly disjoint capabilities
(`cloud/broker/acl/aclfile`):

```
user remote-ac-device
topic write remote-ac/v1/devices/bedroom-ac-01/telemetry
topic write remote-ac/v1/devices/bedroom-ac-01/state
topic write remote-ac/v1/devices/bedroom-ac-01/availability
topic write remote-ac/v1/devices/bedroom-ac-01/commands/ack
topic read  remote-ac/v1/devices/bedroom-ac-01/commands/set

user remote-ac-backend
topic read  remote-ac/v1/devices/bedroom-ac-01/telemetry
topic read  remote-ac/v1/devices/bedroom-ac-01/state
topic read  remote-ac/v1/devices/bedroom-ac-01/availability
topic read  remote-ac/v1/devices/bedroom-ac-01/commands/ack
topic write remote-ac/v1/devices/bedroom-ac-01/commands/set
```

Two properties follow directly from this ACL:

- A compromised device **cannot** issue commands to itself or to any other
  device; it has no write access to `commands/set`.
- A compromised backend **cannot** forge telemetry or availability.

Mosquitto denies anything not explicitly granted. Per-device ACL blocks must
be added as devices are provisioned.

## 3. Payloads

All payloads are UTF-8 JSON. Unknown fields must be ignored by receivers.

### 3.1 `telemetry` (device → backend)

Built by `buildJson()` in `firmware/src/cloud/telemetry_service.cpp`.

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | int | Payload schema version |
| `device_id` | string | Device identity |
| `seq` | int | Monotonic sequence number since boot |
| `uptime_s` | int | Seconds since boot |
| `temperature_c` | number | Ambient temperature |
| `humidity_pct` | number | Relative humidity |
| `sensor_ok` | bool | False when the last sample failed |
| `wifi_rssi_dbm` | int | Signal strength |
| `free_heap_bytes` | int | Free heap |
| `max_free_block_bytes` | int | Largest contiguous block (fragmentation indicator) |
| `boot_id` | string | Random per-boot identifier |
| `reset_reason` | string | Reset cause reported by the SDK |
| `wifi_reconnect_count` | int | Cumulative counters, useful for stability triage |
| `mqtt_reconnect_count` | int | |
| `mqtt_disconnect_count` | int | |
| `mqtt_loop_fail_count` | int | |
| `mqtt_publish_fail_count` | int | |
| `mqtt_initial_connect_count` | int | |
| `mqtt_reconnect_attempt_count` | int | |
| `mqtt_reconnect_success_count` | int | |
| `ir_ready` | bool | IR module responsive |
| `ir_code_id` | string | Last dispatched code identifier |
| `ir_code_length` | int | Frame length in bytes |
| `ir_code_sha256` | string | Frame digest, for provenance checking |
| `simulated` | bool | True when values are synthetic |
| `firmware_version` | string | Build identity |

Publish interval: `DEVICE_PUBLISH_INTERVAL_MS` (default 5000 ms); sampling
interval `DEVICE_SAMPLE_INTERVAL_MS` (default 2500 ms).

### 3.2 `state` (device → backend)

| Field | Type |
|-------|------|
| `power` | bool |
| `target_temperature_c` | number |
| `mode` | string |
| `simulated` | bool |

### 3.3 `availability` (device → backend, retained)

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"online"` \| `"offline"` | |
| `sent_at` / `ts` | number | Publisher timestamp |

Registered as the MQTT Last Will (`willQos=0`, `willRetain=true`) so an
ungraceful disconnect yields `offline` automatically.

> **Design note.** The backend intentionally does **not** advance
> `last_seen_at` from this topic. A retained `online` message is redelivered
> to any new subscriber long after the device has died, which would make a
> dead device look healthy. Liveness comes from telemetry recency instead —
> see §5.

### 3.4 `commands/set` (backend → device)

Standard (non-IR) command:

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | string | Idempotency key |
| `expires_at` | number | Epoch ms; device rejects after this |
| `action` | `set_state` \| `set_power` \| `set_temperature` | |
| `power` | 1 \| 0 | For `set_power` |
| `target_temperature_c` | number | For `set_temperature` |

IR command:

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | string | Idempotency key |
| `type` | `"ir_action"` | Discriminator |
| `action` | string | The AC state / code identifier |
| `expires_at` | number | Epoch ms |

IR commands are published with **QoS 1, retain false** (`publishIrAction()` in
`cloud/backend/src/mqtt_bridge.ts`). QoS 1 because a lost actuation is
user-visible; retain false because a retained actuation replayed on reconnect
would be dangerous.

Command lifetime is governed by `IR_COMMAND_TTL_MS` (default 25 000 ms).

### 3.5 `commands/ack` (device → backend)

| Field | Type |
|-------|------|
| `schema` | int |
| `command_id` | string |
| `status` | see below |
| `reason` | string |
| `received_uptime_s` | int |

Status enumeration (`firmware/src/cloud/command_service.cpp`):

| Status | Meaning |
|--------|---------|
| `accepted_mock` | Legacy/special mock implementation only; not the default IR-disabled result |
| `ir_executed` | IR frame transmitted |
| `blocked_by_ir_policy` | Safely blocked by firmware policy; normally reason `real_ir_control_disabled` |
| `ir_state_disabled` | The requested state is disabled in this build |
| `ir_unknown_code` | No frame is provisioned for the requested code |
| `ir_module_busy` | IR module was mid-operation |
| `ir_execute_failed` | Transmission attempted and failed |
| `expired` | `expires_at` had passed on arrival |
| `duplicate` | `command_id` seen within the exec cache TTL |
| `rejected` | Generic rejection |

## 4. Idempotency

Deduplication happens at both ends, deliberately:

- **Backend** — `tryInsertCommand()` in `mqtt_bridge.ts` refuses to insert a
  duplicate command key. A repeated request with a *different* payload for the
  same key is rejected with `idempotency_key_payload_mismatch`; an identical
  repeat returns `idempotency_replay`.
- **Firmware** — `commandIdRecentlyExecuted()` / `recordExecutedCommandId()`
  in `ir_module.h` maintain a recently-executed cache with
  `IR_EXEC_TTL_MS = 30000`.

This survives QoS 1 duplicate delivery and user double-taps alike.

## 5. Liveness Classification

`cloud/backend/src/device_liveness.ts` derives device state from telemetry
recency:

| Condition | Classification |
|-----------|----------------|
| Last telemetry within `STALE_THRESHOLD_MS` (60 s) | `online` |
| Between 60 s and `OFFLINE_THRESHOLD_MS` (90 s) | `stale` |
| Beyond 90 s | `offline` |

Commands issued to an `offline` device are refused with `DEVICE_OFFLINE`
rather than published into the void.

## 6. Transport Security

- MQTT runs over TLS. The device validates the broker certificate via BearSSL:
  the **CA certificate takes priority** (`setTrustAnchors`); a SHA-1
  server-certificate fingerprint (`setFingerprint`, 40 hex characters, colons
  optional) is used only when no valid CA is present. The fingerprint pins the
  current server certificate, so it must be updated when the certificate
  rotates. If neither is present, MQTT initialization is refused
  (`TLS_MATERIAL_MISSING`). See [`security-model.md`](./security-model.md).
- BearSSL buffers are sized `setBufferSizes(4096, 1024)`; see
  [`hardware.md`](./hardware.md) §5.
- Plaintext MQTT is acceptable only for local development
  (`cloud/tools/broker-dev.cjs`).

## 7. Extending the Protocol

1. Add fields as **optional**; never repurpose an existing field.
2. Add the corresponding ACL entries for any new topic suffix.
3. Bump the `v1` prefix segment for breaking changes and run both versions
   during migration.
4. Update `schema` in the payload when field semantics change.
