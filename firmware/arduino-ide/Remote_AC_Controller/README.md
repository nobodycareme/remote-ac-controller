**简体中文** | [English](./README.en.md)

# Remote AC Controller — Arduino IDE 构建指南

**Remote AC Controller**（ESP8266 NodeMCU v2）的 Arduino IDE / arduino-cli 固件构建说明。

本 sketch 是一个薄入口，全部业务逻辑位于共享库 `firmware/shared/RemoteACCore/`。
PlatformIO 构建（`firmware/agent-platformio/`）与本构建共用同一套源码。

---

## 一、先决条件

### 1. 安装 ESP8266 开发板支持

1. Arduino IDE → 文件 → 首选项
2. 在"附加开发板管理器网址"中添加：
   `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
3. 工具 → 开发板 → 开发板管理器 → 搜索 `esp8266` → 安装（需 **3.1.x** 及以上）

### 2. 安装依赖库（库管理器）

通过 项目 → 加载库 → 管理库 安装。**并非全部必需**——按你启用的功能开关安装即可：

| 库                      | 作者            | 锁定版本    | 何时需要                                    |
|-------------------------|-----------------|-------------|---------------------------------------------|
| DHT sensor library      | Adafruit        | **1.4.7**   | 始终（`dht11_sensor.h` 无条件引用）          |
| Adafruit Unified Sensor | Adafruit        | **1.1.15**  | 始终（DHT 库的依赖项）                       |
| ArduinoJson             | Benoit Blanchon | **6.21.5**  | 建议始终安装；`ENABLE_CAMPUS_AUTH=1` 时必需  |
| PubSubClient            | Nick O'Leary    | **2.8.0**   | `ENABLE_CLOUD=1` 时必需                      |

> 版本是**锁定**的，不要选"最新版"。ArduinoJson 7.x 与本工程 API 不兼容。

> **不要安装任何名为 "Crypto" 的第三方库。**
> 早期版本的文档曾把 Crypto（Rhys Weatherley）列为必需库，这是错误的。
> 固件中的 `#include <Crypto.h>` 与 `#include <base64.h>` 位于
> `serial_cli.cpp` 的 `#if ENABLE_IR_LAB_LEARNING_COMMANDS` 块内，
> 且这两个头文件由 **ESP8266 核心自带**
> （`framework-arduinoespressif8266/cores/esp8266/`）。
> 额外安装同名第三方库反而可能造成头文件冲突。

**SoftwareSerial**（红外模块使用）同样由 ESP8266 核心自带，无需单独安装。

### 3. 安装仓库内的两个库（用脚本，勿手工复制）

Arduino IDE 只在**草图本（sketchbook）的 `libraries` 目录**中查找库。仓库自带两个库：

- `firmware/shared/RemoteACCore` —— 已是 Arduino 库布局
- `firmware/agent-platformio/lib/srun-c` —— PlatformIO 布局（`include/` + `src/`），
  **arduino-cli 不认识这种拆分**，必须扁平化成单一 `src/` 才能被识别

因此请使用仓库提供的脚本，不要手工 `cp -r`：

```bash
# macOS / Linux / Git Bash
./firmware/arduino-ide/tools/install-arduino-libraries.sh

# Windows PowerShell
.\firmware\arduino-ide\tools\install-arduino-libraries.ps1

# 自定义草图本位置
ARDUINO_SKETCHBOOK=/your/sketchbook ./firmware/arduino-ide/tools/install-arduino-libraries.sh
```

脚本会把 RemoteACCore **符号链接**进草图本（改仓库即时生效），并把 srun-c
**生成**为扁平的 Arduino 库副本。改动 `lib/srun-c` 后需重跑脚本。
脚本不触碰任何凭据、不编译、不烧录。

安装后**重启 Arduino IDE**，否则新库不会被识别。

> `firmware/agent-platformio/lib/srun-c` 是本仓库中 srun-c 的**唯一权威副本**；
> 草图本中的那份是生成物，不要在那里改代码。
> srun-c 仅在 `ENABLE_CAMPUS_AUTH=1` 时参与编译。

---

## 二、配置：Global Build Options（唯一机制）

### 为什么只有这一种机制

Arduino 把库里的每个 `.cpp` 作为**独立编译单元**编译。在 `.ino` 里
`#include` 一个配置头文件，**无法**影响 `RemoteACCore` 自己的 `.cpp` 文件。
因此本项目使用 ESP8266 核心官方的 **Global Build Options** 机制：核心的预构建
步骤 `mkbuildoptglobals.py` 会自动把

```
Remote_AC_Controller.ino.globals.h
```

