# XHT11 旧测试独立性与隔离性审查

> 审查对象：上一轮（2026-07-16）`[env:nodemcuv2_xht11]` 测试
> 审查目的：回答用户提出的 10 个问题，确认上一轮是否“真正独立”、是否真的是标准库测试
> 结论：**上一轮并不是标准库（Adafruit / DHTStable 等）测试，而是复用了工程内自定义的 `dht_service.cpp` 驱动。因此“总线在 bit~21-23 卡高 = 主机侧供电故障”这一结论的底层依据，来自自定义读取器，不符合本轮“用广泛验证的最小化方案”的要求。**

---

## 审查范围与文件

| 文件 | 角色 | 是否被旧测试编译 |
|------|------|------------------|
| `src/xht11_test.cpp` | 上一轮测试入口 | ✅ 编译 |
| `src/dht_service.cpp` | **自定义 DHT11 协议驱动** | ✅ 编译并链接 |
| `src/dht_service.h` | 自定义驱动头 | ✅ 引用 |
| `src/main.cpp` | 集成固件 | ❌ 由 `src_filter` 排除 |
| `src/serial_cli.cpp` | 串口 CLI | ❌ 排除 |
| `src/ir_module.cpp` | 红外模块 | ❌ 排除 |
| `lib/` | 工程本地库目录 | 仅含 README，**无 DHT 库** |
| `.pio/libdeps/` | 库依赖缓存 | **为空，无任何第三方库** |
| `include/` | 头文件 | `app_config.h`、`board_pins.h` 被引用；无 DHT 头 |

`platformio.ini` 中旧环境定义：

```ini
[env:nodemcuv2_xht11]
platform = espressif8266
board = nodemcuv2
framework = arduino
monitor_speed = 115200
upload_speed = 115200
src_filter = +<xht11_test.cpp> +<dht_service.cpp>
```

注意：`src_filter` 这里用的是**只含**两条规则（无 `-<*>` 基线、无 `*` 通配），实际效果等同于“仅编译这两个文件”，集成代码确实被排除。但被编入的 `dht_service.cpp` 本身就是自定义驱动。

---

## 10 个审计问题逐条回答

### 1. 此前所谓“标准库测试”是否仍然调用了 dht_service.cpp？
**是。** `xht11_test.cpp` 第 20 行 `#include "dht_service.h"`，第 22 行 `static Dht11 dht(DHT_PIN);`，读取全部走 `dht.read(r)` 与 `dht.rawTrace()`。所谓“现有 DHT11 协议库读取”指的就是这个 **in-tree 自定义驱动**，并非 Adafruit / DHTStable / DHTesp 等第三方已验证库。因此上一轮**不是标准库测试**。

### 2. dht_service.cpp 是否包含自定义时序、rawTrace、noInterrupts 或 GPIO 操作？
**是，全部包含。**
- `waitPin()`：用 `digitalRead()` 轮询自定义 GPIO 时序；
- `readByte()`：自定义 40-bit 解码（50µs LOW + 可变 HIGH 判位）；
- `read()`：`pinMode(OUTPUT)/digitalWrite(LOW)` 发 20ms 启动、`noInterrupts()`、`pinMode(INPUT_PULLUP)`、`micros()` 计时；
- `rawTrace()`：完全自定义的总线时序测量 + 打印。

=> 这是一个 **100% 自定义 bit-bang 驱动**，不是“网上和官方资料中经过广泛验证的最小化方案”。

### 3. xht11_test.cpp 是否同时链接了自定义读取器和第三方 DHT 库？
**否。** `xht11_test.cpp` 仅 `#include "dht_service.h"`，工程 `lib/` 为空、`.pio/libdeps/` 为空，未链接任何第三方 DHT 库。所以上一轮是“自定义驱动单独测试”，不存在“自定义 + 第三方混链”的情况。

### 4. 工程中是否同时存在多个名称相近的 DHT 库？
**否。** 全工程唯一的 DHT 相关代码是 `src/dht_service.*`（自定义）。无 `lib/DHT`、`lib/DHT11`、`lib/DHTesp`、无 `.pio/libdeps/DHT*`。

