# DHT11 短杜邦线 A/B 复测报告（Round 2）

- 项目：`F:\PIO\Projects\Remote_AC_Controller`
- 测试日期：2026-07-15
- 测试人：远程软件诊断（用户不在现场，仅更换杜邦线）
- 固件版本：`1.0.0-local-integration`（即上一轮最终诊断固件 t1000，**字节级未改动**）

---

## 1. 唯一硬件变更

DHT11 的 **VCC、DATA/S、GND 三根连接线全部更换为更短的杜邦线**。
接口位置、传感器、供电、GPIO 全部保持不变。

## 2. 接口位置未改变

- DHT11 VCC → NodeMCU **3V3**（同前）
- DHT11 DATA/S/OUT → NodeMCU **D2 / GPIO4**（同前）
- DHT11 GND → NodeMCU 当前使用的 GND 引脚（同前）
- 未改接其他 GPIO，未增加外接上拉，未改 5V。

## 3. DHT DATA 仍为 D2 / GPIO4

`include/board_pins.h`：`constexpr uint8_t DHT_PIN = D2; // D2 == GPIO4`（未改动）。

## 4. DHT 仍使用 3.3V

模块 VCC 接 NodeMCU 板载 3V3（AMS1117 输出），未改 5V。

## 5. 是否完整断电重启

是。更换杜邦线时设备已物理断电/重插；随后经 esptool `write_flash` 的
`Hard resetting via RTS pin` 完成一次硬复位；首条 `status`/`dht debug` 在
上电后等待 ≥4s 才执行（满足 ≥3s 要求）。

## 6. 使用的固件版本

与上一轮最后使用的诊断固件 **完全一致（A/B 对照组）**：

- `src/dht_service.cpp`：`read()` 使用 `INPUT_PULLUP` + `noInterrupts()`（K15），
  标准库 `readByte()` 超时 = `DHT_BIT_TIMEOUT_US = 250µs`；
  `rawTrace()` 数据位超时 = **1000µs**（t1000 设置），同时测量
  INPUT_PULLUP 与 native INPUT 两种模式。
- `src/serial_cli.cpp`：`dht debug` → `rawTrace()`；`dht test` → 12 次 `read()` @2s。
- `include/app_config.h`：`DHT_START_SIGNAL_MS=20U`、`DHT_READ_INTERVAL_MS=2000U`。
- **IR 模块在本轮固件中完全禁用**：`dht debug`/`dht test` 均不调用任何 IR 函数；
  SoftwareSerial 仅在 `ir probe/info/learn/send/cancel` 时按需打开，本轮未执行。

> 本轮**未修改任何软件参数**（引脚、类型、库版本、依赖、起始低电平、响应等待、
> 数据位超时、0/1 阈值、INPUT/INPUT_PULLUP 配置、中断策略、读取间隔、采样逻辑、
> IR 代码、编译优化均未变），严格遵循“先保持软件不变做 A/B 对照”。

## 7. 是否与上一轮诊断逻辑完全一致

**是。** 本轮烧录的即为上一轮最后构建产物（`integ_build_t1000.log` 同源），
源码逐字节未改。编译：`BUILD_DONE_EXIT=0`；烧录：`FLASH_EXIT=0`，
`Hash of data verified`。日志：`dht_short_wires_build.log` / `dht_short_wires_upload.log`。

## 8. 上一轮故障特征（t1000，原杜邦线）

- ESP8266 能正常发启动信号（20ms 低电平）。
- DHT11 正常返回 ~80µs 响应脉冲（RESP_LOW≈67µs / RESP_HIGH≈87µs）。
- 前 ~22 个数据位可按 24µs/70µs 脉宽正常解码。
- 随后 DATA 总线持续高电平 >1000µs（1000µs 超时仍卡高）。
- INPUT_PULLUP 模式约在 **bit 21** 卡高，native INPUT 模式约在 **bit 23** 卡高。
- 关闭中断（K15）后仍失败。
- 标准库 `dht test`：**0/12** 通过。
- 结论：硬件电气故障（非固件），原因为 DHT11 供电/灌电流余量或模块本体。

