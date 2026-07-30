**简体中文** | [English](./CONTRIBUTING_EN.md)

# 参与贡献

感谢你关注并希望改进 Remote AC Controller 项目！

## 开始之前

这是一个 Monorepo，包含两个主要子系统：

- `firmware/` —— ESP8266 固件（PlatformIO / Arduino）。
- `cloud/` —— 后端（Node.js / Fastify / TypeScript）与前端（Vue 3 / TypeScript），以及 `broker/`、`deploy/`、`tools/`。

架构与配置细节请参阅根目录 [`README.md`](./README.md) 与 [`docs/`](./docs) 目录。

## 开发流程

1. Fork 并克隆本仓库。
2. 修改固件时，请使用现有的 `firmware/tools/dev.ps1` 入口脚本 —— **不要**直接调用 `pio` / `platformio` / `esptool`。
3. 修改云端时，先在 `cloud/backend` 与 `cloud/frontend` 安装依赖，再运行测试套件。
4. 在发起 Pull Request 前，先运行仓库根目录的辅助脚本：
   - `tools/test-all.ps1` —— 运行固件与云端的测试套件。
   - `tools/build-all.ps1` —— 运行固件与云端的构建。
5. 针对 `main` 分支发起 Pull Request。

## 代码风格

- 提交应保持聚焦，并撰写清晰、符合约定（conventional commit）的提交信息。
- 行为变更应补充或更新对应测试。
- 确保 `firmware-ci` 与 `cloud-ci`（GitHub Actions）通过。

## 安全

- **绝不**提交密钥：密码、私钥、Token、Cookie、Session、真实红外数据或生产环境文件。
- 配置模板请使用 `.example` 文件。
- 安全问题请按 [`SECURITY.md`](./SECURITY.md) 报告。

## 许可

通过贡献，你同意你的贡献内容将依据 [Apache License 2.0](./LICENSE) 授权。
