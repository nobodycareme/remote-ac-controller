**简体中文** | [English](../English/srun-campus-network-porting-guide.md)

# Srun 校园网移植指南

> 将本项目的校园网自动认证功能适配到其他基于 Srun 认证系统的学校。

---

## 概述

本项目的校园网认证模块基于 Srun 4000 协议实现，但**不同学校的 Srun 系统可能存在版本差异和配置差异**。本指南说明如何将认证功能移植到你所在学校的校园网络。

**重要前提：**
- 并非所有学校都使用 Srun 认证系统
- 即使使用 Srun，不同版本（3000/4000/5000）的参数可能不同
- 不得关闭 TLS 验证来换取"能运行"
- 必须使用自己有权使用的合法校园网账号
- 遵守所在学校的网络管理规定

## 需要确认的公开参数

在校准校园网认证之前，需要收集以下参数。这些参数**不包含个人账号密码**，属于学校网络基础设施的公开信息：

### 1. Wi-Fi 参数

| 参数 | 说明 | 例子 |
|------|------|------|
| SSID | 校园 Wi-Fi 的名称 | `XDU`, `STU-XDU`, `eduroam` |
| 是否开放 | 是否需要预共享密钥 | 校园网通常为开放（Open） |
| 认证方式 | 802.1X / Open | 多数校园网 Captive Portal 为 Open |

### 2. Portal 参数

| 参数 | 说明 | 获取方法 |
|------|------|----------|
| Portal Host | Portal 服务器域名/IP | 连接校园 Wi-Fi 后，访问 HTTP 网站被重定向的地址 |
| Base URL | Portal API 基础路径 | 通常为 `http://<host>/` 或 `http://<host>:801/` |
| ac_id | 接入 ID | 从 Portal 登录页面的 HTML 表单中获取 |
| 账号格式 | 是否需要运营商后缀 | 如 `@cmcc`、`@unicom`、`@telecom` |
| 运营商后缀 | 可选运营商标识 | 部分学校需要选择运营商 |

### 3. 认证接口参数

| 参数 | 说明 |
|------|------|
| Challenge 接口 | 获取挑战码的 API 路径（通常为 `/cgi-bin/get_challenge`） |
| Login 接口 | 提交认证请求的 API 路径（通常为 `/cgi-bin/srun_portal`） |
| 认证算法 | 挑战-响应算法（MD5 / SHA1 / 其他） |
| 挑战码参数 | challenge、client_ip、ac_id、username 等 |

### 4. TLS 证书

| 参数 | 说明 |
|------|------|
| 证书指纹 | Portal 服务器的 TLS 证书 SHA256 指纹 |
| 指纹提取时间 | 提取指纹的时间戳 |
| 证书有效期 | 证书的生效和到期日期 |
| 主机名 | 证书绑定的域名 |
| 更新方法 | 证书轮换后如何更新指纹 |

## 移植步骤

### 第一步：获取 Portal 登录页

连接校园 Wi-Fi 后，访问一个 HTTP 网站（如 `http://example.com`），观察是否被重定向到 Portal 登录页面。从重定向 URL 中提取 Portal Host 和 Base URL。

### 第二步：分析登录页面

打开 Portal 登录页面，查看 HTML 源码，提取以下信息：
- `ac_id` 的值（通常在隐藏的 `<input>` 字段中）
- 登录表单的提交地址（action URL）
- 用户名和密码字段的名称

### 第三步：测试 Challenge 接口

使用浏览器开发者工具或 curl 测试 Challenge 接口：

```
GET http://<portal_host>/cgi-bin/get_challenge?callback=json&username=<test_user>
```

观察返回的 challenge 值和 res 状态码。

### 第四步：创建自定义 Profile

基于你收集到的参数，创建新的 Profile 文件：

```cpp
// profiles/my_university.example.h
#define CAMPUS_SSID "my_university_wifi"
#define CAMPUS_PORTAL_HOST "portal.myuniversity.edu.cn"
#define CAMPUS_PORTAL_BASE_URL "http://portal.myuniversity.edu.cn"
#define CAMPUS_AC_ID "1"
#define CAMPUS_ACCOUNT_SUFFIX "@cmcc"  // 如果不需要则留空
```

### 第五步：配置 TLS 证书

```cpp
// campus_tls_pin.h
#define CAMPUS_TLS_FINGERPRINT "sha256$..."  // 提取的证书指纹
#define CAMPUS_TLS_EXTRACTED "2026-07-31"
#define CAMPUS_TLS_EXPIRY "2027-07-31"
#define CAMPUS_TLS_HOST "portal.myuniversity.edu.cn"
```

**安全警告：** 不得关闭 TLS 验证。如果证书指纹不匹配，应停止发送凭据。

### 第六步：验证认证流程

通过串口监视器（115200 波特率）观察认证流程输出，如有认证失败，根据日志中的错误码调整参数。

## 常见问题

### Q: 学校不是 Srun 系统怎么办？
本项目目前仅支持 Srun 协议。如果学校使用其他认证系统（如 H3C、Ruijie、Cisco ISE），需要额外的适配工作。

### Q: 认证算法不匹配怎么办？
Srun 4000 标准使用 MD5 挑战-响应算法。如果学校使用其他算法，需要修改 `srun-c` 库中的认证实现。

### Q: 认证失败没有错误信息？
检查 Portal 地址是否正确，以及 Challenge 接口是否可达。部分学校可能使用非标准 API 路径。

### Q: 是否需要关闭 TLS 验证？
**绝对不要。** 如果 TLS 验证失败，说明证书指纹不匹配或证书已轮换，应更新指纹而非关闭验证。

## 合规要求

- 本功能仅用于用户本人有权使用的校园网账号
- 用户需遵守所在学校网络使用规定
- 本项目不用于绕过身份认证、共享账号或未经授权访问网络
- 不得使用本项目进行任何违反法律法规的活动

## 相关文档

- [西电校园网自动认证](./西电校园网自动认证.md) — 西电 Srun 配置参考
- [系统架构](./系统架构.md) — 网络认证在系统中的位置