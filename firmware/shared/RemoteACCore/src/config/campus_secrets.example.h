#pragma once
/*
 * Campus credential placeholders — EXAMPLE ONLY. NEVER commit real credentials.
 *
 * Copy to config/campus_secrets.h (git-ignored) and fill in. campus_secrets.h
 * is ONLY consulted when ENABLE_CONTROLLED_LIVE_AUTH=1 — a PRIVATE build. In
 * every public / CI build it is unreachable and CampusCredentials::ready() is
 * always false, so no live login is ever possible from a published artifact.
 *
 * To build a private, live-auth firmware:
 *   1. cp config/campus_secrets.example.h config/campus_secrets.h
 *   2. edit config/campus_secrets.h with your real id / password
 *   3. build with -DENABLE_CONTROLLED_LIVE_AUTH=1
 * The private profile/secret files must never be pushed to the public repo.
 */

#define CAMPUS_USERNAME "your_student_id_here"
#define CAMPUS_PASSWORD "your_password_here"
