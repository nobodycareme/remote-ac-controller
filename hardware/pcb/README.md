**简体中文** | [English](./README.en.md)

# PCB 设计文档

## 概述

本 PCB 专为**手机远程控制空调（Remote AC Controller）**项目设计，集成了 ESP32 微控制器、红外发射与接收模块、温湿度传感器以及电源管理电路，用于实现空调的红外遥控与云端数据采集。

## 设计软件

- **EasyEDA Pro**（专业版）
- 工程文件：`source/Remote_AC_Controller_PCB_v1.0.eprj2`

## 层数

- **2 层板**（双层 PCB）
- 顶层（TopLayer）：`Gerber_TopLayer.GTL`
- 底层（BottomLayer）：`Gerber_BottomLayer.GBL`

## 板级规格

| 项目 | 说明 |
|------|------|
| 层数 | 2 层 |
| 板厚 | 1.6mm（标准） |
| 铜厚 | 1oz（35μm） |
| 表面处理 | HASL 有铅 / 无铅（按需选择） |
| 最小线宽/线距 | 6mil / 6mil（推荐） |
| 最小孔径 | 0.3mm |
| 阻焊颜色 | 绿色（默认） |
| 丝印颜色 | 白色 |
| 板材 | FR-4 TG130-140 |

## Gerber 文件列表

所有制造文件位于 `fabrication/gerber/` 和 `fabrication/drill/` 目录：

| 文件名 | 说明 |
|--------|------|
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

## 打样制造注意事项

1. **Gerber 格式**：使用 EasyEDA Pro 导出的标准 RS-274X 格式 Gerber 文件。
2. **钻孔文件**：提供单独的 Excellon 格式钻孔文件（`.DRL`）。
3. **板框**：外形由 `Gerber_BoardOutlineLayer.GKO` 定义，请在提交时确认板框闭合。
4. **阻焊开窗**：阻焊层定义了焊盘和过孔的开窗区域，请按标准工艺处理。
5. **丝印**：顶层丝印包含元件标识和说明文字。

## JLCPCB 下单指引

1. 登录 [jlcpcb.com](https://jlcpcb.com)，选择「在线下单」。
2. 上传 `fabrication/gerber/` 目录下所有 `.GTL`、`.GBL`、`.GTO`、`.GBO`、`.GTS`、`.GBS`、`.GKO`、`.GDD` 文件。
3. 上传 `fabrication/drill/` 目录下的 `.DRL` 钻孔文件。
4. **推荐配置**：
   - 层数：2 Layers
   - 板厚：1.6mm
   - 铜厚：1oz
   - 阻焊颜色：绿色
   - 表面处理：HASL（有铅）或 LeadFree HASL（无铅）
   - 板子数量：5 片（最低起订量）
5. 确认 Gerber 预览无误后下单。

## 许可协议

本项目 PCB 设计文件采用 [Apache License 2.0](../../LICENSE) 许可。

## 风险提示

> **注意**：本 PCB 为开源硬件设计，仅供学习和研究使用。使用者应自行验证设计的完整性和正确性。
>
> - 电路可能包含高压或大电流部分，请确保在通电前仔细检查焊接质量和短路情况。
> - 红外发射模块涉及红外 LED 驱动，请确认限流电阻配置正确，避免烧毁元件。
> - ESP32 模块的供电电路需要稳定 3.3V 输出，请使用合格的稳压器。
> - 制板前请务必进行 DRC（设计规则检查），确保设计满足制造商工艺要求。
> - 作者不对因使用此设计而造成的任何直接或间接损失承担责任。
