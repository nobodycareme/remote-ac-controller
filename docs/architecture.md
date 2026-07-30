**简体中文** | [English](./architecture_EN.md)

# 架构

本文档描述 Remote AC Controller 的端到端架构：各组件、数据流，以及组件之间的边界。

## 1. 系统概览

```
┌──────────────┐   HTTPS    ┌──────────────────┐   MQTT/TLS   ┌─────────────┐   IR
│  Phone /     │──────────▶ │  Cloud Backend   │ ───────────▶ │  ESP8266    │ ─────▶ AC
│  Browser     │ ◀────────  │  (Fastify + Bus) │ ◀─────────── │  Firmware   │
│  (Vue 3 SPA) │  WS/REST   └──────────────────┘   telemetry  └─────────────┘
└──────────────┘                    │                                │
                                    │                                ├─ DHT11 (GPIO5)
                              ┌─────▼──────┐                         └─ ZJ-IR-V2 (GPIO14/12)
                              │ node:sqlite│
                              └────────────┘
```

系统分为四层，每层承担单一职责：

| 层级 | 技术栈 | 职责 |
|------|-----------|----------------|
| 展示层 | Vue 3 + Vite | 页面渲染、用户输入、基于 WebSocket 的实时更新 |
| 应用层 | Node.js + Fastify | 认证、定时调度、自动化、MQTT 桥接、数据持久化 |
| 传输层 | Mosquitto（MQTT over TLS） | 经过认证、受 ACL 约束的消息路由 |
| 设备层 | ESP8266（Arduino/PlatformIO） | 传感采集、红外发射、连接状态监督 |

## 2. 固件（Firmware，`firmware/`）

固件（Firmware）由一组相互协作的非阻塞模块组成，全部由单一 `loop()` 驱动。任何模块都不会阻塞；每个模块都暴露 `update()`/`tick()` 风格的入口。

| 模块 | 文件 | 职责 |
|--------|-------|----------------|
| 入口 | `src/main.cpp` | 模块构建、`setup()`/`loop()` 编排 |
| 串口 CLI | `src/serial_cli.{h,cpp}` | 交互式诊断、红外学习、网络命令 |
| 红外模块 | `src/ir_module.{h,cpp}` | 基于 `SoftwareSerial` 的 ZJ-IR-V2 驱动，采集与重放 |
| 传感器 | `src/sensors/dht11_sensor.cpp` | 具备容错能力的 DHT11 采样 |
| Wi-Fi | `src/network/wifi_manager.cpp` | 非阻塞的连接状态机 |
| 校园网认证 | `src/network/campus_auth.cpp` | 可选的强制门户（srun）认证 |
| MQTT 客户端 | `src/cloud/mqtt_client.{h,cpp}` | TLS MQTT 会话、遗嘱消息（LWT）、重连退避 |
| 连接管理 | `src/cloud/connectivity_state_machine.cpp` | 聚合式在线/离线判定 |
| 遥测 | `src/cloud/telemetry_service.cpp` | 周期性遥测（Telemetry）JSON 组装与发布 |
| 命令 | `src/cloud/command_service.{h,cpp}` | 命令校验、幂等性、红外派发、确认应答（ACK） |

引脚分配只存在于唯一位置：`include/config/hardware_config.h`。`include/board_pins.h` 仅提供向后兼容的别名。

**红外派发只有一个入口** —— `src/cloud/command_service.cpp` 中的 `dispatchIrAction()`。旧式的 `set_power` / `set_temperature` 命令绝不会发射红外，而是以 `accepted_mock` 状态确认应答。这保证了每一次真实红外发射都必须经过唯一的策略检查点。

## 3. 云端后端（Backend，`cloud/backend/`）

后端（Backend）是运行在 Node.js 24 上的 Fastify 应用，使用 TypeScript 与 ESM。