### 5. 是否存在本地 lib/DHT、lib/DHT11、lib/DHTesp 等目录覆盖 PlatformIO 库？
**否。** `lib/` 目录仅含一个 `README`，无任何 DHT 子目录，不存在本地库覆盖 PlatformIO registry 库的情况。

### 6. 是否把 D1 误写成数字 1？
**不涉及上一轮；但需指出**：上一轮根本没有使用 D1，它用的是 `DHT_PIN = D2`（见 `board_pins.h` 第 13 行，`constexpr uint8_t DHT_PIN = D2;`，`D2` 是 NodeMCU 宏 = GPIO4，**不是**数字 2）。所以上一轮没有“D1 误写 1”的问题，但**它用的是 GPIO4 而不是本轮要求的 GPIO5**。本轮已按要求改用 `constexpr uint8_t XHT_PIN = D1;`（=GPIO5）。

### 7. 是否仍然把 DHT_PIN 定义为 D2 或 GPIO4？
**是（仅限上一轮旧环境）。** `board_pins.h` 中 `DHT_PIN = D2`（GPIO4）。上一轮 `nodemcuv2_xht11` 用的就是这个宏 → 数据脚在 **D2/GPIO4**。本轮新要求是把数据线改到 **D1/GPIO5**，并在独立新环境中用 `XHT_PIN = D1`，不引用 `DHT_PIN` 宏。

### 8. 是否配置成 DHT22？
**否。** 自定义驱动只实现 DHT11 单总线 40-bit / 整数协议（5 字节：`湿度整数/小数/温度整数/小数/校验和`），XHT11 也按 DHT11 兼容处理。未配置为 DHT22，未用浮点温湿度寄存器。

### 9. 是否在读取过程中调用了会修改 GPIO5 状态的其他代码？
上一轮旧环境：数据脚在 GPIO4，**红外代码被 `src_filter` 排除**（`ir_module.cpp` 未编译，SoftwareSerial 未初始化），**未初始化 Wi-Fi**。因此没有任何其他代码在读取过程中碰 GPIO5。
**但本轮需注意**：ESP8266 Arduino 的默认 `Wire`（I²C）引脚是 `SDA=GPIO4(D2)`、`SCL=GPIO5(D1)`。只要不调用 `Wire.begin()`，GPIO5 就不会被 I²C 占用。本轮最小示例**不调用 Wire**，故无此冲突。

### 10. 是否有 I²C 默认使用 D1/GPIO5 并与传感器冲突？
**默认 Wire 的 SCL 确实是 GPIO5(D1)**，但本轮最小测试**从不调用 `Wire.begin()`**，因此不会在 GPIO5 上初始化 I²C，实际无冲突。仅作风险提示：后续若误加入 `Wire.begin()` 会占用 GPIO5。本轮代码已保证不引入。

---

## 审查结论

1. 上一轮 **不是** 标准库最小示例测试，而是基于自定义 `dht_service.cpp` 的驱动测试。
2. 上一轮把 XHT11 接在 **GPIO4（D2）**，而本轮要求 **GPIO5（D1）**——引脚不同，本身就是一次单变量变更。
3. 由于底层诊断（`rawTrace()`）来自自定义驱动，且经代码审查存在“在 `noInterrupts()` 临界区内调用 `Serial.print`”的缺陷（见 `DHT_RAW_TRACE_CODE_AUDIT.md`），**上一轮“bit~21-23 卡高 = 主机侧供电故障”不能直接作为唯一硬件结论**。
4. 本轮按要求改用 **Adafruit DHT sensor library 1.4.7 + Adafruit Unified Sensor 1.1.15**，在独立环境中仅编译一个最小示例文件，不碰自定义驱动，以得到可独立采信的结果。

---

*本文件仅记录审查事实，不改变任何源码。新测试见 `nodemcuv2_xht11_gpio5_minimal` 环境。*
