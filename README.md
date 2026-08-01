<p align="center">
  <a href="#项目简介">项目简介</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="./docs/中文/文档导航.md">文档</a> ·
  <a href="./README.en.md">English</a>
</p>

<p align="center">
  <img src="./docs/assets/logo.svg" alt="Remote AC Controller" width="240" />
</p>

<h1 align="center">Remote AC Controller</h1>
<p align="center">用 ESP8266、红外模块和网页，把普通空调接入手机远程控制。</p>

<p align="center">
  <a href="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml"><img src="https://github.com/nobodycareme/remote-ac-controller/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/nobodycareme/remote-ac-controller/releases"><img src="https://img.shields.io/github/v/release/nobodycareme/remote-ac-controller" alt="Latest Release" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
</p>

---

## 项目简介

Remote AC Controller 是一个基于 ESP8266 的空调远程控制项目。设备通过红外控制空调，并把温湿度和设备状态发送到网页。仓库包含固件、云端、PCB 资料和红外学习工具。

如果你只有一台 NodeMCU 开发板、一个红外发射模块和一个小型温湿度传感器，就可以搭建这套系统；核心红外码由你自己的遥控器学习得到，因此适用于大多数支持红外遥控的空调型号。

项目从日常使用出发设计：网页端可以在手机上直接操作，也可以部署在局域网或公网服务器上；固件端支持多种网络接入方式，方便适配不同的使用环境。

## 界面预览

<p align="center">
  <img src="./docs/assets/screenshots/dashboard-desktop.png" alt="桌面端控制界面" width="820" />
</p>

<p align="center">
  <img src="./docs/assets/screenshots/dashboard-mobile.png" alt="移动端控制界面" width="320" />
</p>

桌面端和移动端使用同一套响应式页面；图中数据为演示数据，仅用于展示界面布局。完整功能说明见[部署指南](./docs/中文/部署指南.md)。

## 主要功能

- 手机网页控制空调开关、模式和常用状态；
- DHT11 温湿度监测；
- 定时任务和温度自动控制；
- ESP8266 通过 MQTT 与云端通信；
- 支持普通 WPA/WPA2 WiFi 和可选 Srun 校园网认证；
- 红外学习工具用于采集用户自己的遥控器数据。

整个系统可以按需拆开使用：只在家里用手机控制空调，可以只部署固件；想远程访问，再部署云端服务；想自己做 PCB，可以参考 `hardware/` 下的制造资料。各部分之间通过明确的 MQTT 消息协议协作，单独替换某一端不会影响其他部分。

## 快速开始

| 目标 | 从这里开始 |
|---|---|
| 普通家庭或实验室 WiFi | [首次配置指南](./docs/中文/首次配置.md) |
| 西电校园网 | [西电校园网自动认证](./docs/中文/西电校园网自动认证.md) |
| 编译 ESP8266 固件 | [PlatformIO 固件指南](./firmware/agent-platformio/README.md) |
| 使用 Arduino IDE | [Arduino IDE 使用指南](./docs/中文/Arduino-IDE使用指南.md) |
| 部署自己的服务器 | [部署指南](./docs/中文/部署指南.md) |
| 学习自己的遥控器 | [红外学习指南](./docs/中文/红外学习.md) |
| 制造 PCB | [PCB 说明](./hardware/pcb/README.md) |

一个最小公开构建示例：

```powershell
cd firmware/agent-platformio
./tools/dev.ps1 build -Profile public
```

这是无凭据公开构建，不是完全离线构建：固件仍会编译 WiFi 和云端模块，只是不包含真实凭据，默认也不会在开机时自动连接网络。

想了解如何为普通家庭路由器或西电校园网准备本地凭据、如何烧录固件，请从上面的[首次配置指南](./docs/中文/首次配置.md)开始。如果只是想先编译一次验证环境可用，执行上面的命令即可，不需要创建任何凭据文件。

关于每种配置方式对应的编译开关和命令行参数，文档中都有对应的说明；遇到问题也可以先查看[故障排查](./docs/中文/故障排查.md)。

## 系统组成

```
手机网页 → 云端 → MQTT → ESP8266 → 红外 → 空调
```

服务端使用 Fastify，前端使用 Vue 3，设备端为 NodeMCU ESP8266。

项目按目录组织：`firmware/` 是 ESP8266 固件（PlatformIO 与 Arduino IDE 两种使用方式），`cloud/` 是云端后端与网页前端，`hardware/` 是 PCB 资料，`tools/` 是红外学习工具与辅助脚本。各部分独立维护，接口通过 MQTT 消息协议衔接，详细约定见 [MQTT 协议](./docs/中文/MQTT协议.md)。

如果你只想快速体验网页控制，也可以先用模拟设备或仅运行云端部分；固件、云端和前端各自独立，方便按需启动。固件内部支持多种网络接入方式，配置方法见对应的[首次配置指南](./docs/中文/首次配置.md)。

## 硬件

- 开发板：NodeMCU ESP8266
- 温湿度：DHT11
- 红外模块：ZJ-IR-V2
- PCB：Rev 1.0.1

这些是项目开发和验证时使用的硬件组合，并非唯一选择——ESP8266 系列开发板配合支持红外发射的模块即可运行固件，接线方式可参考 `hardware/` 目录下的文档。

公开仓库不提供真实空调红外码，也未提供经过验证的 BOM 和贴片坐标文件。你可以用[红外学习工具](./docs/中文/红外学习.md)从自己的遥控器上采集红外数据，再按[首次配置指南](./docs/中文/首次配置.md)烧录进设备。

## 文档

| 了解项目 | 使用与配置 | 维护与排障 |
|---|---|---|
| [系统架构](./docs/中文/系统架构.md) | [首次配置指南](./docs/中文/首次配置.md) | [运维指南](./docs/中文/运维指南.md) |
| [安全模型](./docs/中文/安全模型.md) | [Arduino IDE 使用指南](./docs/中文/Arduino-IDE使用指南.md) | [故障排查](./docs/中文/故障排查.md) |
| [MQTT 协议](./docs/中文/MQTT协议.md) | [部署指南](./docs/中文/部署指南.md) | [备份与恢复](./docs/中文/备份与恢复.md) |
| [更新日志](./docs/中文/更新日志.md) | [红外学习](./docs/中文/红外学习.md) | [安全策略](./docs/中文/安全策略.md) |

英文文档见 [English documentation index](./docs/English/documentation-index.md)。

所有文档都提供中英文两种版本，并保持相同的目录结构，方便切换语言对照阅读。如果某个主题在表格中没有列出来，可以在[文档导航](./docs/中文/文档导航.md)里按目录查找。

## 参与贡献与支持

欢迎提交 Issue 和 Pull Request，请先阅读[贡献指南](./docs/中文/参与贡献.md)。如果你在使用中发现了问题，欢迎在 [Issues](https://github.com/nobodycareme/remote-ac-controller/issues) 中描述现象和环境信息，这样能帮助维护者更快定位。安全漏洞请通过 GitHub 的 Private Vulnerability Reporting 报告，见[安全策略](./docs/中文/安全策略.md)。使用问题请先查阅[文档导航](./docs/中文/文档导航.md)，或在 Issues 中提问。

项目使用 [Apache License 2.0](./LICENSE) 许可，第三方组件许可见[第三方组件许可声明](./docs/中文/第三方许可说明.md)。所有代码与文档均在本仓库内维护，发布说明见[更新日志](./docs/中文/更新日志.md)与 [GitHub Releases](https://github.com/nobodycareme/remote-ac-controller/releases)。

项目仍在持续维护，功能与文档会不定期更新，欢迎关注。
