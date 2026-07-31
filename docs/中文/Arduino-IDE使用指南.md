# Arduino IDE 使用指南

> 使用 Arduino IDE 编译、上传和调试 Remote AC Controller 固件的完整指南。

---

## 环境准备

### 1. 安装 Arduino IDE

从 [arduino.cc](https://www.arduino.cc/en/software) 下载并安装 Arduino IDE（推荐 2.x 版本）。

### 2. 安装 ESP8266 开发板支持

1. 打开 Arduino IDE → 文件 → 首选项
2. 在"附加开发板管理器网址"中添加：
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
3. 工具 → 开发板 → 开发板管理器 → 搜索 "esp8266" → 安装

### 3. 安装所需库

通过 项目 → 加载库 → 管理库，安装以下库：

| 库 | 作者 | 版本要求 |
|----|------|----------|
| DHT sensor library | Adafruit | 最新版 |
| Adafruit Unified Sensor | Adafruit | 最新版 |
| ArduinoJson | Benoit Blanchon | 6.x |
| PubSubClient | Nick O'Leary | 最新版 |
| Crypto | Rhys Weatherley | 最新版 |

### 4. 安装 RemoteACCore 共享库

```bash
# Windows (PowerShell)
Copy-Item -Recurse ..\..\shared\RemoteACCore "$env:USERPROFILE\Documents\Arduino\libraries\RemoteACCore"

# macOS / Linux
cp -r ../../shared/RemoteACCore ~/Arduino/libraries/RemoteACCore
```

### 5. 安装 srun-c 库（可选）

如需校园网认证功能：

```bash
cp -r ../agent-platformio/lib/srun-c ~/Arduino/libraries/srun-c
```

## 配置

### 复制配置文件

```bash
cp config.example.h config.h
```

### 编辑 config.h

根据你的使用场景设置以下宏：

| 宏 | 默认值 | 说明 |
|----|--------|------|
| `ENABLE_WIFI` | 1 | Wi-Fi 功能 |
| `ENABLE_CAMPUS_AUTH` | 0 | 校园网认证 |
| `ENABLE_CLOUD` | 0 | MQTT 云连接 |
| `ENABLE_IR_MUTATING_COMMANDS` | 0 | 红外发射命令 |

**`config.h` 已被 .gitignore 忽略**，不会提交到仓库。

## 编译与上传

1. 打开 `Remote_AC_Controller.ino`
2. 选择开发板：工具 → 开发板 → ESP8266 → NodeMCU 1.0 (ESP-12E Module)
3. 选择端口：工具 → 端口 →（你的 ESP8266 COM 端口）
4. 点击"验证"（✓）编译
5. 点击"上传"（→）烧录

## 串口调试

- 工具 → 串口监视器
- 波特率：**115200**
- 换行符：Newline

预期启动输出：
```
BOOT_ID=0x...
DHT11_MODULE_READY pin=GPIO5
IR_MODULE_READY rx=GPIO13 tx=GPIO14
DIAGNOSTIC_CONSOLE_READY=YES
```

## 故障排查

### 编译错误："RemoteACApp.h not found"
- 确保 RemoteACCore 库已复制到 Arduino 库文件夹
- 复制后重启 Arduino IDE

### 编译错误："srun.h not found"
- 复制 srun-c 库，或设置 `ENABLE_CAMPUS_AUTH` 为 `0`

### 上传失败
- 检查端口是否正确选择
- 确保 ESP8266 已通过 USB 连接
- 部分 ESP8266 模块需要按住 FLASH 按钮再按 RST 进入下载模式

### 串口无输出
- 检查波特率是否为 115200
- 检查 CH9102 驱动是否已安装
- 尝试更换 USB 线或端口

## 相关文档

- [西电校园网自动认证](./西电校园网自动认证.md)
- [Srun 校园网移植指南](./Srun校园网移植指南.md)