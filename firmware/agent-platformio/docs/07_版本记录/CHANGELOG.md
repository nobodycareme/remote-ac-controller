# CHANGELOG

本项目遵循语义化的阶段版本记录。日期为工程内记录日期。

## [1.1.4-srun-portal-fix] - 2026-07-17（v0.3.4 · 透明门户检测修复）

> 本版本修复 v0.3.3 唯一功能性缺陷：**透明门户（captive-portal）检测在校园真实网络下
> 全部 `CAPTIVE_PORTAL_DETECTED=NO`**。根因为校园真实返回 `HTTP 200 + meta-refresh`
> 重定向（`content="0;url=srun_portal_pc?ac_id=8"`），而非 3xx；旧检测逻辑只认 3xx，
> 故误判为“无门户”，导致即使后续加入凭据也无法进入 `AUTH_READY`。
> 判定（v0.3.4）：**`READY_FOR_CONTROLLED_LIVE_AUTH`** —— 十二门禁全 PASS / 诚实
> `AUTH_BLOCKED`（仅真实登录与联网验证因仓库无 `secrets.h` 未执行）。**编译通过 ≠ 认证成功**。

### 核心变更（仅门户检测逻辑，认证算法/凭据/TLS 不变）
- `network/portal_detector.cpp`：`bodyHasCaptiveMarker()` 新增识别 meta-refresh 到
  `srun_portal_pc?ac_id=8`（校园真实形态），不再仅依赖 3xx 状态码。
- 设备实测（COM6，固件 `1.1.4-srun-portal-fix`）：
  `WIFI_ASSOC_PASS` / `PORTAL_DETECT_RESULT captive=YES` /
  `CAPTIVE_PORTAL_DETECTED=YES` / `PORTAL_HOST=portal.campus.example.edu` / `AC_ID=8` /
  `PORTAL_LOGIN_URL=https://portal.campus.example.edu/index_8.html` / `INTERNET=DOWN` /
  `AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS`（无凭据诚实阻断，未发起任何真实登录）。
- 六环境 clean build 全 PASS（v0.3.4）：`nodemcuv2` / `nodemcuv2_probe` /
  `nodemcuv2_wifi_assoc` / `nodemcuv2_portal_probe` / `nodemcuv2_campus_auth` /
  `nodemcuv2_srun_c_vector`。
- `srun_c_vector` 独立 C 向量校验：`SRUN_VENDOR_C_VECTOR_PASS`（HMAC-MD5 /
  `{SRBX1}` info / SHA1 chksum 与 Python 参考逐字节一致）。
- TLS 证书固定实时复验（2026-07-17）：`openssl s_client` 抓取指纹 ==
  `CAMPUS_CERT_SHA1`（`F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9`），
  信任链 `Verify return code: 0 (ok)`（门禁十一 PASS）。

### 验证（真实运行时证据）
- **门禁一（主固件门户检测）**：`nodemcuv2` 烧录后实测 `CAPTIVE_PORTAL_DETECTED=YES`
  （v0.3.3 全 NO 根因已解决），诚实阻断未进凭据。
- **门禁五（srun C 向量）**：`nodemcuv2_srun_c_vector` 烧录 + `verify_srun_vendor.py`
  → `SRUN_VENDOR_C_VECTOR_PASS` / `OVERALL: ALL_GATES_PASS`。
- **门禁七（30min 无凭据稳定性）**：DHT 周期读取 0 失败、heap 稳定、无 WDT 复位
  （详见 `logs/stability_30min.log`）。
- **门禁八/十（审查包）**：`tools/make_campus_review_package.ps1` 脱敏 + 敏感扫描
  staging + 六环境 `-j 1` 独立重建，产出 `Remote_AC_Controller_Review_Package_v0.3.4_*.zip`。

---

## [1.1.3-srun-vendor-integration] - 2026-07-17（srun-c 供应商集成 · **硬替换**）

> 本版本**彻底替换**了 `[1.1.2]` 中自制的校园网认证算法（见下方“被替换说明”）。
> 最终判定：**`AUTH_BLOCKED`** —— 仓库内无 `secrets.h`（真实账号密码不在本仓库），
> 设备进入 `AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS`。**编译通过 ≠ 认证成功**，未做任何真实登录。

