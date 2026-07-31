#pragma once
/*
 * Xidian University (西安电子科技大学) campus network profile — EXAMPLE.
 *
 * PUBLIC, non-secret values. Re-forensiced 2026-07-17 (see
 * docs/03_协议与接口/校园网参数实证.md).
 *
 * Copy this file to profiles/xidian.h (git-ignored), edit only if your campus
 * deployment actually differs, and point the build at it via:
 *   -DCAMPUS_PROFILE_HEADER="profiles/xidian.h"
 *
 * These four macros are the ONLY thing a profile may define. Credentials belong
 * in campus_secrets.h (git-ignored), never here.
 */

// OPEN campus SSID — no WPA pre-shared key is ever used.
#define CAMPUS_SSID         "stu-xdwlan"

// srun portal host. The srun base_url uses NO "/index_8.html" suffix; that
// suffix is only for the read-only INSECURE_PROBE_ONLY portal-detection path.
#define CAMPUS_PORTAL_HOST  "portal.campus.example.edu"

// ac_id — empirically confirmed via the portal-probe build.
#define CAMPUS_AC_ID        8

// Operator/domain suffix — EMPTY. Appending @lt/@yd/@dx is forbidden by the
// task; the srun info field is always built with an empty domain.
#define CAMPUS_DOMAIN       ""
