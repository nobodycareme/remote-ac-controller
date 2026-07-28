// ============================================================
// dht11_sensor.h - Formal DHT11 sensor module (Adafruit DHT library)
//
// Wraps the widely-validated Adafruit DHT sensor library (1.4.7) that was
// proven good on D1/GPIO5 (Phase 1: 30/30 valid, 0 failed). Replaces the
// old in-tree custom driver (dht_service.*), which had a defective reader
// (Serial.print inside a noInterrupts() critical section) and was tied to
// the failing GPIO4 channel.
//
// Public API:
//   begin()               - initialise the sensor (call once in setup)
//   read()                - force one fresh read now; returns true on success
//   update(intervalMs)    - read only if intervalMs has elapsed since last read
//   hasValidReading()     - true if the most recent read succeeded
//   temperatureC()        - last valid temperature (degC)
//   humidityPercent()     - last valid relative humidity (%)
//   lastReadTimestamp()   - millis() of the last read attempt
//   failureCount()        - cumulative failed reads
//   successCount()        - cumulative successful reads
// ============================================================
#pragma once
#include <Arduino.h>
#include <DHT.h>

class Dht11Sensor {
public:
  explicit Dht11Sensor(uint8_t pin)
    : _dht(pin, DHT11), _pin(pin), _hasValid(false),
      _tempC(NAN), _humPct(NAN), _lastReadMs(0),
      _failCount(0), _successCount(0) {}

  // Initialise the underlying Adafruit DHT driver. Call once from setup().
  void begin();

  // Force one fresh read immediately. Updates internal state and returns
  // true only when both temperature and humidity are valid (not NaN).
  bool read();

  // Read only if (millis() - lastReadTimestamp) >= intervalMs. Returns true
  // when a fresh read was performed AND succeeded this call.
  bool update(uint32_t intervalMs);

  bool     hasValidReading()   const { return _hasValid; }
  float    temperatureC()      const { return _tempC; }
  float    humidityPercent()   const { return _humPct; }
  uint32_t lastReadTimestamp() const { return _lastReadMs; }
  uint32_t failureCount()      const { return _failCount; }
  uint32_t successCount()      const { return _successCount; }
  uint8_t  pin()               const { return _pin; }

private:
  DHT      _dht;
  uint8_t  _pin;
  bool     _hasValid;
  float    _tempC;
  float    _humPct;
  uint32_t _lastReadMs;
  uint32_t _failCount;
  uint32_t _successCount;
};
