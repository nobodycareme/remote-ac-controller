#!/usr/bin/env bash
# cert-monitor.sh — check TLS certificate expiry for the public endpoints and
# warn before they lapse. Read-only: performs TLS handshakes only, never
# modifies the server.
#
# Endpoints are supplied by the operator via environment variables so that this
# script contains no deployment-specific host names:
#
#   WEB_HOST    hostname of the web app          (default: unset -> skipped)
#   WEB_PORT    port for the web app             (default: 443)
#   MQTT_HOST   hostname of the MQTT endpoint    (default: unset -> skipped)
#   MQTT_PORT   port for the MQTT endpoint       (default: 8883)
#   WARN_DAYS   warn when fewer days remain      (default: 30)
#   CRIT_DAYS   critical when fewer days remain  (default: 14)
#
# If your broker is published behind a TLS-passthrough reverse proxy on 443
# (SNI routing), set MQTT_PORT=443 — the SNI name still selects the broker
# certificate, so the check remains valid.
#
# Usage:
#   WEB_HOST=ac.example.com MQTT_HOST=mqtt.example.com ./cert-monitor.sh
#
# Exit codes: 0 = all OK, 2 = at least one cert inside the warning window,
#             3 = at least one cert expired or unreachable.
# Intended to run daily from a systemd timer or cron.
set -u

WARN_DAYS="${WARN_DAYS:-30}"
CRIT_DAYS="${CRIT_DAYS:-14}"
WEB_HOST="${WEB_HOST:-}"
WEB_PORT="${WEB_PORT:-443}"
MQTT_HOST="${MQTT_HOST:-}"
MQTT_PORT="${MQTT_PORT:-8883}"

check() {
  local host="$1" port="$2" sni="$3" label="$4"
  local end
  end=$(echo | timeout 15 openssl s_client -connect "${host}:${port}" -servername "${sni}" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | sed 's/notAfter=//')
  if [ -z "$end" ]; then
    echo "[$label] UNABLE_TO_FETCH ${host}:${port}"; return 3
  fi
  local end_ts now_ts remain
  end_ts=$(date -d "$end" +%s 2>/dev/null) || { echo "[$label] BAD_DATE $end"; return 3; }
  now_ts=$(date +%s)
  remain=$(( (end_ts - now_ts) / 86400 ))
  printf "[%s] %s  expires=%s  remaining_days=%d\n" "$label" "$host" "$end" "$remain"
  if [ "$remain" -lt "$CRIT_DAYS" ]; then return 3; fi
  if [ "$remain" -lt "$WARN_DAYS" ]; then return 2; fi
  return 0
}

if [ -z "$WEB_HOST" ] && [ -z "$MQTT_HOST" ]; then
  echo "CERT_MONITOR_SKIPPED: set WEB_HOST and/or MQTT_HOST" >&2
  exit 0
fi

rc=0

if [ -n "$WEB_HOST" ]; then
  check "$WEB_HOST" "$WEB_PORT" "$WEB_HOST" WEB
  r=$?; [ "$r" -gt "$rc" ] && rc="$r"
fi

if [ -n "$MQTT_HOST" ]; then
  check "$MQTT_HOST" "$MQTT_PORT" "$MQTT_HOST" MQTT
  r=$?; [ "$r" -gt "$rc" ] && rc="$r"
fi

case "$rc" in
  0) echo "CERT_MONITOR_OK" ;;
  2) echo "CERT_MONITOR_WARN: at least one cert within ${WARN_DAYS}d window" ;;
  3) echo "CERT_MONITOR_CRIT: at least one cert expired, unreachable, or < ${CRIT_DAYS}d" ;;
esac
exit "$rc"