| 文件 | 职责 |
|------|----------------|
| `src/index.ts` | 服务器启动、插件与路由注册 |
| `src/config.ts` | 经 Zod 校验、带安全默认值的环境配置 |
| `src/db.ts` | `node:sqlite` 建表与仅向前的迁移 |
| `src/mqtt_bridge.ts` | MQTT 订阅/发布、消息持久化、命令幂等性 |
| `src/auth.ts` | 密码校验（scrypt）、会话签发、角色分配 |
| `src/guards.ts` | Origin 白名单与 CSRF 校验 |
| `src/automation.ts` | 定时调度引擎与温度规则引擎 |
| `src/weather.ts` | 外部天气数据源集成（带缓存） |
| `src/device_liveness.ts` | online/stale/offline 分类 |
| `src/bus.ts` | 为 WebSocket 通道供数的进程内事件总线 |
| `src/reply_utils.ts` | 统一的成功/拒绝响应封装 |
| `src/ac_states.ts` | 离散空调状态目录 |
| `src/routes/*.ts` | `auth`、`dashboard`、`device`、`telemetry`、`weather`、`ac`、`ir_debug`、`events` |

值得关注的设计决策：

- **内嵌数据库。** `node:sqlite`（Node 22+ 内置）省去了本地原生编译步骤，这对小型服务器意义重大。参见 [`resource-constrained-deployment.md`](./resource-constrained-deployment.md)。
- **速率限制（Rate limiting）。** 使用 `@fastify/rate-limit` 将请求上限设为每分钟 100 次。
- **拒绝响应封装。** 每一次拒绝都返回机器可读的 `errorCode`，而不是裸的 HTTP 状态码，使 UI 能够给出精确的操作指引。

## 4. 前端（Frontend，`cloud/frontend/`）

前端（Frontend）是使用 Vite 构建的 Vue 3 SPA。项目**刻意不引入路由库**：视图切换由 `App.vue` 中的响应式 `currentView` 值控制，在 `home`、`control`、`schedule`、`automation`、`data`、`settings` 和 `more` 之间切换。这样既缩小了打包体积，又让导航模型保持显式。

共享组件：`ClimateHero`、`ThermostatBar`、`TrendChart`、`WeatherCard`、`ActivityTimeline`、`EmptyState`、`AppIcon`。

格式化逻辑被隔离在纯函数层（`lib/format.ts`）中，因此无需挂载组件即可进行单元测试。

## 5. 数据流

### 5.1 遥测（设备 → 用户）

1. `telemetry_service` 采样 DHT11 并组装 JSON 文档。
2. 发布到 `remote-ac/v1/devices/<device_id>/telemetry`（QoS 0）。
3. `mqtt_bridge` 持久化读数并更新滚动分钟聚合。
4. 进程内事件总线通知 WebSocket 订阅者。
5. SPA 更新主卡片和趋势图。

### 5.2 命令（用户 → 设备）

1. SPA 发起已认证且通过 CSRF 校验的 REST 调用。
2. 路由处理器检查角色、安全总开关（Kill switch）以及设备存活状态。
3. `mqtt_bridge.tryInsertCommand()` 按命令键（command key）强制执行幂等性（Idempotency）。
4. 命令携带 `expires_at` 发布到 `.../commands/set`。
5. 设备端的 `command_service` 校验过期时间与重复命令，随后派发红外（或以 mock 方式确认应答）。
6. 设备发布带状态码的 `.../commands/ack`。
7. 后端记录该确认应答（ACK）并通知 UI。

## 6. 可靠性边界

- **可用性不等于存活性。** 设备通过 MQTT 遗嘱消息（LWT）发布带保留标志的 `availability` 保留消息（Retained message）。由于保留消息在发布者下线后依然存在，后端刻意**不**根据 availability 推进 `last_seen_at`。存活性由遥测的新近程度推导（`OFFLINE_THRESHOLD_MS`，默认 90 s）。
- **命令会过期。** 每条命令都携带 `expires_at`。若命令下发时设备处于离线状态，设备重连后会拒绝该命令，而不是执行陈旧的意图。
- **幂等性（Idempotency）。** 两端均做去重：后端按命令键去重，固件按最近执行的命令 ID 缓存去重（TTL 30 s）。

## 7. 刻意省略的内容

- 没有 Git 子模块 —— 一次克隆即可获得完整源码。
- 没有原生数据库驱动，没有 ORM。
- 不包含任何生产凭据、TLS 密钥、红外帧数据或数据库。参见 [`security-model.md`](./security-model.md)。
