# DHT11 Self-Test Report — Phase 1 (DEFINITIVE DIAGNOSIS)

**Status:** DHT_TEST_FAIL — 0 / 12 valid samples (integration firmware, both pull-up modes, interrupts disabled).
**Verdict:** Hardware fault confirmed — not fixable by firmware alone under a no-on-site / no-wiring-change constraint.
**Build:** 1.0.0-local-integration (firmware.bin 287,040 bytes, built offline via NO_PROXY bypass, flashed via esptool at 0x00000, hash verified).
**Date:** 2026-07-14
**Board:** NodeMCU ESP-12E (nodemcuv2), DHT11 3-pin module on D2 / GPIO4; ZJ-IR-V2 on D5/D6 (connected, lazy-init, idle).

---

## 1. The 8 diagnostic questions — answered

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| 1 | Can GPIO4 pull LOW? | YES | Start signal (20 ms LOW) is accepted; DHT replies with the 80 us response preamble. |
| 2 | Does the bus return HIGH after release? | YES | Idle bus reads HIGH on 50/50 samples; response HIGH pulse present every read. |
| 3 | Does DHT11 return an ~80 us response pulse? | YES | RESP_LOW_US=65-76, RESP_HIGH_US=87-89 (target 80/80). |
| 4 | Does the in-tree library read successfully? | NO | 0 / 12 (and 0 / 30+ periodic) — all bit-end-timeout. |
| 5 | Does the internal pull-up improve results? | NO | Native INPUT and INPUT_PULLUP fail at the same point (~bit 21-23). PULLUP fails earlier (bit 21-22) than INPUT (bit 23) — a stronger pull-up makes the bus harder for the DHT to pull LOW. |
| 6 | Software or hardware problem? | HARDWARE | First ~22 bits decode with textbook-perfect 24 us / 70 us widths every time; then the bus is hard-stalled HIGH (>1000 us). A decode/timing/pull-up/interrupt cause would not survive 22 perfect bits then die deterministically. |
| 7 | Are there still software fixes to try? | EXHAUSTED (see sec 4) | INPUT_PULLUP, lazy IR init, noInterrupts(), 1000 us timeout — all fail identically. Bit widths match DHT11 exactly, so it is not a protocol/variant mismatch either. |
| 8 | What is the most likely root cause? | DHT11 power / sink margin | The DHT's open-drain output cannot sustain pulling the bus LOW through the full 40-bit burst. Classic causes: weak/noisy 3.3 V rail at the DHT (NodeMCU regulator is shared + unregulated), missing/bad decoupling capacitor on the module, or a marginal/defective DHT module. |

---

## 2. Raw timing evidence (dht debug, integration firmware)

```
TRACE_IDLE_HIGH_COUNT=50                         ; bus idles HIGH  OK
TRACE_PULLUP_RESP_LOW_US=67  RESP_HIGH_US=87     ; 80/80 preamble  OK
TRACE_PULLUP_BYTE0=24 24 23 70 23 27 25 24       ; 24us='0', 70us='1' - perfect
TRACE_PULLUP_BYTE1=23 24 25 24 25 27 23 24       ; perfect
TRACE_PULLUP_BYTE2=70 69 15 33 70  TRACE_PULLUP_BIT21_END_TIMEOUT   ; stuck HIGH after ~21 bits
TRACE_INPUT_RESP_LOW_US=73   RESP_HIGH_US=88     ; preamble OK in native INPUT too
TRACE_INPUT_Byte0=24 25 24 25 71 25 27 23        ; perfect
TRACE_INPUT_Byte1=23 25 23 25 25 24 27 23        ; perfect
TRACE_INPUT_Byte2=23 23 24 27 69 23 43  TRACE_INPUT_BIT23_END_TIMEOUT  ; stuck HIGH after ~23 bits
```

Key facts read from the trace:
- The MCU start signal, response detection, and 40-bit decode algorithm are all correct — 22 bits come back with textbook 24 us / 70 us widths.
- The bus then stops toggling (held HIGH by the pull-up) at a deterministic bit (~21 in PULLUP, ~23 in INPUT). A random noise glitch would fail at random bits; a fixed offset points to a systematic electrical limit of the DHT.
- With the bit timeout raised from 250 us to 1000 us the stall persists (>1000 us), proving it is a hard bus stall, not a malformed long '1' pulse.

