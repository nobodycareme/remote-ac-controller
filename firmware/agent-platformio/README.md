**简体中文** | [English](./README.en.md)

# Remote AC Controller — PlatformIO 构建指南

**Remote AC Controller**（ESP8266 NodeMCU v2）的 PlatformIO 固件构建说明。

---

## 项目结构

```
agent-platformio/
├── platformio.ini          # PlatformIO 配置
├── src/
│   ├── main.cpp            # 薄入口层（→ appSetup/appLoop）
│   └── private_ir_codes/   # 私有红外码数据（仅 PlatformIO 模式）
├── include/                 # PlatformIO 专用公开头文件
├── lib/                    # PlatformIO 管理的库
├── test/                   # 单元测试
├── tools/
│   └── dev.ps1             # 主要开发入口脚本
└── docs/                   # 项目文档
```

共享业务逻辑位于 `../shared/RemoteACCore/`，作为本地库编译。

## 快速开始

### 先决条件

- [PlatformIO IDE](https://platformio.org/install)（VS Code 扩展或 CLI）
- ESP8266 开发板支持（PlatformIO 自动安装）

### 构建

**请勿直接运行 `pio`**。请使用开发脚本：

```powershell
# 公开构建（安全默认，无凭据）
.\tools\dev.ps1 build -Profile public

# 普通家庭/实验室 WPA/WPA2 WiFi（需 wifi_secrets.h）
.\tools\dev.ps1 build -Profile local-wifi

# 西电校园网（示例 Profile，需 campus_secrets.h 与 profiles/xidian.h）
.\tools\dev.ps1 build -Profile local-campus-example
```

运行全部验证：`.\tools\dev.ps1 test -Profile public`；烧录：`.\tools\dev.ps1 upload -Profile public`。

### 配置（首次配置前必读）

完整教程见 [首次配置指南](../../docs/中文/首次配置.md)。普通 WiFi 密码与西电校园网账号密码是两套独立的凭据，不可互相替代。

1. **普通 WiFi 凭据**（WPA/WPA2，`local-wifi` Profile 必需）：
   ```bash
   cd shared/RemoteACCore/src/config
   cp wifi_secrets.example.h wifi_secrets.h
   # 编辑 wifi_secrets.h：
   #   #define LOCAL_WIFI_SSID     "你的WiFi名称"
   #   #define LOCAL_WIFI_PASSWORD "你的WiFi密码"
   ```
   真实文件 `wifi_secrets.h` 已被 git-ignore，只有 `.example.h` 入库。密码从不会写入串口日志。

2. **西电校园网凭据**（srun Portal 认证，`local-campus-example` Profile 必需）：
   ```bash
   cd shared/RemoteACCore/src/config
   cp profiles/xidian.example.h profiles/xidian.h
   cp campus_secrets.example.h campus_secrets.h
   # 编辑 campus_secrets.h：
   #   #define CAMPUS_USERNAME "你的学号"
   #   #define CAMPUS_PASSWORD "你的校园网密码"
   ```
   西电 `stu-xdwlan` 是开放 SSID（WiFi 层无 WPA 密码），校园账号密码属于 Portal 认证。真实凭据文件均被 git-ignore。

3. **云凭据**（MQTT 连接，可选）：
   ```bash
   cd ../shared/RemoteACCore/src/config
   cp cloud_secrets.example.h cloud_secrets.h
   # 编辑 canonical cloud_secrets.h；PlatformIO 与 Arduino IDE 共用此文件
   ```

### 构建配置（Profile 矩阵）

| Profile | ENABLE_CLOUD | ENABLE_WIFI_CREDENTIALS | ENABLE_CAMPUS_AUTH | 用途 |
|---|---|---|---|---|
| `public` | 1 | 0 | 0 | 安全默认构建（开放 SSID，无本地凭据） |
| `local-wifi` | 0 | 1 | 0 | 普通家庭/实验室 WPA/WPA2（需 wifi_secrets.h） |
| `local-wifi-cloud` | 1 | 1 | 0 | 普通 WiFi + 云连接（需 wifi_secrets.h + cloud_secrets.h） |
| `local-campus-example` | 0 | 0 | 1 | 西电校园网示例（需 profiles/xidian.h + campus_secrets.h） |
| `public-cloud-example` | 1 | 0 | 0 | 公开云传输矩阵条目（同 public 的显式名称） |

所有公开 Profile 均保持 `ENABLE_CONTROLLED_LIVE_AUTH=0` 与 `ENABLE_IR_MUTATING_COMMANDS=0`。真实凭据只存在于 git-ignored 文件中，绝不写入本仓库。Cloud 配置的唯一权威路径是 `shared/RemoteACCore/src/config/cloud_secrets.h`；两个旧路径仍存在时 `dev.ps1` 会硬失败。

> **v1.2.4：只复制模板不能通过构建。** `local-wifi` / `local-wifi-cloud` 构建前运行 `tools/validate-cloud-secrets.py` 做内容校验（WiFi SSID/密码规则、Cloud 主机/端口/设备 ID/账号密码/TLS 材料），模板占位值（`your_wifi_name`、`your-broker.example.com`、`change-me`、空 CA/指纹等）会被拒绝并输出非敏感错误码。`wifi connect`（无参数）使用本地 WPA 配置；`wifi connect <ssid>` 临时切换到指定开放 SSID，不使用本地密码，也不支持在命令行输入 WiFi 密码。
>
> **v1.2.5：SSID 与 TLS 规则。** SSID 允许包含普通空格（`Home WiFi`、`Lab Network 2`），按 UTF-8 字节计数、上限 32 字节，不能全为空格或含控制字符，不会被 trim 或截断。TLS 上 CA 证书优先：同时配置有效 CA 与有效指纹时只使用 CA；没有有效 CA 时才用 SHA-1 服务器证书指纹（40 位十六进制，冒号可选），证书更新后需同步更新指纹；两者都缺失时构建/初始化停止（`TLS_MATERIAL_MISSING`）；不要关闭 TLS 校验。

### 上传

```powershell
.\tools\dev.ps1 upload -Profile public
```

## 测试

```powershell
.\tools\dev.ps1 test -Profile public
```

固件核心的纯逻辑（feature gates 依赖、WiFi 连接决策、CampusAuthPolicy）另有 Host 测试（`test/host/`），由 CI 的 `firmware-host-tests` Job 编译执行。

## 依赖

`lib/` 中的库为 vendored 方式管理。PlatformIO 会自动下载缺失的依赖项。

## 版本

软件版本见 `VERSION` 文件（当前 v1.2.2）。PCB 修订为 Rev 1.0.1，与软件版本相互独立。
