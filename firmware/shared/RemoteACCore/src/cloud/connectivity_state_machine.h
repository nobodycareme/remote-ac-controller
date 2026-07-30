#pragma once
/*
 * connectivity_state_machine.h — non-blocking auto-recovery state machine (v0.4.0)
 *
 * States:
 *   BOOT → WIFI_CONNECTING → WAITING_DHCP → PORTAL_CHECKING
 *      → CAMPUS_AUTHENTICATING → INTERNET_READY
 *      → MQTT_CONNECTING → CLOUD_ONLINE
 *      → BACKOFF (any failure)
 *
 * Design constraints:
 *   - Non-blocking state transitions (no delay() calls > 50ms)
 *   - Each state has a timeout
 *   - Exponential backoff on repeated failures
 *   - Campus auth has minimum re-auth interval (no storm)
 *   - MQTT reconnect does NOT trigger campus re-auth
 *   - Portal re-detection only when internet verification explicitly fails
 *   - CLI loop and DHT reads continue during all states
 */
#include <Arduino.h>

enum CloudState : uint8_t {
    CS_BOOT = 0,
    CS_WIFI_CONNECTING,
    CS_WAITING_DHCP,
    CS_PORTAL_CHECKING,
    CS_CAMPUS_AUTHENTICATING,
    CS_INTERNET_READY,
    CS_MQTT_CONNECTING,
    CS_CLOUD_ONLINE,
    CS_BACKOFF
};

// Result of a telemetry publish attempt (Section 三 liveness supervision)
enum class TelemetryPublishResult {
    NotDue,    // interval not elapsed yet (normal, no action)
    Published, // published successfully
    Failed     // publish failed (buffer full or transport error)
};

// Backoff configuration (ms)
struct BackoffConfig {
    uint32_t initial_ms    = 5000;    // 5s first backoff
    uint32_t max_ms        = 120000;  // 2min max backoff
    uint32_t multiplier    = 2;       // exponential factor
};

// Per-stage timeout (ms)
struct StageTimeouts {
    uint32_t wifi_connect   = 15000;   // 15s
    uint32_t dhcp_wait      = 10000;   // 10s
    uint32_t portal_check   = 10000;   // 10s
    uint32_t campus_auth    = 30000;   // 30s
    uint32_t internet_check = 15000;   // 15s
    uint32_t mqtt_connect   = 15000;   // 15s
    uint32_t cloud_health   = 300000;  // 5min periodic internet check
};

// Re-auth guard
struct AuthGuard {
    uint32_t min_interval_ms = 300000;  // 5min minimum between auth attempts
    uint32_t last_auth_ms    = 0;
    uint8_t  consecutive_failures = 0;
    uint8_t  max_auth_attempts    = 3;  // per boot cycle
    bool     portal_likely_gone   = false; // set true after auth success
};

class ConnectivityStateMachine {
public:
    ConnectivityStateMachine();

    // Called every loop() iteration — must return quickly
    void tick();

    // State queries
    CloudState state() const { return _state; }
    static const char* stateStr(CloudState s);
    bool isOnline() const { return _state == CS_CLOUD_ONLINE; }
    bool isCloudReady() const { return _state >= CS_INTERNET_READY; }

    // Trigger a reconnection from any state
    void forceReconnect();

    // Auth guard queries
    bool canAttemptAuth() const;
    void recordAuthAttempt();
    void recordAuthSuccess();
    void recordAuthFailure();

    // Backoff
    uint32_t currentBackoffMs() const;
    void resetBackoff();
    void enterBackoff(const char* reason);

    // Stage elapsed
    uint32_t elapsedInState() const;

    // External hooks (set by main)
    // These callbacks are polled — no blocking inside them
    bool (*onCheckWifiConnected)()   = nullptr;
    bool (*onCheckDhcpReady)()       = nullptr;  // has valid IP
    bool (*onDetectPortal)()         = nullptr;  // returns true if captive portal detected
    bool (*onCampusAuth)()           = nullptr;  // returns true on success
    bool (*onCheckInternet)()        = nullptr;  // returns true if internet reachable
    bool (*onMqttConnect)()          = nullptr;  // returns true on connect

    // Section 三: MQTT real-connection liveness supervision (CS_CLOUD_ONLINE).
    // The old design trusted isOnline() without ever re-checking the broker link,
    // so a silent disconnect left the device stuck fake-online/real-offline.
    bool (*onMqttConnected)()        = nullptr;  // returns true only if broker link alive
    bool (*onMqttLoop)()             = nullptr;  // drives PubSubClient loop(); returns true if still connected
    TelemetryPublishResult (*onMqttPublishTelemetry)() = nullptr;  // publish telemetry; returns result
    void (*onMqttDisconnect)()       = nullptr;  // cleanly close stale TLS socket before reconnect
    int  (*onMqttErrorState)()       = nullptr;  // last PubSubClient state() for diagnostics
    int  (*onMqttSslError)()         = nullptr;  // last BearSSL SSL error code for diagnostics

    // Derived info
    uint8_t  authFailures() const { return _guard.consecutive_failures; }
    uint32_t uptimeMs() const { return millis() - _bootMs; }

private:
    void transition(CloudState next);

    CloudState     _state;
    uint32_t       _stateEnterMs;
    uint32_t       _bootMs;
    BackoffConfig  _backoffCfg;
    StageTimeouts  _timeouts;
    AuthGuard      _guard;

    uint32_t       _backoffUntilMs;
    uint8_t        _backoffStep;
    uint8_t        _verifyFailStreak;
    uint32_t       _lastHealthCheckMs;
    uint32_t       _lastMqttAttemptMs;

    // MQTT TLS retry: exponential backoff with jitter (avoids handshake/log flooding)
    uint32_t       _mqttRetryBase = 5000;    // 5s first retry
    uint32_t       _mqttRetryCap  = 60000;   // 60s ceiling
    uint32_t       _mqttRetryMs   = 0;       // current required wait
    uint8_t        _mqttRetryStep = 0;       // backoff exponent
};
