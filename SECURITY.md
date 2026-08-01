**简体中文** | [English](./docs/English/security.md)

# Security Policy / 安全策略

## 支持的版本（Supported Versions）

| 版本 | 支持状态 |
|---|---|
| v1.2.x（最新发布） | 支持，建议及时更新 |
| 更早版本 | 不再维护 |

## 报告安全漏洞（Reporting a Vulnerability）

**请勿通过公开 Issue 报告安全漏洞。** 公开评论中的敏感细节会泄露给所有人。

请使用 GitHub 私有安全漏洞报告功能（仓库 `Security` → `Report a vulnerability`）。
我们会在七个自然日内确认收到有效报告（We aim to acknowledge valid security
reports within seven days），并尽可能在修复发布前保持细节私密。

## 属于安全问题的范围

- 凭据泄露或可被读取的凭据材料
- 会话、身份验证或授权绕过
- MQTT/TLS 通信或证书处理的缺陷
- 拒绝服务或资源耗尽风险
- 公开仓库中出现生产私钥、真实红外码、数据库或个人信息

## 属于普通 Bug 的范围

- 功能不符合预期、编译/构建问题、文档错误、性能问题
- 这类问题请通过公开 [Issue](https://github.com/nobodycareme/remote-ac-controller/issues) 提交

## 凭据泄露时的处理建议

如果你认为公开内容中泄露了任何生产凭据：

1. 立即通过私有漏洞报告渠道告知维护者；
2. 在维护者确认前，不要公开描述泄露的具体值；
3. 维护者将评估并安排凭据轮换与公开内容清理。

## 详细指南

- 中文：[安全策略](./docs/中文/安全策略.md)
- English: [security](./docs/English/security.md)
