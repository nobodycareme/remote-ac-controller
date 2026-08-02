**简体中文** | [English](../English/mqtt-protocol.md)

# MQTT 协议

ESP8266 固件（Firmware）与云端后端（Backend）之间的通信契约。

## 1. Topic 命名空间

```
<TOPIC_PREFIX>/<DEVICE_ID>/<suffix>
```

| Setting | Default | Where |
|---------|---------|-------|
| `TOPIC_PREFIX` | `remote-ac/v1/devices` | `cloud/backend/src/config.ts` |
| `DEVICE_ID` | `bedroom-ac-01` | `cloud/backend/src/config.ts`, firmware config |

实际示例：`remote-ac/v1/devices/bedroom-ac-01/telemetry`。

其中 `v1` 段表示协议版本。任何破坏兼容性的载荷变更都必须递增该版本号，而不是原地修改既有字段。

| Suffix | Publisher | Subscriber | QoS | Retain |
|--------|-----------|-----------|-----|--------|
| `telemetry` | device | backend | 0 | no |
| `state` | device | backend | 0 | no |
| `availability` | device (+ LWT) | backend | 0 | **yes** |
| `commands/set` | backend | device | 0 (IR: **1**) | no |
| `commands/ack` | device | backend | 0 | no |

## 2. Broker ACL

消息代理（MQTT Broker）上配置两个能力严格互斥的账号（见 `cloud/broker/acl/aclfile`）：

```
user remote-ac-device
topic write remote-ac/v1/devices/bedroom-ac-01/telemetry
topic write remote-ac/v1/devices/bedroom-ac-01/state
topic write remote-ac/v1/devices/bedroom-ac-01/availability
topic write remote-ac/v1/devices/bedroom-ac-01/commands/ack
topic read  remote-ac/v1/devices/bedroom-ac-01/commands/set

user remote-ac-backend
topic read  remote-ac/v1/devices/bedroom-ac-01/telemetry
topic read  remote-ac/v1/devices/bedroom-ac-01/state
topic read  remote-ac/v1/devices/bedroom-ac-01/availability
topic read  remote-ac/v1/devices/bedroom-ac-01/commands/ack
topic write remote-ac/v1/devices/bedroom-ac-01/commands/set
```

这套 ACL 直接带来两条安全性质：

- 被攻陷的设备**无法**向自身或任何其他设备下发命令，因为它对 `commands/set`
  没有写权限。
- 被攻陷的后端**无法**伪造遥测（Telemetry）或在线状态。

Mosquitto 默认拒绝一切未显式授权的操作。每新增一台设备，都必须相应补充该设备的
ACL 配置块。

## 3. 载荷格式

所有载荷均为 UTF-8 编码的 JSON。接收方必须忽略无法识别的字段。

### 3.1 `telemetry`（设备 → 后端）

由 `firmware/src/cloud/telemetry_service.cpp` 中的 `buildJson()` 构造。

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | int | 载荷 schema 版本 |
| `device_id` | string | 设备标识 |
| `seq` | int | 自启动以来单调递增的序号 |
| `uptime_s` | int | 自启动以来的秒数 |
| `temperature_c` | number | 环境温度 |
| `humidity_pct` | number | 相对湿度 |
| `sensor_ok` | bool | 上一次采样失败时为 false |
| `wifi_rssi_dbm` | int | 信号强度 |
| `free_heap_bytes` | int | 空闲堆内存 |
| `max_free_block_bytes` | int | 最大连续可用内存块（内存碎片化指标） |
| `boot_id` | string | 每次启动随机生成的标识 |
| `reset_reason` | string | SDK 上报的复位原因 |
| `wifi_reconnect_count` | int | 累计计数器，便于稳定性问题定位 |
| `mqtt_reconnect_count` | int | |
| `mqtt_disconnect_count` | int | |
| `mqtt_loop_fail_count` | int | |
| `mqtt_publish_fail_count` | int | |
| `mqtt_initial_connect_count` | int | |
| `mqtt_reconnect_attempt_count` | int | |
| `mqtt_reconnect_success_count` | int | |
| `ir_ready` | bool | 红外模块可正常响应 |
| `ir_code_id` | string | 最近一次下发的码值标识 |
| `ir_code_length` | int | 帧长度（字节） |
| `ir_code_sha256` | string | 帧摘要，用于溯源校验 |
| `simulated` | bool | 为 true 表示数值是模拟生成的 |
| `firmware_version` | string | 构建标识 |

上报周期由 `DEVICE_PUBLISH_INTERVAL_MS` 控制（默认 5000 ms）；采样周期由
`DEVICE_SAMPLE_INTERVAL_MS` 控制（默认 2500 ms）。

### 3.2 `state`（设备 → 后端）

| Field | Type |
|-------|------|
| `power` | bool |
| `target_temperature_c` | number |
| `mode` | string |
| `simulated` | bool |