## 9. 本轮每次接收位数（10 次 `dht debug`，每次含 PULLUP + INPUT 两 Trace）

| attempt | PULLUP 模式 接收位数 | INPUT 模式 接收位数 | PULLUP 失败位 | INPUT 失败位 |
|--------:|---------------------:|--------------------:|:-------------:|:------------:|
| 1 | 22 | 24 | BIT22 | BIT24 |
| 2 | 22 | 24 | BIT22 | BIT24 |
| 3 | 22 | 24 | BIT22 | BIT24 |
| 4 | 22 | 23 | BIT22 | BIT23 |
| 5 | 22 | 23 | BIT22 | BIT23 |
| 6 | 22 | 23 | BIT22 | BIT23 |
| 7 | 22 | 22 | BIT22 | BIT22 |
| 8 | 22 | 22 | BIT22 | BIT22 |
| 9 | 22 | 23 | BIT22 | BIT23 |
| 10 | 22 | 23 | BIT22 | BIT23 |

> 说明：失败位索引 = 该位 `END_TIMEOUT`（总线卡高）。PULLUP 模式稳定卡在 **bit 22**；
> INPUT 模式卡在 **bit 22–24**（多数 23）。与上一轮（PULLUP≈21、INPUT≈23）属同一故障区。

## 10. 本轮每次失败位索引

见上表：PULLUP 恒为 BIT22；INPUT 为 BIT22–BIT24。

## 11. 完整 40 位次数

**0**（20 个 Trace 均未能完成 40 位）。

## 12. 校验和通过次数

**0**（无完整帧，无法校验）。

## 13. 标准库有效读取次数

**0 / 24**（`dht test` ×2，每次 12 读，全部 `bit-end-timeout`）。
- Run1：`DHT_TEST_FAIL valid=0/12`
- Run2：`DHT_TEST_FAIL valid=0/12`

## 14. NaN 次数

**0**（所有失败均为 `bit-end-timeout`，未产生 NaN 数值；无“偶然成功”假象）。

## 15. 温湿度统计

无有效读数，温湿度统计不适用（N/A）。

## 16. 是否发生重启

**未发生异常重启 / 看门狗复位。**
- `status`（测试前）：`uptime_ms=104707 free_heap=51296`
- `status`（测试后）：`uptime_ms=314714 free_heap=51296`
- uptime 单调递增（≈+210s，与测试时长吻合），free_heap 前后一致（51296）；
  捕获日志中**无第二次 `APP_BOOT_OK` 启动横幅**，证明全程无复位。

## 17. 新旧结果逐项对比（A/B）

| 指标 | 上一轮（原杜邦线, t1000） | 本轮（短杜邦线） | 变化 |
|------|--------------------------|------------------|------|
| 总线空闲高 | 50/50 HIGH | 50/50 HIGH | 无 |
| PULLUP 响应低 | 67µs | 65–72µs（≈69） | 无 |
| PULLUP 响应高 | 87µs | 87–89µs（≈88） | 无 |
| PULLUP 失败位 | BIT21 | BIT22 | 无（同区） |
| INPUT 响应低 | 73µs | 72–76µs（≈74） | 无 |
| INPUT 响应高 | 88µs | 88µs | 无 |
| INPUT 失败位 | BIT23 | BIT23–24 | 无（同区） |
| Byte0/1 脉宽分布 | 24µs‘0’ / 70µs‘1’ | 24µs‘0’ / 70µs‘1’ | 无 |
| 完整 40 位次数 | 0 | 0 | 无 |
| 校验和通过 | 0 | 0 | 无 |
| 标准库有效读取 | 0/12 | 0/24 | 无 |
| 是否重启 | 否 | 否 | 无 |

**对比标志：`DHT_WIRE_CHANGE_COMPARISON=NO_CHANGE`**
**`DHT_FAILURE_PATTERN_MATCHES_PREVIOUS=YES`**

## 18. 最终结论

