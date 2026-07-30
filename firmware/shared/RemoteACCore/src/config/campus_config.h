#pragma once
/*
 * Campus network static parameters (Xidian University / 西安电子科技大学).
 *
 * Re-forensiced 2026-07-17 — see docs/03_协议与接口/校园网参数实证.md.
 *
 * These are PUBLIC, non-secret configuration values. They are kept separate
 * from credentials (config/campus_credentials.h) and the TLS pin
 * (config/campus_tls_pin.h).
 *
 * Constraints enforced by the task (Phase 7):
 *   - SSID is the OPEN campus network (no WPA pre-shared key).
 *   - host is portal.campus.example.edu ONLY; the srun base_url uses NO "/index_8.html"
 *     suffix (the /index_8.html hit is only used by the INSECURE_PROBE_ONLY
 *     portal-detection path, which never sends credentials).
 *   - ac_id = 8 (empirically confirmed via the portal-probe build).
 *   - domain is EMPTY: NO operator suffix (@lt / @yd / @dx) is ever appended.
 *   - The ESP8266 uses its REAL DHCP-assigned IP (never a phone/fixed IP).
 */
#define CAMPUS_SSID        "stu-xdwlan"
#define CAMPUS_PORTAL_HOST "portal.campus.example.edu"
#define CAMPUS_AC_ID       8

// Operator/domain suffix — intentionally EMPTY. Appending @lt/@yd/@dx is
// forbidden by the task; the srun info field is built with an empty domain.
#define CAMPUS_DOMAIN      ""