### 3.3 `availability`（设备 → 后端，保留消息）

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"online"` \| `"offline"` | |
| `sent_at` / `ts` | number | 发布方时间戳 |

该主题同时注册为 MQTT 遗嘱消息（LWT，`willQos=0`、`willRetain=true`），因此设备非
正常断开时会自动产生 `offline` 状态。

> **设计说明。** 后端有意**不**根据该主题推进 `last_seen_at`。保留消息（Retained
> message）意味着即使设备早已失联，一条 `online` 消息仍会被重新投递给任何新订阅
> 者，从而让一台已经死掉的设备看起来仍然健康。存活性判断改为依据遥测数据的新鲜度
> —— 参见 §5。

### 3.4 `commands/set`（后端 → 设备）

标准（非红外）命令：

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | string | 幂等性（Idempotency）键 |
| `expires_at` | number | Epoch 毫秒；超过该时刻设备将拒绝执行 |
| `action` | `set_state` \| `set_power` \| `set_temperature` | |
| `power` | 1 \| 0 | 用于 `set_power` |
| `target_temperature_c` | number | 用于 `set_temperature` |

红外命令：

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | string | 幂等性键 |
| `type` | `"ir_action"` | 类型判别字段 |
| `action` | string | 空调状态 / 码值标识 |
| `expires_at` | number | Epoch 毫秒 |

红外命令以 **QoS 1、retain false** 发布（见 `cloud/backend/src/mqtt_bridge.ts`
中的 `publishIrAction()`）。使用 QoS 1 是因为一次丢失的实际动作对用户可见；不使用
保留消息则是因为重连时被重放的执行类消息会带来危险。

命令生存期由 `IR_COMMAND_TTL_MS` 控制（默认 25 000 ms）。

### 3.5 `commands/ack`（设备 → 后端）

| Field | Type |
|-------|------|
| `schema` | int |
| `command_id` | string |
| `status` | 见下表 |
| `reason` | string |
| `received_uptime_s` | int |

状态枚举（见 `firmware/src/cloud/command_service.cpp`）：

| Status | Meaning |
|--------|---------|
| `accepted_mock` | 仅用于遗留 / 特殊模拟实现；不是真实 IR 关闭时的默认结果 |
| `ir_executed` | 红外帧已发送 |
| `blocked_by_ir_policy` | 被固件策略安全阻止；通常原因为 `real_ir_control_disabled` |
| `ir_state_disabled` | 请求的状态在当前构建中被禁用 |
| `ir_unknown_code` | 请求的码值没有对应的已配置帧 |
| `ir_module_busy` | 红外模块正处于操作中 |
| `ir_execute_failed` | 已尝试发送但失败 |
| `expired` | 消息到达时 `expires_at` 已过期 |
| `duplicate` | 在执行缓存 TTL 内已见过该 `command_id` |
| `rejected` | 通用拒绝 |

## 4. 幂等性

去重在两端同时进行，这是刻意的设计：

- **后端** —— `mqtt_bridge.ts` 中的 `tryInsertCommand()` 拒绝插入重复的命令键。
  若同一个键携带*不同*载荷重复请求，将以 `idempotency_key_payload_mismatch` 拒绝；
  完全相同的重复请求则返回 `idempotency_replay`。
- **固件** —— `ir_module.h` 中的 `commandIdRecentlyExecuted()` /
  `recordExecutedCommandId()` 维护一份最近执行记录缓存，TTL 为
  `IR_EXEC_TTL_MS = 30000`。

这套机制既能应对 QoS 1 的重复投递，也能应对用户的连续误触。

## 5. 存活性判定

`cloud/backend/src/device_liveness.ts` 依据遥测数据的新鲜度推导设备状态：

| Condition | Classification |
|-----------|----------------|
| 最近一次遥测在 `STALE_THRESHOLD_MS`（60 s）以内 | `online` |
| 介于 60 s 与 `OFFLINE_THRESHOLD_MS`（90 s）之间 | `stale` |
| 超过 90 s | `offline` |

对判定为 `offline` 的设备下发命令会以 `DEVICE_OFFLINE` 直接拒绝，而不是把消息发进
无人接收的虚空。

## 6. 传输安全

- MQTT 运行在 TLS 之上。设备通过 BearSSL 校验 Broker 证书：**CA 证书优先**（`setTrustAnchors`）；没有有效 CA 时才使用 SHA-1 服务器证书指纹（`setFingerprint`，40 位十六进制、冒号可选），指纹固定的是当前服务器证书，证书更新后必须同步更新。二者都缺失时 MQTT 初始化被拒绝（`TLS_MATERIAL_MISSING`）。参见
  [`security-model.md`](./安全模型.md)。
- BearSSL 缓冲区大小设置为 `setBufferSizes(4096, 1024)`；参见
  [`hardware.md`](./硬件说明.md) §5。
- 明文 MQTT 仅在本地开发场景下可接受（`cloud/tools/broker-dev.cjs`）。

## 7. 协议扩展

1. 新增字段一律为**可选**；绝不复用既有字段的语义。
2. 为任何新增的 topic 后缀补齐对应的 ACL 条目。
3. 破坏性变更需递增前缀中的 `v1` 段，并在迁移期内同时运行两个版本。
4. 字段语义发生变化时，更新载荷中的 `schema`。
