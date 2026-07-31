**简体中文** | [English](../English/arduino-ide-guide.md)

# Arduino IDE 使用指南

> 用 Arduino IDE 2.x（或 `arduino-cli`）编译、上传、调试 Remote AC Controller 固件的完整流程。
> 不需要安装 PlatformIO。

---

## 0. 这份指南的关键前提

本工程的功能开关（`ENABLE_*`）**不写在 `sketch.yaml` 里，也不需要你手动 `#include` 任何配置头**。
它使用的是 ESP8266 官方内核自带的 **Global Build Options** 机制：

- ESP8266 内核（arduino-esp8266 ≥ 2.5）的预构建脚本 `mkbuildoptglobals.py` 会自动把
  `<工程名>.ino.globals.h` **强制包含进每一个编译单元**；
- 因此你只需要在草图目录下放一个 `Remote_AC_Controller.ino.globals.h`，宏就会全局生效；
- **不需要** `-include` 参数，**不需要** `sketch.yaml` 的 `compile.extra_flags`，
  **不需要**在 `.ino` 里 `#include` 它。

参考：[Arduino ESP8266 — Global Build Options](https://arduino-esp8266.readthedocs.io/en/latest/faq/a06-global-build-options.html)

---

## 1. 环境准备

### 1.1 安装 Arduino IDE

从 [arduino.cc](https://www.arduino.cc/en/software) 下载安装 Arduino IDE **2.x**。

### 1.2 安装 ESP8266 开发板支持

1. 文件 → 首选项 → "附加开发板管理器网址"中加入：
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
2. 工具 → 开发板 → 开发板管理器 → 搜索 `esp8266` → 安装
   （本项目在 **3.1.2** 上验证；对应 PlatformIO 的 `espressif8266@4.2.1`）
3. 工具 → 开发板 → ESP8266 → **NodeMCU 1.0 (ESP-12E Module)**

### 1.3 安装第三方库（库管理器）

项目 → 加载库 → 管理库，按**精确版本**安装：

| 库 | 作者 | 锁定版本 | 何时需要 |
|----|------|----------|----------|
| DHT sensor library | Adafruit | **1.4.7** | 始终 |
| Adafruit Unified Sensor | Adafruit | **1.1.15** | 始终（DHT 依赖） |
| PubSubClient | Nick O'Leary | **2.8.0** | `ENABLE_CLOUD=1` 时 |
| ArduinoJson | Benoit Blanchon | **6.21.5** | 始终 |

> 版本是锁定的，不要用"最新版"。ArduinoJson 7.x 与本工程 API 不兼容。
>
> **不要安装任何名为 "Crypto" 的第三方库**（例如 Rhys Weatherley 的 Crypto）。
> 校园网认证不需要它——`srun-c` 自带 MD5/SHA1/HMAC 实现；固件中仅有的
> `#include <Crypto.h>` / `#include <base64.h>` 位于 `serial_cli.cpp` 的
> `#if ENABLE_IR_LAB_LEARNING_COMMANDS` 块内，而这两个头文件由 **ESP8266 核心
> 自带**。多装同名库反而可能造成头文件冲突。`SoftwareSerial` 同理。

### 1.4 安装仓库内两个库（一条脚本搞定）

仓库自带两个库，Arduino IDE 只会在**草图本（sketchbook）的 libraries 目录**里找库，
所以需要把它们装进去。仓库提供了脚本，避免手动复制出错：

```bash
# macOS / Linux / Git Bash
./firmware/arduino-ide/tools/install-arduino-libraries.sh

# 自定义草图本位置
ARDUINO_SKETCHBOOK=/your/sketchbook ./firmware/arduino-ide/tools/install-arduino-libraries.sh
```

```powershell
# Windows PowerShell
.\firmware\arduino-ide\tools\install-arduino-libraries.ps1
```

脚本做两件事：

| 库 | 处理方式 | 原因 |
|----|----------|------|
| `RemoteACCore` | **软链接**到 `firmware/shared/RemoteACCore` | 本身就是 Arduino 库布局；软链接后你在仓库里改代码（比如放自己的 `config/profiles/xidian.h`）立即生效 |
| `srun-c` | **生成**扁平化副本 | 上游是 PlatformIO 的 `include/` + `src/` 双目录布局，`arduino-cli` 不认；脚本合并进单一 `src/` 并生成 `library.properties` |

> 软链接不可用时（如未开发者模式的 Windows）脚本会退化为复制，此时**改完仓库要重跑脚本**。
> 同理，改动 `lib/srun-c` 后必须重跑脚本。
> 脚本**不碰任何凭据、不编译、不烧录**。

---

## 2. 配置功能开关（globals 工作流）

### 2.1 复制 globals 头文件

```bash
cd firmware/arduino-ide/Remote_AC_Controller
cp Remote_AC_Controller.ino.globals.example.h Remote_AC_Controller.ino.globals.h
```

`Remote_AC_Controller.ino.globals.h` **已被 .gitignore 忽略**——它可能开启实网认证，
绝不入库。仓库里提交的只有 `.example.h`，其默认值是安全的（一切能发射、能认证、
能内嵌秘密的开关都是 `0`），保证**全新 clone 直接可编译**。

### 2.2 编辑开关

| 宏 | 默认 | 说明 |
|----|------|------|
| `ENABLE_WIFI` | 1 | Wi-Fi 基础功能 |
| `ENABLE_CAMPUS_AUTH` | 0 | 校园网 srun 认证（编译认证代码） |
| `ENABLE_AUTO_CAMPUS_AUTH` | 0 | 检测到强制门户时自动认证 |
| `ENABLE_CLOUD` | 0 | MQTT 云连接 |
| `ENABLE_CLOUD_CREDENTIALS` | 0 | 编译云端凭据 |
| `ENABLE_CONTROLLED_LIVE_AUTH` | 0 | **实网**登录（编译真实账号密码） |
| `ENABLE_IR_MUTATING_COMMANDS` | 0 | 真实红外发射 |
| `ENABLE_IR_LAB_LEARNING_COMMANDS` | 0 | 红外学习实验命令 |

每个宏都用 `#ifndef` 包着，所以命令行 `-D` 仍可覆盖。

### 2.3 开启校园网认证时必须选 Profile

`ENABLE_CAMPUS_AUTH=1` 但没指定 Profile 时，**编译会直接 `#error` 中止**——
工程绝不会"默默指向某个不明校园门户"。

```bash
# 以西电为例，复制示例 Profile 为 git-ignored 的实际文件
cd firmware/shared/RemoteACCore/src/config/profiles
cp xidian.example.h xidian.h
```

然后在 `Remote_AC_Controller.ino.globals.h` 里：

```c
#define ENABLE_CAMPUS_AUTH    1
#define CAMPUS_PROFILE_HEADER "profiles/xidian.h"
```

其它学校用 `generic_srun.example.h` 作模板，参见
[Srun 校园网移植指南](./Srun校园网移植指南.md)。

### 2.4 凭据放哪里

账号密码**只能**放在 git-ignored 的 `campus_secrets.h`，且**仅当**你本机显式设置
`ENABLE_CONTROLLED_LIVE_AUTH=1` 时才参与编译。仓库中不存在任何账号、密码、
Cookie、Token 或私钥。

---

## 3. 编译与上传

Arduino IDE：

1. 打开 `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino`
2. 工具 → 开发板 → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. 工具 → 端口 → 选择你的 ESP8266 串口
4. 点"验证"（✓）编译；点"上传"（→）烧录

`arduino-cli`：

```bash
cd firmware/arduino-ide/Remote_AC_Controller
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 .
arduino-cli upload  --fqbn esp8266:esp8266:nodemcuv2 -p COM3 .
```

> 上传约需 2~3 分钟，请勿中途拔线。

---

## 4. 串口调试

- 工具 → 串口监视器，波特率 **115200**，换行符 Newline

预期启动输出：

```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
```

开启校园网认证后还会看到门户检测输出，例如：

```
CAPTIVE_PORTAL_DETECTED host=w.xidian.edu.cn AC_ID=8
```

未提供凭据时会明确打印（这是设计行为，不是故障）：

```
CAMPUS_CREDS_READY=NO
AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS
```

---

## 5. 故障排查

| 现象 | 原因与处理 |
|------|-----------|
| `RemoteACApp.h: No such file` | 未运行 `install-arduino-libraries` 脚本，或装完没重启 IDE |
| `srun.h: No such file` | 同上；或把 `ENABLE_CAMPUS_AUTH` 设回 `0` |
| `#error ... no campus profile selected` | 开了 `ENABLE_CAMPUS_AUTH=1` 却没定义 `CAMPUS_PROFILE_HEADER`，见 §2.3 |
| 改了 globals 里的宏但**没生效** | 文件名必须**严格**是 `Remote_AC_Controller.ino.globals.h` 且与 `.ino` **同目录**；改名或放错目录内核不会加载它 |
| `#include expects "FILENAME"` | `CAMPUS_PROFILE_HEADER` 的值必须带引号，如 `"profiles/xidian.h"` |
| 改了仓库代码但编译用的还是旧的 | 脚本退化成了复制模式，重跑 `install-arduino-libraries` |
| 上传失败 | 检查端口；部分模块需按住 FLASH 再点 RST 进下载模式 |
| 串口无输出 | 波特率是否 115200；CH9102/CP2102 驱动是否安装；换 USB 线 |
| `TLS_PIN_MISMATCH` | 门户证书已轮换，按 [TLS 证书固定与更新](../../firmware/agent-platformio/docs/03_协议与接口/TLS证书固定与更新.md) 重抽指纹；**严禁**改成 `setInsecure()` |

---

## 6. 相关文档

- [西电校园网自动认证](./西电校园网自动认证.md)
- [Srun 校园网移植指南](./Srun校园网移植指南.md)
- [安全模型](./安全模型.md)
- [硬件说明](./硬件说明.md) ・ [接线说明](./接线说明.md)
