/*
 * test_auto_auth_epoch.cpp — host unit tests for the auth-epoch model.
 *
 * Covers the unattended-auth cycle semantics required by the v1.2.0 spec:
 *   T03  one first-attempt per auth epoch
 *   T04  high-frequency update() cannot re-trigger after the first attempt
 *   T14  Wi-Fi drop + re-association starts a new decision cycle
 *   T15  DHCP IP change invalidates the old cycle and allows re-auth
 *   T16  portal re-appearance (new portal generation) re-enables auth
 *   T18  no portal + healthy internet: nothing to do (no stale auth latch)
 *
 * Compile (host, no Arduino):
 *   g++ -std=c++11 -Wall -Wextra -I firmware/shared/RemoteACCore/src \
 *       test/host/test_auto_auth_epoch.cpp -o /tmp/test_auto_auth_epoch && \
 *       /tmp/test_auto_auth_epoch
 */

#include <cstdio>
#include <cstdint>
#include "network/auto_auth_epoch.h"

static int g_failures = 0;

#define CHECK(cond, msg)                                                     \
  do {                                                                       \
    if (!(cond)) {                                                           \
      std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, msg);               \
      g_failures++;                                                          \
    }                                                                        \
  } while (0)

static void test_first_attempt_per_epoch() {
  AutoAuthEpoch e;
  e.beginEpoch();                       // portal detected: epoch 1
  CHECK(e.epoch() == 1, "epoch increments on portal detection");
  CHECK(e.mayStartAuth(), "first attempt allowed in fresh epoch");
  e.markAuthTriggered();
  CHECK(!e.mayStartAuth(), "second first-attempt suppressed in same epoch");

  e.beginEpoch();                       // portal re-detected: epoch 2
  CHECK(e.epoch() == 2, "epoch 2 after portal re-appearance");
  CHECK(e.mayStartAuth(), "re-auth allowed after portal re-appearance (T16)");
}

static void test_high_frequency_update_suppression() {
  AutoAuthEpoch e;
  e.beginEpoch();
  CHECK(e.mayStartAuth(), "allow on first update() tick");
  e.markAuthTriggered();
  // Many update() ticks in the same epoch: never a second first-attempt.
  for (int i = 0; i < 1000; ++i) {
    CHECK(!e.mayStartAuth(), "no re-trigger on high-frequency update (T04)");
  }
}

static void test_link_loss_invalidates() {
  AutoAuthEpoch e;
  e.beginEpoch();
  e.markAuthTriggered();
  CHECK(!e.mayStartAuth(), "blocked after trigger");
  e.onLinkReassociated();               // Wi-Fi dropped, re-associated
  CHECK(e.mayStartAuth(), "re-auth allowed after link re-association (T14)");
}

static void test_dhcp_change_invalidates() {
  AutoAuthEpoch e;
  e.beginEpoch();
  e.markAuthTriggered();
  e.markAuthSuccess(0xC0A8000A);        // authenticated on 192.168.0.10
  CHECK(e.authenticatedOnCurrentIp(0xC0A8000A), "same-IP success recognized");
  CHECK(e.authenticatedOnCurrentIp(0xC0A8000B) == false, "new IP is stale");
  e.onDhcpIpChanged(0xC0A8000B);        // lease changed
  CHECK(e.mayStartAuth(), "re-auth allowed after DHCP change (T15)");
  CHECK(e.authenticatedOnCurrentIp(0xC0A8000B) == false,
        "old auth no longer counts on new IP");
}

static void test_no_portal_no_stale_latch() {
  AutoAuthEpoch e;
  // No portal cycle ever begun: epoch 0, never triggered — auth is eligible
  // only when the state machine reaches AUTH_READY, which itself only happens
  // after a portal detection (T18 handled at the state-machine level).
  CHECK(e.epoch() == 0, "no epoch before any portal detection");
  CHECK(!e.everAuthenticated(), "never authenticated before success");
  e.beginEpoch();
  e.markAuthSuccess(0xC0A80001);
  CHECK(e.everAuthenticated(), "authenticated flag set on success");
}

int main() {
  test_first_attempt_per_epoch();
  test_high_frequency_update_suppression();
  test_link_loss_invalidates();
  test_dhcp_change_invalidates();
  test_no_portal_no_stale_latch();

  if (g_failures == 0) {
    std::printf("AUTO_AUTH_EPOCH_TESTS_PASS\n");
    return 0;
  }
  std::printf("AUTO_AUTH_EPOCH_TESTS_FAILED=%d\n", g_failures);
  return 1;
}
