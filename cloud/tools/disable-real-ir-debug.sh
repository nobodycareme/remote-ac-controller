#!/usr/bin/env bash
set -euo pipefail

# Emergency close for the temporary no-login real-IR debug window.
# Usage on the production host:
#   bash /opt/remote-ac-cloud/tools/disable-real-ir-debug.sh

ROOT="${1:-/opt/remote-ac-cloud}"
ENV_FILE="${ROOT}/deploy/secrets.env"
DB_PATH="${DB_PATH:-${ROOT}/data/app.db}"
SERVICE="${SERVICE:-remote-ac-backend}"
TS="$(date +%Y%m%d-%H%M%S)"

if [ ! -f "${ENV_FILE}" ]; then
  echo "ENV_FILE_NOT_FOUND=${ENV_FILE}" >&2
  exit 2
fi

cp -a "${ENV_FILE}" "${ENV_FILE}.bak.disable-real-ir-debug.${TS}"

ensure_key_false() {
  local key="$1"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s/^${key}=.*/${key}=false/" "${ENV_FILE}"
  else
    printf '\n%s=false\n' "${key}" >> "${ENV_FILE}"
  fi
}

ensure_key_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

ensure_key_false "REAL_IR_DEBUG_MODE"
ensure_key_false "WEB_REAL_IR_ENABLED"
ensure_key_value "REAL_IR_DEBUG_EXPIRES_AT" "1970-01-01T00:00:00Z"
ensure_key_value "REAL_IR_DEBUG_MAX_TOTAL_COMMANDS" "3"
ensure_key_value "REAL_IR_DEBUG_COOLDOWN_SECONDS" "10"
ensure_key_value "REAL_IR_PRODUCTION_CONTROL_ENABLED" "true"

if [ -f "${DB_PATH}" ]; then
  DB_PATH="${DB_PATH}" node <<'NODE'
const { DatabaseSync } = require('node:sqlite');
const db = new DatabaseSync(process.env.DB_PATH);
const now = Date.now();
db.exec('PRAGMA busy_timeout = 5000');
try { db.prepare('DELETE FROM ir_debug_sessions').run(); } catch {}
try {
  db.prepare(`UPDATE ir_debug_commands
    SET status='expired', terminal_at=?, terminal_reason='debug_disabled'
    WHERE terminal_at IS NULL`).run(now);
} catch {}
try {
  db.prepare(`UPDATE commands
    SET status='expired', completed_at=?, failure_reason='debug_disabled'
    WHERE action='ir_action'
      AND requested_by='anonymous-real-ir-debug'
      AND status IN ('pending','published')`).run(now);
} catch {}
db.close();
NODE
fi

systemctl restart "${SERVICE}"
echo "REAL_IR_DEBUG_MODE=false"
echo "WEB_REAL_IR_ENABLED=false"
echo "REAL_IR_DEBUG_EXPIRES_AT=1970-01-01T00:00:00Z"
echo "REAL_IR_DEBUG_MAX_TOTAL_COMMANDS=3"
echo "REAL_IR_DEBUG_COOLDOWN_SECONDS=10"
echo "REAL_IR_PRODUCTION_CONTROL_ENABLED=true"
echo "ANONYMOUS_DEBUG_SESSION_INVALIDATED=true"
