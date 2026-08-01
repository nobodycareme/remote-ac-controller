**简体中文** | [English](./README.en.md)

<p align="center">
  <img src="./docs/assets/logo.svg" alt="Remote AC Controller" width="240" />
</p>

<h1 align="center">Remote AC Controller</h1>
<p align="center"><strong>手机远程控制空调 — 全栈开源方案</strong></p>

<p align="center">
  <a href="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml"><img src="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License" /></a>
  <a href="https://github.com/nobodycareme/remote-ac-controller/releases"><img src="https://img.shields.io/github/v/release/nobodycareme/remote-ac-controller?include_prereleases" alt="Latest Release" /></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/PlatformIO-ESP8266-orange" alt="PlatformIO" /></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Arduino-IDE-00979D" alt="Arduino IDE" /></a>
</p>

<p align="center">
  <a href="#quick-start">快速开始</a> ·
  <a href="./docs/中文/文档导航.md">中文文档</a> ·
  <a href="./docs/English/README.md">English</a> ·
  <a href="#hardware">硬件</a> ·
  <a href="#documentation">文档</a>
</p>

---

一套完整的开源远程空调控制系统：手机网页 → 云端后端 → MQTT（TLS）→ ESP8266 → 红外 → 空调。固件、云端、前端、PCB 与红外学习工具全部开源，可自行部署、扩展与二次开发。

---

## 核心功能

