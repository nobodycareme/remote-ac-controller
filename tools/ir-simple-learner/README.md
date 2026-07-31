**简体中文** | [English](./README.en.md)

# IR Simple Learner — 红外简易学习工具

通过 CH9102 USB 转串口适配器连接 ESP8266 NodeMCU（搭载 ZJ-IR-V2 红外学习模块），从空调遥控器采集红外信号的 Windows 简易 GUI 工具。

---

## 用途

本工具通过串口与 ESP8266 固件（公开 Profile）通信，学习空调遥控器发出的红外帧。采集到的帧经过验证、比对和保存，用于集成到 remote-ac-controller 固件中。

**本工具不包含任何真实空调红外帧或生产凭据。** 所有随附的测试向量均为合成数据。

## 系统要求

- **操作系统**：Windows 10/11 (x64)
- **Python**：3.9 或更高版本
- **硬件**：ESP8266 NodeMCU（CH9102 USB 芯片）+ ZJ-IR-V2 红外学习模块
- **驱动**：CH9102 驱动（[WCH 官方下载](https://www.wch.cn/downloads/CH341SER_EXE.html)）

## 快速开始（预编译 EXE）

1. 从 [Releases](https://github.com/nobodycareme/remote-ac-controller/releases) 页面下载 `IR_Simple_Learner_v4_windows_x64.exe`。
2. Windows 可能显示 SmartScreen 警告（因 EXE **未签名**）。点击"更多信息"→"仍要运行"。
3. 通过 USB 连接 ESP8266 NodeMCU。
4. 运行 EXE 并按屏幕提示操作。

### SHA256 校验

使用公布的 SHA256 哈希值校验下载的 EXE：

```powershell
Get-FileHash IR_Simple_Learner_v4_windows_x64.exe -Algorithm SHA256
```

预期哈希值在每个 GitHub Release 中公布。

## 从源码安装

```powershell
cd tools/ir-simple-learner

# 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行工具
python src/simple_ir_learner.py
```

### 运行单元测试

```powershell
python -m unittest discover -s src/tests -p "test_*.py" -v
```

## 构建 EXE

```powershell
pwsh tools/ir-simple-learner/build.ps1
```

EXE 将写入 `tools/ir-simple-learner/dist/`。
使用 `-Clean` 参数从头重建：

```powershell
pwsh tools/ir-simple-learner/build.ps1 -Clean
```

## 使用方法

### 1. 连接设备

通过 USB 将 ESP8266 NodeMCU 连接到电脑。CH9102 驱动通常自动安装；如未安装，请从 [WCH 官网](https://www.wch.cn/downloads/CH341SER_EXE.html) 下载。

### 2. 启动工具

运行 EXE 或 `python src/simple_ir_learner.py`。主窗口包含三个区域：

- **设备连接**（顶部）：扫描端口、连接/断开、状态指示灯。
- **空调状态**（左侧）：预设选择器、模式、温度、风速、附加选项。
- **采集**（右侧）：采集按钮（1-3）、比对、选定标准帧。

### 3. 采集流程

1. 点击 **Scan Ports** 查找 CH9102 设备。
2. 选择端口并点击 **Connect**。
3. 从预设下拉菜单中选择空调状态，或手动填写参数。
4. 点击 **Capture 1**。当状态显示"please press remote"时，按一次遥控器按钮。
5. 等待采集完成（日志中显示 SHA256 和字节数）。
6. 重复 **Capture 2** 和 **Capture 3**。
7. 点击 **Compare All** 查看三次采集的字节级差异。
8. 选择标准帧（1、2 或 3）并点击 **Select Canonical**。

### 4. 保存位置

采集数据保存到用户可配置的目录（默认：`~/IR_Learned/`）。在工具中点击 **Set Save Directory** 更改。

## CH9102 驱动说明

本项目使用的 ESP8266 NodeMCU 采用 **CH9102** USB 转串口芯片（VID 0x1A86，PID 0x55D4）。Windows 可能不会自动安装驱动。

- 下载：[WCH CH341SER 驱动包](https://www.wch.cn/downloads/CH341SER_EXE.html)
- 安装后，设备应在设备管理器中显示为 COM 端口。

## 安全说明

- **EXE 未签名。** 这是预期行为。Windows SmartScreen 会显示警告。请通过公布的 SHA256 哈希值校验。
- **无生产凭据、WiFi 密码或真实红外码**嵌入在工具或其源代码中。
- 仓库中的所有测试数据（包括 `presets.py`）仅包含配置元数据，不包含实际红外帧载荷。
- 采集的红外数据保存在本地，本工具不会将其传输到任何地方。

安全相关问题请通过 [SECURITY.md](../../SECURITY.md) 报告。

## 许可

本工具是 remote-ac-controller 项目的一部分，采用 Apache License, Version 2.0 许可。完整文本见 [LICENSE](../../LICENSE)。

第三方组件许可列于 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。

## 相关文档

- [固件 README](../../firmware/README.md) — ESP8266 固件构建与烧录
- [项目 README](../../README.md) — 完整项目概览