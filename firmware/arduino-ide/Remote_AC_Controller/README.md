**简体中文** | [English](./README.en.md)

# Remote AC Controller — Arduino IDE 构建指南

**Remote AC Controller**（ESP8266 NodeMCU v2）的 Arduino IDE 固件构建说明。

---

## 先决条件

### 1. 安装 ESP8266 开发板支持

1. 打开 Arduino IDE → 文件 → 首选项
2. 在"附加开发板管理器网址"中添加：`https://arduino.esp8266.com/stable/package_esp8266com_index.json`
3. 工具 → 开发板 → 开发板管理器 → 搜索 "esp8266" → 安装

### 2. 安装所需库（库管理器）

通过 项目 → 加载库 → 管理库 安装以下库：

| 库                    | 作者              | 说明                          |
|-----------------------|-------------------|-------------------------------|
| DHT sensor library    | Adafruit          | DHT11 温湿度传感器驱动         |
| Adafruit Unified Sensor | Adafruit        | DHT 库的依赖项                 |
| ArduinoJson           | Benoit Blanchon   | JSON 解析/序列化               |
| PubSubClient          | Nick O'Leary      | MQTT 客户端                    |
| Crypto                | Rhys Weatherley   | SHA256、Base64、BLAKE2s        |

### 3. 安装 RemoteACCore 共享库

将共享核心库复制到 Arduino 库文件夹：

```bash
# Windows (PowerShell)
Copy-Item -Recurse ..\..\shared\RemoteACCore "$env:USERPROFILE\Documents\Arduino\libraries\RemoteACCore"

# macOS / Linux
cp -r ../../shared/RemoteACCore ~/Arduino/libraries/RemoteACCore
```

### 4. 安装 srun-c 库（校园网认证）

如需校园网认证功能，复制 srun-c 库：

```bash
# 从 PlatformIO lib/ 目录复制
cp -r ../agent-platformio/lib/srun-c ~/Arduino/libraries/srun-c
```

### 5. SoftwareSerial

红外模块使用 SoftwareSerial。ESP8266 核心已内置，无需单独安装。

## 配置

1. **复制并编辑数值配置文件：**
   ```bash
   cp config.example.h config.h
   ```

2. **编辑 `config.h`** 填写你的运行期参数（仅数值/凭据占位）：
   - 设置 `CAMPUS_SSID` 为你的 Wi-Fi 网络名称
   - 如需校园网认证，校园网账号凭据填在 `config/campus_secrets.h`（复制
     `config/campus_secrets.example.h` → `config/campus_secrets.h`）
   - 如需 MQTT 云连接，填写 MQTT Broker 信息

3. **（可选）复制并编辑全局功能开关头文件：**
   ```bash
   cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
   ```
   在其中设置 `ENABLE_CAMPUS_AUTH` / `ENABLE_CLOUD` / `ENABLE_IR_MUTATING_COMMANDS`
   等编译期功能开关；并将 `sketch.yaml` 的 `compile.extra_flags` 指向你的
   `globals.h`。**跳过此步也可编译**——提交的 `.example.h` 已含安全公开默认值，
   通过 ESP8266 核心的 `-include` 机制自动注入。

4. **`config.h` 与 `globals.h` 均已被 git-ignore** — 切勿提交真实凭据或开启真实认证。

## 构建与上传

1. 在 Arduino IDE 中打开 `Remote_AC_Controller.ino`
2. 选择开发板：工具 → 开发板 → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. 选择端口：工具 → 端口 →（你的 ESP8266 COM 端口）
4. 点击"验证"（勾选图标）编译
5. 点击"上传"（箭头图标）烧录

## 串口监视器

- 工具 → 串口监视器
- 波特率：**115200**
- 换行符：Newline

预期启动消息：
```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
SINGLE_SERIAL_ROUTER=TRUE
```

## 构建配置矩阵

| 功能                | 宏                            | 默认值（globals.example.h） |
|--------------------|-------------------------------|------------------------------|
| Wi-Fi              | ENABLE_WIFI                   | ON                           |
| 云连接 (MQTT)      | ENABLE_CLOUD                  | OFF                          |
| 云凭据加载         | ENABLE_CLOUD_CREDENTIALS      | OFF                          |
| 校园网自动认证     | ENABLE_AUTO_CAMPUS_AUTH       | OFF                          |
| 校园网认证         | ENABLE_CAMPUS_AUTH            | OFF                          |
| 受控真实认证       | ENABLE_CONTROLLED_LIVE_AUTH   | OFF                          |
| 红外发射命令       | ENABLE_IR_MUTATING_COMMANDS   | OFF                          |

这些编译期功能开关在 `Remote_AC_Controller.ino.globals.h`（由 `sketch.yaml` 的
`-include` 注入）中设置；运行期数值（SSID、Broker、TLS 等）在 `config.h` 中设置。
两者职责分离。

## 与 PlatformIO 构建的差异

| 特性            | PlatformIO (`agent-platformio/`) | Arduino IDE (`arduino-ide/`)  |
|----------------|----------------------------------|-------------------------------|
| 入口文件        | `src/main.cpp`                   | `Remote_AC_Controller.ino`    |
| 配置系统        | `include/cloud_secrets.h` + 环境  | `config.h`                    |
| 私有红外码      | 支持（`ENABLE_IR_MUTATING`）     | 需要手动设置                  |
| 构建工具        | PlatformIO CLI / VS Code          | Arduino IDE                   |

两种构建方式共享**同一套业务逻辑**（`shared/RemoteACCore/`）。

## 故障排查

### 编译错误："RemoteACApp.h not found"
- 确保 RemoteACCore 库在 Arduino 库文件夹中
- 复制库后重启 Arduino IDE

### 编译错误："srun.h not found"
- 复制 srun-c 库，或设置 `ENABLE_CAMPUS_AUTH` 为 `0`

### 云功能不工作
- 检查 `config.h` 中 MQTT Broker 信息是否正确
- 确保 `ENABLE_CLOUD` 设置为 `1`
- 查看串口监视器是否有 `CLOUD_MQTT_INIT_OK`