### 核心变更（硬替换，非修补）
- **删除自制认证算法**，vendor 上游权威实现 `srun-c` v1.1.0（钉固提交
  `1881da8fa98e52041fb92f38888b3d5eb4789f7a`，WTFPL）。
  - 7 个文件与上游提交**逐字节一致**（SHA256 见
    `docs/03_协议与接口/_srun_sha256_manifest.json` + `第三方_srun-c_来源与版本.md`）。
  - 唯一允许的偏离：`lib/srun-c/src/esp8266_http_adapter_secure.cpp` 用
    `BearSSL::setFingerprint(CAMPUS_CERT_SHA1)` 证书指纹固定，替换上游
    `setInsecure()`（携带账号密码的登录请求不得裸 TLS）。
- 旧自制实现（`md5(md5(password)+token)` / 裸 XOR / 标准 Base64 / 简化 SHA1）
  **移入** `archive/rejected_auth_implementation/`，不参与任何构建
  （校验 `OLD_AUTH_IMPLEMENTATION_EXCLUDED` PASS）。
- **不保留两套并行认证算法**，不把编译通过等同于认证成功，不在凭据加载或 TLS 校验
  不正确时提交真实账号密码。

### 凭据与 TLS 修正
- `include/config/campus_credentials.h` 改用 `#if __has_include("secrets.h")`
  （**废弃**旧的 `#ifdef SECRETS_H` 误写）；单一来源 `CAMPUS_USERNAME`/`CAMPUS_PASSWORD`；
  无凭据时 `CAMPUS_CREDS_READY=NO`，启动仅打印该标志，**绝不打印**账号/密码/token/info/chksum/URL。
- `include/config/campus_tls_pin.h`：`CAMPUS_CERT_SHA1=F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9`
  （`CN=*.campus.example.edu`，GlobalSign，有效期 2025-10-16~2026-11-17，经 PC 可信 TLS 核验为真证非 MITM）。
- 保留 `INSECURE_PROBE_ONLY` 模式（仅门户检测，无 challenge/login、无凭据、无 secrets）。

### 校园参数再取证
- SSID `stu-xdwlan`、host `portal.campus.example.edu`、`base_url` 仅 `https://portal.campus.example.edu`
  （无 `/index_8.html`）、`ac_id=8`、domain 空、禁运营商后缀、ESP IP 走真实 DHCP。

### 验证（真实运行时证据）
- **算法一致性（Phase 6）**：`SRUN_VENDOR_SHA_PASS` / `SRUN_ALGORITHM_VECTOR_PASS` /
  `OLD_AUTH_IMPLEMENTATION_EXCLUDED` → `OVERALL: ALL_GATES_PASS`。
- **敏感信息扫描**：`SENSITIVE_SCAN_PASS`（无真实凭据、凭证路径无 `setInsecure()`、无私钥）。
- **四环境 clean build 全 PASS**（Phase 14）：`nodemcuv2` / `nodemcuv2_probe` /
  `nodemcuv2_wifi_assoc` / `nodemcuv2_campus_auth`。
- **独立认证环境门禁（Phase 8）**：`nodemcuv2_campus_auth` 烧录后实测
  `CAMPUS_CREDS_READY=NO` / `TLS_PIN_CONFIGURED=YES` / `WIFI_ASSOC_PASS` /
  `INSECURE_PROBE_ONLY` / `AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS`（无凭据诚实阻断）。
- **主固件集成（Phase 12）**：`nodemcuv2` 烧录后 `APP_BOOT_OK`、DHT11@D1/GPIO5 稳定读取
  （Adafruit）、IR `IR_UART_PASS`、CLI `wifi/net/campus` 响应正确；`campus status` → 阻断，
  无自动登录，heap 稳定。

### 待真实凭据验证（诚实标注，非失败）
- 真实 srun 登录（live `campus login` + 互联网可达性确认）：需 `secrets.h`（不在仓库）。
- ≥60min 联合稳定性测试（DHT+IR+Wi-Fi+auth 同跑）：凭据门控，无凭据 → 仅报告 BLOCKED。

