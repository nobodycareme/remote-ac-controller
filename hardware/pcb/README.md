**简体中文** | [English](./README.en.md)

# PCB 设计文档（Rev 1.0.1）

## 概述

本 PCB 专为**手机远程控制空调（Remote AC Controller）**项目设计，配套固件运行在 **NodeMCU ESP8266 开发板**上。PCB 提供红外发射/接收模块与温湿度传感器的接口与外围电路，用于实现空调的红外遥控与本地数据采集。

本仓库公开的是 PCB 制造文件与 EasyEDA 工程源，**不包含**物料清单（BOM）、坐标文件或 pick-and-place 文件——需要自行整理后用于装配。

## 设计软件与版本

- **EasyEDA Pro**（专业版）
- 工程文件：`source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2`
- 逻辑修订：**Rev 1.0.1**（`hardware/pcb/REVISION`）

> **版本区分**：软件发布版本（v1.2.1）与 PCB 设计修订（Rev 1.0.1）相互独立；PCB 丝印标记仍为 v1.0，但不影响 Rev 1.0.1 为当前唯一有效制造数据。

> **工程源声明**：仓库包含 EasyEDA Pro 工程容器文件；其完整可编辑性和器件型号信息尚未独立验证。制造请以已校验的 Gerber、钻孔文件和制造清单为准。

## 层数与制造文件

**2 层板**，制造文件位于 `fabrication/gerber/`、`fabrication/drill/` 与 `fabrication/test/`：

| 文件 | 说明 |
|------|------|
| `Gerber_TopLayer.GTL` | 顶层铜皮 |
| `Gerber_BottomLayer.GBL` | 底层铜皮 |
| `Gerber_TopSilkscreenLayer.GTO` | 顶层丝印 |
| `Gerber_BottomSilkscreenLayer.GBO` | 底层丝印 |
| `Gerber_TopSolderMaskLayer.GTS` | 顶层阻焊 |
| `Gerber_BottomSolderMaskLayer.GBS` | 底层阻焊 |
| `Gerber_BoardOutlineLayer.GKO` | 板框（外形层） |
| `Gerber_DrillDrawingLayer.GDD` | 钻孔图层 |
| `Drill_PTH_Through.DRL` | 通孔钻孔文件 |
| `Drill_PTH_Through_Via.DRL` | 过孔钻孔文件 |
| `FlyingProbeTesting.json` | 飞针测试数据（`fabrication/test/`） |
| `manufacturing-manifest.md` | 制造清单（含包内文件哈希） |

制造包内容合同见 `fabrication/manufacturing-manifest.md`。

## 打样制造注意事项

1. **Gerber 格式**：标准 RS-274X（EasyEDA Pro 导出），制造前请在嘉立创下单页确认 Gerber 预览。
2. **钻孔文件**：单独提供 Excellon 格式 `.DRL` 钻孔文件，请核对钻孔尺寸与数量。
3. **板框**：外形由 `Gerber_BoardOutlineLayer.GKO` 定义，提交时请确认板框闭合。
4. **DRC**：制板前请执行设计规则检查，确保满足制造商工艺要求。
5. **Rev 1.0 制造文件已取代**：不得使用 Rev 1.0 的 Gerber/钻孔文件制板，请使用本 Rev 1.0.1 数据。

## 许可协议

本项目 PCB 设计文件采用 [Apache License 2.0](../../LICENSE) 许可。

## 风险提示

> **注意**：本 PCB 为开源硬件设计，仅供学习和研究使用；开源设计需要使用者自行完成适用性验证。
>
> - 上电前请检查电源极性与焊接短路。
> - 红外 LED 驱动应使用正确的限流电阻，避免烧毁元件。
> - 制造前请检查 Gerber 预览与钻孔文件。
> - Rev 1.0 制造文件已经被取代，不得继续使用。
> - 作者不对因使用此设计而造成的任何直接或间接损失承担责任。
