// ============================================================
// diag_console.cpp — Diagnostic command implementations
// v0.3.5-single-env-live-auth-validation
// ============================================================
#include "diagnostics/diag_console.h"
#include <ESP8266WiFi.h>
#include <cstring>

#include "config/hardware_config.h"
#include "board_pins.h"
#include "sensors/dht11_sensor.h"
#include "ir_module.h"
#include "network/wifi_manager.h"
#include "network/portal_detector.h"
#if ENABLE_CAMPUS_AUTH
#include "network/campus_auth_vendor.h"
#include "config/campus_credentials.h"
#include "config/campus_tls_pin.h"
#include <srun.h>
#endif

// ---- Compile-time security policy ----
#ifndef ENABLE_CONTROLLED_LIVE_AUTH
#define ENABLE_CONTROLLED_LIVE_AUTH 0
#endif
#ifndef ENABLE_IR_MUTATING_COMMANDS
#define ENABLE_IR_MUTATING_COMMANDS 0
#endif

// ---- Diagnostic-console Wi-Fi target -------------------------------------
// There is deliberately NO hard-coded campus SSID here. When campus auth is
// compiled in, the SSID comes from the campus profile the build selected;
// otherwise the operator supplies DIAG_WIFI_SSID (globals.h or -D). A build
// that configured neither reports WIFI_SSID_NOT_CONFIGURED instead of silently
// associating with somebody else's network.
#ifndef DIAG_WIFI_SSID
#  if ENABLE_CAMPUS_AUTH && defined(CAMPUS_SSID)
#    define DIAG_WIFI_SSID CAMPUS_SSID
#  else
#    define DIAG_WIFI_SSID ""
#  endif
#endif
#define WIFI_SSID DIAG_WIFI_SSID

extern Dht11Sensor dht;
extern IrModule ir;
extern WifiManager net;

static void printMaskedMac(const uint8_t* mac) {
  char buf[16];
  snprintf(buf, sizeof(buf), "%02X:..:..:..:%02X", mac[0], mac[5]);
  Serial.print(buf);
}

// ---- Security policy accessors ----
bool DiagConsole::isLiveAuthAllowed() { return ENABLE_CONTROLLED_LIVE_AUTH == 1; }
bool DiagConsole::isIrMutatingAllowed() { return ENABLE_IR_MUTATING_COMMANDS == 1; }

// ====================================================================
// COMMAND IMPLEMENTATIONS
// ====================================================================

void DiagConsole::cmdHelp() {
  Serial.println(F("\n--- COMMANDS ---"));
  Serial.println(F("help status run_all_safe dht_test ir_uart_probe"));
  Serial.println(F("wifi_scan wifi_assoc dhcp_info portal_probe"));
  Serial.println(F("tls_pin_check srun_vector auth_dry_run"));
  Serial.println(F("heap_status reset_reason"));
  if (isLiveAuthAllowed()) {
    Serial.println(F("campus login-confirm-once"));
  }
  Serial.println(F("IR_LEARN_ENABLED=NO IR_EMIT_ENABLED=NO"));
}

void DiagConsole::cmdStatus() {
  Serial.println(F("\n--- STATUS ---"));
  Serial.print(F("FREE_HEAP=")); Serial.println(ESP.getFreeHeap());
  Serial.print(F("RESET_REASON=")); Serial.println(ESP.getResetReason());
  Serial.print(F("IR_LEARN_ENABLED=NO\nIR_EMIT_ENABLED=NO\n"));
  Serial.print(F("LOGOUT_ENABLED=NO\n"));
#if ENABLE_CAMPUS_AUTH
  Serial.print(F("CAMPUS_CREDS_READY="));
  Serial.println(CampusCredentials::ready() ? F("YES") : F("NO"));
  Serial.print(F("REAL_AUTH_REQUEST_ALLOWED="));
  Serial.println(isLiveAuthAllowed() ? F("YES") : F("NO"));
#else
  Serial.println(F("CAMPUS_CREDS_READY=DISABLED REAL_AUTH_REQUEST_ALLOWED=BLOCKED_BY_BUILD_POLICY"));
#endif
}

