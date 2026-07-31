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
| SSID | 校园 Wi-Fi 的名称 | 西电为 `stu-xdwlan`；其他学校形如 `eduroam`、`xxx-wlan` |
| 是否开放 | 是否需要预共享密钥 | 校园网通常为开放（Open） |
| 认证方式 | 802.1X / Open | 多数校园网 Captive Portal 为 Open |

### 2. Portal 参数

| 参数 | 说明 | 获取方法 |
|------|------|----------|
| Portal Host | Portal 服务器域名 | 连接校园 Wi-Fi 后，访问 HTTP 网站被重定向的地址；只取主机名 |
| ac_id | 接入 ID | 从 Portal 登录页面的 HTML 表单隐藏字段，或固件探测输出的 `AC_ID=` 中获取 |
| 域后缀 | 是否需要运营商后缀 | 多数学校为空；少数需要 `@lt`/`@yd`/`@dx` 等 |

> Base URL **不需要收集**：固件固定由 `CAMPUS_PORTAL_HOST` 派生为 `https://<host>`。若你的学校门户只有 HTTP 或使用非 443 端口（如 `:801`），当前实现无法直接适配——凭据只允许在固定了叶证书指纹的 TLS 连接上发送，这是不可绕过的设计约束。

### 3. 认证接口参数

| 参数 | 说明 |
|------|------|
| Challenge 接口 | 获取挑战码的 API 路径（通常为 `/cgi-bin/get_challenge`） |
| Login 接口 | 提交认证请求的 API 路径（通常为 `/cgi-bin/srun_portal`） |
| 认证算法 | 挑战-响应算法（MD5 / SHA1 / 其他） |
| 挑战码参数 | challenge、client_ip、ac_id、username 等 |

### 4. TLS 证书

| 参数 | 对应宏 | 说明 |
|------|--------|------|
| 证书指纹 | `CAMPUS_CERT_SHA1` | Portal 叶证书的 **SHA-1** 指纹（20 字节，冒号分隔） |
| 生效日期 | `CAMPUS_CERT_NOT_BEFORE` | 证书 notBefore，格式 `YYYY-MM-DD` |
| 到期日期 | `CAMPUS_CERT_NOT_AFTER` | 证书 notAfter，到期后必须重抽 |
| 签发者 | `CAMPUS_CERT_ISSUER` | 签发 CA 的 CN |
| 主体 | `CAMPUS_CERT_SUBJECT` | 证书绑定的域名/主体 |

> **必须是 SHA-1，不是 SHA-256。** ESP8266 的 BearSSL `setFingerprint()` 只接受 20 字节 SHA-1 叶证书指纹；填入 SHA-256 会导致 `tlsPinValid()` 校验失败并 fail-closed 拒绝认证。这不是安全性妥协——指纹固定的安全性来自"精确匹配某一张证书"，而非摘要算法的抗碰撞强度，且指纹是在受信网络上带外获取的。

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
GET https://<portal_host>/cgi-bin/get_challenge?callback=json&username=<test_user>
```

观察返回的 challenge 值和 res 状态码。

固件实际使用的三个端点是固定的，无需配置：

```
challenge  GET   https://<host>/cgi-bin/get_challenge
login      POST  https://<host>/cgi-bin/srun_portal   (action=login)
logout     POST  https://<host>/cgi-bin/srun_portal   (action=logout)
```

base_url 由 `CAMPUS_PORTAL_HOST` 派生为 `https://<host>`，**不含任何路径后缀**，因此没有 `CAMPUS_PORTAL_BASE_URL` 这样的宏。

### 第四步：创建自定义 Profile

以 `profiles/generic_srun.example.h` 为模板，复制为 git-ignored 的私有副本并填入你学校的真实公开参数：

```bash
cd firmware/shared/RemoteACCore/src/config/profiles
cp generic_srun.example.h my_university.h    # 非 *.example.h 的名字会被 git-ignore
```

Profile 的完整宏集合如下（这是权威列表，不存在其他 Profile 宏）：

```cpp
// profiles/my_university.h
#define CAMPUS_SSID         "my-campus-open-ssid"       // 开放 SSID，绝不含 WPA 密钥
#define CAMPUS_PORTAL_HOST  "portal.myuniversity.edu.cn" // 仅主机名，不带协议和路径
#define CAMPUS_AC_ID        1                            // 整数，不是字符串
#define CAMPUS_DOMAIN       ""                           // 运营商/域后缀，通常留空

// TLS 叶证书 Pin（见第五步）
#define CAMPUS_CERT_SHA1        "AA:BB:...:FF"
#define CAMPUS_CERT_NOT_BEFORE  "YYYY-MM-DD"
#define CAMPUS_CERT_NOT_AFTER   "YYYY-MM-DD"
#define CAMPUS_CERT_ISSUER      "<签发 CA 的 CN>"
#define CAMPUS_CERT_SUBJECT     "<证书主体>"
```

注意三个常见错误：`CAMPUS_AC_ID` 是**整数**（`1`，非 `"1"`）；域后缀宏名为 `CAMPUS_DOMAIN`（非 `CAMPUS_ACCOUNT_SUFFIX`）；多数学校 `CAMPUS_DOMAIN` 应留空，只有 srun 服务端确实要求时才填 `@lt`/`@yd`/`@dx`。

然后在构建配置中选中它：

```cpp
// Arduino IDE：Remote_AC_Controller.ino.globals.h
#define CAMPUS_PROFILE_HEADER "profiles/my_university.h"
```

```ini
; PlatformIO：注意双引号必须转义
-DCAMPUS_PROFILE_HEADER=\"profiles/my_university.h\"
```

### 第五步：提取并固定 TLS 证书指纹

**证书宏写在你的 Profile 里，不要修改 `config/campus_tls_pin.h`。** 该头文件只负责提供 fail-closed 的空串默认值，是所有 Profile 共用的基础设施。

在**受信网络**（不要在待适配的校园网内）上带外提取指纹：

```bash
openssl s_client -connect <host>:443 -servername <host> -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha1 -subject -issuer -dates
```

输出中**必须**出现 `Verify return code: 0 (ok)`。若没有，说明系统信任链未通过，你可能正在固定一个中间人代理的证书而非真实门户证书——此时必须停止，换到可信网络重抽。

把得到的值填入第四步的五个 `CAMPUS_CERT_*` 宏。

**安全警告：** 不得关闭 TLS 验证，不得回退 `setInsecure()`。指纹缺失或不匹配时，固件会打印 `TLS_PIN_MISMATCH` 并 fail-closed 中止，**凭据绝不发出**——这是设计行为，不是需要绕过的故障。

### 第六步：验证认证流程

先在**不编入凭据**的前提下验证探测链路是否正确（`ENABLE_CAMPUS_AUTH=1`、`ENABLE_CONTROLLED_LIVE_AUTH=0`），通过串口监视器（115200 波特率）确认：

```
CAPTIVE_PORTAL_DETECTED=YES
PORTAL_HOST=<你的门户主机>
AC_ID=<探测到的 ac_id>
```

若探测到的 `AC_ID` 与你在 Profile 中填写的不一致，以**探测值**为准。确认无误后再设置 `ENABLE_CONTROLLED_LIVE_AUTH=1` 并填写 `campus_secrets.h`，进行真实认证。认证失败时按日志中的 `CAMPUS_AUTH_FAIL reason=` 与 `AUTH_SERVER_ERROR=` 字段调整参数。

若因密码错误等硬失败被锁存进 `WIFI_BLOCKED`，用串口命令 `campus unblock` 解除，**不要**反复重试——自动重放被拒绝的密码会导致校园账号被锁定。

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