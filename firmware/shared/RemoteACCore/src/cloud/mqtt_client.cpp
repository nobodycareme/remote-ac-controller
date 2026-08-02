#include "config/feature_gates.h"
#if ENABLE_CLOUD
// ============================================================
// mqtt_client.cpp — MQTT-over-TLS client for ESP8266 (v0.4.0)
// ============================================================
#include "cloud/mqtt_client.h"
#include <ESP8266WiFi.h>
#include <time.h>

// Built-in PubSubClient callback adapter
static MqttClientWrapper* g_activeMqtt = nullptr;

static void pubsubCallback(char* topic, uint8_t* payload, unsigned int length) {
    if (g_activeMqtt) {
        g_activeMqtt->forwardMessage(topic, payload, length);
    }
}

MqttClientWrapper::MqttClientWrapper()
    : _reconnectCount(0), _publishCount(0),
      _lastConnectMs(0), _lastReconnectAttemptMs(0),
      _initialized(false)
{}

MqttClientWrapper::~MqttClientWrapper() {
    if (_mqtt) { _mqtt->disconnect(); }
    // _mqtt, _tlsClient, and _trustAnchors are unique_ptr — automatically destroyed
    // in reverse declaration order: _mqtt first, then _tlsClient, then _trustAnchors.
    // This ensures X509List outlives WiFiClientSecure during teardown.
    // No manual delete — unique_ptr eliminates the -Wdelete-non-virtual-dtor warning.
}

bool MqttClientWrapper::begin(const MqttConfig& cfg) {
    _cfg = cfg;

    // Validate minimal config
    if (!cfg.broker_host || strlen(cfg.broker_host) == 0) {
        Serial.println(F("MQTT_CFG_ERR: broker_host empty"));
        return false;
    }

    // v1.2.5: derive the TLS identity plan from the incoming config ONLY.
    // begin() never reads CloudCredentials globals — the caller (RemoteACApp)
    // fills cfg.ca_cert / cfg.tls_fingerprint explicitly, so tests can build
    // CA-only and fingerprint-only configs directly.
    const MqttTlsPlan tlsPlan = makeMqttTlsPlan(cfg.ca_cert, cfg.tls_fingerprint);
    if (!tlsPlan.valid) {
        // Non-sensitive error code only; never the fingerprint or CA content.
        Serial.print(F("MQTT_TLS_CONFIG_REJECTED reason="));
        Serial.println(tlsPlan.reason ? tlsPlan.reason : "TLS_MATERIAL_MISSING");
        return false;
    }
    Serial.print(F("MQTT_TLS_MODE="));
    Serial.println(mqttTlsModeLabel(tlsPlan.mode));

    // Create TLS client (unique_ptr — lifetime tied to MqttClientWrapper)
    _tlsClient.reset(new BearSSL::WiFiClientSecure());
    // --- BearSSL memory footprint (ESP8266 heap-constrained) ---------------
    // The default BearSSL rx buffer is 16384 bytes. On this device the
    // private-production build (IR mutating tables + controlled-live-auth)
    // raises static RAM use, leaving only ~25KB free at handshake time. A
    // 16KB contiguous alloc + X.509 validation working memory then fails
    // (OOM), aborting the handshake with a generic error (bearssl_code=0,
    // heap crushed from ~25KB to ~4.5KB). Shrinking the rx buffer to 4096
    // (enough to hold our small private-CA cert-chain record) frees ~12KB of
    // handshake headroom. This is a MEMORY optimization only — it does NOT
    // weaken security: the TLS identity below (CA or fingerprint) is
    // unchanged and setInsecure() is NEVER used.
    _tlsClient->setBufferSizes(4096, 1024);   // rx=4096, tx=1024

    // v1.2.5: apply the plan through the SAME seam the host tests exercise.
    // CA_CERT  -> setTrustAnchors(X509List)
    // FINGERPRINT_SHA1 -> setFingerprint(uint8_t[20]) (real BearSSL API)
    // setInsecure() is NEVER used (spec). Without a usable identity (Public
    // build) begin() returns false here -> connect() never runs -> safe.
    Esp8266MqttTlsAdapter tlsAdapter(*_tlsClient, _trustAnchors);
    if (!applyMqttTlsPlan(tlsAdapter, tlsPlan)) {
        Serial.print(F("MQTT_TLS_APPLY_FAILED mode="));
        Serial.println(mqttTlsModeLabel(tlsPlan.mode));
        return false;
    }

    // Raw pointer alias for PubSubClient constructor (takes WiFiClient& reference)
    _tlsClient_wifi = _tlsClient.get();

    // Create PubSubClient
    _mqtt.reset(new PubSubClient(*_tlsClient_wifi));
    _mqtt->setServer(cfg.broker_host, cfg.broker_port);
    _mqtt->setBufferSize(cfg.buffer_size);
    _mqtt->setKeepAlive(cfg.keepalive_s);
    _mqtt->setSocketTimeout(15);   // 15s socket timeout (spec: 10-15s)

    // NOTE: LWT is passed via the connect() overload (PubSubClient v2.8 has no setWill()).
    // Set callback
    g_activeMqtt = this;
    _mqtt->setCallback(pubsubCallback);

    _initialized = true;
    Serial.println(F("MQTT_CLIENT_INIT_OK"));
    return true;
}

