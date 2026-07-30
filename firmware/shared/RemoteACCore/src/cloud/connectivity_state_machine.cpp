// ============================================================
// connectivity_state_machine.cpp — v0.4.0 cloud foundation
// ============================================================
#include "cloud/connectivity_state_machine.h"

ConnectivityStateMachine::ConnectivityStateMachine()
    : _state(CS_BOOT), _stateEnterMs(0), _bootMs(millis()),
      _backoffUntilMs(0), _backoffStep(0), _verifyFailStreak(0),
      _lastHealthCheckMs(0), _lastMqttAttemptMs(0)
{}

void ConnectivityStateMachine::transition(CloudState next) {
    _state = next;
    _stateEnterMs = millis();
    if (next == CS_MQTT_CONNECTING) {
        _lastMqttAttemptMs = 0; // allow immediate first attempt
    }
}

const char* ConnectivityStateMachine::stateStr(CloudState s) {
    switch (s) {
        case CS_BOOT:                return "BOOT";
        case CS_WIFI_CONNECTING:     return "WIFI_CONNECTING";
        case CS_WAITING_DHCP:        return "WAITING_DHCP";
        case CS_PORTAL_CHECKING:     return "PORTAL_CHECKING";
        case CS_CAMPUS_AUTHENTICATING: return "CAMPUS_AUTHENTICATING";
        case CS_INTERNET_READY:      return "INTERNET_READY";
        case CS_MQTT_CONNECTING:     return "MQTT_CONNECTING";
        case CS_CLOUD_ONLINE:        return "CLOUD_ONLINE";
        case CS_BACKOFF:             return "BACKOFF";
        default: return "UNKNOWN";
    }
}

uint32_t ConnectivityStateMachine::elapsedInState() const {
    return millis() - _stateEnterMs;
}

// === Auth guard ===
bool ConnectivityStateMachine::canAttemptAuth() const {
    if (_guard.consecutive_failures >= _guard.max_auth_attempts) return false;
    if (_guard.portal_likely_gone) return false;  // already authed this cycle
    uint32_t elapsed = millis() - _guard.last_auth_ms;
    return (_guard.last_auth_ms == 0) || (elapsed >= _guard.min_interval_ms);
}

void ConnectivityStateMachine::recordAuthAttempt() {
    _guard.last_auth_ms = millis();
}

void ConnectivityStateMachine::recordAuthSuccess() {
    _guard.consecutive_failures = 0;
    _guard.portal_likely_gone = true;
}

void ConnectivityStateMachine::recordAuthFailure() {
    if (_guard.consecutive_failures < _guard.max_auth_attempts)
        _guard.consecutive_failures++;
}

// === Backoff ===
uint32_t ConnectivityStateMachine::currentBackoffMs() const {
    uint32_t v = _backoffCfg.initial_ms;
    for (uint8_t i = 0; i < _backoffStep && v < _backoffCfg.max_ms; i++) {
        v *= _backoffCfg.multiplier;
    }
    return (v > _backoffCfg.max_ms) ? _backoffCfg.max_ms : v;
}

void ConnectivityStateMachine::resetBackoff() {
    _backoffStep = 0;
    _backoffUntilMs = 0;
}

void ConnectivityStateMachine::enterBackoff(const char* reason) {
    (void)reason; // reserved for future logging
    _backoffUntilMs = millis() + currentBackoffMs();
    if (_backoffStep < 10) _backoffStep++; // cap to prevent overflow
    transition(CS_BACKOFF);
}

void ConnectivityStateMachine::forceReconnect() {
    resetBackoff();
    _guard.portal_likely_gone = false;
    _verifyFailStreak = 0;
    transition(CS_WIFI_CONNECTING);
}