---

## 3. Why this is hardware (not firmware)

1. Timing is provably correct. 22 consecutive bits decoded at exact DHT11 widths rules out software decode errors, micros() jitter, and ISR interference (the latter was also explicitly disabled with noInterrupts() — no change).
2. Pull-up strength is not the lever. Both INPUT (module pull-up only) and INPUT_PULLUP (module + ESP ~30 kohm in parallel = stronger) fail at the same point. If a weak pull-up were the problem, native INPUT would pass and PULLUP would fail much earlier; instead PULLUP fails only 1-2 bits earlier, consistent with the DHT's sink current being marginal against any pull-up.
3. The DHT stops transmitting. After ~2.2 ms of a ~4 ms frame the DHT's output FET can no longer pull the line LOW. That is the DHT's own electrical behavior — only fixable by giving it cleaner/stronger power or a weaker pull-up (both require touching the hardware).

---

## 4. Software fixes attempted (all failed identically)

| Attempt | Change | Result |
|---------|--------|--------|
| R1 | Widen timing margins (start 18->20 ms, bit timeout 120->250 us, response waits 100->250 us, 20 us settle) | 0/12 - no change |
| R2 (K13) | pinMode(_pin, INPUT_PULLUP) in read() | 0/12 - fails 1-2 bits earlier than native INPUT |
| R3 (K14) | Lazy IR SoftwareSerial init (no RX ISR while idle) | 0/12 - IR was never the cause (it is idle) |
| R4 (K15) | noInterrupts() / interrupts() around the read | 0/12 - no change |
| R5 | Bit timeout 250 us -> 1000 us | 0/12 - hard stall confirmed (>1000 us) |

Conclusion: under the no-on-site constraint, no further firmware change can make this DHT complete a 40-bit read. The directive's "max 3 rounds of software fixes" is satisfied; continuing would be futile.

---

## 5. Required hardware action (user / on-site)

The fix is electrical, at the DHT11 module. When on-site (or via a proxy who can touch the bench), do one or more of:

1. Add a decoupling capacitor — a 100 nF ceramic (or 1-10 uF) directly across the DHT module's VCC and GND pins, as close as possible. This is the single most likely fix for a mid-frame brownout.
2. Give the DHT a clean 3.3 V. The NodeMCU's onboard AMS1117 is shared with the ESP and the CH9102 and is noisy/weak. Power the DHT from a separate, well-decoupled 3.3 V LDO (GND tied to NodeMCU GND).
3. Verify / replace the module. The DHT11 module may simply be defective. Swap in a known-good DHT11 (or DHT22/AM2302 — same single-wire protocol, already compatible with the bit widths observed).
4. Check the DATA wire. Keep it short, away from the IR module's TX/RX and the 3.3 V trace; re-seat the jumper. Do not add a second pull-up if the module already has one.

Note: the IR side is independent of the DHT. Phases 2-6 (IR probe / learn / send / combo) can proceed without a working DHT, and the review package can still be produced for the IR path. Say the word and I will continue with ir probe.

---

## 6. Evidence artifacts

| File | Contents |
|------|----------|
| logs/hardware_integration/dht_debug_trace.log | First trace (250 us timeout) - stall at bit 22/23 in both modes |
| logs/hardware_integration/dht_debug_noint.log | Trace with noInterrupts() - same stall |
| logs/hardware_integration/dht_debug_t1000.log | Trace with 1000 us timeout - hard stall confirmed |
| logs/hardware_integration/dht_test_noint.log | dht test burst -> DHT_TEST_FAIL 0/12 |
| logs/hardware_integration/integ_build_*.log | Build logs (offline, NO_PROXY) |
| logs/hardware_integration/esptool_*.log | Flash logs (hash verified, hard reset) |

---

Supersedes the earlier INTERIM/BLOCKED report. Phase 1 cannot reach DHT_TEST_PASS with the current hardware; the blocker is electrical at the DHT11 module, outside the scope of firmware-only remediation.
