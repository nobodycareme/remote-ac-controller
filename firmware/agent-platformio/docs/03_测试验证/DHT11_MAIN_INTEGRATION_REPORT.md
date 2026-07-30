# DHT11 主工程集成报告（Phase 2）

- **日期**：2026-07-16
- **目标**：将 Phase 1 验证通过的 DHT11 读取方案（Adafruit DHT 库 + D1/GPIO5）
  正式集成进主工程 `[env:nodemcuv2]`，替换旧的自定义 `dht_service.*` 驱动。
- **结论**：**集成编译 + 烧录 + 启动 + 周期读取均通过**（进入 Phase 3 稳定性验证）。

---

## 1. 架构改动

### 新增：集中式硬件配置
`include/config/hardware_config.h` —— 全项目引脚唯一真源：

| 常量 | 值 | 说明 |
|------|-----|------|
| `DHT11_DATA_PIN` | `D1`（GPIO5） | DHT11 数据线（Phase 1 验证通过） |
| `IR_UART_RX_PIN` | `D5`（GPIO14） | 模块 TXD → MCU RX |
| `IR_UART_TX_PIN` | `D6`（GPIO12） | MCU TX → 模块 RXD |

`include/board_pins.h` 改为**兼容垫片**，`#include "config/hardware_config.h"` 并保留旧别名
（`DHT_PIN`/`IR_RX_PIN`/`IR_TX_PIN`），使 `ir_module.*` 无需改动即可继续编译。

### 新增：正式传感器模块（Adafruit 库）
- `include/sensors/dht11_sensor.h` + `src/sensors/dht11_sensor.cpp`
- 类 `Dht11Sensor`，公开 API：
  - `begin()` — 初始化（setup 调用一次）
  - `read()` — 立即强制读取一次，成功返回 true（isnan 校验）
  - `update(intervalMs)` — 间隔到达才读
  - `hasValidReading()` / `temperatureC()` / `humidityPercent()`
  - `lastReadTimestamp()` / `failureCount()` / `successCount()`
- 底层用 Adafruit `DHT`（type=DHT11），`readHumidity(true)` 强制新帧 + `readTemperature(false)` 复用缓存帧。

### 移除旧驱动引用
- `main.cpp`：`Dht11 dht(DHT_PIN)` → `Dht11Sensor dht(DHT11_DATA_PIN)`；setup 中调用 `dht.begin()`，
  打印 `DHT11_MODULE_READY pin=GPIO5`。
- `serial_cli.h/.cpp`：`Dht11& _dht` → `Dht11Sensor& _dht`；`doDhtRead()` 改用 `_dht.read()` + getters；
  **删除 `dht debug`（rawTrace）子命令**（旧自定义驱动专用，已废弃）；`status` 增补
  `dht_valid/dht_temp_c/dht_hum_pct/dht_ok/dht_fail`。
- `app_config.h`：`FIRMWARE_VERSION` → `1.1.0-dht11-adafruit-integration`；
  `DHT_READ_INTERVAL_MS` 2000 → 2500（避开 Adafruit 库 2s 缓存边界）。

### 构建隔离（关键）
`[env:nodemcuv2]` 增加 `build_src_filter`，只编译生产源、排除旧驱动与所有独立测试草稿
（各自带 setup/loop，会破坏链接）：
```
build_src_filter =
    +<*>
    -<dht_service.cpp>
    -<xht11_test.cpp>
    -<xht11_gpio5_minimal.cpp>
    -<dht11_gpio5_minimal.cpp>
lib_deps =
    adafruit/DHT sensor library@1.4.7
    adafruit/Adafruit Unified Sensor@1.1.15
```
`[env:nodemcuv2_probe]`（DISABLE_DHT）同步加 `build_src_filter`，额外排除
`sensors/dht11_sensor.cpp`（其依赖 DHT 库，probe 无 lib_deps）。

---

## 2. 编译验证

| 项 | 结果 |
|----|------|
| `pio run -e nodemcuv2 -t clean` | `CLEAN_EXIT=0` |
| `pio run -e nodemcuv2` | `SUCCESS 00:00:40.579`，`BUILD_EXIT=0` |
| RAM | 35.5%（29108 / 81920 字节） |
| Flash | 27.4%（285747 / 1044464 字节） |
| firmware.bin | 289904 字节 |

**编译源核对**（只应有 4 个生产源）：
- ✅ `main.cpp`、`serial_cli.cpp`、`ir_module.cpp`、`sensors\dht11_sensor.cpp`
- ✅ 排除文件引用计数=0：`dht_service.cpp` / `xht11_test.cpp` / `xht11_gpio5_minimal.cpp` / `dht11_gpio5_minimal.cpp`

**依赖图**：
```
|-- DHT sensor library @ 1.4.7
|-- Adafruit Unified Sensor @ 1.1.15
|-- EspSoftwareSerial @ 8.0.1
```

---

## 3. 烧录与启动验证

- `pio run -e nodemcuv2 -t upload --upload-port COM6` → `SUCCESS`，289904 字节，`Hash of data verified`，`UPLOAD_EXIT=0`。
- 启动串口（关键标记全部命中）：
```
 Remote AC Controller  firmware v1.1.0-dht11-adafruit-integration
 Local integration build (DHT11 + ZJ-IR-V2)
APP_BOOT_OK
IR_UART_INIT baud=0
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO14 tx=GPIO12
```
  > `IR_UART_INIT baud=0` 为横幅在 `ir.begin()` 之前打印所致（既有行为，无害）；
  > `IR_MODULE_READY` 显示 rx=GPIO14/tx=GPIO12 正确。

- 周期读取（集成后主固件自动每 2.5s 读一次，节选连续 8 次）：
```
DHT_READ_OK sample=29 temperature_c=35.2 humidity_pct=8.0 free_heap=51360
DHT_READ_OK sample=30 temperature_c=35.8 humidity_pct=8.0 free_heap=51360
...
DHT_READ_OK sample=36 temperature_c=35.7 humidity_pct=8.0 free_heap=51360
```
  连续成功、free_heap 恒定 51360（无泄漏）。

---

## 4. 结论

**Phase 2 集成成功**：DHT11 已通过 Adafruit 库 + D1/GPIO5 正式并入主工程，
旧自定义驱动与所有测试草稿已从主构建中隔离；IR 模块保持既有 lazy-open、不自动发码。
**满足进入 Phase 3（完整断电重启 + ≥5 分钟 / ≥100 次读取稳定性验证）的条件。**

## 5. 产物
- 固件：`.pio/build/nodemcuv2/firmware.bin`（289904 字节）
- 新增源：`include/config/hardware_config.h`、`include/sensors/dht11_sensor.h`、`src/sensors/dht11_sensor.cpp`
- 修改：`include/board_pins.h`、`include/app_config.h`、`src/main.cpp`、`src/serial_cli.h`、`src/serial_cli.cpp`、`platformio.ini`
- 日志：`logs/02_main_integration/`（`main_clean.log`、`main_build.log`、`main_upload.log`、`main_serial_boot.log`、`main_serial_reads.log`）
