# Hardware

This directory is the entry point for the physical side of the project: what to
buy, how to wire it, and what is (and is not) published here.

Full documentation lives in [`../docs`](../docs):

| Document | Covers |
|---|---|
| [`docs/hardware.md`](../docs/hardware.md) | Bill of materials, module selection, GPIO constraints, power budget, memory limits |
| [`docs/wiring.md`](../docs/wiring.md) | Pin-by-pin wiring, the DHT11 and IR module connections, verification steps |
| [`docs/ir-learning.md`](../docs/ir-learning.md) | Capturing and registering your air conditioner's IR frames |
| [`docs/troubleshooting.md`](../docs/troubleshooting.md) | Sensor, IR and connectivity fault tables |

---

## Minimum Build

You can build a working node on a breadboard. No custom PCB is required.

| Item | Part | Notes |
|---|---|---|
| MCU board | NodeMCU v2/v3 (ESP8266, ESP-12E/F) | USB-serial bridge is typically CH340 or CH9102 — install the matching driver |
| Temperature / humidity | DHT11 (3-pin module with pull-up) | Bare DHT11 needs an external 4.7 kΩ–10 kΩ pull-up on DATA |
| IR transmit / receive | ZJ-IR-V2 style module, or a discrete IR LED + driver transistor and a 38 kHz receiver | Receiver only needed while learning codes |
| Power | 5 V supply, ≥ 1 A, via micro-USB or VIN | Under-powered supplies cause Wi-Fi/TLS instability, not obvious "power" faults |
| Wiring | Dupont jumpers, breadboard | — |

Default pin assignment (see `docs/wiring.md` for the reasoning and for pins to
avoid):

| Signal | NodeMCU pin | GPIO |
|---|---|---|
| DHT11 DATA | D1 | GPIO5 |
| IR module TXD | D5 | GPIO14 |
| IR module RXD | D6 | GPIO12 |

The IR module's TXD/RXD are **crossed** relative to the MCU: module TXD → MCU
receive side, module RXD → MCU transmit side. Getting this backwards is the most
common first-build mistake.

---

## What Is Not Published Here

- **No PCB source files.** The reference build is breadboard/perfboard; a custom
  board is unnecessary for a single node and the original layout is not
  published under a compatible licence.
- **No enclosure models.** Any small ABS box works. Keep the IR LED unobstructed
  and give the DHT11 airflow that is not warmed by the board's own regulator.
- **No IR code data.** Air-conditioner IR frames are model-specific and are not
  distributed with this project. Capture your own — the procedure is in
  [`docs/ir-learning.md`](../docs/ir-learning.md).

---

## Safety

This project drives an air conditioner. Two consequences worth stating plainly:

1. **Everything on the node is low-voltage (3.3 V / 5 V).** Nothing in this
   design connects to mains wiring. If a proposed modification involves mains,
   it is outside the scope of this project and should be done by a qualified
   electrician.
2. **Automation can command a real appliance.** Real IR transmission is
   disabled by default and gated behind multiple kill switches (see
   [`docs/security-model.md`](../docs/security-model.md)). Enable it only once
   you have verified your captured codes, and keep the emergency shutdown
   procedure to hand.