bool MqttClientWrapper::syncTime() {
    time_t now = time(nullptr);
    if (_timeSynced && now > 1600000000) return true;
    // NTP before TLS validation (ESP8266 uses SNTP via configTime)
    configTime(0, 0, "pool.ntp.org", "time.nist.gov", "cn.ntp.org.cn");
    for (uint8_t i = 0; i < 30; i++) {
        now = time(nullptr);
        if (now > 1600000000) { _timeSynced = true; return true; }
        yield();
        delay(100);
    }
    Serial.println(F("NTP_SYNC_WARN time not yet valid"));
    return false;
}

bool MqttClientWrapper::connect() {
    if (!_initialized) return false;
    // Section 四: only count an ATTEMPT as a *reconnect* once we have ever connected
    // before. The very first boot connect is an INITIAL connect, not a reconnect, so it
    // must NOT inflate reconnect_attempt. This fixes the old "counter always 0 / counts
    // every boot attempt as a reconnect" instrumentation gap.
    if (_hasEverConnected) _reconnectAttemptCount++;

    // Clean slate: if a stale TLS socket lingers from a silent disconnect,
    // stop it before re-handshaking to avoid a 15s socket-timeout hang.
    if (!_mqtt->connected() && _tlsClient) {
        _tlsClient->stop();
    }

    // Ensure valid time before TLS cert validation (prevents false expiry failures)
    syncTime();

    // LWT availability topic (retained offline marker). Passed via connect() overload.
    String lwtTopic = makeTopic("availability");
    const char* lwtPayload = "{\"status\":\"offline\"}";

    // Diagnostics captured BEFORE the TLS handshake (heap + trusted time)
    const uint32_t heapBefore  = ESP.getFreeHeap();
    const time_t   epochBefore = time(nullptr);

    Serial.print(F("MQTT_CONNECTING host="));
    Serial.print(_cfg.broker_host);
    Serial.print(F(" port="));
    Serial.println(_cfg.broker_port);

    // PubSubClient v2.8 connect overload with LWT (no setWill() exists):
    //   connect(id, user, pass, willTopic, willQos, willRetain, willMessage, cleanSession)
    bool ok = _mqtt->connect(
        _cfg.device_id,
        _cfg.username,
        _cfg.password,
        lwtTopic.c_str(),
        0,      // will QoS 0
        true,   // will retained
        lwtPayload,
        true    // clean session
    );

    if (ok) {
        _lastConnectMs = millis();
        _reconnectCount = 0;
        // Section 四: split initial connect vs runtime reconnect success.
        if (!_hasEverConnected) {
            _initialConnectCount++;
            _hasEverConnected = true;
            // reconnectSuccessCount stays 0 on the first (initial) connect.
        } else {
            _reconnectSuccessCount++;
        }
        _wasConnected = true;
        // Section 四: observable proof of the connect-count instrumentation.
        Serial.print(F("MQTT_CONNECT_COUNTERS initial="));
        Serial.print(_initialConnectCount);
        Serial.print(F(" reconnect_attempt="));
        Serial.print(_reconnectAttemptCount);
        Serial.print(F(" reconnect_success="));
        Serial.println(_reconnectSuccessCount);
        Serial.println(F("MQTT_CONNECT_PASS"));

        // Subscribe to command topic (QoS 1 acceptable per spec)
        String cmdTopic = makeTopic("commands/set");
        bool subOk = _mqtt->subscribe(cmdTopic.c_str(), 1);
        _resubscribeCount++;
        Serial.print(F("MQTT_RESUBSCRIBE_PASS topic="));
        Serial.print(cmdTopic);
        Serial.print(F(" ret="));
        Serial.println(subOk ? F("ok") : F("fail"));

        // Publish online availability (retained)
        bool avOk = publishAvailability("{\"status\":\"online\"}");
        Serial.print(F("MQTT_ONLINE_REPUBLISH_PASS ret="));
        Serial.println(avOk ? F("ok") : F("fail"));
        Serial.println(F("MQTT_RECONNECT_PASS"));
    } else {
        _reconnectCount++;
        int state = _mqtt->state();
        const uint32_t heapAfter = ESP.getFreeHeap();
        char berr[170];
        int bcode = _tlsClient->getLastSSLError(berr, sizeof(berr));
        // Next-retry estimate mirrors the state machine's jittered exponential backoff
        uint32_t retryMs = 5000;
        for (uint8_t i = 1; i < _reconnectCount && i < 12; i++) {
            retryMs *= 2;
            if (retryMs >= 60000) { retryMs = 60000; break; }
        }
        // Semantic-rich TLS failure record. NO secrets: host only never user/pass/key.
        Serial.println(F("TLS_FAIL"));
        Serial.print(F("stage=MQTT_TLS_CONNECT pubsub_rc="));
        Serial.println(state);
        Serial.print(F("bearssl_code="));
        Serial.println(bcode);
        Serial.print(F("bearssl_text="));
        Serial.println(berr);
        Serial.print(F("heap_before="));
        Serial.print(heapBefore);
        Serial.print(F(" heap_after="));
        Serial.print(heapAfter);
        Serial.print(F(" epoch="));
        Serial.print((uint32_t)epochBefore);
        Serial.print(F(" host="));
        Serial.print(_cfg.broker_host);
        Serial.print(F(" retry_in_ms="));
        Serial.println(retryMs);
    }
    return ok;
}

