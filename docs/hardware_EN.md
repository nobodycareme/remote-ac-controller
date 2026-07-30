[简体中文](./hardware.md) | **English**

# Hardware

Bill of materials, module selection rationale, and electrical constraints.
For the physical connection table see [`wiring.md`](./wiring_EN.md).

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
certificate problem. See [`troubleshooting.md`](./troubleshooting_EN.md).

## 6. Placement

The IR emitter needs line of sight to the air conditioner's receiver window.
Reflected-path operation off a light-coloured wall or ceiling often works at
short range but is unreliable; verify with the diagnostics described in
[`ir-learning.md`](./ir-learning_EN.md).

Keep the DHT11 away from the ESP8266's own heat and out of direct airflow from
the AC, otherwise readings will track the appliance rather than the room.
