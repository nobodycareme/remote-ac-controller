# 工具目录 / Tools

本目录同时包含用户工具和仓库维护脚本。现有路径被 CI、发布流程、文档或源码引用，因此本轮保持路径不变；新增脚本时应先选择下面的职责分类，避免继续形成无说明的平铺目录。

## 用户工具 / User tools

| Path | Purpose |
|---|---|
| [`ir-simple-learner/`](./ir-simple-learner/) | Windows 红外学习应用的源码、依赖锁定、构建入口和双语说明。 |

普通用户通常只需要这一组。使用方法见[中文说明](./ir-simple-learner/README.md)或 [English guide](./ir-simple-learner/README.en.md)。

## Validation

| Path | Purpose |
|---|---|
| [`check-cloud-secret-authority.py`](./check-cloud-secret-authority.py) | 检查 Cloud 凭据来源和忽略规则。 |
| [`check-doc-language-links.py`](./check-doc-language-links.py) | 检查中英文文档的跨语言链接边界。 |
| [`check-doc-links.mjs`](./check-doc-links.mjs) | 检查 Cloud 文档链接和结构。 |
| [`check-doc-links.py`](./check-doc-links.py) | 检查全仓库第一方相对链接。 |
| [`check-doc-parity.py`](./check-doc-parity.py) | 检查中英文文档映射。 |
| [`check-doc-structure.mjs`](./check-doc-structure.mjs) | 检查 Cloud 文档章节结构。 |
| [`check-ir-tool-parity.py`](./check-ir-tool-parity.py) | 检查红外学习工具与固件预设的一致性。 |
| [`check-no-insecure-tls.py`](./check-no-insecure-tls.py) | 阻止不安全的 TLS 客户端配置。 |
| [`check-pcb-release.py`](./check-pcb-release.py) | 校验 PCB 制造包合同。 |
| [`check-public-docs.py`](./check-public-docs.py) | 检查公开主页、文档索引和社区入口。 |
| [`check-readme-render.py`](./check-readme-render.py) | 通过 GitHub Markdown API 验证 README 渲染。 |
| [`check-v126-reproducibility.py`](./check-v126-reproducibility.py) | 检查 v1.2.6 部署与所有者合同。 |
| [`check-version.py`](./check-version.py) | 检查各组件软件版本一致。 |
| [`security_scan.py`](./security_scan.py) | 扫描公开文件中的秘密和高风险材料。 |
| [`test-devps1-profile-contract.py`](./test-devps1-profile-contract.py) | 验证固件开发脚本的 Profile 行为。 |
| [`test-public-docs-negative.py`](./test-public-docs-negative.py) | 证明公开文档检查能拦截故意破坏。 |
| [`test-v126-reproducibility-negative.py`](./test-v126-reproducibility-negative.py) | 证明 v1.2.6 复现检查能拦截合同漂移。 |
| [`test-wifi-ssid-parity.py`](./test-wifi-ssid-parity.py) | 验证两个固件入口的 SSID 行为一致。 |
| [`validate-cloud-secrets.py`](./validate-cloud-secrets.py) | 验证 Cloud 本地秘密文件的字段与占位值。 |

## Release

| Path | Purpose |
|---|---|
| [`package-pcb-release.py`](./package-pcb-release.py) | 生成 PCB Release 制造包。 |
| [`pcb_release_contract.py`](./pcb_release_contract.py) | 定义 PCB 制造包的文件合同。 |

发布脚本会影响资产内容。修改前应先阅读[维护者发布流程](../docs/中文/维护者发布流程.md)或 [Maintainer release process](../docs/English/maintainer-release-process.md)。

## Development

| Path | Purpose |
|---|---|
| [`build-all.ps1`](./build-all.ps1) | 构建 Cloud、固件和红外学习工具。 |
| [`test-all.ps1`](./test-all.ps1) | 运行跨组件测试与校验。 |
| [`gen-wifi-ssid-cases.py`](./gen-wifi-ssid-cases.py) | 生成 SSID 边界测试样例。 |
| [`prepare_srun_arduino_library.py`](./prepare_srun_arduino_library.py) | 为 Arduino IDE 工程准备 Srun 库。 |

## 路径约定 / Path policy

- 用户文档应链接到稳定入口，不要链接临时输出。
- Validation 脚本只检查合同，不修改产品数据。
- Release 脚本必须保持资产内容可复核。
- 路径迁移需要同步更新 CI、文档、导入和发布流程，并运行完整测试；在这些条件满足前保留现有路径。
