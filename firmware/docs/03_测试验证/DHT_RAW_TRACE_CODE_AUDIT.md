# 旧自定义读取器 (dht_service.cpp / rawTrace) 代码审计

> 审计目标：判断上一轮“总线在 bit~21-23 卡高”的底层诊断能否作为**单一硬件故障证明**
> 依据：用户第⑨节列出的 10 项硬性否决条件 + 额外代码缺陷清单
> 文件：`src/dht_service.cpp`、`src/dht_service.h`
> 结论：**解码逻辑本身没有数组越界，但 `rawTrace()` 在 `noInterrupts()` 临界区内调用 `Serial.print`，违反否决条件，导致该诊断不能作为干净、独立的硬件证据。**

---

## 一、数据结构与索引审查（是否满足“干净读取”）

### A. 40-bit 解码数组
`read()` 与 `rawTrace()` 均使用 `uint8_t data[5] = {0};`，循环 `for (uint8_t i = 0; i < 40; i++)`，位落点：
```cpp
data[i / 8] |= (bit & 0x01) << (7 - (i % 8));
```
- `i` 范围 0..39 → `i/8` 范围 0..4，正好覆盖 `data[5]` 全部下标。✅ 无越界。
- `7 - (i % 8)` 范围 7..0，MSB 优先，标准 DHT11 排布。✅ 无索引偏移。

### B. 80 个高低脉冲 vs 40 项
`rawTrace()` 每个数据位只测量**一次 HIGH 脉冲宽度**（`bw = micros() - b0`），用 `(bw > 40)` 判 0/1。没有分配“80 个过渡”数组，也没有“80 项缓冲只给 40 项”的越界问题。✅ 该项不适用（无此类缺陷）。

### C. 固定日志缓冲越界（“约 22 项后越界”）
`rawTrace()` 的所有输出均走 `Serial.print(...)` **流式打印**，没有固定长度字符缓冲、没有 `sprintf` 到定长数组。**不存在“约 22 项后缓冲区写越界”。** ❗ 重要：上一轮观察到的“bit~21-23 卡高”是**物理超时标记**（`TRACE_PULLUP_BIT21_END_TIMEOUT`），不是打印缓冲越界造成的伪影。

### D. micros() 差值类型
```cpp
const uint32_t t  = micros();
const uint32_t dur = micros() - t;     // uint32_t - uint32_t -> uint32_t
const uint32_t bw = micros() - b0;     // 同上
```
差值类型均为 `uint32_t`，减法在 32 位无符号下回绕安全，无符号/类型错误。✅

### E. 读取前是否主动把 DATA 推高
`read()` 流程：`pinMode(OUTPUT); digitalWrite(LOW); delay(20ms); pinMode(INPUT_PULLUP);`
启动信号结束后是**切换为 INPUT_PULLUP（释放总线、由上拉拉高）**，并非 `digitalWrite(HIGH)` 主动驱动。✅ 正确。

### F. D1 误为 GPIO1
驱动本身不出现 `D1`/`GPIO1` 字面量，引脚来自构造参数 `_pin`。上一轮传入 `DHT_PIN = D2`（宏，=GPIO4）。✅ 无此类错误。

### G. sizeof(pointer) / bit 与 pulse 索引混用
未发现 `sizeof(pointer)` 当数组长度使用；`i` 在 40-bit 循环中始终作为 bit 索引，无 pulse 索引混用。✅

---

## 二、关键缺陷：临界区内调用 Serial（命中否决条件）

`rawTrace()` 结构（节选）：

