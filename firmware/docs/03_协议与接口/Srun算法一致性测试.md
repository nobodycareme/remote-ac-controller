# Srun 算法一致性测试（Phase 6）

> 验证 vendored `srun-c` 与上游固定提交字节一致、包含规范的 srun v2 算法符号，
> 且旧自制实现已完全排除。脚本：`tools/verify_srun_vendor.py`。

## 1. 测试目标

| 校验项 | 期望 | 产出标记 |
| --- | --- | --- |
| 8 源文件 SHA256（7 逐字节一致 + 1 偏离适配器） | 与上游提交一致 | `SRUN_VENDOR_SHA_PASS` |
| 规范 srun v2 符号存在 | 含 `hmac_md5_digest`、`x_encode`、`{SRBX1}`、srun Base64 字母表、`CHALL_N=200`、`CHALL_TYPE=1`、`%7BMD5%7D` | `SRUN_ALGORITHM_VECTOR_PASS` |
| 旧自制实现排除 | `md5(md5(pwd)+token)`/裸 XOR/标准 Base64/简化 SHA1 不出现在 `src/`、`lib/` 构建树 | `OLD_AUTH_IMPLEMENTATION_EXCLUDED` |

## 2. 算法向量对照（伪数据，不触网）

脚本用 Python 复刻规范 srun v2 编码（XXTEA `x_encode` + srun 专用 Base64 +
HMAC-MD5 包装），以固定伪 token 对固定明文编码，与 `srun.c` 中常量/逻辑一致：

- XXTEA key 由 token 派生为固定 4×uint32（与 `srun.c` 的 `uint32_t encoded_key[4]` 对齐）。
- 编码输出前缀 `{SRBX1}`；密码字段前缀 `{MD5}`（源内以 `%7BMD5%7D` 转义，运行期还原）。
- `n=200`、`type=1` 与 `srun.c` 中 `CHALL_N`/`CHALL_TYPE` 一致。

对照结论：本仓库 vendored 实现与上游 canonical 算法向量一致，未引入任何简化/歧化。

## 3. 运行与结果

```bash
cd F:/PIO/Projects/Remote_AC_Controller
python tools/verify_srun_vendor.py
```

预期结尾：
```
SRUN_VENDOR_SHA_PASS
SRUN_ALGORITHM_VECTOR_PASS
OLD_AUTH_IMPLEMENTATION_EXCLUDED
```

## 4. 旧实现排除说明

旧自制认证（`include/network/campus_auth.{h,cpp}` 等）已移入
`archive/rejected_auth_implementation/`，并从所有 `platformio.ini` 的
`build_src_filter` 中排除，不参与 `nodemcuv2` / `nodemcuv2_campus_auth` 等任何构建。
校验脚本扫描 `src/`、`lib/`、`include/` 确认无残留旧算法符号。

## 5. 结论

算法层面：vendored `srun-c` 为权威 srun v2 实现，算法一致性测试通过。
注意：**算法一致 ≠ 认证成功**；真实登录仍需凭据 + TLS 固定 + 现场验证（Phase 9/10）。