// === Main tick (non-blocking) ===
void ConnectivityStateMachine::tick() {
    const uint32_t now = millis();
    const uint32_t elapsed = now - _stateEnterMs;

    switch (_state) {

    case CS_BOOT:
        // Auto-start: begin Wi-Fi association immediately
        transition(CS_WIFI_CONNECTING);
        break;

    case CS_WIFI_CONNECTING:
        if (onCheckWifiConnected && onCheckWifiConnected()) {
            resetBackoff();
            transition(CS_WAITING_DHCP);
        } else if (elapsed > _timeouts.wifi_connect) {
            enterBackoff("wifi_connect_timeout");
        }
        break;

    case CS_WAITING_DHCP:
        if (onCheckDhcpReady && onCheckDhcpReady()) {
            transition(CS_PORTAL_CHECKING);
        } else if (elapsed > _timeouts.dhcp_wait) {
            enterBackoff("dhcp_timeout");
        }
        break;

    case CS_PORTAL_CHECKING:
        if (onDetectPortal) {
            bool captive = onDetectPortal();
            if (captive) {
                // Captive portal detected → need auth
                if (canAttemptAuth()) {
                    transition(CS_CAMPUS_AUTHENTICATING);
                } else {
                    // Auth not available (maxed out or min interval not met)
                    // Skip to internet check — maybe we already have internet
                    transition(CS_INTERNET_READY);
                }
            } else {
                // No portal → direct to internet verification
                transition(CS_INTERNET_READY);
            }
        } else {
            // No detector callback → skip to internet check
            transition(CS_INTERNET_READY);
        }
        break;

    case CS_CAMPUS_AUTHENTICATING:
        if (onCampusAuth) {
            recordAuthAttempt();
            bool ok = onCampusAuth();
            if (ok) {
                recordAuthSuccess();
                transition(CS_INTERNET_READY);
            } else {
                recordAuthFailure();
                enterBackoff("auth_failed");
            }
        } else {
            transition(CS_INTERNET_READY); // no auth callback → skip
        }
        break;

    case CS_INTERNET_READY:
        if (onCheckInternet) {
            if (onCheckInternet()) {
                _verifyFailStreak = 0;
                transition(CS_MQTT_CONNECTING);
            } else {
                _verifyFailStreak++;
                if (_guard.portal_likely_gone && _verifyFailStreak >= 2) {
                    // Portal may have reappeared
                    _guard.portal_likely_gone = false;
                    transition(CS_PORTAL_CHECKING);
                } else {
                    enterBackoff("internet_down");
                }
            }
        } else {
            transition(CS_MQTT_CONNECTING);
        }
        break;

    case CS_MQTT_CONNECTING:
        if (onMqttConnect) {
            // Exponential backoff with jitter for MQTT TLS retries (avoid flood).
            // First attempt is immediate (_lastMqttAttemptMs==0); subsequent attempts
            // wait _mqttRetryMs (5s, 10s, 20s, ... cap 60s + <=10% jitter).
            if (_lastMqttAttemptMs != 0 && (now - _lastMqttAttemptMs) < _mqttRetryMs) break;
            _lastMqttAttemptMs = now;
            if (onMqttConnect()) {
                _mqttRetryStep = 0;
                _mqttRetryMs   = _mqttRetryBase;
                transition(CS_CLOUD_ONLINE);
            } else if (elapsed > _timeouts.mqtt_connect) {
                enterBackoff("mqtt_connect_failed");
            } else {
                _mqttRetryStep = (_mqttRetryStep < 12) ? (_mqttRetryStep + 1) : 12;
                uint32_t base = _mqttRetryBase;
                for (uint8_t i = 1; i < _mqttRetryStep; i++) {
                    base *= 2;
                    if (base >= _mqttRetryCap) { base = _mqttRetryCap; break; }
                }
                uint32_t jitter = (uint32_t)random() % (_mqttRetryCap / 10 + 1);
                _mqttRetryMs = (base > _mqttRetryCap) ? _mqttRetryCap : (base + jitter);
            }
        } else {
            transition(CS_CLOUD_ONLINE);
        }
        break;

    case CS_CLOUD_ONLINE: {
        // 1) Wi-Fi link down -> full reconnect (incl. campus re-auth if needed)
        if (onCheckWifiConnected && !onCheckWifiConnected()) {
            Serial.println(F("MQTT_CONNECTION_LOST reason=wifi_down"));
            forceReconnect();
            return;
        }
        // 2) Periodic internet health check (keep existing behaviour)
        if (now - _lastHealthCheckMs > _timeouts.cloud_health) {
            _lastHealthCheckMs = now;
            if (onCheckInternet && !onCheckInternet()) {
                _verifyFailStreak++;
                if (_verifyFailStreak >= 2) {
                    _guard.portal_likely_gone = false;
                    forceReconnect();
                    return;
                }
            } else {
                _verifyFailStreak = 0;
            }
        }
        // 3) MQTT real-connection liveness supervision (Section 三 — the fix).
        //    Old design never re-checked the broker link, so a silent disconnect
        //    left the device stuck fake-online/real-offline forever.
        if (onMqttConnected && !onMqttConnected()) {
            Serial.print(F("MQTT_CONNECTION_LOST reason=not_connected pubsub_state="));
            Serial.print((onMqttErrorState ? onMqttErrorState() : -1));
            Serial.print(F(" bearssl_code="));
            Serial.print((onMqttSslError ? onMqttSslError() : -1));
            Serial.print(F(" wifi_status="));
            Serial.print((onCheckWifiConnected && onCheckWifiConnected()) ? 1 : 0);
            Serial.print(F(" internet_ready="));
            Serial.print((onCheckInternet && onCheckInternet()) ? 1 : 0);
            Serial.print(F(" heap="));
            Serial.print(ESP.getFreeHeap());
            Serial.print(F(" uptime="));
            Serial.print(uptimeMs() / 1000);
            Serial.print(F(" retry_in_ms="));
            Serial.println(_mqttRetryBase);
            if (onMqttDisconnect) onMqttDisconnect();
            transition(CS_MQTT_CONNECTING);
            return;
        }
        // 4) Drive the MQTT client loop (inbound processing + keepalive).
        //    Called every loop() iteration -> interval << keepalive_s (30s), no starvation.
        bool stillUp = true;
        if (onMqttLoop) {
            stillUp = onMqttLoop();
        }
        if (!stillUp) {
            Serial.println(F("MQTT_CONNECTION_LOST reason=loop_disconnected"));
            transition(CS_MQTT_CONNECTING);
            return;
        }
        // 5) Telemetry publish + supervise result
        if (onMqttPublishTelemetry) {
            TelemetryPublishResult tpr = onMqttPublishTelemetry();
            if (tpr == TelemetryPublishResult::Failed) {
                // Publish failed — determine if it is a transport disconnect
                if (onMqttConnected && !onMqttConnected()) {
                    Serial.println(F("MQTT_CONNECTION_LOST reason=publish_failed_disconnected"));
                    if (onMqttDisconnect) onMqttDisconnect();
                    transition(CS_MQTT_CONNECTING);
                    return;
                }
                // else transient (buffer full / QoS0 drop) — do not thrash the loop
            }
        }
        break;
    }

    case CS_BACKOFF:
        if (now >= _backoffUntilMs) {
            // Re-enter the connect cycle
            transition(CS_WIFI_CONNECTING);
        }
        break;
    }
}
