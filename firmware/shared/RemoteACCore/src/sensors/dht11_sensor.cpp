// ============================================================
// dht11_sensor.cpp - Formal DHT11 sensor module implementation
// Backed by the Adafruit DHT sensor library (1.4.7).
// ============================================================
#include "sensors/dht11_sensor.h"

void Dht11Sensor::begin() {
  _dht.begin();
  _hasValid = false;
  _tempC = NAN;
  _humPct = NAN;
  // Do not record a timestamp here; the first update()/read() will do so.
}

bool Dht11Sensor::read() {
  // force = true triggers a fresh 40-bit frame; the paired temperature read
  // reuses the cached frame (Adafruit lib caches for its MIN_INTERVAL).
  const float h = _dht.readHumidity(true);
  const float t = _dht.readTemperature(false);

  _lastReadMs = millis();

  if (isnan(h) || isnan(t)) {
    _hasValid = false;
    _failCount++;
    return false;
  }

  _humPct = h;
  _tempC = t;
  _hasValid = true;
  _successCount++;
  return true;
}

bool Dht11Sensor::update(uint32_t intervalMs) {
  const uint32_t now = millis();
  // First call (lastReadMs == 0 and no reading yet) reads immediately.
  if (_lastReadMs != 0 && (now - _lastReadMs) < intervalMs) {
    return false;
  }
  return read();
}
