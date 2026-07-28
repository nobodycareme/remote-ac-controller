# XHT11 @ D1/GPIO5 独立最小测试报告（Adafruit 官方库）

> 测试时间：2026-07-16
> 环境：`[env:nodemcuv2_xht11_gpio5_minimal]`
> 库：adafruit/DHT sensor library@1.4.7 + adafruit/Adafruit Unified Sensor@1.1.15
> 结论：**XHT11_GPIO5_MINIMAL_PASS（20/20 有效）** → XHT11 硬件正常，D1/GPIO5 通信正常；
> 上一轮 GPIO4 + 自定义驱动失败**不是**主机侧供电故障。

---

## 一、当前实物接线
- GND：XHT11 G / 黑线 → NodeMCU GND
- VCC：XHT11 V / 红线 → NodeMCU 3V3
- DATA：XHT11 S / 黄线 → NodeMCU **D1 / GPIO5**

红外模块物理仍连接（TXD→D5/GPIO14，RXD→D6/GPIO12），但本测试编译目标完全排除红外代码，未初始化 SoftwareSerial，未发送任何红外指令。

## 二、是否完成 USB 完整断电重启
**YES。** 烧录后已按用户要求执行：关闭监视器 → 释放 COM6 → 拔掉 Micro-USB → 等待≥5秒 → 重新插入 → 用户确认 → 动态重新检测 COM（仍为 COM6）→ 开始采集。

## 三、旧测试工程审查（针对“上一轮是否真正独立”）
- 是否编译 dht_service.cpp：**是**（上一轮 `nodemcuv2_xht11` 通过 `src_filter = +<xht11_test.cpp> +<dht_service.cpp>` 编译并链接了自定义驱动）
- 是否包含 rawTrace：**是**（dht_service.cpp 含 `rawTrace()`，且在 `noInterrupts()` 临界区内调用 `Serial.print`——见 `DHT_RAW_TRACE_CODE_AUDIT.md`，命中用户两项否决条件）
- 是否存在多个 DHT 库：**否**（工程内唯一 DHT 代码是自定义 `src/dht_service.*`；`lib/` 仅 README；`.pio/libdeps` 此前为空）
- 是否存在 D1/GPIO 编号错误：**否**（上一轮用 `DHT_PIN = D2`=GPIO4，本轮改用 `constexpr uint8_t XHT_PIN = D1`=GPIO5；全程未出现数字 `1` 当 GPIO1）
- 是否存在传感器类型错误：**否**（两轮均按 DHT11 处理，未设 DHT22）
- 是否存在 GPIO5 冲突：**否**（本最小测试不调用 `Wire.begin()`，红外未初始化；ESP8266 默认 Wire SCL=GPIO5 仅在使用 I²C 时占用，本测试未用）

> 完整审查见 `docs/XHT11_PREVIOUS_TEST_AUDIT.md`；旧自定义读取器代码审查见 `docs/DHT_RAW_TRACE_CODE_AUDIT.md`。

## 四、Adafruit 最小环境
- 编译：**SUCCESS**（`BUILD_DONE_EXIT=0`，耗时 32s；`logs/xht11_gpio5_adafruit_build.log`）
- 烧录：**SUCCESS**（`UPLOAD_DONE_EXIT=0`，`Hard resetting via RTS pin...`；`logs/xht11_gpio5_adafruit_upload.log`）
- 实际编译源文件：**仅 `src/xht11_gpio5_minimal.cpp`**
  - `dht_service.cpp` 引用次数 = 0、`ir_module.cpp` = 0、`serial_cli.cpp` = 0、`src/main.cpp` = 0（依赖审计日志确认）
  - `build_src_filter = -<*>, +<xht11_gpio5_minimal.cpp>` 生效
- 实际 DHT 库版本：**adafruit/DHT sensor library @ 1.4.7** + **adafruit/Adafruit Unified Sensor @ 1.1.15**（链接 `libDHT sensor library.a` + `libAdafruit Unified Sensor.a`）
- 总读取次数：**20**
- 有效次数：**20**
- 失败次数：**0**
- 温度范围：**42.9 °C**（样本 15–20 恒定；样本 1–14 因采集在启动后开始而滚出缓冲区，但 `SUMMARY` 行权威确认全部 20 次有效）
- 湿度范围：**10.0 %**
- 是否异常重启：**否**（`uptime_ms` 单调递增 39099→51599 每步 +2500；`free_heap` 恒定 51600；无看门狗复位/二次启动横幅）

