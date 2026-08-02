#pragma once
/*
 * mqtt_client.h — lightweight MQTT-over-TLS client for ESP8266 (v0.4.0)
 *
 * Uses PubSubClient over WiFiClientSecure (BearSSL).
 * Broker connection parameters come from config/cloud_secrets.h (git-ignored).
 *
 * Security:
 *   - TLS enforced (no plaintext MQTT)
 *   - Server certificate fingerprint pinning (optional)
 *   - Username/password auth required
 *   - LWT (Last Will Testament) for offline detection
 *   - Client ID includes device identity
 *   - Reconnection with jitter
 */
#include <Arduino.h>
#include <memory>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "cloud/cloud_credentials.h"  // credential isolation gate (ENABLE_CLOUD_CREDENTIALS)
#include "cloud/mqtt_tls_policy.h"    // TLS identity plan (v1.2.5)
#include "cloud/mqtt_tls_adapter.h"   // injectable TLS application seam (v1.2.5)

// ---- Topic structure ----
// remote-ac/v1/devices/{device_id}/telemetry     — ESP publish (JSON telemetry)
// remote-ac/v1/devices/{device_id}/state         — ESP publish (retained, current state)
// remote-ac/v1/devices/{device_id}/availability  — ESP publish (LWT online/offline)
// remote-ac/v1/devices/{device_id}/commands/set  — ESP subscribe (control commands)
// remote-ac/v1/devices/{device_id}/commands/ack  — ESP publish (command acks)

#define MQTT_DEVICE_ID_DEFAULT "bedroom-ac-01"
#define MQTT_TOPIC_PREFIX "remote-ac/v1/devices/" MQTT_DEVICE_ID_DEFAULT

// === Configuration ===
// Default values are safe for Public builds (no credentials).
// When ENABLE_CLOUD_CREDENTIALS=1, the caller should populate these
// from CloudCredentials before calling begin().
struct MqttConfig {
    const char* broker_host = "";
    uint16_t    broker_port = 8883;
    const char* device_id   = MQTT_DEVICE_ID_DEFAULT;
    const char* username    = "";
    const char* password    = "";

    uint32_t    keepalive_s       = 30;
    uint32_t    reconnect_min_ms  = 3000;
    uint32_t    reconnect_max_ms  = 30000;
    uint16_t    buffer_size       = 1024;

    // TLS fingerprint pinning (optional, set to "" to disable)
    const char* tls_fingerprint   = "";

    // TLS CA certificate (PEM). Empty in Public builds. v1.2.5: begin()
    // derives the TLS identity plan from THIS field + tls_fingerprint only —
    // it never reads CloudCredentials globals directly. CA wins when both
    // are valid; fingerprint is used only when no valid CA is present.
    const char* ca_cert           = "";
};

// Forward declare PubSubClient callback type (raw function pointer for ESP8266 compatibility)
typedef void (*MqttMessageCallback)(const char* topic, const uint8_t* payload, unsigned int length);

// MQTT client loop result (explicit status for liveness supervision, Section 三)
enum class MqttLoopResult {
    Ok,             // connected and processed inbound/keepalive
    Disconnected,   // not connected (silent drop or transport close) -> needs reconnect
    TransportError  // client not initialized
};

class MqttClientWrapper {
public:
    MqttClientWrapper();
    ~MqttClientWrapper();

    // Initialize with config. Call once in setup().
    bool begin(const MqttConfig& cfg);

    // Non-blocking tick — call in loop(). Returns explicit liveness status.
    // Section 三: replaces the old void-ish bool that silently returned false
    // on a silent disconnect (root cause of fake-online / real-offline).
    MqttLoopResult loop();

    // Connection state
    bool isConnected() const;
    bool connect();              // blocking connect attempt
    void disconnect();

    // NTP time sync before TLS cert validation (prevents false cert-expiry failures)
    bool syncTime();

    // Publish helpers
    bool publishTelemetry(const char* json, bool retained = false);
    bool publishState(const char* json);
    bool publishAvailability(const char* json);  // retained
    bool publishAck(const char* json);

    // Set incoming message handler
    void onMessage(MqttMessageCallback cb) { _onMessage = cb; }
    // Forward incoming messages from the static PubSubClient callback
    void forwardMessage(const char* topic, const uint8_t* payload, unsigned int length) {
        if (_onMessage) _onMessage(topic, payload, length);
    }

    // Stats
    uint32_t reconnectCount() const { return _reconnectCount; }
    uint32_t publishCount()   const { return _publishCount; }
    uint32_t lastConnectMs()  const { return _lastConnectMs; }

    // Liveness / counters (Section 三 + 四): observable proof of runtime reconnect
    uint32_t loopCount()             const { return _loopCount; }
    uint32_t loopFailureCount()      const { return _loopFailureCount; }
    uint32_t disconnectCount()       const { return _disconnectCount; }
    uint32_t reconnectAttemptCount() const { return _reconnectAttemptCount; }
    uint32_t reconnectSuccessCount() const { return _reconnectSuccessCount; }
    uint32_t initialConnectCount()   const { return _initialConnectCount; }
    uint32_t resubscribeCount()      const { return _resubscribeCount; }
    uint32_t publishFailureCount()   const { return _publishFailureCount; }
    int      lastErrorState()        const { return _lastError; }
    int      lastSslError()          const { return _lastSslError; }

    // Configuration
    const MqttConfig& config() const { return _cfg; }

private:
    bool ensureConnected();
    String makeTopic(const char* suffix) const;
    // Publish with MQTT buffer-size guard: reject (no truncation) if payload >= buffer
    bool publishChecked(const char* topic, const char* json, bool retained);

    // Member order (C++ destroys in reverse declaration order):
    //  1. _tlsClient destroyed first  (BearSSL::WiFiClientSecure dtor)
    //  2. _trustAnchors destroyed      (BearSSL::X509List dtor)
    // This ensures X509List outlives WiFiClientSecure during teardown.
    std::unique_ptr<BearSSL::X509List> _trustAnchors;
    std::unique_ptr<BearSSL::WiFiClientSecure> _tlsClient;
    WiFiClientSecure* _tlsClient_wifi = nullptr;  // raw alias for PubSubClient ctor, no-op dtor
    std::unique_ptr<PubSubClient> _mqtt;
    MqttConfig        _cfg;
    MqttMessageCallback _onMessage;

    uint32_t _reconnectCount;
    uint32_t _publishCount;
    uint32_t _lastConnectMs;
    uint32_t _lastReconnectAttemptMs;
    bool     _initialized;
    bool     _timeSynced = false;

    // Liveness counters (Section 三 + 四)
    uint32_t _loopCount            = 0;
    uint32_t _loopFailureCount     = 0;
    uint32_t _disconnectCount      = 0;
    uint32_t _reconnectAttemptCount= 0;
    uint32_t _reconnectSuccessCount= 0;
    uint32_t _initialConnectCount  = 0;     // Section 四: successful FIRST connects (per boot)
    bool     _hasEverConnected     = false; // Section 四: distinguishes initial connect from runtime reconnect
    uint32_t _resubscribeCount     = 0;
    uint32_t _publishFailureCount  = 0;
    bool     _wasConnected         = false;
    int      _lastError            = 0;   // PubSubClient state() at disconnect
    int      _lastSslError         = 0;   // BearSSL last SSL error code
    char     _lastSslText[170]     = {0};
};
