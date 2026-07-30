# 文档清单（DOCUMENTATION_INVENTORY）

本清单记录公开 Monorepo 的 Markdown 文档现状、语言、处理方式与双语目标路径。
工作目录：`remote-ac-controller`（main 分支，v1.0.0 尚未发布）。

> 规则：中文为默认文档（无后缀）；英文使用 `_EN.md` 后缀；英文文档**保留不删**；
> 历史通过 `git mv` 保留。业务代码、固件逻辑、生产配置、Git 历史均未改动。

## 一、根级社区 / 法律文档（用户文档）

| 路径 | 当前语言 | 用户/内部 | 需中文 | 需英文 | 目标路径 | 处理方式 |
|---|---|---|---|---|---|---|
| README.md | 中文 | 用户 | 否（已存在） | — | README.md / README_EN.md | 保留并修正发布状态与链接 |
| README_EN.md | 英文 | 用户 | — | 否（已存在） | README_EN.md | 修正自链接 bug + 状态 |
| SECURITY.md | 中文（新建） | 用户 | 新建 | — | SECURITY.md | `git mv SECURITY_EN.md` 后新建中文版 |
| SECURITY_EN.md | 英文 | 用户 | — | 保留 | SECURITY_EN.md | `git mv` 自 SECURITY.md |
| SUPPORT.md | 中文（新建） | 用户 | 新建 | — | SUPPORT.md | `git mv SUPPORT_EN.md` 后新建中文版 |
| SUPPORT_EN.md | 英文 | 用户 | — | 保留 | SUPPORT_EN.md | `git mv` 自 SUPPORT.md |
| CONTRIBUTING.md | 中文（新建） | 用户 | 新建 | — | CONTRIBUTING.md | `git mv CONTRIBUTING_EN.md` 后新建中文版 |
| CONTRIBUTING_EN.md | 英文 | 用户 | — | 保留 | CONTRIBUTING_EN.md | `git mv` 自 CONTRIBUTING.md |
| CHANGELOG.md | 中文（新建） | 用户 | 新建 | — | CHANGELOG.md | `git mv` 后新建；状态改为 `[Unreleased]` |
| CHANGELOG_EN.md | 英文 | 用户 | — | 保留 | CHANGELOG_EN.md | `git mv` 自 CHANGELOG.md；状态改为 `[Unreleased]` |
| CODE_OF_CONDUCT.md | 中文（新建） | 用户 | 新建 | — | CODE_OF_CONDUCT.md | `git mv` 后新建；保留 Contributor Covenant 2.1 归属 |
| CODE_OF_CONDUCT_EN.md | 英文 | 用户 | — | 保留 | CODE_OF_CONDUCT_EN.md | `git mv` 自 CODE_OF_CONDUCT.md |
| THIRD_PARTY_NOTICES.md | 中文（新建） | 用户 | 新建 | — | THIRD_PARTY_NOTICES.md | `git mv` 后新建；IR 库许可保持"待确认" |
| THIRD_PARTY_NOTICES_EN.md | 英文 | 用户 | — | 保留 | THIRD_PARTY_NOTICES_EN.md | `git mv` 自 THIRD_PARTY_NOTICES.md |
| LICENSE | 英文（Apache-2.0 原文） | 法律 | 否 | 保留原文 | LICENSE | **未修改** |
| LICENSE_ZH.md | 中文（新建） | 法律参考 | 新建 | — | LICENSE_ZH.md | 非官方中文参考译文，顶部声明以英文原文为准 |
| NOTICE | 英文 | 法律 | 否 | 保留 | NOTICE | 未修改 |
| FINAL_RECOVERY_GUIDE.md | 英文（内部） | **内部** | — | 移除 | 移出公开树 | 已 `git rm`；私有副本存于发布归档（非公开） |

## 二、docs/ 技术文档（用户文档，全部需中英文）

