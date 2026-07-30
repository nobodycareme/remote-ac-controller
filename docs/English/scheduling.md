[简体中文](../中文/定时任务.md) | **English**

# Scheduling

Time-based automation: fire a discrete AC state at a given local time on
selected weekdays.

Implementation: `scanSchedules()` in `cloud/backend/src/automation.ts`;
storage: the `ac_schedules` table in `cloud/backend/src/db.ts`.

## 1. Model

A schedule says: *at this local time, on these weekdays, put the air
conditioner into this state.*

It does not express duration or ranges. "Cool from 22:00 to 06:00" is
expressed as two schedules — one that applies a cooling state at 22:00 and one
that applies the off state at 06:00. This keeps every schedule a single,
idempotent, auditable action.

## 2. Schema

| Column | Type | Default | Meaning |
|--------|------|---------|---------|
| `id` | INTEGER PK | | |
| `name` | TEXT | `''` | Display label |
| `state_id` | TEXT | — | Must exist in the AC state catalogue |
| `time_hhmm` | TEXT | — | Local time, `"HH:MM"`, 24-hour |
| `days_mask` | INTEGER | `127` | Weekday bitmask, see §3 |
| `one_shot` | INTEGER | `0` | `1` = disable after firing once |
| `enabled` | INTEGER | `1` | |
| `last_fired_minute` | TEXT | `''` | Minute-idempotency anchor |
| `last_fired_at` | INTEGER | | Epoch ms |
| `created_by` | TEXT | `'owner'` | |
| `created_at` / `updated_at` | INTEGER | | Epoch ms |

Indexed on `(enabled, time_hhmm)`.

## 3. Weekday Bitmask

`days_mask` is a 7-bit field. **Bit 0 is Monday.**

| Bit | Value | Day |
|-----|-------|-----|
| 0 | 1 | Monday |
| 1 | 2 | Tuesday |
| 2 | 4 | Wednesday |
| 3 | 8 | Thursday |
| 4 | 16 | Friday |
| 5 | 32 | Saturday |
| 6 | 64 | Sunday |

| Intent | Mask |
|--------|------|
| Every day | `127` |
| Weekdays only | `31` |
| Weekends only | `96` |
| Monday, Wednesday, Friday | `21` |

## 4. Time Zone

Local time is computed with `Intl.DateTimeFormat` pinned to
**`Asia/Shanghai`** (`getLocalNow()`), independent of the host's system time
zone. A server running in UTC therefore still fires an "07:30" schedule at
07:30 local time.

To relocate the deployment, change the `timeZone` in the formatter
construction in `automation.ts`. Note that this project performs no
daylight-saving transition handling, because `Asia/Shanghai` has none. Adapt
that logic before moving to a DST zone.

## 5. Execution Loop

A single `setInterval` runs every `AUTOMATION_SCAN_INTERVAL_MS` (10 000 ms) and
drives both the schedule scan and the temperature rule scan.

For each enabled schedule:

1. Skip if the current weekday bit is not set in `days_mask`.
2. Skip unless `time_hhmm` equals the current local `HH:MM`.
3. Skip if `last_fired_minute` already equals the current minute key.
4. Dispatch, then mark fired via `markAcScheduleFired()`, disabling the row if
   `one_shot` is set.

### Minute idempotency

The minute key has the form `2026-07-28T07:30`. Because the scan runs every
10 s, a schedule matches roughly six times within its minute. Comparing
against `last_fired_minute` guarantees exactly one dispatch. The anchor is
persisted, so a process restart mid-minute does not cause a re-fire.

### Missed schedules are not replayed

If the backend is down at 07:30 and starts at 07:35, the 07:30 schedule does
**not** fire. This is deliberate: actuating a physical appliance on stale
intent is worse than skipping it. The skip is visible in the execution audit.

## 6. Dispatch Path and Guards

All schedule dispatches go through `dispatchForAutomation()`, which reuses the
same `dispatchIrAction()` path as manual control. There is no privileged
automation shortcut. Guards applied in order:

| Guard | Recorded status |
|-------|----------------|
| State missing or `enabled = false` in the catalogue | `skipped_state_unavailable` |
| `REAL_IR_PRODUCTION_CONTROL_ENABLED` is not enabled | `skipped_ir_disabled` |
| Device classified offline | `skipped_device_offline` |
| Duplicate idempotency key | `idempotent_replay` |
| Dispatched successfully | `dispatched` |

Consequently, **schedules do nothing physical until the production IR kill
switch is enabled** — see [`security-model.md`](./security-model.md) §5. They
still record audit rows, which is a useful dry-run mode.

The `requested_by` field is set to `automation:schedule:<id>`. This prefix
marks the command as non-manual and excludes it from the manual-suppression
window used by temperature automation — see
[`temperature-automation.md`](./temperature-automation.md) §5.

## 7. Audit Trail

Every evaluation that reaches dispatch — successful or skipped — inserts a row
into `ac_automation_executions`:

| Column | Meaning |
|--------|---------|
| `source` | `'schedule'` |
| `rule_id` | Schedule id |
| `state_id` | Requested state |
| `command_id` | Present when dispatched |
| `status` | `dispatched`, `idempotent_replay`, or a `skipped_*` reason |
| `detail` | Free-text explanation |

Exposed via `GET /api/ac/automation/executions`.

Audit before blame: if a schedule "did not work", read this table first. In
practice the answer is almost always `skipped_ir_disabled` or
`skipped_device_offline`.

## 8. Worked Example

Cool to 26 °C at 21:00 on weekdays, turn off at 06:30 daily:

| Field | Schedule A | Schedule B |
|-------|-----------|-----------|
| `name` | Evening cool | Morning off |
| `state_id` | `acme_cool_26_auto_v1` | `acme_power_off_v1` |
| `time_hhmm` | `21:00` | `06:30` |
| `days_mask` | `31` | `127` |
| `one_shot` | `0` | `0` |
| `enabled` | `1` | `1` |

## 9. Operational Notes

- A `state_id` that is not in the catalogue never fires. Renaming a state
  (for example bumping `_v1` to `_v2`) silently breaks existing schedules —
  update them, and check the audit table for `skipped_state_unavailable`.
- Two schedules at the same minute both fire; ordering is by scan order and is
  not guaranteed. Avoid conflicting states at the same time.
- The interval timer is `unref()`'d, so it does not keep the process alive on
  its own.
