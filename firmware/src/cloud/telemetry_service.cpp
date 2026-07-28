// ============================================================
// telemetry_service.cpp — v0.4.0 cloud foundation
// ============================================================
#include "cloud/telemetry_service.h"
#include <ESP8266WiFi.h>
#include "app_config.h"
#if ENABLE_IR_MUTATING_COMMANDS
#include "private_ir_codes/ir_code_registry.h"
#endif

extern uint32_t gBootId;

static String jsonEscaped(String s) {
    s.replace("\\", "\\\\");
    s.replace("\"", "\\\"");
    return s;
}

TelemetryService::TelemetryService()
    : _dht(nullptr), _mqtt(nullptr),
      _count(0), _lastPublishMs(0), _nextReadMs(0), _seq(0),
      _lastDhtOk(false), _lastTempC(0), _lastHumPct(0),
      _wifiReconnects(0), _mqttReconnects(0)
{}

void TelemetryService::begin(Dht11Sensor* dht, MqttClientWrapper* mqtt) {
    _dht = dht;
    _mqtt = mqtt;
    _nextReadMs = millis() + DHT_MIN_INTERVAL_MS;
}

void TelemetryService::readSensor() {
    if (!_dht) return;
    _lastDhtOk = _dht->read();
    if (_lastDhtOk) {
        _lastTempC = _dht->temperatureC();
        _lastHumPct = _dht->humidityPercent();
    }
}

String TelemetryService::buildJson() {
    // Manual JSON construction to avoid ArduinoJson overhead
    String json;
    json.reserve(448);
    json += "{\"schema\":1";
    json += ",\"device_id\":\"" + String(CloudCredentials::deviceId()) + "\"";
    json += ",\"seq\":"; json += _seq;
    json += ",\"uptime_s\":"; json += (millis() / 1000);
    json += ",\"temperature_c\":"; json += String(_lastTempC, 1);
    json += ",\"humidity_pct\":"; json += String(_lastHumPct, 1);
    json += ",\"sensor_ok\":"; json += (_lastDhtOk ? "true" : "false");
    json += ",\"wifi_rssi_dbm\":"; json += WiFi.RSSI();
    json += ",\"free_heap_bytes\":"; json += ESP.getFreeHeap();
    json += ",\"max_free_block_bytes\":"; json += ESP.getMaxFreeBlockSize();
    json += ",\"boot_id\":"; json += gBootId;
    json += ",\"reset_reason\":\""; json += jsonEscaped(ESP.getResetReason()); json += "\"";
    json += ",\"wifi_reconnect_count\":"; json += _wifiReconnects;
    json += ",\"mqtt_reconnect_count\":"; json += (_mqtt ? _mqtt->reconnectCount() : 0);
    json += ",\"mqtt_disconnect_count\":"; json += (_mqtt ? _mqtt->disconnectCount() : 0);
    json += ",\"mqtt_loop_fail_count\":"; json += (_mqtt ? _mqtt->loopFailureCount() : 0);
    json += ",\"mqtt_publish_fail_count\":"; json += (_mqtt ? _mqtt->publishFailureCount() : 0);
    // Section 四: expose the connect-count instrumentation in telemetry so the backend
    // (and the dashboard) can prove initial-connect vs runtime-reconnect behaviour.
    json += ",\"mqtt_initial_connect_count\":"; json += (_mqtt ? _mqtt->initialConnectCount() : 0);
    json += ",\"mqtt_reconnect_attempt_count\":"; json += (_mqtt ? _mqtt->reconnectAttemptCount() : 0);
    json += ",\"mqtt_reconnect_success_count\":"; json += (_mqtt ? _mqtt->reconnectSuccessCount() : 0);
#if ENABLE_IR_MUTATING_COMMANDS
    const PrivateIrCode* code = privateIrCodeCount() > 0 ? privateIrCodeAt(0) : nullptr;
    json += ",\"ir_ready\":"; json += code ? "true" : "false";
    json += ",\"ir_code_id\":\""; json += code ? code->codeId : ""; json += "\"";
    json += ",\"ir_code_length\":"; json += code ? code->len : 0;
    json += ",\"ir_code_sha256\":\""; json += code ? code->sha256 : ""; json += "\"";
#else
    json += ",\"ir_ready\":false";
    json += ",\"ir_code_id\":\"\"";
    json += ",\"ir_code_length\":0";
    json += ",\"ir_code_sha256\":\"\"";
#endif
    json += ",\"simulated\":false";
    json += ",\"firmware_version\":\"" FIRMWARE_VERSION "\"";
    json += "}";
    return json;
}

bool TelemetryService::publishTelemetry() {
    if (!_mqtt || !_mqtt->isConnected()) return false;

    _seq++;
    String json = buildJson();
    bool ok = _mqtt->publishTelemetry(json.c_str());
    _lastPublishMs = millis();

    if (ok) {
        _count++;
        return true;
    } else {
        Serial.println(F("MQTT_PUBLISH_FAIL"));
        return false;
    }
}

TelemetryService::TickResult TelemetryService::tick() {
    const uint32_t now = millis();

    // Read DHT at >= 2.5s intervals
    if (now >= _nextReadMs) {
        readSensor();
        _nextReadMs = now + DHT_MIN_INTERVAL_MS;
    }

    // Publish at >= 5s intervals
    if (now - _lastPublishMs >= PUBLISH_INTERVAL_MS) {
        bool ok = publishTelemetry();
        return ok ? TickResult::Published : TickResult::Failed;
    }
    return TickResult::NotDue;
}
