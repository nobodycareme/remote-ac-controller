**简体中文** | [English](./README.en.md)

# RemoteACCore — 共享核心库

**Remote AC Controller** 固件的核心业务逻辑，由 **PlatformIO** 和 **Arduino IDE** 两种构建方式共享。

---

## 架构

本库包含从旧版 `firmware/src/` 目录提取的全部业务逻辑，是以下模块的**唯一真实来源**：

| 模块          | 说明                                      |
|--------------|-------------------------------------------|
| `cloud/`     | MQTT 客户端、命令分发、遥测、连接状态机      |
| `network/`   | Wi-Fi 管理器、校园网认证（srun）、Portal 检测 |
| `sensors/`   | DHT11 温湿度传感器驱动                      |
| `diagnostics/` | 设备端诊断控制台                          |
| `config/`    | 硬件引脚定义、校园网配置                     |

此外还有独立模块：红外模块（`ir_module.cpp`）、串口 CLI（`serial_cli.cpp`）。

## 入口函数

本库通过 `RemoteACApp.h` 暴露两个 C 链接函数：

```cpp
void appSetup(void);  // 在 setup() 中调用一次 — 初始化所有模块
void appLoop(void);   // 在 loop() 中重复调用 — 主控制循环
```

PlatformIO（`agent-platformio/`）和 Arduino IDE（`arduino-ide/`）的入口点都是**薄包装层**，仅调用这两个函数。

## 构建集成

### PlatformIO

通过 `platformio.ini` 中的 `lib_extra_dirs` 作为本地库编译：

```ini
lib_extra_dirs = ../shared
```

### Arduino IDE

将 `shared/RemoteACCore/` 复制到 Arduino 的 `libraries/` 文件夹安装为库，或等待库发布后通过库管理器安装。

## 隐私与安全

本库**不包含**：
- 真实云凭据（`cloud_secrets.h`）
- 真实私有红外码（`ir_code_registry.h` 私有实现）
- 生产环境的 Wi-Fi 或 MQTT 凭据
- 硬件关联的秘密

所有凭据相关的配置预期在构建特定的项目层完成：PlatformIO 使用
`agent-platformio/include/`（`cloud_secrets.h` 等）；Arduino IDE 使用本库
`src/` 与 `src/config/` 下的 git-ignored 秘密头文件。编译期功能开关一律来自
`config/feature_gates.h` 及其上游宏定义，而非任何运行期配置文件。

## 依赖

所需的 Arduino 库（通过 PlatformIO 库管理器或 Arduino 库管理器安装）。
**并非全部无条件必需**——取决于启用的功能开关：

| 库                          | 何时需要                                  |
|-----------------------------|-------------------------------------------|
| **DHT sensor library** (Adafruit) | 始终（`sensors/dht11_sensor.h`）      |
| **Adafruit Unified Sensor**       | 始终（DHT 的依赖项）                   |
| **ArduinoJson** (Benoit Blanchon) | `ENABLE_CAMPUS_AUTH=1`                |
| **PubSubClient** (Nick O'Leary)   | `ENABLE_CLOUD=1`                      |
| **srun-c**（本仓库捆绑）           | `ENABLE_CAMPUS_AUTH=1`                |

> **不需要**第三方 Crypto 库。`serial_cli.cpp` 中的 `<Crypto.h>` / `<base64.h>`
> 仅在 `ENABLE_IR_LAB_LEARNING_COMMANDS=1` 时引用，且这两个头文件由 ESP8266
> 核心自带。`<SoftwareSerial.h>` 同理，无需单独安装。

## 版本

1.0.0 — 从固件 v0.4.0-cloud-foundation 提取。