更换三根更短的杜邦线后，DHT11 故障特征**完全不变**：
- 前 ~22 位仍以教科书级 24µs/70µs 脉宽正常解码（证明 MCU 时序、起始信号、
  响应、解码算法均正确）；
- 随后总线在**完全相同的 bit 22 附近**被上拉硬拉高 >1000µs，DHT 不再拉低；
- INPUT_PULLUP 与 native INPUT 在**相同位置**卡高；
- 标准库读取成功率仍为 **0%**。

> 决定性推论：**杜邦线长度 / 接触不良 / 线阻 / 寄生电容 / 某根线异常均不是根因。**
> 若线材是主因，缩短线后应观察到失败位后移、卡高时间变化或成功率提升——
> 实际上三项指标纹丝不动。

剩余高概率根因（按用户情况 D 清单）：
1. **DHT11 模块本体缺陷**（内部 MCU/传感器在发送长帧中途失电或锁死）；
2. **模块 PCB 焊点 / 内部走线问题**；
3. **模块板载上拉电阻参数或焊接异常**；
4. **3.3V 供电完整性**（NodeMCU 板载 AMS1117 与 ESP8266+CH9102 共载、噪声大、
   长帧中段跌落）；
5. **模块去耦缺失/不良**（无/劣质 VCC-GND 旁路电容）。

## 19. 是否还有合理的软件修复空间

**NO。**
已在前序诊断中穷尽所有纯软件变量（R1 时序余量 → R2 INPUT_PULLUP →
R3 IR 懒初始化 → R4 noInterrupts 关键段 → R5 超时 250→1000µs），且本轮
严格 A/B 证明换线无效。当前故障与软件/固件参数无关，继续改码无意义。
依据用户判定规则**停止修改固件**。

## 20. 是否仍需要现场硬件处理

**YES。** 必须在现场（或委托他人）进行以下一项或多项：

1. **增加 100nF 陶瓷去耦电容**：DHT11 模块 VCC-GND 就近并联（最优先、最易试）；
2. **检查/更换板载上拉**：确认模块 DATA 上拉电阻焊接与阻值正常；
3. **更换 DHT11 模块**：排除模块本体缺陷（最直接的排除手段）；
4. **检查焊点**：模块与杜邦头焊点、PCB 铜箔；
5. **测量 3.3V 供电**：用万用表在 DHT11 VCC-GND 处测电压，重点看长帧中段
   是否被拉低（建议独立干净 3.3V LDO 单独供 DHT）。

---

## 判定汇总（用户格式）

```
DHT_SHORT_WIRE_RESULT=NO_CHANGE
DHT_FAILURE_PATTERN_MATCHES_PREVIOUS=YES
DHT_TEST_FAIL_HARDWARE_INSPECTION_REQUIRED
```

- 原始握手成功次数：10/10（响应脉冲正常，但均不能完成 40 位）
- 完整 40 位次数：0
- 校验和通过次数：0
- 标准库有效读取：0/24
- NaN 次数：0
- 温度范围：N/A（无有效读数）
- 湿度范围：N/A
- 是否发生异常重启：NO
- 与上一轮相比：NO_CHANGE
- 是否仍在约第 22 位附近失败：YES
- 短杜邦线是否解决问题：NO
- 最终根因判断：非杜邦线问题；为 DHT11 模块本体 / 板载上拉 / 3.3V 供电完整性 /
  模块去耦相关的硬件电气故障。
- 是否还有合理的软件修复空间：NO
- 是否仍需现场硬件处理：YES

## 证据文件

- `logs/hardware_integration/dht_short_wires_build.log` — 编译（未改码，BUILD_DONE_EXIT=0）
- `logs/hardware_integration/dht_short_wires_upload.log` — 烧录（FLASH_EXIT=0，hash 校验）
- `logs/hardware_integration/dht_short_wires_raw_timing.log` — 10 次 raw trace（含 status_before）
- `logs/hardware_integration/dht_short_wires_library.log` — 2 次 dht test + status_after
- 对照基准：`logs/hardware_integration/dht_debug_t1000.log`、`dht_test_noint.log`
