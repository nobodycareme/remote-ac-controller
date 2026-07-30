#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
门禁八 — 敏感信息扫描（重写版）。

扫描目标（root）：
  - 默认：本脚本所在工程的父目录（开发期自检）。
  - 若传入 argv[1]：以该目录为 root 扫描（审查包流水线传入「最终 staging 目录」，
    其下含 project/ 与 logs/，从而覆盖 project/logs/review/evidence/tools/archive）。

检查类别（HARD FAIL = 阻断打包；WARN = 检出并记录，不阻断）：
  HARD FAIL:
    1. 真实校园网账号/密码（由安全环境变量 SENSITIVE_SCAN_REAL_USER /
       SENSITIVE_SCAN_REAL_PASS 传入，绝不写日志；若命中即泄露）。
    2. secrets.h 含非占位真实值（占位为 YOUR_CAMPUS_ACCOUNT / YOUR_CAMPUS_PASSWORD）。
    3. 私钥块（-----BEGIN ... PRIVATE KEY-----）。
    4. 凭证承载路径 lib/srun-c/src/esp8266_http_adapter_secure.cpp 含 ->setInsecure()。
    5. 已拼装的完整登录 URL（含 password= 参数）。
    6. 明文 password 字面量赋值（非占位）。
    7. 完整设备 MAC 出现在 logs/ 或 setup-report.md 中（必须脱敏）。
  WARN（检出并记录，不阻断）:
    - Bearer / Authorization / Cookie / api_key 等令牌类模式。
    - Windows 绝对路径（如 F:\PIO\...）或 /c/Users/... 类 Unix 路径。
    - Windows 用户名路径（Users\<user>）。
    - 完整 MAC 出现在 src/doc/review 等非强制脱敏位置（供人工复核）。

脱敏要求（来自门禁八原文）：
  - wifi status 与串口日志 MAC 脱敏（固件 macMasked() 已做；旧 esptool 上传日志需掩码）。
  - setup-report.md 完整 MAC 脱敏。
  - SENSITIVE_SCAN_PASS 仅基于「最终 ZIP 解压内容」——即流水线必须传入 staging root。

