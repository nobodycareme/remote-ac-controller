#pragma once
/*
 * wifi_station_adapter.h - minimal injectable Wi-Fi association seam.
 *
 * WifiManager::connect() must NEVER call WiFi.begin() directly if we want a
 * host test to exercise the REAL production connection path. This interface
 * is the only place that maps the two begin() overloads onto the concrete
 * ESP8266 API; the production implementation is used by the firmware and a
 * fake implementation records call counts for the integration tests.
 *
 * The fake must NOT store or print the password value — it only records
 * whether a password was provided (passwordWasProvided).
 */
class WifiStationAdapter {
public:
  virtual ~WifiStationAdapter() {}
  virtual void beginOpen(const char* ssid) = 0;
  virtual void beginWpa(const char* ssid, const char* password) = 0;
};

#if defined(ESP8266) || defined(ARDUINO_ARCH_ESP8266)
#include <ESP8266WiFi.h>

class Esp8266WifiStationAdapter : public WifiStationAdapter {
public:
  void beginOpen(const char* ssid) override {
    WiFi.begin(ssid);
  }
  void beginWpa(const char* ssid, const char* password) override {
    WiFi.begin(ssid, password);
  }
};
#endif
