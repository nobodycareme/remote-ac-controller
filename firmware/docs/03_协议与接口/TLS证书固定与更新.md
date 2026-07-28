# TLS 证书固定与更新

> 校园网登录请求携带学工号与密码，绝不能在 `setInsecure()`（关闭 TLS 校验）下发送。
> 本文件说明证书指纹固定的实现、取值来源与轮换流程。

## 1. 实现方式

- 文件：`lib/srun-c/src/esp8266_http_adapter_secure.cpp`（上游 `esp8266_arduino_http.cpp`
  的唯一偏离版本）。
- 在建立 HTTPS 连接前调用 `BearSSL::WiFiClientSecure::setFingerprint(CAMPUS_CERT_SHA1)`。
- 仅固定 **leaf 证书 SHA-1 指纹**；指纹不匹配（`getLastSSLError() != 0`）时立即
  `client.stop()` **并拒绝发送任何凭据**，返回明确的 pin-mismatch 错误分类。
- 指纹常量来自 `include/config/campus_tls_pin.h`，由 `CAMPUS_CERT_SHA1` 宏提供。

## 2. 指纹取值来源（真实证书，非 MITM）

- 主机：`portal.campus.example.edu`
- 取值手段：经由 PC 可信 TLS 通道（绕过本地死 MITM 代理）用 `openssl s_client`
  抓取 leaf 证书，计算 SHA-1。
- 核验结果：`Verify return code: 0 (ok)` —— 为 GlobalSign 签发的真实证书，
  **不是**本地代理伪造证书。
- 证书字段：
  - Subject CN：`*.campus.example.edu`
  - Issuer：`GlobalSign RSA OV SSL CA 2018`
  - SHA-1：`F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9`
  - Not Before：`2025-10-16`
  - Not After：`2026-11-17`

## 2b. 实时复验记录（2026-07-17，v0.3.4 收口）

经 PC 直连可信通道（绕过本地 MITM 代理）用 `openssl s_client` 重新抓取叶证书，
与固化指纹逐项比对，结果**完全一致**：

```
$ openssl s_client -connect portal.campus.example.edu:443 -servername portal.campus.example.edu \
  | openssl x509 -noout -fingerprint -sha1 -subject -issuer -dates

sha1 Fingerprint=F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9
subject=C=CN, ST=陕西省, L=西安市, O=西安电子科技大学, CN=*.campus.example.edu
issuer=C=BE, O=GlobalSign nv-sa, CN=GlobalSign RSA OV SSL CA 2018
notBefore=Oct 16 09:22:11 2025 GMT
notAfter=Nov 17 09:11:52 2026 GMT
```

- 抓取指纹 == `CAMPUS_CERT_SHA1`（逐字符一致），证明固化的 leaf 指纹是**真实服务器证书**，
  而非本地代理重签。
- 信任链由 GlobalSign 签发，`Verify return code: 0 (ok)`；证书在有效期内
  （至 2026-11-17 前无需轮换）。
- 结论：**TLS 证书固定证据成立（门禁十一 PASS）**。

## 3. 仅保留 INSECURE_PROBE_ONLY 模式

- 唯一允许 `setInsecure()` 的位置是 `WifiManager::doPortalDetect()`（门户探测），
  且受 `INSECURE_PROBE_ONLY` 约束：**只做连通性/重定向探测，不发起 challenge、不登录、
  不读取/发送任何凭据、不打印账号密码**。
- 任何携带凭据的 challenge/login 请求都必须走指纹固定通道。

## 4. 指纹失效（过期或换证）时的处理

1. 设备侧：若 `tlsPinValid()` 失败（指纹不匹配），状态机进入 `BLOCKED`，
   打印 `TLS_PIN_MISMATCH`，**不重试、不降级到 insecure、不发送凭据**。
2. 运维侧更新流程：
   - 在 PC 上重新经可信通道抓取 `portal.campus.example.edu` 新 leaf 证书 SHA-1；
   - 仅更新 `include/config/campus_tls_pin.h` 中的 `CAMPUS_CERT_SHA1` 及有效期字段；
   - 重新 clean build 并烧录；**严禁**为图省事改回 `setInsecure()`。
3. 过渡期可临时保留旧指纹 + 新指纹双固定逻辑，但本项目当前仅固定单指纹。

## 5. 安全约束

- 不得将 `setInsecure()` 用于 credential-bearing 路径（编译期审计项）。
- 指纹常量不得与任何私钥一起提交；本仓库不持有任何私钥。
- 调试输出不得打印完整登录 URL、token、info、chksum。
