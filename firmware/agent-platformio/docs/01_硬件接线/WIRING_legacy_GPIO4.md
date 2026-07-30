# WIRING — NodeMCU ESP8266 + DHT11 + ZJ-IR-V2

All connections are 3.3 V logic. The IR module is powered from **3V3** for the
first tests (NOT 5 V) per the integration directive.

## 1. DHT11 (3-pin PCB module, on-board pull-up)

The module is a 3-pin PCB type. The PCB already includes the DATA-line
pull-up resistor, so **no external pull-up is added** in the current phase.

| DHT11 pin | NodeMCU | ESP8266 GPIO | Notes |
|-----------|---------|--------------|-------|
| VCC / +   | 3V3     | —            | 3.3 V supply |
| DATA / OUT / S | D2 | GPIO4  | 1-wire data; onboard pull-up |
| GND / -   | GND     | —            | common ground |

Code: `constexpr uint8_t DHT_PIN = D2;` (== GPIO4)

## 2. ZJ-IR-V2 IR learn / emit module (TTL)

| ZJ-IR-V2 pin | NodeMCU | ESP8266 GPIO | Direction |
|--------------|---------|--------------|-----------|
| VCC          | 3V3     | —            | 3.3 V supply (first tests) |
| GND          | GND     | —            | common ground |
| TXD          | D5      | GPIO14       | module TX → MCU RX (SoftwareSerial RX) |
| RXD          | D6      | GPIO12       | MCU TX → module RX (SoftwareSerial TX) |

Code:
```cpp
constexpr uint8_t IR_RX_PIN = D5; // GPIO14 (module TXD -> MCU RX)
constexpr uint8_t IR_TX_PIN = D6; // GPIO12 (MCU TX -> module RXD)
SoftwareSerial irSerial(IR_RX_PIN, IR_TX_PIN); // (RX, TX)
```

**Direction summary:** the module's **TXD** connects to the MCU's **RX** pin
(D5/GPIO14); the module's **RXD** connects to the MCU's **TX** pin (D6/GPIO12).

## 3. Common ground (mandatory)

```
NodeMCU GND
├── DHT11 GND
└── ZJ-IR-V2 GND
```

Both modules MUST share ground with the NodeMCU. Do not connect a USB-TTL
adapter to the IR module while the NodeMCU is also connected to the PC.

## 4. Module orientation (ZJ-IR-V2)

- **Black component** = IR receiver (learning): point the remote at this.
- **Clear/transparent component** = IR emitter (transmitting): point this at
  the air-conditioner receiver window.

## 5. Forbidden / avoided pins

- **GPIO6–GPIO11** are wired to on-board Flash — never use.
- Avoid boot-strapping pins where possible: **D3/GPIO0, D4/GPIO2, D8/GPIO15**.
- DHT11 uses D2/GPIO4; IR uses D5/GPIO14 (RX) and D6/GPIO12 (TX) — all clear
  of the forbidden/avoided set.

## 6. Pre-power checklist

- [ ] NodeMCU connected to PC via Micro-USB (data cable).
- [ ] DHT11: VCC→3V3, DATA→D2, GND→GND.
- [ ] ZJ-IR-V2: VCC→3V3, GND→GND, TXD→D5, RXD→D6.
- [ ] Common ground verified.
- [ ] No USB-TTL also attached to the IR module.
- [ ] No 5 V applied to the IR module (3V3 only for first tests).
- [ ] Serial port auto-detected at runtime — COM number not hard-coded.
