[简体中文](./docs/中文/更新日志.md) | [English](./docs/English/changelog.md)

# 更新日志 / Changelog

## [1.2.0] - 2026-08-01

Monorepo 统一整合版 / Canonical monorepo consolidation release.

- **唯一正式 Monorepo 确立**：firmware / cloud / hardware / tools / docs 全部收口于本仓库；remote-ac-firmware 与 remote-ac-cloud 仅保留为私有归档记录（历史未合入，凭据零泄漏）
- **西电校园网自动认证（正式版）**：authEpoch 认证周期模型 + CampusAuthPolicy 退避/配额/硬阻断 + 编译期 feature-gate 依赖约束（AUTO→LIVE_AUTH→CAMPUS_AUTH→WIFI）；Wi-Fi 掉线 / DHCP 变化 / Portal 重现均可重新认证；30/60/120s 退避阶梯
- **Host Tests**：CampusAuthPolicy / feature gates / auth epoch / campus profiles 纯逻辑单测
- **Cloud 安全整合**：backend_verify.js 凭据仅来自环境变量；拆分仓库含真实 IR 默认值的 config.ts 未迁入（保持 fail-closed）
- **完整中英文双路径**：根 README.md / README.en.md 互链；docs/doc-map.json 24 对一一映射；doc-parity / doc-links / doc-language-links 三套校验
- **统一 CI**：firmware-platformio-public、firmware-arduino-public、firmware-host-tests、cloud-backend-build-test、cloud-frontend-build-test、repository-secret-scan、real-ir-exclusion、doc-parity、doc-links、version-consistency、license-check
- **编码治理**：18 个源文件去除 UTF-8 BOM；CONTROLRED 拼写残留 0；乱码 0
- **版本统一 v1.2.0**：根 VERSION / 固件 / backend / frontend 一致
- 公开构建安全边界不变：无真实凭据、无真实 IR 帧、自动认证关闭

## [1.0.0] - 2026-07-31

首个正式公开发布版本。Initial public release.

- 完整 Monorepo 结构（固件 + 云端 + 前端 + 文档）
- ESP8266 固件 — PlatformIO 自动化模式与 Arduino IDE 模式
- Cloud 后端（Fastify + MQTT 桥接）与前端（Vue 3 响应式 UI）
- 红外学习工具（源码 + Windows x64 EXE）
- PCB 源文件（EasyEDA Pro）与制造资料（Gerber / 钻孔 / BOM）
- 11 状态空调红外控制、DHT11 温湿度监测
- 定时调度与双阈值温控自动化
- Owner / Guest 权限模型与受信任设备
- 跨设备自适应网页界面
- MQTT/TLS 加密设备链路
- 中英文完整文档
- Apache License 2.0

> 本仓库不含任何生产凭据、TLS 私钥、真实红外帧、数据库或生产配置。

- [简体中文完整更新日志](./docs/中文/更新日志.md)
- [English Changelog](./docs/English/changelog.md)
