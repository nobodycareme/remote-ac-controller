#pragma once
/*
 * campus_auth_policy.h — rate limiting and backoff policy for unattended
 * campus (srun) authentication.
 *
 * DESIGN CONSTRAINTS
 * ------------------
 * 1. Header-only and free of every Arduino dependency. `millis()` is passed in
 *    as a parameter, so the whole policy is exercised by host unit tests
 *    (test/host/test_campus_auth_policy.cpp) with a synthetic clock instead of
 *    being "verified" by staring at it.
 * 2. Deliberately conservative. An unattended device that hammers a university
 *    RADIUS server is an incident, not a feature. Every knob below is a ceiling
 *    on outbound traffic, never a floor.
 * 3. Monotonic-clock safe. millis() wraps every ~49.7 days; all comparisons use
 *    unsigned subtraction (`now - since >= window`) which stays correct across
 *    the wrap.
 *
 * POLICY
 * ------
 *   - Minimum spacing between two attempts: MIN_ATTEMPT_INTERVAL_MS.
 *   - Consecutive failures escalate the wait: 30s, 60s, 120s, 300s, then 600s
 *     for every further failure (no unbounded growth, no silent give-up).
 *   - No more than MAX_ATTEMPTS_PER_WINDOW attempts inside ROLLING_WINDOW_MS.
 *     The window is a simple counter with a reset timestamp: a ring buffer of
 *     timestamps would be more precise and is not worth the RAM here, because
 *     the counter can only ever be *stricter* than the true rolling count.
 *   - A hard block (bad credentials, wrong domain, TLS pin mismatch) latches
 *     until an operator clears it. Retrying a rejected password automatically
 *     is how accounts get locked out.
 */

#include <stdint.h>
#include <stddef.h>

// Reason an attempt was refused — surfaced verbatim over the serial console so
// field diagnosis never needs a debugger.
enum CampusAuthGateDecision {
  CAMPUS_GATE_ALLOW = 0,
  CAMPUS_GATE_DENY_HARD_BLOCK,     // latched: operator action required
  CAMPUS_GATE_DENY_MIN_INTERVAL,   // too soon after the previous attempt
  CAMPUS_GATE_DENY_BACKOFF,        // still inside the failure backoff
  CAMPUS_GATE_DENY_QUOTA           // rolling-window attempt quota exhausted
};

class CampusAuthPolicy {
 public:
  // ---- Tunables (compile-time; exposed for the unit tests) ----
  static const uint32_t MIN_ATTEMPT_INTERVAL_MS = 15000UL;        // 15 s
  static const uint32_t ROLLING_WINDOW_MS       = 3600000UL;      // 1 h
  static const uint8_t  MAX_ATTEMPTS_PER_WINDOW = 12;
  static const uint8_t  BACKOFF_STEPS           = 5;

  static uint32_t backoffMs(uint8_t failStreak) {
    // failStreak is 1-based on entry (1 == first failure).
    static const uint32_t kTable[BACKOFF_STEPS] = {
        30000UL, 60000UL, 120000UL, 300000UL, 600000UL};
    if (failStreak == 0) return 0;
    const uint8_t idx = (failStreak - 1 < BACKOFF_STEPS) ? (uint8_t)(failStreak - 1)
                                                         : (uint8_t)(BACKOFF_STEPS - 1);
    return kTable[idx];
  }

  // ---- Queries -------------------------------------------------------------

  CampusAuthGateDecision evaluate(uint32_t nowMs) const {
    if (_hardBlocked) return CAMPUS_GATE_DENY_HARD_BLOCK;

    if (_attempts > 0 && (uint32_t)(nowMs - _lastAttemptMs) < MIN_ATTEMPT_INTERVAL_MS) {
      return CAMPUS_GATE_DENY_MIN_INTERVAL;
    }
    if (_failStreak > 0) {
      const uint32_t wait = backoffMs(_failStreak);
      if ((uint32_t)(nowMs - _lastFailureMs) < wait) return CAMPUS_GATE_DENY_BACKOFF;
    }
    if (windowAttempts(nowMs) >= MAX_ATTEMPTS_PER_WINDOW) {
      return CAMPUS_GATE_DENY_QUOTA;
    }
    return CAMPUS_GATE_ALLOW;
  }

  bool allows(uint32_t nowMs) const { return evaluate(nowMs) == CAMPUS_GATE_ALLOW; }

