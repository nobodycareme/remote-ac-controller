# 硬件 / Hardware

- [简体中文：硬件说明](../docs/中文/硬件说明.md) · [接线说明](../docs/中文/接线说明.md)
- [English: Hardware](../docs/English/hardware.md) · [Wiring](../docs/English/wiring.md)

本目录是项目实体侧的入口。**完整硬件文档已统一收敛到 `docs/`**，本文件只做导航与
最小构建摘要。

This directory is the entry point for the physical side of the project. **The full
hardware documentation now lives under `docs/`**; this file only provides
navigation and a minimal build summary.

## 文档导航 / Documentation

| 简体中文 | English | 内容 / Covers |
|---|---|---|
| [硬件说明](../docs/中文/硬件说明.md) | [hardware](../docs/English/hardware.md) | 物料清单、模块选型、GPIO 约束、供电与内存预算 |
| [接线说明](../docs/中文/接线说明.md) | [wiring](../docs/English/wiring.md) | 逐针脚接线、DHT11 与红外模块连接、验证步骤 |
| [红外学习](../docs/中文/红外学习.md) | [ir-learning](../docs/English/ir-learning.md) | 采集并登记你自己空调的红外帧 |
| [故障排查](../docs/中文/故障排查.md) | [troubleshooting](../docs/English/troubleshooting.md) | 传感器、红外与连接故障对照表 |

## 最小构建 / Minimum Build

面包板即可跑通，不需要定制 PCB。A working node can be built on a breadboard; no
custom PCB is required.

| 部件 / Item | 型号 / Part | 说明 / Notes |
|---|---|---|
| 主控 / MCU | NodeMCU v2/v3（ESP8266，ESP-12E/F） | USB 串口芯片通常是 CH340 或 CH9102，需安装对应驱动 |
| 温湿度 / Temp & humidity | DHT11（带上拉的三针模块） | 裸 DHT11 需在 DATA 上外加 4.7 kΩ–10 kΩ 上拉电阻 |
| 红外收发 / IR TX+RX | ZJ-IR-V2 类模块，或分立红外 LED + 驱动三极管 + 38 kHz 接收头 | 接收头只在学习红外码时需要 |
| 供电 / Power | 5 V、≥ 1 A，micro-USB 或 VIN 供电 | 供电不足表现为 Wi-Fi/TLS 不稳定，而不是明显的"没电" |
| 连线 / Wiring | 杜邦线、面包板 | — |

默认引脚分配（取舍理由与需要避开的引脚见接线文档）：
Default pin assignment (rationale and pins to avoid are in the wiring docs):

| 信号 / Signal | NodeMCU 引脚 / Pin | GPIO |
|---|---|---|
| DHT11 DATA | D1 | GPIO5 |
| IR 模块 TXD / IR module TXD | D5 | GPIO14 |
| IR 模块 RXD / IR module RXD | D6 | GPIO12 |

红外模块的 TXD/RXD 相对 MCU 是**交叉**的：模块 TXD → MCU 接收侧，模块 RXD → MCU
发射侧。接反是首次搭建最常见的错误。

The IR module's TXD/RXD are **crossed** relative to the MCU: module TXD goes to
the MCU receive side, module RXD to the MCU transmit side. Getting this backwards
is the most common first-build mistake.

## 未随仓库发布的内容 / Not Published Here

- **无 PCB 源文件 / No PCB sources.** 参考实现为面包板/洞洞板；单节点无需定制板，
  原始布线图不在兼容许可下发布。
- **无外壳模型 / No enclosure models.** 任意小型 ABS 盒即可。保持红外 LED 无遮挡，
  并让 DHT11 处于不受板载稳压器余热影响的气流中。
- **无红外码数据 / No IR code data.** 空调红外帧与机型强相关，不随项目分发，
  请自行采集，流程见[红外学习](../docs/中文/红外学习.md) /
  [ir-learning](../docs/English/ir-learning.md)。

## 安全 / Safety

1. **节点侧全部为低压（3.3 V / 5 V）**，本设计不接触市电。任何涉及市电的改造都超出
   本项目范围，应由有资质的电工完成。
   Everything on the node is low-voltage; nothing in this design connects to mains.
2. **自动化会真实驱动电器。** 真实红外发射默认关闭，并由多重独立开关保护，详见
   [安全模型](../docs/中文/安全模型.md) / [security-model](../docs/English/security-model.md)。
   只有在确认自己采集的红外码无误后再启用，并随手准备好紧急停机流程。
