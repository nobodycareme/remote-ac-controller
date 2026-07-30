#!/usr/bin/env bash
# cert-monitor.sh — checks expiry of the two public TLS certs and warns if < N days.
#   - ac.example.com:443      (Let's Encrypt YE1 web cert, DNS-01)
#   - mqtt.example.com:443    (local-CA broker leaf cert via nginx stream SNI passthrough)
# Exit code 0 = all OK; 2 = at least one cert within WARNING window; 3 = expired.
# Intended to run from a systemd timer / cron daily. Low-risk, read-only (no server changes).
set -u
WARN_DAYS="${WARN_DAYS:-30}"
CRIT_DAYS="${CRIT_DAYS:-14}"

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

rc=0
check ac.example.com 443 ac.example.com WEB;   r1=$?
# 2026-07-29: public 8883 closed (security hardening 2026-07-20); probe production path 443 (nginx stream SNI passthrough)
check mqtt.example.com 443 mqtt.example.com MQTT; r2=$?

for r in "$r1" "$r2"; do
  if [ "$r" -gt "$rc" ]; then rc="$r"; fi
done

if [ "$rc" -eq 0 ]; then echo "CERT_MONITOR_OK"; fi
if [ "$rc" -eq 2 ]; then echo "CERT_MONITOR_WARN: at least one cert within ${WARN_DAYS}d window"; fi
if [ "$rc" -eq 3 ]; then echo "CERT_MONITOR_CRIT: at least one cert expired or < ${CRIT_DAYS}d"; fi
exit "$rc"
