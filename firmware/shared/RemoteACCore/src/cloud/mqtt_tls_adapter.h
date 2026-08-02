#pragma once
/*
 * mqtt_tls_adapter.h — minimal injectable MQTT TLS application seam.
 *
 * v1.2.5: MqttClientWrapper::begin() applies the MqttTlsPlan through this
 * adapter, and the host tests call the SAME applyMqttTlsPlan() free function
 * with a fake adapter. There is no copied/parallel TLS decision logic.
 *
 * The production implementation (ESP8266 only) performs:
 *   - applyCaCertificate: create BearSSL::X509List + setTrustAnchors();
 *   - applyFingerprint:   call the REAL setFingerprint(const uint8_t[20])
 *     API supported by the locked ESP8266 core (espressif8266@4.2.1).
 *
 * The fake MUST NOT store or print the CA content or fingerprint bytes —
 * it only records call counts and the last mode.
 */
#include "cloud/mqtt_tls_policy.h"

class MqttTlsAdapter {
public:
  virtual ~MqttTlsAdapter() {}
  virtual bool applyCaCertificate(const char* pem) = 0;
  virtual bool applyFingerprint(const uint8_t fingerprint[20]) = 0;
};

/*
 * Single production/tested TLS application path. begin() calls exactly this
 * function; the host tests call exactly this function.
 */
inline bool applyMqttTlsPlan(MqttTlsAdapter& adapter, const MqttTlsPlan& plan) {
  if (!plan.valid) return false;
  if (plan.mode == MQTT_TLS_MODE_CA_CERT) {
    return adapter.applyCaCertificate(plan.caCert);
  }
  if (plan.mode == MQTT_TLS_MODE_FINGERPRINT_SHA1) {
    return adapter.applyFingerprint(plan.fingerprint);
  }
  return false;   // NONE / unknown mode -> never succeeds
}

#if defined(ESP8266) || defined(ARDUINO_ARCH_ESP8266)
#include <WiFiClientSecure.h>
#include <memory>

class Esp8266MqttTlsAdapter : public MqttTlsAdapter {
public:
  // trustAnchors is the unique_ptr<BearSSL::X509List> owned by
  // MqttClientWrapper; it must outlive the WiFiClientSecure that references it.
  Esp8266MqttTlsAdapter(BearSSL::WiFiClientSecure& client,
                        std::unique_ptr<BearSSL::X509List>& trustAnchors)
      : _client(client), _trustAnchors(trustAnchors) {}

  bool applyCaCertificate(const char* pem) override {
    if (!pem || pem[0] == '\0') return false;
    _trustAnchors.reset(new BearSSL::X509List(pem));
    _client.setTrustAnchors(_trustAnchors.get());
    return true;
  }

  bool applyFingerprint(const uint8_t fingerprint[20]) override {
    // Real BearSSL API on the locked core (espressif8266@4.2.1):
    // bool setFingerprint(const uint8_t fingerprint[20]);
    return _client.setFingerprint(fingerprint);
  }

private:
  BearSSL::WiFiClientSecure& _client;
  std::unique_ptr<BearSSL::X509List>& _trustAnchors;
};
#endif  // ESP8266
