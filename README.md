**简体中文** | [English](./docs/English/README.md)

# Remote AC Controller · 手机远程控制空调


一套完整的开源远程空调控制系统：手机网页 → 云端后端 → MQTT（TLS） →
ESP8266 → 红外 → 空调。从固件到前端全部开源，可自行部署。

> **状态：** 公开预发布版（main），`v1.0.0` 尚未发布
> **许可：** [Apache License 2.0](./LICENSE)

---

## 系统做什么

```
手机网页 ──▶ 云端后端 ──▶ MQTT (TLS) ──▶ ESP8266 ──▶ 红外 ──▶ 空调
              │
              ├─ 定时调度
              ├─ 温控自动化（DHT11 + 规则）
              ├─ 天气联动
              ├─ Owner / Guest 与受信任设备模型
              └─ 仪表盘、遥测、命令 ACK
```

- **手机网页** — Vue 3 响应式界面，覆盖状态查看、控制、定时、自动化与设备管理。
- **云端后端** — Fastify + MQTT 桥接、调度引擎、温控自动化、天气集成、
  Owner/Guest 鉴权、受信任设备、遥测与仪表盘 API；持久化使用内置
  `node:sqlite`。
- **MQTT** — Mosquitto，TLS 加密，连接后端与设备。
- **ESP8266 固件** — NodeMCU，DHT11 温湿度采集、红外学习与发射、安全 MQTT
  客户端、11 状态空调控制模型。
- **红外** — 学习并复现空调红外码，支持 11 种离散状态与温度设定。

## 主要特性

- **11 种空调状态**（开关、模式、风速、扫风、睡眠、强劲、节能、除湿、健康、
  显示、定时），每种状态独立启用开关。
- **温湿度监测** — DHT11 接 GPIO5。
- **定时调度与温控自动化** — 支持按星期掩码的周期任务；温控采用双阈值滞回，
  避免频繁开关机。
- **Owner / Guest 双角色** + 受信任设备模型，支持长期会话。
- **跨设备自适应界面** — 桌面与移动端同一套 UI。
- **默认安全** — TLS MQTT、按用途隔离的凭据、公开仓库不含任何真实密钥。

## 仓库结构

本仓库是 **Monorepo**，由原先独立的固件与云端两个项目合并而成，保留了完整的
提交历史。

```
remote-ac-controller/
├─ firmware/      # ESP8266 固件（PlatformIO）
│  ├─ src/  include/  lib/  test/  tools/  platformio.ini  README.md
├─ cloud/         # 后端 + 前端 + broker + 部署 + 工具
│  ├─ backend/  frontend/  broker/  deploy/  tools/  README.md
├─ docs/          # 架构、硬件、红外、MQTT、安全、运维、备份恢复（共 13 篇）
├─ hardware/      # 物料清单、接线摘要、未公开内容说明
├─ tools/         # test-all.ps1, build-all.ps1
├─ .github/       # CI 工作流
├─ LICENSE  NOTICE  THIRD_PARTY_NOTICES.md
├─ README.md（中文）  docs/English/README.md（English）
└─ CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md  SUPPORT.md  CHANGELOG.md
```

不使用 Git 子模块，单次 `git clone` 即可获得固件与云端的全部源码。

## 环境要求

| 组件 | 要求 |
|---|---|
| Node.js | **≥ 22.5，推荐 24** — 后端使用内置 `node:sqlite` 模块，Node 20 上不存在该模块，启动会抛 `ERR_UNKNOWN_BUILTIN_MODULE` |
| 编译工具链 | 不需要。全部依赖均无原生编译（`node:sqlite`、`bcryptjs` 都是纯 JS / 内置） |
| 开发板 | NodeMCU / ESP8266（ESP-12E/F），PlatformIO |
| 服务器 | 1 GB 内存可用，但**构建必须在本机或 CI 完成**，详见 [`docs/resource-constrained-deployment.md`](./docs/中文/低配置服务器部署.md) |

## 快速开始（安全 / 非生产）

公开仓库的默认配置一律为**非生产**行为：不发真实红外、不连生产 broker。

### 固件

