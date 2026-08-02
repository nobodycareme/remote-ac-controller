#!/usr/bin/env python3
"""Static v1.2.6 reproducibility and authorization contract checks."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FAILURES = []


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition, label):
    print(f"V126_CONTRACT {label}={'PASS' if condition else 'FAIL'}")
    if not condition:
        FAILURES.append(label)


compose = read("cloud/docker-compose.yml")
dockerfile = read("cloud/backend/Dockerfile")
acl = read("cloud/broker/acl/aclfile")
config = read("cloud/backend/src/config.ts")
auth = read("cloud/backend/src/auth.ts")
route = read("cloud/backend/src/routes/auth.ts")
backend_env = read("cloud/backend/.env.example")
deploy_env = read("cloud/deploy/secrets.env.example")

require(bool(re.search(r"eclipse-mosquitto:[^\s@]+@sha256:[0-9a-f]{64}", compose)), "MOSQUITTO_PINNED_MANIFEST")
require("CMD-SHELL" in compose and "mosquitto_sub" in compose, "BROKER_HEALTHCHECK_SHELL_SUBSCRIBE")
require("$${MQTT_USERNAME}" in compose and "$${MQTT_PASSWORD}" in compose, "BROKER_HEALTHCHECK_AUTHENTICATED")
require("$$SYS/broker/version" in compose, "BROKER_HEALTHCHECK_SYS_VERSION")
require("mosquitto_pub" not in compose.split("healthcheck:", 1)[1].split("backend:", 1)[0], "BROKER_HEALTHCHECK_NO_PUBLISH")
require("rm -f /mosquitto/run/passwordfile" in compose and "chown mosquitto:mosquitto" in compose, "BROKER_PASSWORDFILE_RESTART_SAFE")
require("topic read  $SYS/broker/version" in acl, "BACKEND_SYS_ACL_NARROW")
require("package-lock.json" in dockerfile and dockerfile.count("npm ci --no-audit --no-fund") == 2, "DOCKERFILE_LOCKED_NPM_CI")
require("npm install" not in dockerfile, "DOCKERFILE_NO_NPM_INSTALL")
require("IR_OWNER_PASSWORD" not in config and "IR_OWNER_USER" not in config, "OWNER_SCHEMA_SINGLE_CREDENTIAL")
require("config.IR_OWNER_PASSWORD" not in auth and "config.IR_OWNER_USER" not in auth, "OWNER_AUTH_SINGLE_CREDENTIAL")
require("config.WEB_PASSWORD" in route and "config.IR_OWNER_PASSWORD" not in route, "OWNER_ROUTE_WEB_PASSWORD")
require("IR_OWNER_PASSWORD" not in backend_env + deploy_env and "IR_OWNER_USER" not in backend_env + deploy_env, "OWNER_TEMPLATES_DEPRECATED")
require("REAL_IR_PRODUCTION_CONTROL_ENABLED" in config and ".default('false')" in config, "REAL_IR_DEFAULT_DISABLED")

current_ack_docs = [
    "docs/English/deployment.md",
    "docs/中文/部署指南.md",
    "docs/English/operations-guide.md",
    "docs/中文/运维指南.md",
    "docs/English/security-model.md",
    "docs/中文/安全模型.md",
    "docs/English/architecture.md",
    "docs/中文/系统架构.md",
    "docs/English/troubleshooting.md",
    "docs/中文/故障排查.md",
]
for path in current_ack_docs:
    text = read(path).lower()
    require("accepted_mock" not in text, f"ACK_DOC_NO_STALE_{path}")
    require("blocked_by_ir_policy" in text and "real_ir_control_disabled" in text, f"ACK_DOC_SAFE_RESULT_{path}")
    require("command loop failed" not in text and "闭环失败" not in text, f"ACK_DOC_NOT_FAILURE_{path}")
    require("physical ir was transmitted" not in text and "已执行物理 ir" not in text, f"ACK_DOC_NO_PHYSICAL_CLAIM_{path}")

protocol_docs = read("docs/English/mqtt-protocol.md") + read("docs/中文/MQTT协议.md")
require("accepted_mock" in protocol_docs and "legacy" in protocol_docs.lower(), "ACK_PROTOCOL_LEGACY_ONLY")
require((ROOT / "cloud/tools/generate-scrypt-hash.mjs").is_file(), "SCRYPT_TOOL_PRESENT")

if FAILURES:
    print("V126_REPRODUCIBILITY_CONTRACT_PASS=False")
    sys.exit(1)
print("V126_REPRODUCIBILITY_CONTRACT_PASS=True")