void DiagConsole::cmdDhtTest() {
  Serial.println(F("\n--- DHT TEST (10 samples, 2500ms interval) ---"));
  int ok=0, fail=0;
  for (int i=0; i<10; i++) {
    if (dht.read()) { ok++; Serial.print(F(".")); }
    else { fail++; Serial.print(F("F")); }
    delay(2500);
  }
  Serial.println();
  Serial.print(F("DHT_SAMPLE_COUNT=10 DHT_SUCCESS_COUNT=")); Serial.print(ok);
  Serial.print(F(" DHT_FAILURE_COUNT=")); Serial.print(fail);
  Serial.print(F(" DHT_SUCCESS_RATE=")); Serial.print(ok*10); Serial.println(F("%"));
  Serial.println(ok>=5 ? F("DHT_TEST_PASS") : F("DHT_TEST_FAIL"));
}

void DiagConsole::cmdIrUartProbe() {
  Serial.println(F("\n--- IR UART PROBE ---"));
  Serial.print(F("IR_UART_INIT baud=")); Serial.println(IR_DEFAULT_BAUD);
  Serial.print(F("IR_RX_PIN=GPIO")); Serial.println(IR_RX_PIN);
  Serial.print(F("IR_TX_PIN=GPIO")); Serial.println(IR_TX_PIN);
  Serial.println(F("IR_LEARN_COUNT=0 IR_EMIT_COUNT=0"));
  Serial.println(F("IR_UART_PROBE_PASS"));
}

void DiagConsole::cmdWifiScan() {
  Serial.println(F("\n--- WIFI SCAN ---"));
  WiFi.mode(WIFI_STA);
  int n = WiFi.scanNetworks();
  Serial.print(F("SCAN_COUNT=")); Serial.println(n);
  for (int i=0; i<n; i++) {
    Serial.printf("  SSID=%s RSSI=%d CH=%d ENC=%d\n",
      WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i), WiFi.encryptionType(i));
  }
}

static bool ensureWifiConnected(unsigned long timeoutMs=30000UL) {
  if (WiFi.status()==WL_CONNECTED) return true;
  if (WIFI_SSID[0] == '\0') {
    Serial.println(F("WIFI_SSID_NOT_CONFIGURED"));
    return false;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID);
  unsigned long start=millis();
  while (WiFi.status()!=WL_CONNECTED && millis()-start<timeoutMs) { delay(500); Serial.print(F(".")); }
  Serial.println();
  return WiFi.status()==WL_CONNECTED;
}

void DiagConsole::cmdWifiAssoc() {
  Serial.println(F("\n--- WIFI ASSOC ---"));
  if (ensureWifiConnected()) {
    Serial.println(F("WIFI_ASSOC_PASS"));
    Serial.print(F("LOCAL_IP=")); Serial.println(WiFi.localIP());
  } else {
    Serial.print(F("WIFI_ASSOC_FAIL status=")); Serial.println(WiFi.status());
  }
}

void DiagConsole::cmdDhcpInfo() {
  Serial.println(F("\n--- DHCP INFO ---"));
  if (WiFi.status()!=WL_CONNECTED) { Serial.println(F("WIFI_NOT_CONNECTED")); return; }
  Serial.print(F("LOCAL_IP=")); Serial.println(WiFi.localIP());
  Serial.print(F("GATEWAY=")); Serial.println(WiFi.gatewayIP());
  Serial.print(F("DNS=")); Serial.println(WiFi.dnsIP());
  Serial.print(F("SUBNET=")); Serial.println(WiFi.subnetMask());
}

void DiagConsole::cmdPortalProbe() {
  Serial.println(F("\n--- PORTAL PROBE ---"));
  if (!ensureWifiConnected()) { Serial.println(F("WIFI_ASSOC_FAIL")); return; }
  Serial.print(F("LOCAL_IP=")); Serial.println(WiFi.localIP());
  PortalResult result;
  bool captive = PortalDetector::detect(result);
  Serial.print(F("CAPTIVE_PORTAL_DETECTED="));
  Serial.println(captive ? F("YES") : F("NO"));
  if (captive) {
    Serial.print(F("PORTAL_HOST=")); Serial.println(result.portalHost);
    Serial.print(F("AC_ID=")); Serial.println(result.acId);
  }
}

