// Host unit test for CampusAuthPolicy (pure logic, no Arduino deps).
// Built and run by the `host-tests` CI job with a plain host g++.
//
//   g++ -std=c++11 -I firmware/shared/RemoteACCore/src \
//       test/host/test_campus_auth_policy.cpp -o /tmp/t && /tmp/t
//
// Exits non-zero on any failure.

#include "network/campus_auth_policy.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

static int g_fail = 0;

#define CHECK(cond, msg)                                                 \
  do {                                                                   \
    if (!(cond)) {                                                       \
      std::printf("FAIL [%s:%d]: %s\n", __FILE__, __LINE__, (msg));      \
      ++g_fail;                                                          \
    }                                                                    \
  } while (0)

static void test_fresh() {
  CampusAuthPolicy p;
  CHECK(!p.hardBlocked(), "fresh policy not hard-blocked");
  CHECK(p.allows(0), "fresh policy allows at t=0");
  CHECK(p.failStreak() == 0, "fresh failStreak 0");
  CHECK(p.totalAttempts() == 0, "fresh totalAttempts 0");
  CHECK(p.windowAttempts(0) == 0, "fresh windowAttempts 0");
}

static void test_min_interval() {
  CampusAuthPolicy p;
  uint32_t now = 1000;
  CHECK(p.evaluate(now) == CAMPUS_GATE_ALLOW, "allow first attempt");
  p.noteAttempt(now);
  now += 5000;  // within 15s
  CHECK(p.evaluate(now) == CAMPUS_GATE_DENY_MIN_INTERVAL,
        "deny: too soon after attempt");
  now += 15000;  // > 15s total since last attempt
  CHECK(p.evaluate(now) == CAMPUS_GATE_ALLOW, "allow after min interval");
}

static void test_backoff_ladder() {
  CampusAuthPolicy p;
  const uint32_t base = 100000UL;
  uint32_t t = base;
  CHECK(p.evaluate(t) == CAMPUS_GATE_ALLOW, "backoff: allow at base");
  p.noteAttempt(t);
  p.noteRetryableFailure(t);

  // failStreak=1 -> 30s
  CHECK(p.evaluate(t + 1000) == CAMPUS_GATE_DENY_BACKOFF, "backoff: streak1 deny");
  CHECK(p.evaluate(t + 30000) == CAMPUS_GATE_ALLOW, "backoff: allow after 30s");
  p.noteAttempt(t + 30000);
  p.noteRetryableFailure(t + 30000);

  // failStreak=2 -> 60s
  CHECK(p.evaluate(t + 30000 + 1000) == CAMPUS_GATE_DENY_BACKOFF,
        "backoff: streak2 deny");
  CHECK(p.evaluate(t + 30000 + 60000) == CAMPUS_GATE_ALLOW,
        "backoff: allow after 60s");
  p.noteAttempt(t + 30000 + 60000);
  p.noteRetryableFailure(t + 30000 + 60000);

  // failStreak=3 -> 120s
  CHECK(p.evaluate(t + 30000 + 60000 + 120000) == CAMPUS_GATE_ALLOW,
        "backoff: allow after 120s");
  p.noteAttempt(t + 30000 + 60000 + 120000);
  p.noteRetryableFailure(t + 30000 + 60000 + 120000);

  // failStreak=4 and beyond -> 120s (cap; the ladder never grows past 120s)
  CHECK(p.evaluate(t + 30000 + 60000 + 120000 + 120000) == CAMPUS_GATE_ALLOW,
        "backoff: allow after capped 120s (streak4)");
  p.noteAttempt(t + 30000 + 60000 + 120000 + 120000);
  p.noteRetryableFailure(t + 30000 + 60000 + 120000 + 120000);
  CHECK(p.evaluate(t + 30000 + 60000 + 120000 + 120000 + 120000) ==
            CAMPUS_GATE_ALLOW,
        "backoff: allow after capped 120s (streak5)");
}

