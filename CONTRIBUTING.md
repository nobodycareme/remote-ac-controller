[简体中文](./docs/中文/参与贡献.md) | [English](./docs/English/contributing.md)

# Contributing / 参与贡献

欢迎修正文档、缺陷或实现新的能力。提交前请先在相关 Issue 中说明范围，安全问题请改用 [Private Vulnerability Reporting](https://github.com/nobodycareme/remote-ac-controller/security/advisories/new)。

## 开始修改

- 固件位于 `firmware/`，Cloud 后端和前端位于 `cloud/`，PCB 资料位于 `hardware/`。
- 文档按 `docs/中文/` 与 `docs/English/` 成对维护；修改一个语言版本时，请同步核对另一个版本。
- `tools/README.md` 列出公开工具、校验脚本和发布脚本的职责。
- 不要提交真实凭据、数据库、证书私钥、真实红外数据或生成产物。

## 提交 Pull Request

1. 从最新 `main` 创建范围明确的分支。
2. 只修改完成该问题所需的文件。
3. 运行与改动相关的测试，并在 PR 中写明实际命令和结果。
4. 检查版本、文档、安全边界和 Release 资产是否受到影响。

完整的开发命令、分支约定和检查清单见[中文贡献指南](./docs/中文/参与贡献.md)与 [English contributing guide](./docs/English/contributing.md)。使用问题请查看 [SUPPORT.md](./SUPPORT.md)。
