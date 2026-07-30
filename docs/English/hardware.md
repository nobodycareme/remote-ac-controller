[简体中文](../中文/硬件说明.md) | **English**

# Hardware

Bill of materials, module selection rationale, and electrical constraints.
For the physical connection table see [`wiring.md`](./wiring.md).

## 1. Bill of Materials

| # | Component | Specification | Qty | Notes |
|---|-----------|---------------|-----|-------|
| 1 | MCU board | NodeMCU v1.0 (ESP-12E, ESP8266) | 1 | PlatformIO board id `nodemcuv2` |
| 2 | Temperature/humidity sensor | DHT11 (3-pin breakout with pull-up) | 1 | 4-pin bare sensors need an external 4.7 kΩ pull-up |
| 3 | IR transceiver module | ZJ-IR-V2 (UART, learning-capable) | 1 | Contains both receiver and emitter |
| 4 | Power supply | 5 V / ≥1 A USB | 1 | See §4 |
| 5 | Jumper wires | Female-female Dupont | ~6 | |
| 6 | USB cable | Data-capable micro-USB | 1 | Charge-only cables will not enumerate |

Optional: a breadboard or a small perfboard for a permanent build.

## 2. Component Notes

### 2.1 NodeMCU ESP8266

The ESP8266 was chosen over an ESP32 for cost and sufficiency: this workload
is one sensor, one UART peripheral, and one TLS MQTT session. That said, TLS
on the ESP8266 is memory-tight — see §5.

Board revisions ship with different USB-UART bridges. This project has been
validated with **CH9102** (`VID:PID 1A86:55D4`). CH340, CP210x, and FTDI
bridges also work; the build tooling enumerates serial ports dynamically
rather than hard-coding a port number.

### 2.2 DHT11

The DHT11 is adequate here (±2 °C, ±5 % RH, 1 Hz sampling) because the control
loop is coarse — it drives a rule engine with hysteresis, not a PID loop.

Use the **Adafruit DHT Sensor Library (1.4.7)** together with
**Adafruit Unified Sensor (1.1.15)**. Other DHT libraries have been observed
to produce intermittent read failures on this pin/timing combination. Do not
substitute the library without re-validating.

If you need better accuracy, the DHT22/AM2302 is pin-compatible and the driver
change is a single constructor argument — but this has not been validated in
this repository.

### 2.3 ZJ-IR-V2 Infrared Module

A UART-driven learning module rather than a raw IR LED + demodulator pair.
Rationale:

- Learning and replay are handled in-module, so the ESP8266 does not need
  cycle-accurate bit-banging while also servicing Wi-Fi.
- Frames are opaque byte blobs, which decouples the firmware from
  manufacturer-specific IR encodings.

On the module, the **black** element is the receiver (used for learning) and
the **clear/transparent** element is the emitter.

The module is addressed via `SoftwareSerial`, so the emitter's carrier timing
is not affected by ESP8266 interrupt jitter.

## 3. GPIO Constraints (ESP8266)

Not every ESP8266 pin is usable. Observe the following:

| Pin | Status | Reason |
|-----|--------|--------|
| GPIO6–GPIO11 | **Unusable** | Wired to the on-board SPI flash |
| D0 / GPIO16 | Avoid | No interrupt support; used for deep-sleep wake |
| D2 / GPIO4 | Avoid here | Reserved to keep I²C available |
| D4 / GPIO2 | Avoid | Boot-strapping pin; also drives the on-board LED |
| D8 / GPIO15 | Avoid | Boot-strapping pin; must be low at reset |
| D3 / GPIO0 | Avoid | Boot-strapping pin (flash/run mode select) |

The pins actually used (GPIO5, GPIO14, GPIO12) are free of boot-strapping
duties and interrupt-capable.

## 4. Power Budget

| Load | Typical | Peak |
|------|---------|------|
| ESP8266 idle (Wi-Fi associated) | ~70 mA | — |
| ESP8266 TX burst | — | ~350 mA |
| DHT11 | ~1 mA | 2.5 mA |
| ZJ-IR-V2 (emitting) | ~10 mA | ~120 mA |

A 5 V / 1 A supply provides ample headroom. **Do not power the board from a
low-current source** (e.g. a 300 mA USB hub port): the ESP8266's TX current
spikes cause brown-out resets that present as random reboots, which are easy
to misdiagnose as firmware faults.

Both peripherals run from the NodeMCU **3V3** rail. Do not connect them to
VIN/5 V — the ESP8266 GPIOs are not 5 V tolerant.

## 5. Memory Constraints

TLS is the binding constraint on this platform. BearSSL buffer sizing has been
tuned to `setBufferSizes(4096, 1024)` in `src/cloud/mqtt_client.cpp`. Reducing
the receive buffer below 4096 breaks the TLS handshake with typical
certificate chains; increasing it risks heap exhaustion.

Diagnostic rule of thumb: if free heap is below ~28 KB at handshake time and
the BearSSL error code is `0`, the failure is heap exhaustion, not a
certificate problem. See [`troubleshooting.md`](./troubleshooting.md).

## 6. Placement

The IR emitter needs line of sight to the air conditioner's receiver window.
Reflected-path operation off a light-coloured wall or ceiling often works at
short range but is unreliable; verify with the diagnostics described in
[`ir-learning.md`](./ir-learning.md).

Keep the DHT11 away from the ESP8266's own heat and out of direct airflow from
the AC, otherwise readings will track the appliance rather than the room.


# Hardware

This directory is the entry point for the physical side of the project: what to
buy, how to wire it, and what is (and is not) published here.

Full documentation lives in [`../docs`](..):

| Document | Covers |
|---|---|
| [`docs/hardware.md`](./hardware.md) | Bill of materials, module selection, GPIO constraints, power budget, memory limits |
| [`docs/wiring.md`](./wiring.md) | Pin-by-pin wiring, the DHT11 and IR module connections, verification steps |
| [`docs/ir-learning.md`](./ir-learning.md) | Capturing and registering your air conditioner's IR frames |
| [`docs/troubleshooting.md`](./troubleshooting.md) | Sensor, IR and connectivity fault tables |

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
  [`docs/ir-learning.md`](../中文/红外学习.md).

---

## Safety

This project drives an air conditioner. Two consequences worth stating plainly:

1. **Everything on the node is low-voltage (3.3 V / 5 V).** Nothing in this
   design connects to mains wiring. If a proposed modification involves mains,
   it is outside the scope of this project and should be done by a qualified
   electrician.
2. **Automation can command a real appliance.** Real IR transmission is
   disabled by default and gated behind multiple kill switches (see
   [`docs/security-model.md`](./security-model.md)). Enable it only once
   you have verified your captured codes, and keep the emergency shutdown
   procedure to hand.

