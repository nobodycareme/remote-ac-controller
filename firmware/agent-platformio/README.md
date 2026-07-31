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
├── include/
│   └── cloud_secrets.example.h  # MQTT 凭据模板
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
.\tools\dev.ps1

# 启用云功能（需 cloud_secrets.h）
.\tools\dev.ps1 -WithCloud
```

### 配置

1. **云凭据**（MQTT 连接）：
   ```bash
   cp include/cloud_secrets.example.h include/cloud_secrets.h
   # 编辑 include/cloud_secrets.h 填入你的 MQTT Broker 信息
   ```

2. **校园网认证**（srun 认证）：
   编辑 `shared/RemoteACCore/src/config/campus_credentials.h`

3. **私有红外码**：
   红外发射命令需要 `src/private_ir_codes/` 目录。生成的红外码放入 `src/private_ir_codes/generated/`。

### 构建配置

| Profile    | ENABLE_CLOUD | ENABLE_IR_MUTATING | 用途                  |
|-----------|-------------|-------------------|-----------------------|
| Public    | 1           | 0                 | 安全默认构建          |
| Private   | 1           | 1                 | 红外实验室 / 全功能   |

通过 `dev.ps1 -Profile Public|Private` 设置。

### 上传

```powershell
.\tools\dev.ps1 -Upload
```

## 测试

```bash
pio test -e nodemcuv2
```

## 依赖

`lib/` 中的库为 vendored 方式管理。PlatformIO 会自动下载缺失的依赖项。

## 版本

参见 `VERSION` 文件。当前版本：v0.4.0-cloud-foundation。