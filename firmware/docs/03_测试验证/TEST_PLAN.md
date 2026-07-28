# TEST PLAN — DHT11 + ZJ-IR-V2 Local Integration

Phased, evidence-driven hardware verification. Each phase must PASS (or be
explicitly NOT TESTED) before the next begins. Build success ≠ hardware success;
module ACK ≠ AC response.

## Phase 0 — Environment & git baseline
- `git status` / `branch` / `diff` recorded; safety branch `feature/dht11-zjir-local-integration`.
- `before_changes.patch` generated (pre-edit snapshot).
- `PLATFORMIO_CORE_DIR=F:\PIO\Core` confirmed; `pio system info` → Core Directory correct.
- NodeMCU COM port auto-detected (not hard-coded).

## Phase 1 — DHT11 standalone self-test
- In-tree DHT11 driver (`src/dht_service.*`), pin `D2/GPIO4`, 3.3 V, no external pull-up.
- Build → flash → capture ≥ 10 valid samples over ~24 s.
- Pass: ≥ 10 valid reads, no persistent NaN, temp ≈ -10~60 ℃, humidity ≈ 0~100 %RH,
  no watchdog reset, no infinite block. Output `DHT_TEST_PASS`.
- Deliverables: `logs/hardware_integration/dht_build.log`, `dht_upload.log`,
  `dht_serial.log`, `docs/DHT11_TEST_REPORT.md`.

## Phase 2 — IR protocol review (documentation)
- All four manufacturer files read; protocol in `docs/IR_PROTOCOL_ANALYSIS.md`.
- Frame `68/LEN/ADDR/AFN/DATA/CS/16`, CS = (ADDR+AFN+DATA) mod 256, default 115200/8N1.

## Phase 3 — ZJ-IR-V2 UART probe (read-only)
- SoftwareSerial(D5, D6). Baud scan [115200, 9600, 57600, 38400, 19200] via `queryBaud`.
- Pass: a valid `AFN=04` response at some baud → `IR_UART_PASS baud=<actual>`.
- No learn/send frames sent. Deliverables: `ir_probe_*.log`, `docs/IR_UART_TEST_REPORT.md`.

## Phase 4 — Learn group 0 (user-authorized)
- Pre: DHT_TEST_PASS + IR_UART_PASS + user holds remote + user agrees to overwrite group 0.
- `ir learn 0` → module enters learn (green LED on) → user presses remote once
  (LED off) → module sends report `AFN=02` flag 0x80 → `IR_LEARN_PASS index=0`.
- User must confirm LED went out. Deliverables: `ir_learn_serial.log`, `docs/IR_LEARN_TEST_REPORT.md`.

## Phase 5 — Send group 0 (user-authorized)
- Pre: IR_LEARN_PASS + emitter aimed at AC + user authorizes one emission.
- `ir send 0` → module ACK (`IR_SEND_COMMAND_ACCEPTED`) → `IR_PHYSICAL_RESULT_PENDING`.
- **AC actual response confirmed by user only** → `IR_PHYSICAL_PASS` (recorded by agent).
- Deliverables: `ir_send_serial.log`, `docs/IR_SEND_TEST_REPORT.md`.

## Phase 6 — Local combined run
- One firmware: DHT11 every 2 s + IR CLI, no auto-send. Run 5–10 min.
- Verify uptime, free heap, stable DHT output, no watchdog, no auto IR.
- Output `LOCAL_INTEGRATION_PASS`. Deliverables: `integration_*.log`, `docs/LOCAL_INTEGRATION_REPORT.md`.

## Phase 17 — Review package
- `ESP8266_DHT11_ZJIR_Local_Integration_Review_Package_v1.0_*.zip` into `F:\PIO\ReviewPackages`,
  with hardened verify + forward-slash paths + sensitive scan. See `docs/` and `review/`.

## Hard rules
- No auto IR on boot/reset/flash. No Wi-Fi/cloud this phase.
- Forbidden IR ops (format/reset/addr-change/code-overwrite/power-on-send/baud-change)
  require explicit user authorization.
- LED / AC status never marked PASS without user confirmation.
