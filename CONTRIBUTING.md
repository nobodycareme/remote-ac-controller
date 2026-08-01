**简体中文** | [English](./docs/English/contributing.md)

# Contributing / 参与贡献

欢迎参与 Remote AC Controller 的开发。本文件是根级指南，可直接执行；
详细的规范文档见[参与贡献指南](./docs/中文/参与贡献.md)（English: [contributing](./docs/English/contributing.md)）。

## 环境要求

- Git、Python 3.10+（校验脚本）
- Node.js 24 与 npm（云端）
- PlatformIO Core 6.x（固件 CLI 工作流）或 Arduino IDE 2.x
- Windows PowerShell 5.1+（`tools/dev.ps1`、`tools/test-all.ps1` 等脚本）

## 仓库目录入口

| 路径 | 说明 |
|---|---|
| `firmware/agent-platformio/` | PlatformIO / command-line workflow（自动化构建与烧录） |
| `firmware/arduino-ide/` | Arduino IDE workflow |
| `firmware/shared/RemoteACCore/` | 固件业务核心（两工作流共享） |
| `cloud/backend/` | Fastify 后端 + MQTT 桥接 |
| `cloud/frontend/` | Vue 3 前端 |
| `hardware/` | PCB 与硬件文档 |
| `docs/` | 中英文文档（成对维护） |
| `tools/` | 校验与发布脚本 |

## 常用命令

### Backend

```bash
cd cloud/backend
npm ci
npx tsc --noEmit
npm run build
npm test
```

### Frontend

```bash
cd cloud/frontend
npm ci
npx tsc --noEmit
npm run build
npm test
```

### Firmware（PlatformIO / command-line workflow，public profile）

```powershell
cd firmware/agent-platformio
pwsh ./tools/dev.ps1 test -Profile public
pwsh ./tools/dev.ps1 verify -Profile public
pwsh ./tools/dev.ps1 build -Profile public
```

### Firmware（Arduino IDE workflow）

用 Arduino IDE 2.x 打开 `firmware/arduino-ide/Remote_AC_Controller/Remote_AC_Controller.ino`，
按 sketch 内 README 完成一次性配置后编译上传。

### 文档校验

```bash
python tools/check-doc-parity.py
python tools/check-doc-links.py
python tools/check-doc-language-links.py
python tools/check-public-docs.py
python tools/check-version.py
python tools/check-pcb-release.py
```

## 分支命名

- 功能/修复：`feat/<slug>`、`fix/<slug>`
- 文档：`docs/<slug>`
- 发布准备：`release/<version>`

## Commit 要求

- 清晰的主题行（type(scope): summary）。
- 一个提交只做一件事；不要用 `git commit -a` 跳过范围审查。
- 提交前运行 `git diff --check`。

## PR 检查清单

- [ ] 本地通过 Backend/Frontend/Firmware 命令（见上）
- [ ] 文档校验脚本全绿
- [ ] 不包含生产凭据、私钥、数据库、真实 IR 帧或 Windows 本地路径
- [ ] 中英文文档成对更新（如涉及 docs/）

## 禁止提交的内容

- 任何凭据：`campus_secrets.h`、`cloud_secrets.h`、`profiles/*.h`（真实值）、`secrets.env`、`.env`
- TLS 私钥/证书、数据库文件（`*.db`、`*.sqlite*`）
- 真实红外帧数据（仅允许公开状态元数据）
- `Private/`、`Evidence/`、`Archives/`、`Deliverables/` 目录内容
- 生成产物（`node_modules/`、`.build/`、`dist/`、ZIP、EXE）

## 详细指南

- 中文：[参与贡献指南](./docs/中文/参与贡献.md)、[支持说明](./docs/中文/支持说明.md)
- English: [contributing](./docs/English/contributing.md)、[support](./docs/English/support.md)