退出码 0 当且仅当无 FAIL。
"""
import os
import re
import sys

# ---------------------------------------------------------------------------
# root 解析
# ---------------------------------------------------------------------------
if len(sys.argv) > 1 and sys.argv[1]:
    ROOT = os.path.abspath(sys.argv[1])
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 真实凭据（来自安全环境变量，绝不打印其值）
REAL_USER = os.environ.get("SENSITIVE_SCAN_REAL_USER", "")
REAL_PASS = os.environ.get("SENSITIVE_SCAN_REAL_PASS", "")

PLACEHOLDER_USER = "YOUR_CAMPUS_ACCOUNT"
PLACEHOLDER_PASS = "YOUR_CAMPUS_PASSWORD"

# ---------------------------------------------------------------------------
# 模式
# ---------------------------------------------------------------------------
# 私钥块
RE_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")
# 仅凭证路径禁止的 setInsecure 真实调用
RE_INSECURE = re.compile(r"[.\-]>setInsecure\s*\(")
# 完整设备 MAC：6 组十六进制，前后不为十六进制/冒号（避免误伤 20 字节 TLS 证书指纹）
RE_MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
# 已拼装登录 URL（含 password= 参数）
RE_FULL_LOGIN_URL = re.compile(r"srun_portal\?[^\s\"']*password=[^\s\"']+")
# 明文 password 字面量赋值（非占位）
RE_PASSWORD_LITERAL = re.compile(r"password\s*=\s*[\"']([^\"']+)[\"']")
# 令牌类（WARN）
RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}")
RE_AUTHZ = re.compile(r"Authorization:\s*\S+")
RE_COOKIE = re.compile(r"(?i)Set-Cookie:\s*\S+")
RE_APIKEY = re.compile(r"(?i)(?:api[_-]?key|secret_key|access[_-]?token)\s*[:=]\s*[\"'][A-Za-z0-9]{12,}[\"']")
# Windows / Unix 绝对路径（WARN）
RE_WINPATH = re.compile(r"[A-Za-z]:\\[^\s\"'<>|]+")
RE_UNIXPATH_USER = re.compile(r"/[a-zA-Z]/Users/[a-zA-Z0-9_.\-]+")
RE_WINUSER = re.compile(r"[\\/]Users[\\/]([a-zA-Z0-9_.\-]+)")

INSECURE_BANNED = os.path.join("lib", "srun-c", "src", "esp8266_http_adapter_secure.cpp").replace("\\", "/")

# 已知伪凭据文件：门禁五的算法向量测试用确定性伪输入（testuser/testpass/
# 固定 token），非真实账号，故 password 字面量不按真实泄露处理，仅记录 WARN。
KNOWN_FAKE_FILES = {"src/srun_c_vector_test.cpp"}

BINARY_EXT = {".bin", ".exe", ".dll", ".zip", ".png", ".jpg", ".gif", ".pdf", ".pyc"}

failures = []  # (severity, rel, msg)


def add(sev, rel, msg):
    failures.append((sev, rel, msg))


def scan_file(rel, text):
    reln = rel.replace("\\", "/")
    # 审查包流水线以「最终 staging 目录」为 root 扫描，工程被置于 <staging>/project/
    # 之下（见模块 docstring）。白名单类路径判定（vendored / KNOWN_FAKE_FILES /
    # INSECURE_BANNED）以工程根相对路径书写，因此需剥离可选的前导 "project/"，
    # 使「工程根扫描」与「staging 根扫描」两种模式下判定完全一致。此归一化仅影响
    # 白名单/凭证路径匹配，不改变任何真实泄露类硬检查的覆盖面。
    logical = reln[len("project/"):] if reln.startswith("project/") else reln
    # lib/srun-c 是 byte-identical 上游第三方代码（门禁五要求），其 README 含
    # password 文档示例、构建脚本含绝对路径——这些不是本项目的真实凭据泄露，
    # 仅对其实行「真实泄露」类硬检查（私钥/setInsecure/secrets/真实凭据/登录URL/MAC），
    # 跳过 password 字面量与路径/用户名类 WARN 检查。
    vendored = logical.startswith("lib/srun-c/")

    # 1) secrets.h 真实值
    if os.path.basename(reln) == "secrets.h":
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("//") or s.startswith("*") or s.startswith("#"):
                continue
            if "CAMPUS_USERNAME" in s and PLACEHOLDER_USER not in s and '"' in s:
                add("FAIL", rel, "secrets.h 含非占位 CAMPUS_USERNAME")
            if "CAMPUS_PASSWORD" in s and PLACEHOLDER_PASS not in s and '"' in s:
                add("FAIL", rel, "secrets.h 含非占位 CAMPUS_PASSWORD")

    # 2) 真实凭据值（来自安全环境变量）
    if REAL_USER and REAL_USER in text:
        add("FAIL", rel, "泄露真实账号值")
    if REAL_PASS and REAL_PASS in text:
        add("FAIL", rel, "泄露真实密码值")

    # 3) 私钥
    if RE_PRIVATE_KEY.search(text):
        add("FAIL", rel, "检测到私钥块")

    # 4) 凭证路径 setInsecure
    if logical == INSECURE_BANNED and RE_INSECURE.search(text):
        add("FAIL", rel, "凭证承载路径含 ->setInsecure()")

    # 5) 已拼装登录 URL
    if RE_FULL_LOGIN_URL.search(text):
        add("FAIL", rel, "检测到含 password 参数的拼装登录 URL")

    # 6) 明文 password 字面量（非占位）—— 跳过 vendored 第三方文档示例
    if not vendored:
        if logical in KNOWN_FAKE_FILES:
            add("WARN", rel, "含已知伪凭据字面量（算法向量测试，确定性输入，非真实账号）")
        else:
            for m in RE_PASSWORD_LITERAL.finditer(text):
                val = m.group(1)
                if val and PLACEHOLDER_PASS not in val:
                    add("FAIL", rel, "检测到非占位 password 字面量赋值")

    # 7) 完整 MAC：强制脱敏位置 -> FAIL
    if RE_MAC.search(text):
        if reln.startswith("logs/") or os.path.basename(reln) == "setup-report.md":
            add("FAIL", rel, "logs/ 或 setup-report.md 含完整设备 MAC（须脱敏）")
        else:
            add("WARN", rel, "含完整 MAC（非强制脱敏位置，供复核）")

    if vendored:
        return  # 第三方代码不再做路径/用户名/令牌类 WARN 检查

    # WARN: 令牌类
    for pat, name in ((RE_BEARER, "Bearer 令牌"), (RE_AUTHZ, "Authorization 头"),
                      (RE_COOKIE, "Cookie 头"), (RE_APIKEY, "api/secret key 赋值")):
        if pat.search(text):
            add("WARN", rel, "检出 %s" % name)

    # WARN: Windows/Unix 绝对路径
    if RE_WINPATH.search(text) or RE_UNIXPATH_USER.search(text):
        add("WARN", rel, "检出 Windows/Unix 绝对路径")

    # WARN: Windows 用户名
    m = RE_WINUSER.search(text)
    if m:
        add("WARN", rel, "检出 Windows 用户路径 (user=%s)" % m.group(1))


def walk():
    for dp, dns, fns in os.walk(ROOT):
        rel_dir = os.path.relpath(dp, ROOT).replace("\\", "/")
        if any(part in (".git", ".pio", "node_modules", "__pycache__", ".workbuddy", ".work")
               for part in rel_dir.split("/")):
            dns[:] = []
            continue
        for fn in fns:
            if fn.endswith(tuple(BINARY_EXT)):
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            if "\x00" in text[:4096]:
                continue  # 跳过二进制
            scan_file(rel, text)


def main():
    walk()
    fails = [x for x in failures if x[0] == "FAIL"]
    warns = [x for x in failures if x[0] == "WARN"]
    print("=== SENSITIVE SCAN (root=%s) ===" % ROOT)
    for sev, rel, msg in failures:
        print("  %s %s : %s" % (sev, rel, msg))
    print("FAIL_COUNT=%d WARN_COUNT=%d" % (len(fails), len(warns)))
    if fails:
        print("SENSITIVE_SCAN_FAIL")
        return 1
    print("SENSITIVE_SCAN_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
