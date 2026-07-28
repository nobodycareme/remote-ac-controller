# 第三方 `srun-c` 来源与版本

> 本文件记录校园网认证所 vendored 的上游实现 `srun-c` 的来源、版本钉固、完整性
> 校验与唯一允许的本地偏离（TLS 证书固定）。所有 SHA256 由
> `tools/verify_srun_vendor.py` 自动校验并写入 `docs/03_协议与接口/_srun_sha256_manifest.json`。

## 1. 上游来源（单一可信来源）

| 项 | 值 |
| --- | --- |
| 仓库 | `https://github.com/45gfg9/srun-c` |
| 钉固提交 | `1881da8fa98e52041fb92f38888b3d5eb4789f7a` |
| 版本标签 | `v1.1.0`（提交信息：`lib: bump version to 1.1.0`） |
| 许可证 | `WTFPL`（文件 `lib/srun-c/LICENSE`） |
| 协议 | srun v2（深澜 / 校园网兼容实现） |

**规则**：仅允许从该固定提交 vendor 代码；不得升级、不得从其他分支/PR 取代码；
不得在本仓库内维护第二套并行的自制认证算法。

## 2. 文件清单与 SHA256（8 个源文件）

上游仓库在固定提交下包含以下实现文件（`platform/` 在 vendor 时扁平化为
`lib/srun-c/{include,src}/`）。其中 **7 个与原提交逐字节一致**，第 8 个
（`esp8266_arduino_http.cpp`）被本仓库唯一允许的偏离版本替换。

| # | 上游路径 | vendor 路径 | SHA256（原提交） | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `srun.h` | `lib/srun-c/include/srun.h` | `eee399bda20b9968a81993700e057216f4096dceef99af52bfc3031b5d9ae234` | 逐字节一致 |
| 2 | `platform/compat.h` | `lib/srun-c/include/compat.h` | `9e8928bc5781c937569f156e29e91fc572dbf815d728dcbabe020eb44eab3dfe` | 逐字节一致 |
| 3 | `srun.c` | `lib/srun-c/src/srun.c` | `660b62b98b037a0705f2f602b892810f94bad5bd97b7133d123f38de3171a9f6` | 逐字节一致 |
| 4 | `platform/md.c` | `lib/srun-c/src/md.c` | `b4007b3c392d10197f12f8dd64b786cc5ab2956bab4c53e2d87ae94462559df2` | 逐字节一致 |
| 5 | `platform/arduinojson.cpp` | `lib/srun-c/src/arduinojson.cpp` | `bbbc3c059160b0f74d92abca487c042d59155faa268a194d18abed3bab431f7b` | 逐字节一致 |
| 6 | `LICENSE` | `lib/srun-c/LICENSE` | `0356258391e190dc1d44ea01565cfe627fe44e27dad693a0a54c2483a7b223e5` | 逐字节一致 |
| 7 | `README.md` | `lib/srun-c/README_UPSTREAM.md` | `a7c1707d63f9d37197ce823f16ec0205a52b3d68eb9266cecce510112587ea3f` | 逐字节一致（改名） |
| 8 | `platform/esp8266_arduino_http.cpp` | ——（见下方） | `66929aaddcef2cf12b8a4ff04656adaab58f8c45c2d59551d997d5ee51cbe3c1` | **被替换** |

### 第 8 个文件（唯一允许的偏离）

- 上游 `platform/esp8266_arduino_http.cpp` 使用 `client.setInsecure()` 关闭 TLS 校验。
- 携带校园网账号密码的登录请求**不得**在 `setInsecure()` 下发送（存在中间人泄露凭据风险）。
- 本仓库替换为 `lib/srun-c/src/esp8266_http_adapter_secure.cpp`
  （SHA256 `f87aa741214a329d5323b1b6f107cadbdb25ad22c175e7e170554e3068ebca05`），
  将 `setInsecure()` 改为 `BearSSL::setFingerprint(CAMPUS_CERT_SHA1)` 证书指纹固定，
  并在指纹不匹配时拒绝连接、不发送任何凭据。
- 除本适配器外，其余 7 个文件与上游**逐字节一致**，无任何算法改动。

## 3. 算法符号校验（Phase 6）

`tools/verify_srun_vendor.py` 对 vendored 代码做三项校验，全部通过：
- `SRUN_VENDOR_SHA_PASS`：8 文件 SHA256 与上方一致（第 8 个为偏离版本，单独标注）。
- `SRUN_ALGORITHM_VECTOR_PASS`：存在规范 srun v2 符号
  `hmac_md5_digest`、`x_encode`、`{SRBX1}`、srun 专用 Base64 字母表、
  `CHALL_N=200`、`CHALL_TYPE=1`、`%7BMD5%7D`（即运行期 `{MD5}`）。
- `OLD_AUTH_IMPLEMENTATION_EXCLUDED`：旧自制实现
  （`md5(md5(password)+token)` / 裸 XOR / 标准 Base64 / 简化 SHA1）仅存于
  `archive/rejected_auth_implementation/`，未参与任何构建。

## 4. 依赖与打包

- `lib/srun-c/library.json`：`name=srun-c`，`version=1.1.0`，
  `frameworks=arduino`，`platforms=espressif8266`，
  依赖 `bblanchon/ArduinoJson@6.21.5`（用于 `arduinojson.cpp` 的 JSON 解析）。
- 该依赖已在离线缓存中预装（`F:/PIO/Core/lib` 或 `.pio/libdeps/<env>/ArduinoJson`），
  全新 clean build 不再需要网络拉取。

## 5. 复验命令

```bash
cd F:/PIO/Projects/Remote_AC_Controller
python tools/verify_srun_vendor.py
# 期望输出结尾：
#   SRUN_VENDOR_SHA_PASS
#   SRUN_ALGORITHM_VECTOR_PASS
#   OLD_AUTH_IMPLEMENTATION_EXCLUDED
```