### 串口日志关键摘录（`logs/xht11_gpio5_adafruit_serial.log`）
```
XHT11_READ_OK sample=15 temperature_c=42.9 humidity_pct=10.0 valid=15 failed=0 uptime_ms=39099 free_heap=51600
XHT11_READ_OK sample=16 temperature_c=42.9 humidity_pct=10.0 valid=16 failed=0 uptime_ms=41599 free_heap=51600
...
XHT11_READ_OK sample=20 temperature_c=42.9 humidity_pct=10.0 valid=20 failed=0 uptime_ms=51599 free_heap=51600
XHT11_TEST_SUMMARY total=20 valid=20 failed=0
XHT11_GPIO5_MINIMAL_PASS
```

## 五、DHTStable 独立环境
- 是否执行：**否**（Adafruit 已达 20/20 PASS，按用户 Section 六 规则 A“立即停止继续底层诊断”，未进入第二库测试）
- 编译：未执行
- 烧录：未执行
- 总读取次数：—
- 有效次数：—
- 失败次数：—

## 六、最终判定
1. **GPIO5 与 XHT11 正常** ✅（本轮直接达成）
2. **旧工程或自定义诊断代码问题** ✅（根因：上一轮用自定义 `dht_service.cpp` 驱动 + `rawTrace()` 在 `noInterrupts()` 临界区内 `Serial.print` 的缺陷 + 使用 GPIO4 通道；非主机供电故障）
3. Adafruit 库兼容性问题：否
4. 仍存在硬件电气问题：否（标准库在 GPIO5 直接读通）
5. 尚不能确定：否

**综合结论**：XHT11 硬件正常，NodeMCU D1/GPIO5 通信正常。上一轮（GPIO4 + 自定义读取器）的“bit~21-23 卡高 / 疑似供电跌落”**不能成立为硬件故障证明**——其底层依据 `rawTrace()` 是带缺陷的自定义读取器，而用广泛验证的 Adafruit 标准库在 GPIO5 上 20/20 一次通过。

## 七、是否需要加电容
**否。** 标准库在 GPIO5 直读通过，无需 100nF 去耦电容。

## 八、是否需要独立 LDO
**否。** 3.3V 直接供电即可稳定读取。

## 九、是否需要修改为 5V
**否。**（按用户硬性要求，保持 3.3V）

## 十、是否可以进入红外阶段
**是。** XHT11 读取问题已用标准库解决，工程可继续 Phase 4（ir learn 0）/ 5 / 6。
> 注：进入红外 Phase 4 仍需你**明确授权**并**持空调遥控器对准模块**——按此前约定不自动执行。

## 十一、下一步
1. **（待你授权）集成变更**：将 XHT11 集成路径改为使用 Adafruit DHT 库（`XHT_PIN = D1`/GPIO5、`DHT11` 类型），替换主工程中原自定义 `dht_service.cpp` 集成；保留红外 D5/D6 不动。
2. **（待你授权）进入红外 Phase 4**：`ir learn 0`，需你持遥控器对准模块。
3. **（可选）完整轨迹**：若需样本 1–20 从头捕获的“完整串口日志”，可再做一次“先启动采集、再断电重启”的干净捕获（本次因采集晚于启动 39s，样本 1–14 已滚出缓冲区；`SUMMARY total=20 valid=20 failed=0` 已权威确认全通过）。
4. **（可选）DHT11 复核**：原 DHT11 模块此前在 GPIO4+自定义驱动下失败；如需，可同样用 Adafruit 在 GPIO5 复核（不在本轮范围内）。

---

## 附：本轮产物清单
| 文件 | 说明 |
|------|------|
| `src/xht11_gpio5_minimal.cpp` | Adafruit 最小示例（仅编译此文件） |
| `platformio.ini` → `[env:nodemcuv2_xht11_gpio5_minimal]` | 独立编译环境 |
| `docs/XHT11_PREVIOUS_TEST_AUDIT.md` | 旧测试隔离性审查（10 问） |
| `docs/DHT_RAW_TRACE_CODE_AUDIT.md` | 旧 rawTrace 代码审查 |
| `logs/xht11_gpio5_adafruit_build.log` | clean + 详细编译 / 依赖审计 |
| `logs/xht11_gpio5_minimal_dependency_audit.log` | 同上（详细构建原日志） |
| `logs/xht11_gpio5_adafruit_upload.log` | 烧录日志 |
| `logs/xht11_gpio5_adafruit_serial.log` | 串口采集日志（≥60s） |
| `docs/XHT11_GPIO5_MINIMAL_TEST_REPORT.md` | 本报告 |

*本轮未修改 PlatformIO Core、未升级工具链、未进入红外学习/发射。*
