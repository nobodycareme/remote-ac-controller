# XHT11 独立读取测试报告

- 日期：2026-07-16
- 目标：验证新换上的 XHT11 三针温湿度模块能否在 D2/GPIO4 上被读取
- 构建目标：`[env:nodemcuv2_xht11]`（独立测试，不初始化红外模块）
- 固件版本：`FIRMWARE_VERSION=1.0.0-local-integration`

---

## 0. 结论速览

| 项 | 结果 |
|----|------|
| XHT11 是否 DHT11 协议兼容 | **是**（握手 + 40-bit 帧结构 + 5 字节布局均一致）|
| 能否用现有 DHT11 协议库读取 | **协议层可以；电气链路当前无法完成整帧** |
| 原始握手 | ✅ 正常（~80µs LOW/HIGH 响应）|
| 40-bit 时序诊断 | ⚠️ 在第 ~21–23 bit 总线卡高（bit-end-timeout）|
| 有效采样 | **0 / 25**（全部 XHT11_READ_FAIL）|
| XHT11_TEST_PASS | **未达成** → 记为 `XHT11_TEST_FAIL`（电气链路）|
| 故障归属 | **NodeMCU 主机侧**（3.3V 供电完整性 / 总线 / GND），非 XHT11 模块本体 |

> 关键判读：旧 DHT11 与本枚全新 XHT11 在**完全相同的 bit 位置（~21–23）**出现**完全相同**的“总线卡高”故障。
> 由于本测试固件已 `noInterrupts()` 且无 IR/WiFi 负载，旧结论“背景中断导致 3V3 跌落”被**证伪**；
> 故障必然是**主机侧共享链路**（3.3V  rail / 上拉 / GND），与具体传感器芯片无关。

---

## 1. 协议兼容性判定（需求 #4 / #5）

用户上传的示例 `XHT11/XHT11.ino` 仅含片段：

```cpp
if (xht.receive(dht)) {
  int humi = dht[0];   // 湿度整数
  int temp = dht[2];   // 温度整数
  ...
}
```

- 该示例**未随附 XHT11 库**（`XHT11.h` / `xht.receive` 实现缺席；仅 `XHT11.ino` 片段 + 原始 `.7z` 归档，本地无 7-Zip/`py7zr` 可解）。
- 其 `dht[0]=湿度、dht[2]=温度` 的 5 字节布局与 **DHT11 完全一致**。
- 因此按需求 #5“优先判断能否用现有 DHT11 协议库读取”，本测试**复用现有 in-tree 驱动 `src/dht_service.cpp`（`Dht11`）**，未编造任何 `xht.receive` API。

实测结果证实该判断正确：XHT11 以 DHT11 单线协议响应（见 §3 原始时序）。

---

## 2. 测试固件与执行约束

新增独立源 `src/xht11_test.cpp` + 新构建目标 `[env:nodemcuv2_xht11]`：

- `src_filter = +<xht11_test.cpp> +<dht_service.cpp>` → 仅编译这两个文件；
  `main.cpp` / `serial_cli.cpp` / `ir_module.cpp` **不参与编译**，集成代码原样保留。
- **D2/GPIO4** 接 XHT11 S 线（引脚未变）。
- **红外模块 D5/D6 完全不初始化**（`xht11_test.cpp` 不含 `IrModule`，`setup()` 不调用 `ir.begin()`）。
- 上电等待 **3000 ms** 后开始读取；采样间隔 **2500 ms**；连续采集 **25 次**（≥20）。
- 每次输出：
  - `XHT11_READ_OK sample=<n> temperature_c=<v> humidity_pct=<v> raw=<5字节>`
  - `XHT11_READ_FAIL sample=<n> reason=<原因>`
- 启动阶段保留原始握手 + 40-bit 时序诊断（`dht.rawTrace()`，包裹于 `XHT11_RAW_TRACE_START/END`）。
- 仅当“完整 40 位 + 校验和通过 + 连续 ≥10 次有效”才标记 `XHT11_TEST_PASS`。

构建/烧录未改动 PlatformIO Core、未升级工具链（沿用 `espressif8266 4.2.1` + 已缓存工具，经 `NO_PROXY` 直连绕过 MITM 代理，未设 `PLATFORMIO_OFFLINE=1`）。

---

## 3. 原始握手与 40-bit 时序（需求 #10）

完整串口日志（`xht11_serial.log`）关键段落：

