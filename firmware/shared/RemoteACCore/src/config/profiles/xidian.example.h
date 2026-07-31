#pragma once
/*
 * 西安电子科技大学（Xidian University）公开非秘密校园网 Profile — EXAMPLE。
 *
 * 本文件仅含公开、非秘密的网络参数，绝不包含任何账号、密码、Cookie、Token
 * 或私钥。凭据必须放在 git-ignored 的 campus_secrets.h 中，且仅在本地显式
 * 设置 ENABLE_CONTROLLED_LIVE_AUTH=1 时才参与编译。
 *
 * 参数来源（只读核验，无凭据）：
 *   - Private/Firmware/Remote_AC_Controller/include/config/campus_config.h
 *   - Private/Firmware/Remote_AC_Controller/docs/03_协议与接口/西电校园网参数实证.md
 *   - 同上 docs/00_项目总览/最终验收报告.md（v0.3.4 实时复验 2026-07-17）
 *   - 同上 docs/03_协议与接口/TLS证书固定与更新.md
 * 核验状态：XIDIAN_PROFILE_PUBLIC_PARAMETERS_VERIFIED=True（2026-07-31）。
 *
 * 真实 srun 接口规则（来自 srun-c，所有 srun 校园网通用）：
 *   - challenge = GET  https://<host>/cgi-bin/get_challenge
 *   - login     = POST https://<host>/cgi-bin/srun_portal  (action=login)
 *   - logout    = POST https://<host>/cgi-bin/srun_portal  (action=logout)
 *   - 认证所用 base_url 仅为 https://<host>，禁止追加 /index_8.html
 *   - /index_8.html 仅用于只读 INSECURE_PROBE_ONLY 门户探测（绝不发送凭据）
 *
 * TLS：ESP8266 的 BearSSL 采用**叶证书指纹固定**（setFingerprint），而不是
 * 完整 CA 链校验——后者在 80KB RAM 上不可行。指纹、签发者与有效期均为公开
 * 信息，随本 Profile 一同发布，见文末 CAMPUS_CERT_* 宏。
 *   - 指纹不匹配即中止握手（TLS_PIN_MISMATCH），凭据绝不发出；
 *   - 绝不回退 setInsecure()；
 *   - 未提供指纹的构建同样拒绝认证（config/campus_tls_pin.h 的 fail-closed 默认）。
 * 证书 2026-11-17 到期，届时必须按 campus_tls_pin.h 中的 openssl 流程重抽。
 *
 * 使用方式：
 *   cp profiles/xidian.example.h profiles/xidian.h   # xidian.h 被 git-ignore
 *   # 在 globals / 构建配置中： -DCAMPUS_PROFILE_HEADER="profiles/xidian.h"
 * 如需用自己的合法账号，复制 campus_secrets.example.h -> campus_secrets.h 并填写。
 */

// OPEN 校园 SSID —— 绝不带 WPA 预共享密钥。
#define CAMPUS_SSID         "stu-xdwlan"

// srun 门户主机（公开非秘密）。base_url 仅由此派生为 https://w.xidian.edu.cn，
// 不含任何路径后缀。
#define CAMPUS_PORTAL_HOST  "w.xidian.edu.cn"

// ac_id —— 校区/接入控制器编号，已通过门户探测实证确认。
#define CAMPUS_AC_ID        8

// 运营商/域后缀 —— 空字符串。禁止追加 @lt/@yd/@dx；
// srun info 字段始终以空域构建。
#define CAMPUS_DOMAIN       ""

// ---------------------------------------------------------------------------
// 门户 TLS 叶证书 Pin（公开信息，非秘密）
//
// 实时复验 2026-07-31（只读，无凭据、未登录）：
//   openssl s_client -connect w.xidian.edu.cn:443 -servername w.xidian.edu.cn
//     -showcerts </dev/null | openssl x509 -noout -fingerprint -sha1 -dates
//   subject = C=CN, ST=陕西省, L=西安市, O=西安电子科技大学, CN=*.xidian.edu.cn
//   issuer  = C=BE, O=GlobalSign nv-sa, CN=GlobalSign RSA OV SSL CA 2018
//   Verify return code: 0 (ok)   -> 系统信任链通过，确认为真实服务器证书而非中间人
//   结论：与 2026-07-17 首次抽取的指纹逐字符一致。
//
// 到期后本 Pin 失效，认证将 fail-closed（拒绝发送凭据），需重抽后更新。
// ---------------------------------------------------------------------------
#define CAMPUS_CERT_SHA1        "F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9"
#define CAMPUS_CERT_NOT_BEFORE  "2025-10-16"
#define CAMPUS_CERT_NOT_AFTER   "2026-11-17"
#define CAMPUS_CERT_ISSUER      "GlobalSign RSA OV SSL CA 2018"
#define CAMPUS_CERT_SUBJECT     "CN=*.xidian.edu.cn, O=Xidian University"