### 被替换说明（`[1.1.2]` 已作废）
`[1.1.2-campus-wifi-integration]` 中的自制校园网认证算法（密码 `md5(md5(pw)+token)`、
`info` 裸 XOR+标准 Base64、`chksum` 简化 SHA1）**已被本版本完整移除并归档**。其代码结构、
CLI 交互与状态机骨架被保留并改为调用 vendored srun-c，但算法实现本身不再使用。
请勿再参考 `[1.1.2]` 的认证算法细节。

---

## [1.1.2-campus-wifi-integration] - 2026-07-17（校园网接入集成 · **算法已被 [1.1.3] 替换**）

### 新增
- 校园网接入模块 `network/campus_auth.*`（srun v2 客户端：challenge / login / logout，密码 `md5(md5(pw)+token)`，info xor+base64，chksum sha1）与状态机 `network/wifi_manager.*`。
- CLI 命令组 `wifi` / `net` / `campus`（受 `ENABLE_WIFI` 编译开关保护），开机不自动联网，保持既有本地 IR 控制哲学。
- 凭据模板 `include/secrets.example.h`；`secrets.h` 被 `.gitignore` 忽略，永不提交。
- 文档：`08_校园网接入/校园网门户取证.md`、`09_校园网接入/校园网集成设计说明.md`。

### 验证（真实运行时证据）
- Wi-Fi 关联：`WIFI_ASSOC_PASS`，`LOCAL_IP=10.0.x.x`，`GATEWAY=10.0.0.1`，`DNS=198.51.100.53`。
- 透明门户检测（校园 srun，`ac_id=8`）：`PORTAL_DETECTED=YES` / `CAPTIVE_PORTAL_DETECTED host=portal.campus.example.edu`。
- 主固件合并：`nodemcuv2` 编译 SUCCESS（416,416 B），烧录后 boot OK（DHT11 持续读取、heap 稳定），CLI 命令实测响应正确。
- 无凭据诚实行为：所有真实登录/联网验证路径统一标记 `AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS`，不伪造成功。

### 待真实凭据验证（诚实标注，非失败）
- 真实 srun 登录（live `campus login` + 互联网可达性确认）。
- srun `chksum` 拼接顺序、`info` xor/base64 细节、`ac_id=8` 即“校园网”身份控制器 —— 代码已实现，需首次真实凭据接入按返回微调。
- ≥60min 联合稳定性测试（DHT+IR+Wi-Fi+auth 同跑）。

---

## [1.1.1-dht11-doc-correction] - 2026-07-16（审查修正 v0.3.1）

本轮为独立审查后的修正发布（对应审查包 `Remote_AC_Controller_Review_Package_v0.3.1_*`）。

### 根因结论修正（重要）
- 不再将旧故障定性为“自定义驱动缺陷 **+ GPIO4 通道**”，也不再称“GPIO4 是唯一不稳定
  通道 / D1 是唯一稳定通道”。
- 新权威表述：旧故障的**主要问题**是自定义 `dht_service`/`rawTrace` **测试方法存在缺陷**；
  **D2/GPIO4 是否存在独立异常尚未进行 Adafruit 标准库单变量验证**；当前正式方案采用
  **已经验证稳定的 Adafruit DHT 1.4.7 + D1/GPIO5**，且未再改动接线。

### 文档 / 配置修正
- `AGENTS.md`：DHT11 引脚改正为 D1/GPIO5；IR 协议文档路径改为 `docs/04_红外模块/
  IR_PROTOCOL_ANALYSIS.md`；禁止恢复 `dht_service`/`rawTrace`；未经确认不得改 D1/D5/D6。
- `include/config.example.h`：删除 `DHT11_PIN 4` 与 IR 引脚重复定义，仅保留凭证示例；
  统一凭证约定为 `config.example.h → config.h`（单一约定，不再混用 secrets.h）。
- `include/app_config.h`：删除已无用途的 `DHT_START_SIGNAL_MS` / `DHT_BIT_TIMEOUT_US`；
  `DHT11_DISABLED_PENDING_HARDWARE_INSPECTION` → `DHT11_DISABLED_FOR_IR_PROBE`。