**force-include 进每一个编译单元**。你无需写 `-include` 参数、无需修改
`sketch.yaml`、也**不要**在 `.ino` 中 `#include` 它。

> 早期版本的文档要求"复制 `config.example.h` → `config.h`"并"把 `sketch.yaml`
> 的 `compile.extra_flags` 指向 globals.h"。**这两种做法均已废弃**：前者创建的
> `config.h` 不被任何编译单元包含（在其中设置 `CAMPUS_SSID` 会静默失效），
> 后者不是 Arduino sketch-project 的受支持配置项。`config.example.h` 已从仓库删除。

### 配置步骤

```bash
cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

`Remote_AC_Controller.ino.globals.h` 已被 git-ignore。编辑其中的开关：

| 功能                | 宏                                | 默认值（example.h）|
|---------------------|-----------------------------------|--------------------|
| Wi-Fi               | `ENABLE_WIFI`                     | `1`                |
| 校园网认证          | `ENABLE_CAMPUS_AUTH`              | `0`                |
| 校园网自动认证      | `ENABLE_AUTO_CAMPUS_AUTH`         | `0`                |
| 云连接 (MQTT)       | `ENABLE_CLOUD`                    | `0`                |
| 云凭据加载          | `ENABLE_CLOUD_CREDENTIALS`        | `0`                |
| 受控真实认证        | `ENABLE_CONTROLLED_LIVE_AUTH`     | `0`                |
| 红外发射命令        | `ENABLE_IR_MUTATING_COMMANDS`     | `0`                |
| 红外实验室学习命令  | `ENABLE_IR_LAB_LEARNING_COMMANDS` | `0`                |

**跳过本步也能编译**——提交的 `.example.h` 已含安全公开默认值（一切可发射、
可认证、可嵌入秘密的开关都是 `0`），全新克隆即可通过编译。

各开关的相互约束规则由 `RemoteACCore/src/config/feature_gates.h` 单一权威定义，
违反约束时会在编译期 `#error` 而非静默降级。

### 启用校园网认证时必须选择 Profile

```c
#define ENABLE_CAMPUS_AUTH   1
#define CAMPUS_PROFILE_HEADER "profiles/xidian.h"        // 你自己的副本
// 或
#define CAMPUS_PROFILE_HEADER "profiles/generic_srun.h"  // 你自己的副本
```

Profile 副本从示例复制而来（`profiles/*.example.h` 之外的文件均被 git-ignore）：

```bash
cd ~/Arduino/libraries/RemoteACCore/src/config/profiles
cp xidian.example.h xidian.h          # 西安电子科技大学，参数已填好
cp generic_srun.example.h generic_srun.h   # 其他 srun 校园，需自行填写
```

若 `ENABLE_CAMPUS_AUTH=1` 却未选择 Profile，构建会 `#error` 中止——固件**绝不会**
指向一个未指定的校园 Portal。详见
[《西电校园网自动认证》](../../../docs/中文/西电校园网自动认证.md) 与
[《Srun 校园网移植指南》](../../../docs/中文/Srun校园网移植指南.md)。

### 凭据文件（全部 git-ignored）

运行期数值**不在本 sketch 目录**配置：

| 项目          | 位置                                                   | 生效条件                          |
|---------------|--------------------------------------------------------|-----------------------------------|
| Wi-Fi SSID    | 串口命令 `wifi connect <ssid>`（无自动连接）            | `ENABLE_WIFI=1`                   |
| 校园网参数    | Profile 头文件（SSID / Portal Host / ac_id / 证书指纹） | `ENABLE_CAMPUS_AUTH=1`            |
| 校园网账号密码| `RemoteACCore/src/config/campus_secrets.h`             | `ENABLE_CONTROLLED_LIVE_AUTH=1`   |
| MQTT Broker   | `RemoteACCore/src/cloud_secrets.h`                     | `ENABLE_CLOUD_CREDENTIALS=1`      |

```bash
# 校园网账号（仅在你确需真实认证时创建）
cp ~/Arduino/libraries/RemoteACCore/src/config/campus_secrets.example.h \
   ~/Arduino/libraries/RemoteACCore/src/config/campus_secrets.h

# MQTT 凭据（仅在启用云连接时创建）
cp ../../agent-platformio/include/cloud_secrets.example.h \
   ~/Arduino/libraries/RemoteACCore/src/cloud_secrets.h
```

> `cloud_secrets.h` 需放在库的 `src/` 目录下（该目录在 Arduino 的头文件搜索路径中）；
> `campus_secrets.h` 需放在 `src/config/` 下（与引用它的 `campus_credentials.h` 同目录）。
> 缺失时构建会 `#error` 明确报错，而不是静默使用空凭据。

