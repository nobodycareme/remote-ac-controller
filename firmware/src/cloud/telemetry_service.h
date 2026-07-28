#pragma once
/*
 * telemetry_service.h — periodic DHT11 sensor data publishing (v0.4.0)
 *
 * Reads DHT11 at >= 2.5s intervals and publishes JSON telemetry via MQTT.
 * Also tracks Wi-Fi RSSI, uptime, reconnect counts, and heap.
 */
#include <Arduino.h>
#include "cloud/mqtt_client.h"
#include "sensors/dht11_sensor.h"

class TelemetryService {
public:
    TelemetryService();

    // Result of a telemetry tick (Section 三 liveness supervision)
    enum class TickResult {
        NotDue,    // interval not elapsed yet (normal, no publish attempted)
        Published, // telemetry published successfully
        Failed     // publish attempted but failed (transport/buffer)
    };

    // Attach sensors and MQTT client
    void begin(Dht11Sensor* dht, MqttClientWrapper* mqtt);

    // Non-blocking tick — returns what happened this call
    TickResult tick();

    // Metrics
    uint32_t telemetryCount()   const { return _count; }
    uint32_t lastPublishMs()    const { return _lastPublishMs; }
    bool     lastDhtOk()        const { return _lastDhtOk; }
    float    lastTemperatureC() const { return _lastTempC; }
    float    lastHumidityPct()  const { return _lastHumPct; }

    uint32_t wifiReconnectCount() const { return _wifiReconnects; }
    void     incrementWifiReconnect()  { _wifiReconnects++; }

    uint32_t mqttReconnectCount() const { return _mqttReconnects; }
    void     incrementMqttReconnect()  { _mqttReconnects++; }

private:
    Dht11Sensor*       _dht;
    MqttClientWrapper*  _mqtt;

    uint32_t _count;
    uint32_t _lastPublishMs;
    uint32_t _nextReadMs;
    uint32_t _seq;

    bool     _lastDhtOk;
    float    _lastTempC;
    float    _lastHumPct;

    uint32_t _wifiReconnects;
    uint32_t _mqttReconnects;

    static const uint32_t PUBLISH_INTERVAL_MS = 5000;  // 5s between publishes
    static const uint32_t DHT_MIN_INTERVAL_MS = 2500;  // sensor minimum

    void readSensor();
    bool publishTelemetry();
    String buildJson();
};
