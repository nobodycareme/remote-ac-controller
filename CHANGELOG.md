[简体中文](./docs/中文/更新日志.md) | [English](./docs/English/changelog.md)

# 更新日志 / Changelog

## [1.2.1] - 2026-08-01

### Changed

- 中英文 README 改为面向开发者的信息架构。
- 社区文件（CONTRIBUTING / SECURITY / SUPPORT）改为可直接执行的指南。
- PCB 版本独立为 Rev 1.0.1（软件版本与 PCB 修订分离）。

### Fixed

- 修正 PCB 制造文件（Gerber、钻孔、飞针测试数据与 EasyEDA 工程全部更新）。
- 修正 PCB README 中的 ESP32 错误表述（实际为 NodeMCU ESP8266 开发板）。
- 修正 README 过期 Release 链接与不存在的 BOM/坐标声明。
- 修复启动横幅双 v 显示（现为 `firmware v1.2.1`）。
- 修复英文 README 语义链接（中文入口指向中文、英文入口指向英文）。

### Security

- 制造数据改为按字节受控发布（`.gitattributes` + 确定性打包），消除换行导致的哈希漂移。

### Known issues

- 未提供经过验证的 BOM 或 pick-and-place 文件。
- 实际空调红外帧不在公开仓库中，需使用红外学习工具自行采集。
- v1.2.0 自动源码归档仍包含旧 PCB 文件，制板请使用 v1.2.1。

No cloud API or database schema changes.

## [1.2.0] - 2026-08-01

首个 Monorepo 统一发布版。

- 可选西电/Srun 校园网认证（默认关闭；公开构建不含凭据）。
- 断线与会话恢复：Wi-Fi 掉线、IP 变化或 Portal 重现后自动恢复连接。
- PlatformIO 与 Arduino IDE 双工作流构建验证。
- 完整中英文文档与统一 CI。
- Monorepo 统一发布（固件、云端、PCB、工具、文档一次获取）。

## [1.0.0] - 2026-07-31

首个正式公开发布版本。

- ESP8266 固件（PlatformIO 与 Arduino IDE 两种方式）。
- Cloud 后端（Fastify + MQTT 桥接）与前端（Vue 3 响应式 UI）。
- 红外学习工具（源码 + Windows EXE）。
- 基础安全模型（双角色、受信任会话）。