void MqttClientWrapper::disconnect() {
    if (_mqtt && _mqtt->connected()) {
        _mqtt->disconnect();
    }
}

MqttLoopResult MqttClientWrapper::loop() {
    if (!_initialized) {
        _loopFailureCount++;
        return MqttLoopResult::TransportError;
    }
    bool stillConnected = _mqtt->connected();
    if (!stillConnected) {
        _loopFailureCount++;
        // Count a disconnect only on the connected->disconnected transition
        // (not every loop iteration while already down) to avoid counter flooding.
        if (_wasConnected) {
            _disconnectCount++;
            _lastError = _mqtt->state();
            if (_tlsClient) {
                _lastSslError = _tlsClient->getLastSSLError(_lastSslText, sizeof(_lastSslText));
            }
            _wasConnected = false;
        }
        return MqttLoopResult::Disconnected;
    }
    _wasConnected = true;
    bool ok = _mqtt->loop();
    _loopCount++;
    if (!ok) {
        _loopFailureCount++;
        if (_wasConnected) {
            _disconnectCount++;
            _wasConnected = false;
        }
        return MqttLoopResult::Disconnected;
    }
    return MqttLoopResult::Ok;
}

bool MqttClientWrapper::isConnected() const {
    return _initialized && _mqtt && _mqtt->connected();
}

// === Publish helpers ===
bool MqttClientWrapper::publishChecked(const char* topic, const char* json, bool retained) {
    size_t len = strlen(json);
    if (len >= _cfg.buffer_size) {
        // Reject rather than truncate; MQTT buffer too small for this payload
        Serial.print(F("MQTT_PUBLISH_REJECT len="));
        Serial.print((unsigned)len);
        Serial.print(F(" >= buffer="));
        Serial.println(_cfg.buffer_size);
        _publishFailureCount++;
        return false;
    }
    bool ok = _mqtt->publish(topic, json, retained); // QoS 0 (spec)
    if (ok) _publishCount++;
    else _publishFailureCount++;
    return ok;
}

bool MqttClientWrapper::publishTelemetry(const char* json, bool retained) {
    if (!isConnected()) return false;
    String topic = makeTopic("telemetry");
    return publishChecked(topic.c_str(), json, retained);
}

bool MqttClientWrapper::publishState(const char* json) {
    if (!isConnected()) return false;
    String topic = makeTopic("state");
    return publishChecked(topic.c_str(), json, true); // retained
}

bool MqttClientWrapper::publishAvailability(const char* json) {
    if (!isConnected()) return false;
    String topic = makeTopic("availability");
    return publishChecked(topic.c_str(), json, true); // retained
}

bool MqttClientWrapper::publishAck(const char* json) {
    if (!isConnected()) return false;
    String topic = makeTopic("commands/ack");
    return publishChecked(topic.c_str(), json, false); // NOT retained, QoS 0
}

// onMessage() is inline in header

String MqttClientWrapper::makeTopic(const char* suffix) const {
    return String(MQTT_TOPIC_PREFIX "/") + suffix;
}
#endif  // ENABLE_CLOUD
