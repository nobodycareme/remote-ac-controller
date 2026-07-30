[简体中文](./ir-learning.md) | **English**

# Infrared Learning

How to capture the infrared frames for **your** air conditioner and register
them with the firmware.

> **You must do this.** The repository ships no real IR frame data. The state
> catalogue in `cloud/backend/src/ac_states.ts` describes one specific
> appliance and will not control yours.

## 1. Why Learning Instead of a Protocol Library

Air-conditioner remotes do not send discrete "power on" or "temp up" events.
Most send the **entire machine state** in every frame — mode, setpoint, fan
speed, swing flags, sleep, timer — as one long encoded burst. Frame lengths of
250–450 bytes are typical for the appliance this project was developed against.

Two consequences shape the design:

1. **State, not deltas.** There is no "increase temperature" command to send.
   You capture one frame per complete state you want to reach. This is why the
   system models a discrete *catalogue* of states rather than independent
   controls.
2. **Vendor-specific encoding.** Decoding every manufacturer's format is a
   large and brittle undertaking. Capturing and replaying opaque byte frames
   is model-agnostic and robust.

The trade-off is honest: you can only reach states you have captured.

## 2. Prerequisites

- Hardware assembled and verified per [`wiring.md`](./wiring_EN.md).
- Firmware flashed with the public profile.
- Your original AC remote control, with working batteries.
- A serial monitor: `./tools/dev.ps1 monitor` from `firmware/`.

## 3. Serial CLI Reference

The interactive CLI (`firmware/src/serial_cli.cpp`) exposes these commands.
Type `help` for the authoritative list on your build.

| Command | Purpose |
|---------|---------|
| `status` | Overall device status |
| `version` | Firmware version string |
| `dht read` / `dht test` | Sensor sanity checks |
| `ir probe` | Verify the IR module responds |
| `ir info` | Module information |
| `ir learn` | Enter learning mode (module-internal slot) |
| `ir send` | Replay the learned frame |
| `ir cancel` | Abort the current IR operation |
| `ir extlearn` | Enter external learning — capture the frame to the host |
| `ir extsend` | Transmit the frame currently staged on the device |
| `ir extload` | Load a frame into the staging buffer |
| `ir stage clear` / `append` / `commit` / `info` / `send` | Incremental staging of a long frame |
| `ir longframe` | Long-frame capture helper |
| `ir stress` / `stressfixed` / `stressbounded` | Reliability soak tests |
| `ir setbaud` | Adjust the module UART baud rate |
| `wifi connect` / `disconnect` / `scan` / `status` | Network control |
| `net check` | Connectivity probe |
| `campus status` / `login` / `logout` | Optional captive-portal authentication |

## 4. Capture Procedure

For **each** state you want to control:

### Step 1 — Confirm the module is alive

```
ir probe
```

Expect an identification response. Silence almost always means the UART lines
are not crossed — see [`wiring.md`](./wiring_EN.md) §1.

### Step 2 — Set the physical remote to the target state

Use the remote's own display to reach exactly the state you want, for example
*cool / 26 °C / auto fan / vertical swing on*. Do not send it yet.

### Step 3 — Arm capture

```
ir extlearn
```

The module enters receive mode. Note that many modules have a capture timeout
of a few seconds.

### Step 4 — Transmit

Hold the remote 3–10 cm from the **black** (receiver) element and press the
button that re-sends the current state. Most remotes have a dedicated
send/confirm button; otherwise toggling any setting and returning it works.

### Step 5 — Verify the capture

The CLI reports the captured frame length and digest. Repeat the capture
**three times** for the same state and compare:

- Frame lengths must be identical.
- Digests must be identical.

If they differ, the capture is contaminated by ambient IR (sunlight,
fluorescent lighting, another remote) or the distance was wrong. Discard and
retry. **Never register a frame you have not reproduced.**

### Step 6 — Replay test

```
ir extsend
```

Point the clear (emitter) element at the appliance. It must enter exactly the
captured state. If nothing happens:

- Check line of sight and distance (start within 1 m).
- Confirm the AC is not already in that state — many units give no feedback
  for a no-op.
- Try `ir stage send` for frames long enough to require staged transfer.

### Step 7 — Record

Store the frame bytes, length, and SHA-256 in your local private directory.
The default is `<repo>/Private/Firmware/IR/Learned/<stateId>/`, which is
git-ignored. Override with the `IR_LEARNED_ROOT` environment variable.

**Do not commit captured frames.** Beyond leaking your appliance model, a
published frame lets anyone within IR range replay it.

## 5. Naming States

Use a stable, descriptive `stateId`. The convention in this repository is:

```
<vendor>_<mode>_<temperature>_<fan>[_<modifiers>]_v<n>
```

Examples: `acme_cool_26_auto_v1`, `acme_power_off_v1`,
`acme_heat_22_quiet_swingV_v1`.

The `_v<n>` suffix lets you re-capture a state later without breaking existing
schedules that reference the old identifier.

## 6. Registering States

1. Generate the firmware PROGMEM registry from your captured data:

   ```powershell
   python firmware/tools/gen_ir_state_registry.py
   ```

   This reads the learned directory and emits a git-ignored `.inc` resource
   containing the frame bytes.

2. Update `cloud/backend/src/ac_states.ts` with matching metadata. Every entry
   must satisfy:

   | Field | Must equal |
   |-------|-----------|
   | `stateId` | The firmware `codeId`, exactly |
   | `frameLength` | The captured byte count |
   | `frameSha256` | The captured digest |
   | `mode` / `temperature` / `fan` / `swing*` / `powerOn` | The real semantics of the state |
   | `enabled` | `true` to expose it in the UI |

   Length and digest mismatches are a deliberate integrity check: the backend
   and firmware must agree on which frame a `stateId` denotes.

3. Rebuild both tiers:

   ```powershell
   ./tools/build-all.ps1
   ```

## 7. Enabling Real Transmission

Real IR is disabled by default at multiple layers. To enable it, see
[`security-model.md`](./security-model_EN.md) §5. In summary:

- `WEB_REAL_IR_ENABLED` gates the constrained debug path.
- `REAL_IR_PRODUCTION_CONTROL_ENABLED` gates normal production control.
- Both accept only the exact strings `"true"` or `"1"`.

Recommended order: verify end-to-end with mock acknowledgements first, then
enable the debug path with a single allowed code ID and a low command cap, and
only then enable production control.

## 8. Reliability Testing

Before trusting the system unattended:

```
ir stressbounded 50
```

This transmits repeatedly with bounded timing. Watch for `ir_module_busy` or
`ir_execute_failed` acknowledgements. An occasional failure under stress is
tolerable; a consistent failure rate indicates a power or wiring problem — see
[`hardware.md`](./hardware_EN.md) §4.

## 9. Troubleshooting Matrix

| Symptom | Likely cause |
|---------|-------------|
| `ir probe` silent | TXD/RXD not crossed, or module unpowered |
| Capture length varies between attempts | Ambient IR interference; dim the lights, move closer |
| Capture succeeds, replay does nothing | Emitter aimed wrong, out of range, or AC already in that state |
| Replay works at 10 cm but not 3 m | Insufficient supply current — see [`hardware.md`](./hardware_EN.md) §4 |
| ACK `ir_unknown_code` | `stateId` not present in the firmware registry; regenerate and reflash |
| ACK `ir_state_disabled` | The state's `enabled` flag is false |
| ACK `blocked_by_ir_policy` | Kill switches still disabled |