- `platformio.ini`：生产与 probe 环境均锁定 `platform = espressif8266@4.2.1`；
  probe 注释 GPIO4 高阻改为 D1/GPIO5 表述。
- 源码警告/调度：`Cli` 构造函数成员初始化顺序修正消除 `-Wreorder`；`ir.begin()` 提前到
  banner 之前（IR_UART_INIT 不再 baud=0）；手动 `dht read` / `dht test` 与周期读取共用
  同一 2.5s 调度，避免短时强制两帧。
- IR 模块注释：SoftwareSerial“必然导致 DHT 失败”断言改为“潜在时序干扰，因此按需开启”。
- `.gitignore`：凭证忽略项统一为 `include/config.h`。

### 审查包重设计
- `review/` 重做为 8 个标准文件（REVIEW_INSTRUCTIONS / BUILD_INFORMATION / FILE_LIST /
  MANIFEST_SHA256 / CLEANUP_SUMMARY / KNOWN_LIMITATIONS / ZIP_VERIFICATION_REPORT /
  SENSITIVE_SCAN）；移除旧 v1.1 review-summary 与无关安装日志。
- 隐私清理：用户名路径、MAC、完整 PATH、不必要绝对路径在打包前脱敏；敏感扫描新增上述四类。

---

## [1.1.0-dht11-adafruit-integration] - 2026-07-15

### 新增
- 正式 DHT11 传感器模块 `sensors/dht11_sensor.*`，封装 Adafruit DHT 库 1.4.7。
- 引脚集中管理 `config/hardware_config.h`（唯一真实来源）+ `board_pins.h` 兼容 shim。
- 文档体系重构为 `docs/00_项目总览 ~ 07_版本记录` 分类结构，新增：项目进度（35 项）、
  硬件接线与引脚分配、软件架构与模块说明、历史问题与结论修正、常见故障排查、
  环境与构建说明、本 CHANGELOG。

### 变更
- **DHT11 数据脚 D2/GPIO4 → D1/GPIO5**（当前正式方案；GPIO4 是否独立异常当时未做单变量验证）。
- 温湿度读取从自定义驱动切换为 Adafruit 标准库。
- `DHT_READ_INTERVAL_MS` 2000 → 2500（Adafruit 强制 ≥2s）。
- `platformio.ini`：`[env:nodemcuv2]` 的 `build_src_filter` 简化为 `+<*>`；顶部依赖注释
  更新为 Adafruit 库描述。

### 移除（阶段4 清理）
- 旧自定义驱动 `src/dht_service.{cpp,h}`。
- 一次性测试 sketch：`xht11_test.cpp`、`xht11_gpio5_minimal.cpp`、`dht11_gpio5_minimal.cpp`。
- 临时构建环境：`[env:nodemcuv2_xht11]`、`[env:nodemcuv2_xht11_gpio5_minimal]`、
  `[env:nodemcuv2_dht11_gpio5_minimal]`。
- 工程内旧备份目录、根目录游离日志、`.pio` 缓存（重命名→重建→删除）。

### 验证
- 阶段1 独立最小化：`DHT11_GPIO5_MINIMAL_PASS`（30/30，100%）。
- 阶段3 主工程稳定性：`DHT11_MAIN_INTEGRATION_PASS`（133/133，堆零泄漏，无复位）。
- 阶段4 清理后干净重建：`nodemcuv2` + `nodemcuv2_probe` 均 SUCCESS。

### 结论修正
- 推翻早期“主机 3.3V 供电故障”假设；主要归因于**自定义 dht_service/rawTrace 测试方法
  缺陷**（GPIO4 是否独立异常当时未做单变量验证）。详见 `05_故障排查/历史问题与结论修正.md`。

---

## [1.0.x] - 2026-07-14 ~ 07-15（历史）
- 建立离线 PlatformIO 环境（`F:\PIO\Core`，NO_PROXY 直连）。
- ESP8266 自检固件 + PowerShell 自动化脚本 + 串口采集器。
- ZJ-IR-V2 红外协议分析 + 只读 UART 探测（`IR_UART_PASS baud=115200`）。
- DHT11/XHT11 多轮排障（GPIO4 + 自定义驱动均失败，最终定位根因）。