  static const char* decisionStr(CampusAuthGateDecision d) {
    switch (d) {
      case CAMPUS_GATE_ALLOW:             return "ALLOW";
      case CAMPUS_GATE_DENY_HARD_BLOCK:   return "HARD_BLOCK";
      case CAMPUS_GATE_DENY_MIN_INTERVAL: return "MIN_INTERVAL";
      case CAMPUS_GATE_DENY_BACKOFF:      return "BACKOFF";
      case CAMPUS_GATE_DENY_QUOTA:        return "QUOTA";
      default:                            return "UNKNOWN";
    }
  }

  // Attempts already spent inside the current rolling window.
  uint8_t windowAttempts(uint32_t nowMs) const {
    if (_windowStartMs == 0 && _windowAttempts == 0) return 0;
    if ((uint32_t)(nowMs - _windowStartMs) >= ROLLING_WINDOW_MS) return 0;
    return _windowAttempts;
  }

  // Milliseconds until evaluate() could return ALLOW again. 0 means "now",
  // UINT32_MAX means "never without operator action".
  uint32_t retryDelayMs(uint32_t nowMs) const {
    switch (evaluate(nowMs)) {
      case CAMPUS_GATE_ALLOW:
        return 0;
      case CAMPUS_GATE_DENY_HARD_BLOCK:
        return 0xFFFFFFFFUL;
      case CAMPUS_GATE_DENY_MIN_INTERVAL:
        return MIN_ATTEMPT_INTERVAL_MS - (uint32_t)(nowMs - _lastAttemptMs);
      case CAMPUS_GATE_DENY_BACKOFF:
        return backoffMs(_failStreak) - (uint32_t)(nowMs - _lastFailureMs);
      case CAMPUS_GATE_DENY_QUOTA:
        return ROLLING_WINDOW_MS - (uint32_t)(nowMs - _windowStartMs);
      default:
        return MIN_ATTEMPT_INTERVAL_MS;
    }
  }

  bool hardBlocked() const { return _hardBlocked; }
  uint8_t failStreak() const { return _failStreak; }
  uint16_t totalAttempts() const { return _attempts; }

  // ---- Transitions ---------------------------------------------------------

  // Record that an attempt is being started NOW. Callers must have checked
  // allows() first; calling this unconditionally is still safe (the counters
  // simply reflect reality) but defeats the purpose of the gate.
  void noteAttempt(uint32_t nowMs) {
    if (_windowAttempts == 0 || (uint32_t)(nowMs - _windowStartMs) >= ROLLING_WINDOW_MS) {
      _windowStartMs  = nowMs;
      _windowAttempts = 0;
    }
    if (_windowAttempts < 0xFF) _windowAttempts++;
    if (_attempts < 0xFFFF) _attempts++;
    _lastAttemptMs = nowMs;
  }

  void noteSuccess(uint32_t nowMs) {
    (void)nowMs;
    _failStreak = 0;
    _lastFailureMs = 0;
  }

  // Retryable failure (timeout, transient server error, portal flapping).
  void noteRetryableFailure(uint32_t nowMs) {
    if (_failStreak < 0xFF) _failStreak++;
    _lastFailureMs = nowMs;
  }

  // Non-retryable failure. Latches until clearHardBlock().
  void noteHardFailure(uint32_t nowMs) {
    _hardBlocked = true;
    _lastFailureMs = nowMs;
  }

  // Operator escape hatch (`campus login` / `campus unblock` / power cycle).
  void clearHardBlock() {
    _hardBlocked = false;
    _failStreak = 0;
  }

  // Full reset — used when the link drops and the association is rebuilt from
  // scratch, so a fresh DHCP lease is not punished for the previous one's sins.
  // The rolling-window quota is intentionally NOT reset: a device stuck in a
  // reassociation loop must not be able to launder its attempt budget.
  void resetForNewAssociation() {
    _failStreak = 0;
    _lastFailureMs = 0;
  }

 private:
  bool     _hardBlocked    = false;
  uint8_t  _failStreak     = 0;
  uint16_t _attempts       = 0;
  uint32_t _lastAttemptMs  = 0;
  uint32_t _lastFailureMs  = 0;
  uint32_t _windowStartMs  = 0;
  uint8_t  _windowAttempts = 0;
};
