# Temperature Automation

Closed-loop control: drive the air conditioner from the DHT11 reading using a
dual-threshold hysteresis rule with several safety guards.

Implementation: `scanTemperatureRule()` in `cloud/backend/src/automation.ts`;
storage: the single-row `ac_temperature_rules` table.

## 1. Why Hysteresis, Not a Setpoint

A single setpoint produces short-cycling: the temperature oscillates around
the threshold and the compressor starts and stops every few minutes, which is
both inefficient and mechanically damaging.

This implementation uses two thresholds with a dead band between them:

```
temperature
     ▲
  29 │            ┌─── ON  (≥ on_threshold_c, default 28.0)
  28 │────────────┘
     │  dead band — no action
  26 │────────────┐
  25 │            └─── OFF (≤ off_threshold_c, default 26.0)
     ▼
```

Inside the dead band nothing happens, regardless of which direction the
temperature is moving. Widening the band reduces cycling at the cost of a
larger comfort swing.

## 2. Schema

Single row, `id = 1`.

| Column | Type | Default | Meaning |
|--------|------|---------|---------|
| `enabled` | INTEGER | `0` | Master switch, **off by default** |
| `on_threshold_c` | REAL | `28.0` | Turn on at or above this |
| `off_threshold_c` | REAL | `26.0` | Turn off at or below this |
| `on_state_id` | TEXT | — | State applied when turning on |
| `off_state_id` | TEXT | — | State applied when turning off |
| `min_interval_s` | INTEGER | `600` | Minimum seconds between actions |
| `sensor_stale_s` | INTEGER | `180` | Reject readings older than this |
| `manual_suppress_s` | INTEGER | `1800` | Back off after manual control |
| `last_action` | TEXT | `''` | `'on'` \| `'off'` \| `''` |
| `last_action_at` | INTEGER | | Epoch ms |
| `last_eval_reason` | TEXT | `''` | Why the last evaluation did what it did |
| `last_eval_at` | INTEGER | | Epoch ms |

`on_threshold_c` must be strictly greater than `off_threshold_c`. Inverting
them produces a rule that can satisfy both branches and will oscillate.

## 3. Evaluation Algorithm

Runs every 10 s, on the same timer as the schedule scan.

```
1. Rule missing or disabled          → clear pending state, return
2. Fetch the 3 most recent telemetry samples
   fewer than 3                      → "insufficient_samples", return
3. Newest sample older than
   sensor_stale_s                    → "sensor_stale", return
4. temp := median(3 samples)
5. temp ≥ on_threshold_c             → desired = 'on'
   temp ≤ off_threshold_c            → desired = 'off'
   otherwise                         → "in_deadband:<t>C", return
6. desired == last_action            → "already_<desired>", return
7. Within min_interval_s of the
   last action                       → "min_interval_hold", return
8. Within manual_suppress_s of the
   last manual command               → "manual_suppressed", return
9. desired differs from the pending
   candidate                         → reset the counter to 1
   pendingCount < 2                  → "pending_confirm_<d>:1/2", return
10. Dispatch, record the action
```

## 4. Noise Rejection

Three independent mechanisms, because a DHT11 in a real room is noisy:

1. **Median of three samples.** A single spurious reading cannot move the
   median. The mean would be dragged by an outlier; the median is not.
2. **Two consecutive agreeing evaluations.** A transient that survives the
   median still has to persist through a second scan ~10 s later. This adds
   about 10 s of latency before any action — negligible for thermal control.
3. **Staleness rejection.** If the newest telemetry is older than
   `sensor_stale_s` (default 180 s), the rule refuses to act. A dead sensor
   produces inaction, not a stuck command.

The two-evaluation confirmation counter is held **in memory**. A process
restart resets it, which fails safe: after a restart the system requires fresh
confirmation before actuating.

## 5. Manual Override

Any manual IR command starts a suppression window of `manual_suppress_s`
(default 1800 s = 30 minutes). During it, temperature automation records
`manual_suppressed:<desired>` and takes no action.

The rule for distinguishing manual from automatic is the `requested_by`
prefix: commands issued by automation carry
`automation:schedule:<id>` or `automation:temperature:<id>`, and
`getLastManualIrCommandAt()` excludes them. Automation therefore never
suppresses itself.

Rationale: if a person just overrode the machine, the machine should defer to
them for a while rather than immediately reverting.

## 6. Rate Limiting

`min_interval_s` (default 600 s) enforces a floor on the interval between
actions, independent of the thresholds. Even with a badly configured narrow
dead band, the compressor cannot be cycled more than once per interval.

Do not reduce this below roughly 300 s for a real compressor.

## 7. Guards Shared With Manual Control

Dispatch uses the same `dispatchForAutomation()` → `dispatchIrAction()` path as
everything else, so the same guards apply:

| Condition | Audit status |
|-----------|-------------|
| State disabled or absent from the catalogue | `skipped_state_unavailable` |
| `REAL_IR_PRODUCTION_CONTROL_ENABLED` not enabled | `skipped_ir_disabled` |
| Device offline | `skipped_device_offline` |
| Dispatched | `dispatched` |

The idempotency key is `auto-temp-<ruleId>-<on|off>-<minuteAnchor>`, so two
evaluations within the same minute cannot produce two physical actions.

## 8. Observability

- `last_eval_reason` / `last_eval_at` on the rule row record **every**
  evaluation, including no-ops. This is the primary diagnostic surface: if the
  system "isn't doing anything", the reason is written there.
- `ac_automation_executions` records dispatch attempts, with
  `source = 'temperature'`.
- Successful actions also write `last_action` / `last_action_at`, and the
  detail string carries the deciding median, e.g. `median=28.4C -> on`.

## 9. Configuration Example

Cool when the room reaches 28 °C, stop at 26 °C, at most one action per
10 minutes:

| Field | Value |
|-------|-------|
| `enabled` | `1` |
| `on_threshold_c` | `28.0` |
| `off_threshold_c` | `26.0` |
| `on_state_id` | `acme_cool_26_auto_v1` |
| `off_state_id` | `acme_power_off_v1` |
| `min_interval_s` | `600` |
| `sensor_stale_s` | `180` |
| `manual_suppress_s` | `1800` |

## 10. Sensor Placement

Control quality is bounded by measurement quality. Place the DHT11:

- Away from direct airflow from the air conditioner — otherwise it measures
  the appliance's output, the rule satisfies itself in seconds, and the room
  never actually reaches the target.
- Away from the ESP8266's own heat, which biases readings upward by 1–2 °C.
- Away from direct sunlight and exterior walls.

A poorly placed sensor cannot be compensated for by tuning thresholds.

## 11. Known Limitations

- Single rule only. Per-season or per-time-of-day rule sets are not supported;
  approximate them with schedules that change the state catalogue in use.
- No predictive or model-based control. This is intentionally a hysteresis
  band, not a thermal model.
- Humidity is recorded and displayed but does not participate in the control
  decision.