- **响应式远程控制网页** — Vue 3 单页应用，桌面与手机均可使用。
- **11 组已注册空调状态元数据** — 覆盖关机、制冷、除湿、制热及常用温度/风速/摆风组合，每组可独立启用。公开仓库不包含任何真实空调红外帧，请使用[红外学习工具](#红外学习工具)采集你自己的遥控器数据。
- **温湿度监测** — DHT11 传感器（GPIO5）。
- **定时与温控自动化** — 按星期掩码的周期调度；温控采用滞回算法避免频繁启停。
- **双角色访问模型** — Owner / Guest 与受信任设备，会话持久。
- **可选校园网自动认证** — 针对使用 Srun 的校园网，可配置上电后自动完成 Portal 认证（默认关闭，见[可选校园网认证](#可选校园网认证)）。

## 仓库包含内容

| 目录 | 内容 |
|---|---|
| `firmware/` | ESP8266 固件：`agent-platformio/`（PlatformIO / command-line workflow）与 `arduino-ide/`（Arduino IDE workflow），共享同一业务核心 `shared/RemoteACCore/` |
| `cloud/` | 云端：`backend/`（Fastify + MQTT 桥接）、`frontend/`（Vue 3 Web UI）、`broker/`、`deploy/` |
| `hardware/` | PCB 设计与制造文件（Rev 1.0.1）、接线说明 |
| `tools/` | 红外学习工具、发布与校验脚本 |
| `docs/` | 完整中英文文档（见[文档](#documentation)） |

## 快速开始

### 1. 编译 ESP8266 固件（PlatformIO）

```powershell
cd firmware/agent-platformio
pwsh ./tools/dev.ps1 test -Profile public
pwsh ./tools/dev.ps1 verify -Profile public
pwsh ./tools/dev.ps1 build -Profile public
```

详细说明：[`firmware/agent-platformio/README.md`](./firmware/agent-platformio/README.md)

### 2. Arduino IDE workflow

用 Arduino IDE 打开 `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino`，按 sketch 内 README 完成一次性配置后编译上传。

详细指南：[Arduino IDE 使用指南](./docs/中文/Arduino-IDE使用指南.md)

### 3. 部署 Backend 和 Frontend

```bash
cd cloud/backend && npm ci && npm test
cd cloud/frontend && npm ci && npm test && npm run build
```

完整流程（含 MQTT Broker 与 Nginx）：[部署指南](./docs/中文/部署指南.md)

### 4. 制造 PCB

使用 `hardware/pcb/fabrication/` 下的 Gerber、钻孔与飞针测试文件下单制造。制造包内容合同与逐文件校验见 [manufacturing-manifest](./hardware/pcb/fabrication/manufacturing-manifest.md)。**注意：Rev 1.0 制造文件已被取代，请勿使用。**

### 5. 使用红外学习工具

采集你自己的空调遥控器红外帧：[红外学习](./docs/中文/红外学习.md)（工具位于 [`tools/ir-simple-learner/`](./tools/ir-simple-learner/)）

### 6. 配置可选 Srun 校园网认证

针对使用 Srun 的校园网（如西电）：[西电校园网自动认证](./docs/中文/西电校园网自动认证.md) 与 [Srun 校园网移植指南](./docs/中文/Srun校园网移植指南.md)

## 简化架构

```mermaid
graph LR
    A[手机 / 桌面浏览器] -->|HTTPS| B[云端后端]
    B -->|MQTT over TLS| C[MQTT Broker]
    C -->|MQTT over TLS| D[ESP8266]
    D -->|红外| E[空调]
    B --> F[(SQLite)]
```

## 硬件

- 开发板：**NodeMCU ESP8266 开发板**
- 温湿度：DHT11（GPIO5）
- 红外模块：ZJ-IR-V2（GPIO12 TX / GPIO14 RX）
- PCB：Rev 1.0.1（[PCB 文档](./hardware/pcb/README.md)，接线见[接线说明](./docs/中文/接线说明.md)）

## 可选校园网认证

针对使用 Srun 协议的校园网（例如西电），固件可在配置后于上电时自动完成 Portal 认证并在断线后自动恢复连接。该功能默认关闭；公开构建不含任何凭据。详见[西电校园网自动认证](./docs/中文/西电校园网自动认证.md)。

## 文档

完整中英文文档位于 [`docs/`](./docs)，索引见[中文文档导航](./docs/中文/文档导航.md)（英文文档在 `docs/English/` 下，成对对应）。

| 快速上手 | 理解项目 | 运维与排障 |
|---|---|---|
| [硬件说明](./docs/中文/硬件说明.md) · [接线说明](./docs/中文/接线说明.md) | [系统架构](./docs/中文/系统架构.md) · [安全模型](./docs/中文/安全模型.md) | [部署指南](./docs/中文/部署指南.md) · [运维指南](./docs/中文/运维指南.md) |
| [Arduino-IDE使用指南](./docs/中文/Arduino-IDE使用指南.md) | [MQTT 协议](./docs/中文/MQTT协议.md) · [定时任务](./docs/中文/定时任务.md) | [故障排查](./docs/中文/故障排查.md) · [备份与恢复](./docs/中文/备份与恢复.md) |
| [红外学习](./docs/中文/红外学习.md) | [温度自动控制](./docs/中文/温度自动控制.md) | [安全策略](./docs/中文/安全策略.md) · [支持说明](./docs/中文/支持说明.md) |

## Development and testing

```powershell
# 全量校验
./tools/test-all.ps1
./tools/build-all.ps1

# 文档一致性（中英对等、链接、禁用措辞）
python tools/check-doc-parity.py
python tools/check-doc-links.py
python tools/check-doc-language-links.py
python tools/check-public-docs.py

# 版本与发布完整性
python tools/check-version.py
python tools/check-pcb-release.py
```

参与开发请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 参与贡献

欢迎提交 Issue 与 Pull Request。请先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md) 与[参与贡献指南](./docs/中文/参与贡献.md)。

## 支持与安全

- 使用与配置问题：先查[文档导航](./docs/中文/文档导航.md)，再开 [Issue](https://github.com/nobodycareme/remote-ac-controller/issues)。
- 安全漏洞：请使用 GitHub Private Vulnerability Reporting，不要公开提交（[SECURITY.md](./SECURITY.md)）。

## 许可协议

本项目采用 [Apache License 2.0](./LICENSE) 许可。第三方组件许可见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。

## Repository 说明

本仓库是此项目**唯一正式仓库**，firmware、cloud、hardware、tools 与 docs 全部在此维护。