| 路径 | 当前语言 | 目标路径 | 处理方式 |
|---|---|---|---|
| docs/architecture.md | 中文（新建） | architecture.md / architecture_EN.md | `git mv` 后新建中文版 |
| docs/architecture_EN.md | 英文 | 保留 | `git mv` 自 architecture.md |
| docs/deployment.md | 中文（新建） | deployment.md / deployment_EN.md | 同上 |
| docs/deployment_EN.md | 英文 | 保留 | `git mv` 自 deployment.md |
| docs/hardware.md | 中文（新建） | hardware.md / hardware_EN.md | 同上 |
| docs/hardware_EN.md | 英文 | 保留 | `git mv` 自 hardware.md |
| docs/wiring.md | 中文（新建） | wiring.md / wiring_EN.md | 同上 |
| docs/wiring_EN.md | 英文 | 保留 | `git mv` 自 wiring.md |
| docs/ir-learning.md | 中文（新建） | ir-learning.md / ir-learning_EN.md | 同上 |
| docs/ir-learning_EN.md | 英文 | 保留 | `git mv` 自 ir-learning.md |
| docs/mqtt-protocol.md | 中文（新建） | mqtt-protocol.md / mqtt-protocol_EN.md | 同上 |
| docs/mqtt-protocol_EN.md | 英文 | 保留 | `git mv` 自 mqtt-protocol.md |
| docs/security-model.md | 中文（新建） | security-model.md / security-model_EN.md | 同上 |
| docs/security-model_EN.md | 英文 | 保留 | `git mv` 自 security-model.md |
| docs/scheduling.md | 中文（新建） | scheduling.md / scheduling_EN.md | 同上 |
| docs/scheduling_EN.md | 英文 | 保留 | `git mv` 自 scheduling.md |
| docs/temperature-automation.md | 中文（新建） | temperature-automation.md / temperature-automation_EN.md | 同上 |
| docs/temperature-automation_EN.md | 英文 | 保留 | `git mv` 自 temperature-automation.md |
| docs/operations-guide.md | 中文（新建） | operations-guide.md / operations-guide_EN.md | 同上 |
| docs/operations-guide_EN.md | 英文 | 保留 | `git mv` 自 operations-guide.md |
| docs/resource-constrained-deployment.md | 中文（新建） | ..._EN.md | 同上 |
| docs/resource-constrained-deployment_EN.md | 英文 | 保留 | `git mv` 自 ...deployment.md |
| docs/troubleshooting.md | 中文（新建） | troubleshooting.md / troubleshooting_EN.md | 同上 |
| docs/troubleshooting_EN.md | 英文 | 保留 | `git mv` 自 troubleshooting.md |
| docs/backup-and-recovery.md | 中文（新建） | backup-and-recovery.md / _EN.md | 新增公开版（替换内部指南） |
| docs/backup-and-recovery_EN.md | 英文（新建） | 保留 | 新增 |
| docs/README.md | 中文（新建） | 文档导航索引 | 新增 |
| docs/README_EN.md | 英文（新建） | 文档导航索引 | 新增 |

## 三、hardware/ 子目录文档（用户文档）

| 路径 | 当前语言 | 目标路径 | 处理方式 |
|---|---|---|---|
| hardware/README.md | 中文（新建） | README.md / README_EN.md | `git mv hardware/README.md` 后新建中文版 |
| hardware/README_EN.md | 英文 | 保留 | `git mv` 自 hardware/README.md；链接改指 `_EN.md` |

## 四、子项目文档（本轮未纳入范围，仅登记）

以下为 `cloud/`、`firmware/` 子项目自带的文档，拥有各自独立的 README / SECURITY /
CONTRIBUTING / CODE_OF_CONDUCT 与 `firmware/docs/` 中文技术文档。本次任务聚焦根级与
`docs/` 双语化，未改动这些子项目文档，以保持范围清晰；如后续需要可单独立项双语化。

## 五、第三方 / 工具文档（不纳入范围）

`firmware/lib/**`（ArduinoJson、Adafruit、DHT、PubSubClient、srun-c 等上游库 README）、
`cloud/backend/node_modules/**`、`.github/` 模板：均为上游或生成内容，不纳入本清单的
本地化范围。

## 六、验证产物

| 文件 | 说明 |
|---|---|
| DOCUMENT_LINK_VALIDATION.md | 链接、语言头、BOM、围栏、敏感信息扫描结果 |
| DOCUMENT_LANGUAGE_MATRIX.csv | 中英文路径、标题、同步/链接/内容检查状态矩阵 |
