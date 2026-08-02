// Host test for the pure cloud-secret validation rules (v1.2.4).
//
// These are the SAME rules enforced at build time by
// tools/validate-cloud-secrets.py and at runtime by
// CloudCredentials::available()/validate(). A contract test keeps the three
// implementations in agreement; this file is the C++ side.
//
//   g++ -std=c++11 -Wall -I firmware/shared/RemoteACCore/src \
//       test/host/test_cloud_secret_validation.cpp -o /tmp/t && /tmp/t

#include <cassert>
#include <cstdio>
#include <cstring>

#include "cloud/cloud_secret_validation.h"

static const char* const CA_OK =
    "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----";
static const char* const FP_OK =
    "F4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9";

static int g_total = 0;
static int g_pass = 0;
static void check(const char* name, bool cond) {
  ++g_total;
  if (cond) { ++g_pass; std::printf("CLOUDVAL_PASS %s\n", name); }
  else      { std::printf("CLOUDVAL_FAIL %s\n", name); }
}

int main() {
  // host
  check("host empty rejected", !cloudHostValid(""));
  check("host nullptr rejected", !cloudHostValid(nullptr));
  check("host template your-broker rejected", !cloudHostValid("your-broker.example.com"));
  check("host example.com rejected", !cloudHostValid("example.com"));
  check("host sub.example.com rejected", !cloudHostValid("mqtt.example.com"));
  check("host https scheme rejected", !cloudHostValid("https://mqtt.example.net"));
  check("host http scheme rejected", !cloudHostValid("http://mqtt.example.net"));
  check("host .invalid rejected", !cloudHostValid("mqtt.example.invalid"));
  check("host whitespace rejected", !cloudHostValid("my host"));
  check("host placeholder prefix rejected", !cloudHostValid("placeholder-host"));
  check("host valid accepted", cloudHostValid("mqtt.myhome.example.net"));
  check("host valid dot tld accepted", cloudHostValid("mqtt.example.network"));

  // port
  check("port 0 rejected", !cloudPortValid(0));
  check("port 65536 rejected", !cloudPortValid(65536));
  check("port 8883 accepted", cloudPortValid(8883));
  check("port 1 accepted", cloudPortValid(1));
  check("port 65535 accepted", cloudPortValid(65535));

  // device id
  check("device id empty rejected", !cloudDeviceIdValid(""));
  check("device id template bedroom-ac-01 rejected", !cloudDeviceIdValid("bedroom-ac-01"));
  check("device id your- prefix rejected", !cloudDeviceIdValid("your-device-id"));
  check("device id bad charset rejected", !cloudDeviceIdValid("has space"));
  check("device id too short rejected", !cloudDeviceIdValid("ab"));
  check("device id valid accepted", cloudDeviceIdValid("bedroom-ac-42"));
  check("device id valid long accepted", cloudDeviceIdValid("my-ac-2026-unit-7"));

  // auth
  check("auth empty user rejected", !cloudAuthValid("", "real-pass-2026"));
  check("auth empty password rejected", !cloudAuthValid("my-user", ""));
  check("auth template user rejected", !cloudAuthValid("bedroom-ac-01", "real-pass-2026"));
  check("auth template password rejected", !cloudAuthValid("my-user", "change-me"));
  check("auth valid accepted", cloudAuthValid("my-user-01", "a-real-password-2026"));

  // TLS
  check("tls ca ok accepted", cloudTlsValid(CA_OK, ""));
  check("tls fingerprint ok accepted", cloudTlsValid("", FP_OK));
  check("tls both empty rejected", !cloudTlsValid("", ""));
  check("tls ca missing END rejected", !cloudCaCertValid("-----BEGIN CERTIFICATE-----\nMIID"));
  check("tls ca placeholder rejected", !cloudCaCertValid("your-ca-cert"));
  check("tls fp wrong length rejected", !cloudFingerprintValid("F4:BD:59:32"));
  check("tls fp non-hex rejected",
        !cloudFingerprintValid("G4:BD:59:32:8E:77:8C:CB:AD:6E:AE:85:86:59:36:FD:0D:28:47:F9"));
  check("tls fp all zeros rejected",
        !cloudFingerprintValid("00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00"));

  // full validate()
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "mqtt.myhome.example.net", 8883, "bedroom-ac-42", "my-user-01",
        "a-real-password-2026", CA_OK, "");
    check("validate: valid ok", v.ok);
    check("validate: valid code OK", v.code == CLOUD_VALID_OK);
    check("validate: OK label", strcmp(cloudValidationCodeStr(v.code), "OK") == 0);
  }
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "your-broker.example.com", 8883, "bedroom-ac-42", "my-user-01",
        "a-real-password-2026", CA_OK, "");
    check("validate: template host rejected", !v.ok);
    check("validate: host placeholder code", v.code == CLOUD_ERR_HOST_PLACEHOLDER);
    check("validate: label", strcmp(cloudValidationCodeStr(v.code), "HOST_PLACEHOLDER") == 0);
  }
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "mqtt.myhome.example.net", 8883, "bedroom-ac-01", "my-user-01",
        "a-real-password-2026", CA_OK, "");
    check("validate: template device rejected", !v.ok);
    check("validate: device code", v.code == CLOUD_ERR_DEVICE_ID);
  }
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "mqtt.myhome.example.net", 8883, "bedroom-ac-42", "my-user-01",
        "a-real-password-2026", "", "");
    check("validate: missing TLS rejected", !v.ok);
    check("validate: tls code", v.code == CLOUD_ERR_TLS);
    check("validate: tls label", strcmp(cloudValidationCodeStr(v.code), "TLS_MATERIAL_MISSING") == 0);
  }
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "mqtt.myhome.example.net", 0, "bedroom-ac-42", "my-user-01",
        "a-real-password-2026", CA_OK, "");
    check("validate: port 0 rejected", !v.ok);
    check("validate: port code", v.code == CLOUD_ERR_PORT);
  }
  {
    CloudCredentialValidation v = validateCloudCredentials(
        "mqtt.myhome.example.net", 8883, "bedroom-ac-42", "my-user-01",
        "change-me", CA_OK, "");
    check("validate: template password rejected", !v.ok);
    check("validate: auth code", v.code == CLOUD_ERR_AUTH);
  }

  std::printf("CLOUD_SECRET_VALIDATION_CASE_TOTAL=%d\n", g_total);
  std::printf("CLOUD_SECRET_VALIDATION_CASE_PASS=%d\n", g_pass);
  std::printf("CLOUD_SECRET_VALIDATION_CASE_FAILURE=%d\n", g_total - g_pass);
  return (g_total == g_pass) ? 0 : 1;
}