**切勿提交** `globals.h`、`campus_secrets.h`、`cloud_secrets.h` 或任何非 `.example.h` 的 Profile。

---

## 三、构建与上传

1. 在 Arduino IDE 中打开 `Remote_AC_Controller.ino`
2. 工具 → 开发板 → ESP8266 → **NodeMCU 1.0 (ESP-12E Module)**
3. 工具 → 端口 → 选择你的 ESP8266 串口
4. 点击"验证"（✓）编译
5. 点击"上传"（→）烧录

arduino-cli 等效命令：

```bash
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 .
arduino-cli upload  --fqbn esp8266:esp8266:nodemcuv2 -p COM3 .
```

参考量级（`ENABLE_WIFI=1`，其余全 `0`）：Flash 约 43%、RAM 约 45%。

---

## 四、串口监视器与首次使用

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

**Wi-Fi 不会自动连接**（offline-first 设计），启动后会看到：

```
AUTO_WIFI_CONNECT_SKIPPED (manual `wifi connect`)
```

常用命令：

```
help                  - 命令总览
wifi connect [ssid]   - 关联开放 SSID（省略则用 Profile 中的 CAMPUS_SSID）
wifi status           - 查看连接状态
campus status         - 查看校园网认证状态
campus login          - 手动发起认证
campus logout         - 注销
campus unblock        - 解除硬失败锁存（latch），重新探测 Portal
```

> `wifi connect` 使用 `WiFi.begin(ssid)`（**开放 SSID，不带密码**），
> 面向 srun 类校园网的开放接入 SSID 场景。

---

## 五、与 PlatformIO 构建的差异

| 特性         | PlatformIO (`agent-platformio/`)        | Arduino IDE (`arduino-ide/`)              |
|--------------|-----------------------------------------|-------------------------------------------|
| 入口文件     | `src/main.cpp`                          | `Remote_AC_Controller.ino`                |
| 开关注入方式 | `platformio.ini` 的 `build_flags -D`    | `*.ino.globals.h`（核心自动 force-include）|
| 依赖库       | `lib/` 内已 vendored，无需手动安装      | 需经库管理器安装 + 手动复制 RemoteACCore/srun-c |
| 多 Profile   | `-e` 环境切换，一条命令跑完整矩阵       | 手动改 `globals.h` 重编                    |
| 构建工具     | PlatformIO CLI / VS Code                | Arduino IDE / arduino-cli                 |

两种构建方式共享**同一套业务逻辑**（`shared/RemoteACCore/`），行为一致。

---

## 六、故障排查

### 编译错误：`RemoteACApp.h: No such file or directory`
- RemoteACCore 未装入 Arduino 库文件夹，或复制后未重启 IDE。

### 编译错误：`srun.h: No such file or directory`
- 你开启了 `ENABLE_CAMPUS_AUTH=1` 但未安装 srun-c 库。
  安装 srun-c，或把该开关改回 `0`。

### 编译错误：`ArduinoJson.h` / `PubSubClient.h` 找不到
- 分别对应 `ENABLE_CAMPUS_AUTH=1` 与 `ENABLE_CLOUD=1`。按第 2 节表格安装对应库。

### 编译错误：`ENABLE_CAMPUS_AUTH=1 but no campus profile selected`
- 需在 `globals.h` 中 `#define CAMPUS_PROFILE_HEADER "profiles/<你的>.h"`，
  且该 Profile 文件确实存在于 `RemoteACCore/src/config/profiles/`。

### 改了 `globals.h` 但开关不生效
1. 确认文件名**精确**为 `Remote_AC_Controller.ino.globals.h`
   （必须与 sketch 主文件同名 + `.globals.h`，且与 `.ino` 同目录）。
2. 确认 ESP8266 核心版本 ≥ 2.5（Global Build Options 由该版本引入）。
3. 项目 → 使用编译警告/详细输出，检查日志中是否出现
   `mkbuildoptglobals.py` 与你的 globals 路径。
4. 执行一次完全重新编译（Arduino IDE 的构建缓存偶尔需要清理）。

### 云功能不工作
- 需同时 `ENABLE_CLOUD=1` 与 `ENABLE_CLOUD_CREDENTIALS=1`，且 `cloud_secrets.h` 存在。
- 串口应出现 `CLOUD_MQTT_INIT_OK`。

### 校园网认证进入 `WIFI_BLOCKED` 且不再重试
- 这是**硬失败锁存**（凭据错误 / 域不匹配 / TLS 指纹不匹配）的预期行为，
  用于防止账号被反复错误登录锁定。
  执行 `campus unblock`（或 `campus login`，或重新上电）解除。
