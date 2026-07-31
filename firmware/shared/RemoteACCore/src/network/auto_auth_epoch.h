#pragma once
/*
 * auto_auth_epoch.h — auth-epoch bookkeeping for unattended campus login.
 *
 * WHY THIS EXISTS
 * ---------------
 * The pre-v1.2.0 unattended design latched "already authenticated" for the
 * whole boot cycle (or never tracked it at all), so a Wi-Fi drop, a DHCP lease
 * change, or a portal re-appearance could never re-trigger authentication.
 * This module makes the recovery policy explicit and host-unit-testable (no
 * Arduino dependency — the same pattern as campus_auth_policy.h):
 *
 *   - A new epoch begins whenever the portal is (re)detected after an
 *     association cycle, a DHCP IP change, or a link drop.
 *   - At most ONE first-attempt ("initial" authentication) may be triggered per
 *     epoch; everything after that is a policy-paced retry owned by
 *     CampusAuthPolicy (30/60/120s backoff, hourly quota, hard-block latch).
 *   - "Authenticated IP" memory: if the DHCP lease changes after a successful
 *     login, the old success is stale and a fresh epoch is required.
 *
 * Threading through WifiManager:
 *   PORTAL_CHECK detects portal  -> beginEpoch()
 *   WIFI_ASSOC_PASS (re-link)    -> onLinkReassociated()
 *   DHCP_IP_CHANGED              -> onDhcpIpChanged(ip)
 *   AUTH_READY decision          -> mayStartAuth() / markAuthTriggered()
 *   doAuth() success             -> markAuthSuccess(ip)
 *
 * All log strings live in WifiManager (this module returns decisions only).
 */

#include <stdint.h>

class AutoAuthEpoch {
 public:
  // Start a brand-new association/portal cycle. Invalidates any latch from the
  // previous cycle so the (possibly different) network can be authenticated.
  void beginEpoch() {
    _epoch++;
    _triggered = false;
    _portalGen++;
  }

  // Wi-Fi link dropped and re-associated (same SSID, same lease possibly).
  // The old cycle is stale: allow a fresh portal detection + auth decision.
  void onLinkReassociated() {
    _triggered = false;
  }

  // DHCP lease changed. If we had authenticated on an older IP, that success
  // is invalid; a fresh decision is required (portal re-check will follow).
  void onDhcpIpChanged(uint32_t newIp) {
    _triggered = false;
    _lastIp = newIp;
  }

  // Current DHCP IP observed by the state machine (for the same-IP check).
  void noteIp(uint32_t ip) {
    _lastIp = ip;
  }

  // May the state machine START an authentication attempt right now?
  // False means this epoch already had its first attempt (retries are then
  // owned by CampusAuthPolicy, not by this latch).
  bool mayStartAuth() const { return !_triggered; }

  // Record that the first attempt of this epoch has been triggered.
  void markAuthTriggered() { _triggered = true; }

  // Record a successful authentication (and the IP it happened on).
  void markAuthSuccess(uint32_t ip) {
    _everAuthenticated = true;
    _authIp = ip;
    _lastIp = ip;
  }

  // True when a previous success exists and it was on the CURRENT IP — i.e. a
  // same-lease "already online" situation, used to skip redundant auth.
  bool authenticatedOnCurrentIp(uint32_t ip) const {
    return _everAuthenticated && _authIp == ip;
  }

  uint16_t epoch() const { return _epoch; }
  uint32_t portalGeneration() const { return _portalGen; }
  bool triggeredThisEpoch() const { return _triggered; }
  bool everAuthenticated() const { return _everAuthenticated; }
  uint32_t lastIp() const { return _lastIp; }

  void resetAll() {
    _epoch = 0;
    _portalGen = 0;
    _authIp = 0;
    _lastIp = 0;
    _triggered = false;
    _everAuthenticated = false;
  }

 private:
  uint16_t _epoch         = 0;   // wraps after 65535 cycles; 0 means "never begun"
  uint32_t _portalGen     = 0;   // portal detection generation
  uint32_t _authIp        = 0;   // IP a successful login happened on (0 = none)
  uint32_t _lastIp        = 0;   // last DHCP IP observed
  bool     _triggered     = false;
  bool     _everAuthenticated = false;
};
