# Wiring

Physical connections between the NodeMCU and the two peripherals.

Pin assignments are defined in exactly one source file:
`firmware/include/config/hardware_config.h`. If you change the wiring, change
that header — do not scatter pin numbers through the code.
`firmware/include/board_pins.h` exists only to provide backwards-compatible
aliases.

## 1. Connection Table

### DHT11 temperature/humidity sensor

| DHT11 pin | NodeMCU pin | GPIO | Notes |
|-----------|-------------|------|-------|
| VCC / `+` | `3V3` | — | **Not** VIN/5 V |
| DATA / `out` | `D1` | GPIO5 | `DHT11_DATA_PIN` |
| GND / `-` | `GND` | — | |

3-pin breakout modules include the pull-up resistor. A bare 4-pin DHT11 needs
an external 4.7 kΩ resistor between DATA and 3V3.

### ZJ-IR-V2 infrared module

| ZJ-IR-V2 pin | NodeMCU pin | GPIO | Direction | Notes |
|--------------|-------------|------|-----------|-------|
| VCC | `3V3` | — | — | |
| GND | `GND` | — | — | |
| TXD | `D5` | GPIO14 | module → MCU | `IR_UART_RX_PIN` |
| RXD | `D6` | GPIO12 | MCU → module | `IR_UART_TX_PIN` |

**The UART lines cross.** The module's TXD goes to the MCU's RX pin and vice
versa. Wiring them straight through is the single most common assembly error
and produces a module that appears dead — no frames received, no ACKs.

The port is opened as `SoftwareSerial(IR_UART_RX_PIN, IR_UART_TX_PIN)`, i.e.
`SoftwareSerial(RX, TX)`.

## 2. Diagram

```
        NodeMCU v1.0 (ESP-12E)
       ┌────────────────────────┐
       │                        │
       │  3V3 ●──────┬──────────┼──▶ DHT11  VCC
       │             └──────────┼──▶ ZJ-IR  VCC
       │                        │
       │  GND ●──────┬──────────┼──▶ DHT11  GND
       │             └──────────┼──▶ ZJ-IR  GND
       │                        │
       │   D1 ● (GPIO5) ────────┼──▶ DHT11  DATA
       │                        │
       │   D5 ● (GPIO14) ◀──────┼─── ZJ-IR  TXD
       │   D6 ● (GPIO12) ───────┼──▶ ZJ-IR  RXD
       │                        │
       └────────────────────────┘
              ▲
              └── micro-USB, 5 V / ≥1 A (data-capable cable)
```

## 3. Assembly Checklist

1. Power off / unplug USB before changing wiring.
2. Confirm both peripherals are on **3V3**, not VIN.
3. Confirm the IR module's TXD/RXD are **crossed**.
4. Confirm no wire lands on GPIO6–GPIO11.
5. Point the clear (emitter) element at the air conditioner.
6. Plug in USB and confirm the board enumerates as a serial device.

## 4. Verification

From the `firmware/` directory:

```powershell
./tools/dev.ps1 status
```

This reports the toolchain state and the detected serial port. A missing port
usually means a charge-only USB cable or an absent USB-UART driver — see
[`troubleshooting.md`](./troubleshooting.md).

After flashing, open the serial monitor:

```powershell
./tools/dev.ps1 monitor
```

Expected within the first few seconds:

- Sensor readings with plausible temperature and humidity, and `sensor_ok` true.
- The IR module responding to a `probe` command from the serial CLI.

If temperature reads as `nan` or the sensor reports failure on every cycle,
re-check the DATA line and the pull-up before suspecting the firmware.

## 5. Changing Pins

If GPIO5/14/12 conflict with something else in your build:

1. Edit `firmware/include/config/hardware_config.h`.
2. Respect the constraints in [`hardware.md`](./hardware.md) §3 — avoid
   boot-strapping pins and the flash-connected range.
3. Rebuild and re-verify with `./tools/dev.ps1 verify`.

No other file should need to change.
