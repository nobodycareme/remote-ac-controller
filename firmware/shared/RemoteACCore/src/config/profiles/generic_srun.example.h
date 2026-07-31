#pragma once
/*
 * Generic DrCOM / srun (城市热点 / drcom) captive-portal profile — EXAMPLE.
 *
 * Use this as a starting point for ANY campus network that authenticates with
 * the srun / drcom protocol (widely deployed across Chinese universities).
 *
 * Copy to profiles/generic_srun.h (git-ignored), fill in your campus's real
 * PUBLIC values, and select it with:
 *   -DCAMPUS_PROFILE_HEADER="profiles/generic_srun.h"
 *
 * These are PUBLIC, non-secret parameters. NEVER put a username/password here —
 * those go in campus_secrets.h (git-ignored), gated by
 * ENABLE_CONTROLLED_LIVE_AUTH.
 */

// OPEN campus SSID (no WPA key).
#define CAMPUS_SSID         "your-campus-open-ssid"

// srun portal host for your school.
#define CAMPUS_PORTAL_HOST  "portal.your-school.edu.cn"

// ac_id assigned by your campus. 1 is the most common default; verify with the
// portal-probe build before relying on it.
#define CAMPUS_AC_ID        1

// Operator/domain suffix — usually EMPTY. Some campuses use @lt/@yd/@dx; only
// set this if your srun server actually requires it.
#define CAMPUS_DOMAIN       ""