```powershell
cd firmware
# 使用提供的入口脚本，不要直接调用 pio：
./tools/dev.ps1 test
./tools/dev.ps1 verify
# 构建公开配置：
./tools/dev.ps1 build <public-profile>
```

公开固件配置不内嵌任何生产 Wi-Fi、MQTT 凭据或真实红外数据，默认不发射真实红外。

### 云端

```bash
cd cloud/backend && npm ci && npm test
cd cloud/frontend && npm ci && npm test && npm run build
```

默认云端配置绑定 `localhost`，使用 `example.com` 占位域名、空/测试数据库、
本地测试 MQTT 地址，红外与自动化均关闭。会话签名密钥由部署者自行提供。

### 统一验证

在仓库根目录执行：

```powershell
./tools/test-all.ps1
./tools/build-all.ps1
```

## 安全与默认值

- **不含任何生产密钥**：无 Wi-Fi / MQTT 口令、无 TLS 私钥、无真实红外数据、
  无数据库、无生产环境文件。
- 固件与云端的公开默认值均为非生产安全值，详见 [`SECURITY.md`](./docs/中文/安全策略.md)。
- 自建者需自行准备 MQTT 凭据、TLS 证书与红外码。
- 真实红外发射受**多重独立开关**保护，全部默认关闭，且只接受字符串
  `"true"` / `"1"` 才视为开启——避免布尔强制转换把 `"false"` 当成真。
  完整清单见 [`docs/operations-guide.md`](./docs/中文/运维指南.md) §7。

## 文档

[`docs/`](./docs) 共 13 篇，按使用目的分组：

| 让它跑起来 | 理解它 | 运维它 |
|---|---|---|
| [硬件选型 `hardware.md`](./docs/中文/硬件说明.md) | [系统架构 `architecture.md`](./docs/中文/系统架构.md) | [部署 `deployment.md`](./docs/中文/部署指南.md) |
| [接线 `wiring.md`](./docs/中文/接线说明.md) | [MQTT 协议 `mqtt-protocol.md`](./docs/中文/MQTT协议.md) | [运维指南 `operations-guide.md`](./docs/中文/运维指南.md) |
| [红外学习 `ir-learning.md`](./docs/中文/红外学习.md) | [安全模型 `security-model.md`](./docs/中文/安全模型.md) | [低配部署 `resource-constrained-deployment.md`](./docs/中文/低配置服务器部署.md) |
| | [定时 `scheduling.md`](./docs/中文/定时任务.md) · [温控 `temperature-automation.md`](./docs/中文/温度自动控制.md) | [故障排查 `troubleshooting.md`](./docs/中文/故障排查.md) · [备份与恢复 `backup-and-recovery.md`](./docs/中文/备份与恢复.md) |

## 参与贡献

见 [`CONTRIBUTING.md`](./docs/中文/参与贡献.md)。贡献内容按 Apache-2.0 授权。

## 许可

[Apache License 2.0](./LICENSE)。中文参考译文见 [`LICENSE_ZH.md`](./docs/中文/Apache-2.0许可证参考译文.md)；第三方许可汇总见
[`THIRD_PARTY_NOTICES.md`](./docs/中文/第三方许可说明.md)。

## 已知限制

诚实列出，便于评估是否适合你的场景：

- **不含具体空调型号的真实红外码** —— 红外帧与机型强相关，需自行捕获
  （流程见 [`ir-learning.md`](./docs/中文/红外学习.md)）。
- **本仓库仅提供源码**，生产部署（TLS、MQTT ACL、密钥管理）由部署者负责。
- **单设备模型** —— 一个后端实例对应一个 `device_id`，未做多设备扇出。
- **无 `/metrics` 端点、无内置备份脚本** —— 监控与备份需自行接入，
  推荐做法见 [`operations-guide.md`](./docs/中文/运维指南.md) §2、§4.3，
  以及 [`backup-and-recovery.md`](./docs/中文/备份与恢复.md)。
- **数据库迁移无版本账本** —— 迁移靠幂等 `ALTER TABLE` 保证，新版本可安全
  向前迁移旧库；**反向降级未经验证**，降级前务必先备份。
- 部分硬件 / PCB 产物因许可不兼容未随仓库发布。