```cpp
noInterrupts();                       // ① 进入临界区（约 4ms 读取窗口）
...
for (uint8_t i = 0; i < 40; i++) {
    if (!waitPin(HIGH, 1000)) {
        Serial.print(F("TRACE_")); ... Serial.println();   // ② 临界区内打印
        break;
    }
    const uint32_t b0 = micros();
    if (!waitPin(LOW, 1000)) {
        Serial.print(F("TRACE_")); ... Serial.println();   // ② 临界区内打印
        break;
    }
    const uint32_t bw = micros() - b0;
    if (i % 8 == 0) { Serial.print(...); }                  // ② 临界区内打印
    Serial.print(bw); Serial.print(' ');
    if (i % 8 == 7) Serial.println();
    data[i / 8] |= (uint8_t)((bw > 40) ? 1 : 0) << (7 - (i % 8));
}
...
interrupts();                        // ③ 退出临界区
```

**直接命中用户第⑨节否决条件：**
- 第 7 条：“存在在临界区内调用 Serial” —— ✅ **命中**（`Serial.print` 全部发生在 `noInterrupts()` 与 `interrupts()` 之间）。
- 第 8 条：“存在在 noInterrupts 期间执行耗时操作” —— ✅ **命中**（串口格式化 + 阻塞输出是典型的耗时操作，且发生在最敏感的 40-bit 采样窗口内）。

> 影响评估：
> 1. 数值测量（`bw`）在 `Serial.print` **之前**完成，单 bit 宽度本身未被打印污染；
> 2. 但“在临界区内做耗时输出”会改变位与位之间的间隔、引入不可预测的延迟，使整段时序的**外部可比性下降**；
> 3. 更关键的是，这与“自定义读取器必须经严格代码审查才可作为硬件证明”的前提直接冲突——**仅凭此诊断断言‘供电跌落’不满足用户设定的采信门槛**。

---

## 三、其他观察（非否决，但记录）

1. `read()`（实际 0/25 读取走的数据路径）在 `noInterrupts()` 内**不打印**，仅做 `digitalRead` 轮询 + `micros()` 计时，临界区相对干净。但其“0/25 有效”的结论仍来自**自定义驱动**，不是第三方验证库。
2. 注释中（K15）将卡高归因于“背景中断导致 3V3 跌落”。但本轮已在**全新独立固件**上复测：新 XHT11（不同型号、全新模块）在 `noInterrupts()` + 无 IR/Wi-Fi 负载下仍于**同一 bit 位（~21-23）卡高**。这反而说明旧“中断假设”不成立，根因更可能在主机侧电气链路——但**该判断现在由新测试（Adafruit 最小示例）独立验证，不再依赖 rawTrace**。

---

## 四、审计结论（对应第⑨节要求）

| 用户否决条件 | 是否满足（即“是否有此缺陷”） |
|---|---|
| 数组长度小于 40 | 否（data[5] 正确覆盖 40 bit） |
| sizeof(pointer) 代替数组长度 | 否 |
| bit 索引和 pulse 索引混用 | 否 |
| 80 脉冲只分配 40 项 | 不适用（未分配 80 项缓冲） |
| 每位 LOW+HIGH 但循环只预留一项 | 否（每 bit 测一次 HIGH 宽度，逻辑正确） |
| 固定日志缓冲约 22 项后越界 | 否（流式打印，无定长缓冲） |
| **临界区内调用 Serial** | **是（命中）** |
| **noInterrupts 期间执行耗时操作** | **是（命中）** |
| 数组/日志缓存写越界 | 否 |
| 高低电平等待顺序错误 | 否（先等 HIGH 再等 LOW，符合 DHT11） |
| 读取前主动推高 DATA | 否（正确释放为 INPUT_PULLUP） |
| D1 误为 GPIO1 | 否 |

**最终判定**：旧 `rawTrace()` 的解码算法无内存越界错误，但**在 `noInterrupts()` 临界区内执行 `Serial.print`**，命中用户设定的两项否决条件。因此，**上一轮“bit~21-23 卡高”不能作为单一、干净的硬件故障证明**，须由本轮 Adafruit（必要时 DHTStable）独立最小环境重新判定。

---

*本文档为只读代码审查，不修改 `dht_service.cpp`。*