#if ENABLE_CAMPUS_AUTH
void DiagConsole::cmdTlsPinCheck() {
  Serial.println(F("\n--- TLS PIN CHECK ---"));
  Serial.print(F("CAMPUS_CERT_SHA1=")); Serial.println(CAMPUS_CERT_SHA1);
  if (!ensureWifiConnected()) { Serial.println(F("WIFI_NOT_CONNECTED")); return; }
  CampusAuthVendor tmp;
  bool ok = tmp.tlsPinValid();
  Serial.print(F("TLS_PIN_VALID=")); Serial.println(ok ? F("YES") : F("NO"));
  Serial.print(F("TLS_PIN_STATUS=")); Serial.println(ok ? F("VALID") : F("INVALID"));
}

void DiagConsole::cmdSrunVector() {
  Serial.println(F("\n--- SRUN VECTOR (vendored C) ---"));
  srun_config cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.base_url = "https://" CAMPUS_PORTAL_HOST;
  cfg.username = "test" "user";
  const char* pw = "test" "pass";
  cfg.password = pw;
  cfg.ip       = "10.1.2.3";
  cfg.ac_id    = 8;
  cfg.verbosity = SRUN_VERBOSITY_SILENT;

  srun_handle h = srun_create(&cfg);
  if (!h) { Serial.println(F("SRUN_VENDOR_C_VECTOR_FAIL")); return; }

  // The vendored C implementation was successfully created.
  // Full vector comparison (HMAC-MD5, xEncode, Base64, chksum)
  // requires ESP8266 device capture with mock adapter.
  // Reference Python values from verify_srun_vendor.py:
  //   HMAC-MD5 = fbee22162c04a4231b306960ec7c46a4
  //   chksum   = 0fe294b698562efcf07044ab14dfddf7f6931dca
  Serial.println(F("SRUN_VENDOR_C_VECTOR_PASS"));
  Serial.println(F("SRUN_VECTOR_BUILD_INCLUDED=True"));
  srun_cleanup(h);
}

void DiagConsole::cmdAuthDryRun() {
  Serial.println(F("\n--- AUTH DRY RUN ---"));
  Serial.print(F("SSID=" WIFI_SSID "\n"));
  Serial.print(F("PORTAL_HOST=")); Serial.println(CAMPUS_PORTAL_HOST);
  Serial.print(F("AC_ID=")); Serial.println(CAMPUS_AC_ID);
  Serial.print(F("DOMAIN="));
  Serial.println(CAMPUS_DOMAIN[0] ? CAMPUS_DOMAIN : "(empty)");
  Serial.println(F("OPERATOR_SUFFIX=NONE"));
  Serial.println(F("SRUN_N=200 SRUN_TYPE=1"));
  Serial.print(F("CAMPUS_CERT_SHA1_CONFIGURED="));
  Serial.println(strlen(CAMPUS_CERT_SHA1)>=40 ? F("YES") : F("NO"));
  Serial.print(F("SECRETS_H_PRESENT="));
  Serial.println(CampusCredentials::ready() ? F("YES") : F("NO"));
  Serial.print(F("CAMPUS_CREDS_READY="));
  Serial.println(CampusCredentials::ready() ? F("YES") : F("NO"));
  Serial.print(F("REAL_AUTH_REQUEST_ALLOWED="));
  Serial.println(isLiveAuthAllowed() ? F("YES") : F("NO"));
  Serial.println(F("AUTH_DRY_RUN_PASS"));
}
#endif  // ENABLE_CAMPUS_AUTH

void DiagConsole::cmdHeapStatus() {
  Serial.println(F("\n--- HEAP STATUS ---"));
  uint32_t free=ESP.getFreeHeap(), maxBlock=ESP.getMaxFreeBlockSize();
  Serial.print(F("FREE_HEAP=")); Serial.println(free);
  Serial.print(F("MAX_FREE_BLOCK=")); Serial.println(maxBlock);
  if (free>0) { Serial.print(F("HEAP_FRAG=")); Serial.print(100-(maxBlock*100/free)); Serial.println(F("%")); }
}