static void test_quota() {
  CampusAuthPolicy p;
  uint32_t t = 0;
  for (int i = 1; i <= 12; ++i) {
    CHECK(p.evaluate(t) == CAMPUS_GATE_ALLOW, "quota: allow within limit");
    p.noteAttempt(t);
    t += 70000;  // > 15s interval; no failure recorded so no backoff blocking
  }
  // 12 attempts consumed inside a single rolling window -> next is quota-denied.
  CHECK(p.evaluate(t) == CAMPUS_GATE_DENY_QUOTA, "quota: deny after 12");
  // Window rolls after 1h; quota resets.
  CHECK(p.evaluate(t + 3600000UL) == CAMPUS_GATE_ALLOW, "quota: allow after window");
}

static void test_hard_block() {
  CampusAuthPolicy p;
  CHECK(p.evaluate(0) == CAMPUS_GATE_ALLOW, "hb: allow before");
  p.noteHardFailure(0);
  CHECK(p.hardBlocked(), "hb: latched");
  CHECK(p.evaluate(1000000UL) == CAMPUS_GATE_DENY_HARD_BLOCK, "hb: deny while latched");
  p.clearHardBlock();
  CHECK(!p.hardBlocked(), "hb: cleared");
  CHECK(p.evaluate(0) == CAMPUS_GATE_ALLOW, "hb: allow after clear");
}

static void test_monotonic_wrap() {
  CampusAuthPolicy p;
  // Place last attempt just before the 32-bit millis() wrap.
  const uint32_t near = 0xFFFFFF00UL;
  p.noteAttempt(near);
  // Evaluate at a small value (post-wrap). Unsigned subtraction must stay safe.
  CHECK(p.evaluate(100U) == CAMPUS_GATE_DENY_MIN_INTERVAL,
        "wrap: still inside min interval across rollover");
  // (100 - 0xFFFFFF00) as uint32 == 0x100 == 256 < 15000 -> deny expected.
  CHECK(p.evaluate(near + 20000UL) == CAMPUS_GATE_ALLOW,
        "wrap: allow well after interval");
}

static void test_backoff_table() {
  CHECK(CampusAuthPolicy::backoffMs(0) == 0, "bo: streak0 -> 0");
  CHECK(CampusAuthPolicy::backoffMs(1) == 30000UL, "bo: streak1 -> 30s");
  CHECK(CampusAuthPolicy::backoffMs(2) == 60000UL, "bo: streak2 -> 60s");
  CHECK(CampusAuthPolicy::backoffMs(3) == 120000UL, "bo: streak3 -> 120s");
  CHECK(CampusAuthPolicy::backoffMs(4) == 120000UL, "bo: streak4 -> 120s (cap)");
  CHECK(CampusAuthPolicy::backoffMs(5) == 120000UL, "bo: streak5 -> 120s (cap)");
  CHECK(CampusAuthPolicy::backoffMs(99) == 120000UL, "bo: streak>=3 capped at 120s");
}

static void test_decision_str() {
  CHECK(std::strcmp(CampusAuthPolicy::decisionStr(CAMPUS_GATE_ALLOW),
                    "ALLOW") == 0,
        "str: ALLOW");
  CHECK(std::strcmp(CampusAuthPolicy::decisionStr(CAMPUS_GATE_DENY_HARD_BLOCK),
                    "HARD_BLOCK") == 0,
        "str: HARD_BLOCK");
  CHECK(std::strcmp(CampusAuthPolicy::decisionStr(CAMPUS_GATE_DENY_QUOTA),
                    "QUOTA") == 0,
        "str: QUOTA");
}

static void test_retry_delay() {
  CampusAuthPolicy p;
  p.noteAttempt(0);
  // Within min interval (15s): delay must be positive and <= 15000.
  const uint32_t d = p.retryDelayMs(5000);
  CHECK(d > 0 && d <= 15000UL, "retryDelay within min interval");
  // Hard block: delay is effectively infinite.
  p.noteHardFailure(0);
  CHECK(p.retryDelayMs(1000) == 0xFFFFFFFFUL, "retryDelay hard block infinite");
}

int main() {
  test_fresh();
  test_min_interval();
  test_backoff_ladder();
  test_quota();
  test_hard_block();
  test_monotonic_wrap();
  test_backoff_table();
  test_decision_str();
  test_retry_delay();

  if (g_fail == 0) {
    std::printf("ALL CAMPUS_AUTH_POLICY TESTS PASSED\n");
    return 0;
  }
  std::printf("%d CAMPUS_AUTH_POLICY TEST(S) FAILED\n", g_fail);
  return 1;
}
