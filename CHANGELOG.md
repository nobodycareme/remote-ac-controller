[简体中文](./docs/中文/更新日志.md) | [English](./docs/English/changelog.md)

# 更新日志 / Changelog

## [1.2.4] - 2026-08-02

### 修复

- **本地 WPA 开机后的 SSID 状态**：WifiManager 引入明确的连接来源模型（`WIFI_SOURCE_COMPILED_LOCAL_WPA` / `CAMPUS_PROFILE_OPEN` / `RUNTIME_OPEN_SSID` / `NONE`），开机路径把 `LOCAL_WIFI_SSID` 同步进内部状态，`wifi status` 与开机日志显示的实际 SSID 与真实连接一致。
- **`wifi connect <ssid>` 被本地 WPA 覆盖**：显式开放 SSID 现在拥有独立来源，不再被编译期 `LOCAL_WIFI_SSID` 隐式覆盖；`wifi connect`（无参数）恢复本地 WPA 配置，命令行为与文档一致。
- **真实关联路径的 Host 集成测试**：新增 `WifiStationAdapter` 可注入接缝与 `WifiAssociationController` 生产组件，Host 测试直接执行生产连接函数（不再只测复制的模拟逻辑）。
- **拒绝未修改的 Cloud 秘密模板**：新增 `tools/validate-cloud-secrets.py` 内容验证器与运行时 `CloudCredentials::available()` 内容校验，模板主机、端口、设备 ID、账号密码与缺失 TLS 材料都会被拒绝。
- **强化 TLS 配置验证**：本地 Cloud 配置至少需要一个有效 CA 证书或 TLS 指纹，构建与运行时规则一致。

### 说明

- 固件、云端 API 与数据库格式无破坏性变化；PCB 保持 Rev 1.0.1。

## [1.2.3] - 2026-08-02

### 修复

- **无凭据 public 构建的自动联网策略**：`WIFI_AUTOCONNECT_ON_BOOT` 不再由 `ENABLE_CLOUD` 单独触发。编译 Cloud 模块并不提供 SSID 与连接身份，`public` 与 `public-cloud-example` 现在不会在开机时自动关联网络。
- **空 SSID 硬保护**：`WifiConnectPlan` 新增 `configurationValid` / `reason`，SSID 为空时打印 `WIFI_CONNECT_SKIPPED reason=SSID_NOT_CONFIGURED`，不调用任何 `WiFi.begin()` 重载，状态保持断开；本地 WPA 密码为空时同样跳过（`WIFI_PASSWORD_NOT_CONFIGURED`）。
- **local-wifi-cloud 语义修正**：该 Profile 现在启用 `ENABLE_CLOUD_CREDENTIALS=1` 并要求本地 `cloud_secrets.h`；缺少 `wifi_secrets.h` 或 `cloud_secrets.h` 时构建直接停止，不再回退为无凭据示例。
- **文档事实错误修正**：README 删除"只部署固件即可手机控制""模拟设备""组件随意替换""任意 ESP8266 板可直接运行"等无代码依据的表述；首次配置指南改用真实的 `Remote_AC_Controller.ino.globals.h` 文件名；西电校园网指南修正 `local-campus-example` 的真实能力（`ENABLE_AUTO_CAMPUS_AUTH=0`、不读取真实凭据、不自动登录）。

### 说明

- 固件、云端 API 与数据库格式无破坏性变化；PCB 保持 Rev 1.0.1。

## [1.2.2] - 2026-08-01

### 新增

- **普通家庭/实验室 WPA/WPA2 Wi-Fi 配置**：`firmware/shared/RemoteACCore/src/config/wifi_secrets.example.h` 占位符模板 + `ENABLE_WIFI_CREDENTIALS` / `ENABLE_AUTO_WIFI_CONNECT` 编译宏 + `local-wifi` / `local-wifi-cloud` PlatformIO Profile + `wifi connect`（无参数）使用编译进固件的本地凭据。密码从不出现在串口日志、build_flags、平台配置文件、CI 环境或 README 示例。
- **首次配置指南（成对中英文）**：`docs/中文/首次配置.md` / `docs/English/first-time-setup.md`。
- **Windows CI IR 学习工具门禁**：新增 `ir-simple-learner-windows` Job（`windows-latest` + Python 3.12），运行：安装锁定依赖 → 单元测试 → 稳定性测试 → 正式 `build.ps1 -Clean` → EXE `--self-test` → EXE SHA-256 计算 → 凭据/真实 IR 扫描 → 上传 EXE 为 CI Artifact。
- **正式 build.ps1（Python 3.12 + PyInstaller 6.21.0）**：原生命令执行辅助函数（System.Diagnostics.Process）解决 PS5.1 stderr 误判；`requirements-lock.txt` 精确锁定 8 个包；`make_zip_info()` 统一构造 ZipInfo 字段（不再依赖任何平台默认值）；EXE `--self-test` / `--version` 写报告文件供 CI 读取退出码。

### Changed

- GitHub 仓库 About 改为中文优先：description=基于 ESP8266 的手机远程空调控制系统，包含云端、MQTT/TLS、PCB、红外学习工具和中英文文档。
- v1.2.1 Release 资产保持**完全不可变**（v1.2.1 tag 未移动，4 资产 ID/名称/大小不变）；v1.2.1 Release 正文改为中文优先并标记由 v1.2.2 取代。
- `feature_gates.h` 增加 WiFi 凭据相关依赖规则：`ENABLE_WIFI_CREDENTIALS=1` / `ENABLE_AUTO_WIFI_CONNECT=1` 必须有 `ENABLE_WIFI=1`，否则编译期 `#error`。
- 红外学习工具：`test_simple_learner.py` 修复 `test_A` / `test_H` 在 `State.EXITING` 卡住的无声 bug（重构 `handle_event` 控制流——`EXITING` 状态在通用 `cancelled` 处理之前检查），并加入 `test_preset_ids_unique`；20 轮稳定性测试全部通过。

### Fixed

- 红外学习工具 `build.ps1` 在 PowerShell 5.1 + `EnableWIFI=Stop` 下因 PyInstaller stderr 被误判为构建失败（之前必须用 D:/python 3.14 手工绕过；现在 3.12 走完官方脚本即可）。
- 红外学习工具 `requirements-lock.txt` 锁定的 PyInstaller 6.11.1 在 Python 3.14 上不可用——已升级到 6.21.0 全家桶精确锁。
- README 顶部导航修复、`.md` 后缀链接清理（[CONTRIBUTING.md] → [贡献指南]）、增加桌面+移动端界面预览截图、首次配置入口。
- `firmware/agent-platformio/README.md` 等固件文档中 v0.4.0-cloud-foundation 等过时表述清除。

### Known issues

- 未提供经过验证的 BOM 或 pick-and-place 文件。
- EasyEDA 工程容器（`eprj2`）的完整可编辑性与器件型号未独立验证；制造请以已校验的 Gerber / 钻孔 / `manufacturing-manifest.md` 为准。
- 实际空调红外帧不在公开仓库中，需使用红外学习工具自行采集。
- v1.2.0 / v1.2.1 自动源码归档中的 PCB 文件**均已失效**——制板请使用 v1.2.2 的 Rev 1.0.1 制造包。

云端 API 与数据库模式均无变更。

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