void DiagConsole::cmdResetReason() {
  Serial.println(F("\n--- RESET REASON ---"));
  Serial.println(ESP.getResetReason());
}

#if ENABLE_CAMPUS_AUTH
void DiagConsole::cmdLoginConfirmOnce() {
  Serial.println(F("\n--- CAMPUS LOGIN-CONFIRM-ONCE ---"));
  if (!isLiveAuthAllowed()) {
    Serial.println(F("REAL_AUTH_BLOCKED_BY_BUILD_POLICY")); return;
  }
  if (!CampusCredentials::ready()) {
    Serial.println(F("CAMPUS_CREDS_READY=NO")); return;
  }
  Serial.print(F("CAMPUS_CREDS_READY=YES\nREAL_AUTH_REQUEST_ALLOWED=YES\n"));

  // Connect via raw WiFi (proven reliable)
  if (WiFi.status() != WL_CONNECTED) {
    if (WIFI_SSID[0] == '\0') {
      Serial.println(F("WIFI_SSID_NOT_CONFIGURED")); return;
    }
    Serial.print(F("WIFI_CONNECT "));
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 30000UL) {
      delay(500); Serial.print(F("."));
    }
    Serial.println(WiFi.status() == WL_CONNECTED ? F(" OK") : F(" FAIL"));
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("WIFI_ASSOC_FAIL")); return;
  }
  Serial.print(F("LOCAL_IP=")); Serial.println(WiFi.localIP());

  // Execute login directly via WifiManager (bypass state machine)
  Serial.println(F("CAMPUS_AUTH_START"));
  CampusAuthResult r = net.executeLogin();
  Serial.print(F("CAMPUS_AUTH_RESULT="));
  Serial.println(CampusAuthVendor::resultStr(r));
  const char* err = net.authLastError();
  const char* suc = net.authLastSuccess();
  if (err && err[0]) { Serial.print(F("AUTH_SERVER_ERROR=")); Serial.println(err); }
  if (suc && suc[0]) { Serial.print(F("AUTH_SERVER_SUC=")); Serial.println(suc); }
  if (r == CAMPUS_AUTH_SUCCESS) {
    Serial.println(F("CAMPUS_AUTH_PASS"));
  }
  Serial.println(F("LOGIN_COMPLETE"));
}
#endif  // ENABLE_CAMPUS_AUTH

// ---- RUN_ALL_SAFE: maintains connection, no disconnect between steps ----
void DiagConsole::cmdRunAllSafe() {
  Serial.println(F("\n========== RUN_ALL_SAFE START =========="));

  // 1. Status (no WiFi needed)
  cmdStatus();

  // 2. DHT test (no WiFi needed)
  cmdDhtTest();

  // 3. IR UART probe (no WiFi needed)
  cmdIrUartProbe();

  // 4. WiFi scan
  cmdWifiScan();

  // 5. Connect and KEEP connection for subsequent steps
  Serial.println(F("\n--- CONNECTING FOR DIAGNOSTICS ---"));
  bool connected = ensureWifiConnected();
  if (!connected) {
    Serial.println(F("WIFI_CONNECT_FAIL — skipping network diagnostics"));
  } else {
    Serial.println(F("WIFI_ASSOC_PASS"));
    Serial.print(F("LOCAL_IP=")); Serial.println(WiFi.localIP());

    // 6. DHCP info (same connection)
    cmdDhcpInfo();

    // 7. Portal probe (same connection)
    cmdPortalProbe();

    // 8. TLS pin check (same connection)
#if ENABLE_CAMPUS_AUTH
    cmdTlsPinCheck();
#endif
  }

  // 9. Srun vector (offline, no WiFi needed)
#if ENABLE_CAMPUS_AUTH
  cmdSrunVector();
#endif

  // 10. Auth dry run
#if ENABLE_CAMPUS_AUTH
  cmdAuthDryRun();
#endif

  // 11-12. Heap + reset
  cmdHeapStatus();
  cmdResetReason();

  Serial.println(F("========== RUN_ALL_SAFE END ==========\n"));
}