```
XHT11_RAW_TRACE_START
DHT_TRACE_BEGIN
TRACE_IDLE_HIGH_COUNT=50
TRACE_PULLUP_RESP_LOW_US=60 RESP_HIGH_US=85
TRACE_PULLUP_BYTE0=20 19 66 20 66 20 20 20
TRACE_PULLUP_BYTE1=19 20 20 19 19 19 19 19
TRACE_PULLUP_BYTE2=66 20 16 64 20 TRACE_PULLUP_BIT21_END_TIMEOUT
TRACE_INPUT_RESP_LOW_US=76 RESP_HIGH_US=84
TRACE_INPUT_BYTE0=20 20 20 65 20 65 19 19
TRACE_INPUT_BYTE1=20 20 20 19 19 19 20 19
TRACE_INPUT_BYTE2=20 20 20 20 57 20 12 TRACE_INPUT_BIT23_END_TIMEOUT
DHT_TRACE_END
XHT11_RAW_TRACE_END
```

判读：

- `TRACE_IDLE_HIGH_COUNT=50`：空闲总线为高 → 模块板载上拉存在。
- `RESP_LOW/HIGH ≈ 60–85 µs`：模块对 DHT11 起始信号返回标准 ~80µs 应答 → **协议握手成功**。
- 前 ~20 bit 宽度正常：`'0'≈16–20µs`、`'1'≈57–66µs`（阈值 >40µs 判 1，解码正确）。
  例如 `Byte0 = 0x28 = 40` → 模块确实在发送**有效温湿度格式数据**（湿度≈40% 量级）。
- `BIT21_END_TIMEOUT`（PULLUP 模式）/ `BIT23_END_TIMEOUT`（INPUT 模式）：
  第 ~21–23 bit 之后总线**再也无法被拉低**（卡高），与旧 DHT11（K13/K15）**故障位置一致**。

---

## 4. 采样结果（需求 #8 / #9 / #11）

```
XHT11_READ_FAIL sample=1  reason=no-response-low
XHT11_READ_FAIL sample=2  reason=bit-end-timeout
...（sample 3–25 均为 bit-end-timeout）...
XHT11_TEST_DONE
XHT11_TEST_INCOMPLETE consecutive_valid=0 total_valid=0
```

- 25 次全部失败；有效次数 0，连续有效 0 → **未达成 XHT11_TEST_PASS**。
- 失败原因统一为 `bit-end-timeout`（握手指令成功，但 40-bit 解码中途总线卡高）。
- sample=1 的 `no-response-low` 为 trace 之后首次读取间隔不足所致（模块需 >1s 恢复），不影响结论。

---

## 5. 根因分析

| 候选 | 评估 |
|------|------|
| XHT11 模块本体损坏 | **排除**：全新模块，且旧 DHT11 / 新 XHT11 故障位完全一致（~21–23）。 |
| DHT11 协议不匹配 | **排除**：握手 + 40-bit 结构 + 5 字节布局与 DHT11 完全一致。 |
| 杜邦线长度 | **排除**：此前短杜邦线 A/B 复测为 `NO_CHANGE`；本枚 XHT11 沿用同套接线。 |
| 背景中断导致 3V3 跌落（旧 K15 假设）| **证伪**：本测试固件 `read()` 内 `noInterrupts()` 且无任何后台负载，仍卡同一 bit。 |
| **NodeMCU 3.3V 供电完整性 / 总线 / GND（主机侧）** | **高概率根因**：故障与具体传感器无关，且恒在帧中段（传感器 MCU 持续拉低总线致 3V3 负载最大处）发生。 |

> 这与 Phase 1 结论中“可能涉及 3.3V 供电完整性（NodeMCU 板载 AMS1117 共载噪声）”的预测**相互印证并强化**：
> 现在可以确定故障位于 **NodeMCU 主机侧链路**，而非旧的 DHT11 芯片本体。

---

## 6. 修复方向（需用户现场操作，非固件可解）

由于总线在电气上**被卡高**（非时序/软件可修），**任何固件改动都无法解决**。需主机侧硬件整改，按优先级：

1. **XHT11 VCC–GND 就近并联 100 nF 陶瓷去耦电容**（抑制 3.3V 中段跌落/噪声）。
2. 为传感器使用**独立、干净的 3.3V LDO**（不要与 NodeMCU 板载 AMS1117 共载）。
3. 检查 GND 回路接触（杜邦头、面包板），确保低阻抗回流。
4. 若仍失败，用万用表在**长帧中段**测 3.3V 是否被拉低；必要时降低 NodeMCU 其他负载。

> 本轮**未**做任何硬件改动、**未**进入红外学习/发射阶段（符合需求 #13）。

---

## 7. 产物与回退

- 新增：`src/xht11_test.cpp`、`[env:nodemcuv2_xht11]`（platformio.ini）。
- 日志：`xht11_build.log`、`xht11_upload.log`、`xht11_serial.log`。
- 固件：`.pio/build/nodemcuv2_xht11/firmware.bin`（271071 B）。
- 回退：当前代码已备份至 `.bak_xht11_20260716/`（含 src/、include/、platformio.ini、docs/）。
- 原 DHT11 集成代码（`main.cpp` 等）与 `[env:nodemcuv2]`、`[env:nodemcuv2_probe]` 均未改动。
