[简体中文](./architecture.md) | **English**

# Architecture

This document describes the end-to-end architecture of Remote AC Controller:
the components, the data flow, and the boundaries between them.

## 1. System Overview

```
┌──────────────┐   HTTPS    ┌──────────────────┐   MQTT/TLS   ┌─────────────┐   IR
│  Phone /     │──────────▶ │  Cloud Backend   │ ───────────▶ │  ESP8266    │ ─────▶ AC
│  Browser     │ ◀────────  │  (Fastify + Bus) │ ◀─────────── │  Firmware   │
│  (Vue 3 SPA) │  WS/REST   └──────────────────┘   telemetry  └─────────────┘
└──────────────┘                    │                                │
                                    │                                ├─ DHT11 (GPIO5)
                              ┌─────▼──────┐                         └─ ZJ-IR-V2 (GPIO14/12)
                              │ node:sqlite│
                              └────────────┘
```

Four tiers, each with a single responsibility:

| Tier | Technology | Responsibility |
|------|-----------|----------------|
| Presentation | Vue 3 + Vite | Rendering, user input, live updates over WebSocket |
| Application | Node.js + Fastify | Auth, scheduling, automation, MQTT bridging, persistence |
| Transport | Mosquitto (MQTT over TLS) | Authenticated, ACL-scoped message routing |
| Device | ESP8266 (Arduino/PlatformIO) | Sensing, IR transmission, connectivity supervision |

## 2. Firmware (`firmware/`)

The firmware is organised as cooperating, non-blocking modules driven from a
single `loop()`. Nothing blocks; every module exposes an `update()`/`tick()`
style entry point.

| Module | Files | Responsibility |
|--------|-------|----------------|
| Entry point | `src/main.cpp` | Module construction, `setup()`/`loop()` orchestration |
| Serial CLI | `src/serial_cli.{h,cpp}` | Interactive diagnostics, IR learning, network commands |
| IR module | `src/ir_module.{h,cpp}` | ZJ-IR-V2 driver over `SoftwareSerial`, capture and replay |
| Sensor | `src/sensors/dht11_sensor.cpp` | DHT11 sampling with error tolerance |
| Wi-Fi | `src/network/wifi_manager.cpp` | Non-blocking association state machine |
| Campus auth | `src/network/campus_auth.cpp` | Optional captive-portal (srun) authentication |
| MQTT client | `src/cloud/mqtt_client.{h,cpp}` | TLS MQTT session, LWT, reconnect backoff |
| Connectivity | `src/cloud/connectivity_state_machine.cpp` | Aggregate online/offline determination |
| Telemetry | `src/cloud/telemetry_service.cpp` | Periodic telemetry JSON assembly and publish |
| Commands | `src/cloud/command_service.{h,cpp}` | Command validation, idempotency, IR dispatch, ACK |

Pin assignments live in exactly one place: `include/config/hardware_config.h`.
`include/board_pins.h` provides backwards-compatible aliases only.

**IR dispatch has a single entry point** — `dispatchIrAction()` in
`src/cloud/command_service.cpp`. Legacy `set_power` / `set_temperature`
commands never transmit IR; they are acknowledged as `accepted_mock`. This
guarantees that every real IR emission passes through one policy checkpoint.

## 3. Cloud Backend (`cloud/backend/`)

Fastify application, TypeScript, ESM, running on Node.js 24.

| File | Responsibility |
|------|----------------|
| `src/index.ts` | Server bootstrap, plugin and route registration |
| `src/config.ts` | Zod-validated environment configuration with safe defaults |
| `src/db.ts` | `node:sqlite` schema creation and forward-only migrations |
| `src/mqtt_bridge.ts` | MQTT subscribe/publish, message persistence, command idempotency |
| `src/auth.ts` | Password verification (scrypt), session issuance, role assignment |
| `src/guards.ts` | Origin allow-listing and CSRF validation |
| `src/automation.ts` | Schedule engine and temperature rule engine |
| `src/weather.ts` | External weather provider integration with caching |
| `src/device_liveness.ts` | Online/stale/offline classification |
| `src/bus.ts` | In-process event bus feeding the WebSocket channel |
| `src/reply_utils.ts` | Uniform success/deny response envelopes |
| `src/ac_states.ts` | The catalogue of discrete AC states |
| `src/routes/*.ts` | `auth`, `dashboard`, `device`, `telemetry`, `weather`, `ac`, `ir_debug`, `events` |

Notable design decisions:

- **Embedded database.** `node:sqlite` (built into Node 22+) avoids a native
  compilation step, which matters on small servers. See
  [`resource-constrained-deployment.md`](./resource-constrained-deployment_EN.md).
- **Rate limiting.** `@fastify/rate-limit` caps requests at 100/minute.
- **Deny envelopes.** Every rejection returns a machine-readable `errorCode`
  rather than a bare HTTP status, so the UI can render precise guidance.

## 4. Frontend (`cloud/frontend/`)

Vue 3 SPA built with Vite. There is deliberately **no router library**: view
selection is a reactive `currentView` value in `App.vue`, switching between
`home`, `control`, `schedule`, `automation`, `data`, `settings`, and `more`.
This keeps the bundle small and the navigation model explicit.

Shared components: `ClimateHero`, `ThermostatBar`, `TrendChart`,
`WeatherCard`, `ActivityTimeline`, `EmptyState`, `AppIcon`.

Formatting logic is isolated in a pure-function layer (`lib/format.ts`) so it
can be unit-tested without mounting components.

## 5. Data Flow

### 5.1 Telemetry (device → user)

1. `telemetry_service` samples the DHT11 and assembles a JSON document.
2. It publishes to `remote-ac/v1/devices/<device_id>/telemetry` (QoS 0).
3. `mqtt_bridge` persists the reading and updates rolling minute aggregates.
4. The in-process bus notifies WebSocket subscribers.
5. The SPA updates the hero card and trend chart.

### 5.2 Command (user → device)

1. The SPA issues an authenticated, CSRF-validated REST call.
2. The route handler checks role, kill switches, and device liveness.
3. `mqtt_bridge.tryInsertCommand()` enforces idempotency by command key.
4. The command is published to `.../commands/set` with an `expires_at`.
5. `command_service` on the device validates expiry and duplicates, then
   dispatches IR (or mock-acknowledges).
6. The device publishes `.../commands/ack` with a status code.
7. The backend records the ACK and notifies the UI.

## 6. Reliability Boundaries

- **Availability is not liveness.** The device publishes a retained
  `availability` message with an MQTT Last Will. Because retained messages
  survive the publisher, the backend deliberately does **not** advance
  `last_seen_at` from availability. Liveness is derived from telemetry
  recency (`OFFLINE_THRESHOLD_MS`, default 90 s).
- **Commands expire.** Every command carries `expires_at`. A device that was
  offline when a command was issued will reject it on reconnect rather than
  actuate stale intent.
- **Idempotency.** Both tiers deduplicate: the backend by command key, the
  firmware by a recently-executed command ID cache (TTL 30 s).

## 7. What Is Deliberately Absent

- No Git submodules — one clone yields the complete source.
- No native database driver, no ORM.
- No production credentials, TLS keys, IR payloads, or databases. See
  [`security-model.md`](./security-model_EN.md).
