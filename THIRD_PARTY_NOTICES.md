**简体中文** | [English](./THIRD_PARTY_NOTICES_EN.md)

# 第三方许可声明

本文件汇总 Remote AC Controller 项目所用第三方组件的许可信息。项目本身采用 **Apache License, Version 2.0** 授权；第三方组件按下列说明保留各自的许可。本清单是开源发布审查的一部分；在再分发前，请依据各子系统的依赖清单（`firmware/platformio.ini`、`cloud/backend/package.json`、`cloud/frontend/package.json`）核对确切版本。

## 固件（PlatformIO / Arduino）

| 组件 | 作用 | 许可 |
|------|------|------|
| ArduinoJson | JSON 序列化 / 反序列化 | MIT |
| Adafruit Unified Sensor | 传感器抽象层 | BSD-3-Clause |
| DHT sensor library（Adafruit） | DHT11/DHT22 读取 | MIT |
| ESP8266 Arduino Core / PlatformIO espressif8266 | MCU 平台 | LGPL-2.1 / 多种许可 |
| BearSSL（ESP8266） | TLS | BSD-3-Clause（来自 ESP8266 core） |
| 用于学习/发射的红外库 | 红外编解码 | 以各库为准（常见为 MIT / GPL） |

> 维护者必须在发布红外相关代码前，确认具体红外库的许可（MIT 还是 GPL）；默认开源构建**不得静态依赖** GPL 组件。

## 云端后端（Node.js）

| 组件 | 作用 | 许可 |
|------|------|------|
| Fastify | HTTP 服务 | MIT |
| MQTT.js | MQTT 客户端 | MIT |
| node:sqlite（Node 22+） | 嵌入式数据库 | MIT（Node.js） |
| Vitest | 测试 | MIT |
| TypeScript | 语言 / 类型检查 | Apache-2.0 |
| Vue 3 | 前端框架 | MIT |
| Vite | 前端构建 | MIT |

## 前端（Vue 3）

| 组件 | 作用 | 许可 |
|------|------|------|
| Vue 3 | UI 框架 | MIT |
| TypeScript | 语言 | Apache-2.0 |
| Vite | 打包器 | MIT |
| ECharts（若打包） | 图表 | Apache-2.0 / BSD |
| 各类 UI / 工具库 | UI 基础组件 | MIT（以各依赖为准） |

## 资源文件

- 仓库内包含的图标、SVG、字体与图片必须带有各自的许可，或为原创。任何许可不明确的资源都**不纳入**公开发布。
- `CODE_OF_CONDUCT.md` 中的 Contributor Covenant 文本以 **CC-BY-4.0** 授权。

## 说明

- 本仓库中的任何第三方组件都**不会**被重新声称为 Apache-2.0 原创作品；每个组件保留其声明的许可。
- 若某个依赖的许可与开源分发目标不兼容（例如带有静态链接影响的 GPL），必须在发布前移除或替换。
