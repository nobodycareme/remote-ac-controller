// ============================================================
// serial_cli.cpp - CLI implementation (DHT11 + ZJ-IR-V2 IR module)
// ============================================================
// Always compiled — the CLI is a local feature independent of cloud
// connectivity. Network commands stay gated behind ENABLE_WIFI/ENABLE_CLOUD.
#include "serial_cli.h"
#include <Arduino.h>
#if ENABLE_IR_LAB_LEARNING_COMMANDS
#include <Crypto.h>
#include <base64.h>
#endif
#include <cstring>
#if ENABLE_WIFI
#include <ESP8266WiFi.h>
#endif
#include "app_config.h"
#include "board_pins.h"
#include "diagnostics/diag_console.h"
#include "config/campus_credentials.h"  // CampusCredentials::ready(); declared always, creds gated by ENABLE_CONTROLLED_LIVE_AUTH
#if ENABLE_IR_MUTATING_COMMANDS
#include "private_ir_codes/ir_code_registry.h"
#endif

#if ENABLE_IR_LAB_LEARNING_COMMANDS
using experimental::crypto::SHA256;

static const uint16_t IR_LAB_EXPORT_RAW_CHUNK = 60;  // multiple of 3 -> concat-safe Base64
#endif

static bool isLabSessionIdSafe(const char* sid) {
  if (!sid || !*sid) return false;
  uint16_t n = 0;
  for (const char* p = sid; *p; p++) {
    const char c = *p;
    const bool ok = (c >= 'a' && c <= 'z') ||
                    (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') ||
                    c == '_' || c == '-' || c == '.';
    if (!ok) return false;
    n++;
    if (n >= 128) return false;
  }
  return true;
}

static bool nextLabToken(const char*& p, char* out, size_t outSize) {
  if (!p || !out || outSize == 0) return false;
  while (*p == ' ' || *p == '\t') p++;
  size_t n = 0;
  while (*p && *p != ' ' && *p != '\t' && n + 1 < outSize) {
    out[n++] = *p++;
  }
  out[n] = '\0';
  while (*p == ' ' || *p == '\t') p++;
  return n > 0 && isLabSessionIdSafe(out);
}

#if ENABLE_IR_LAB_LEARNING_COMMANDS
static uint16_t base64EncodedLength(uint16_t rawLen) {
  return (uint16_t)(((uint32_t)rawLen + 2U) / 3U * 4U);
}

static void sha256Hex(const uint8_t* data, uint16_t len, char out[65]) {
  static const char hexDigits[] = "0123456789abcdef";
  uint8_t digest[SHA256::NATURAL_LENGTH];
  SHA256::hash(data, len, digest);
  for (uint8_t i = 0; i < SHA256::NATURAL_LENGTH; i++) {
    out[i * 2] = hexDigits[(digest[i] >> 4) & 0x0F];
    out[i * 2 + 1] = hexDigits[digest[i] & 0x0F];
  }
  out[64] = '\0';
}
#endif  // ENABLE_IR_LAB_LEARNING_COMMANDS

void Cli::begin() {
  Serial.begin(USB_SERIAL_BAUD);
  delay(50);
}

void Cli::banner() {
  Serial.println(F("=========================================="));
  Serial.print(F(" Remote AC Controller  firmware "));
  Serial.println(F(FIRMWARE_VERSION));
  Serial.println(F(" Local integration build (DHT11 + ZJ-IR-V2)"));
  Serial.println(F(" USB debug: help | status | version | dht read | dht test"));
  Serial.println(F(" IR (module): ir probe | ir info | ir setbaud N | ir stressfixed N | ir longframe"));
#if ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F(" IR lab JSONL: ir_learn_begin/status/cancel/export/clear (capture-only)"));
#endif
  Serial.println(F(" ON BOOT no IR command is sent automatically."));
#if ENABLE_WIFI
  Serial.println(F(" Wi-Fi: wifi connect [ssid] | wifi disconnect | wifi scan | wifi status"));
  Serial.println(F("        net check - captive-portal + internet reachability probe"));
#if WIFI_AUTOCONNECT_ON_BOOT
  Serial.println(F(" Wi-Fi auto-connects on boot (auto wifi connect and/or auto campus auth build)."));
#else
  Serial.println(F(" Wi-Fi does NOT auto-connect; issue `wifi connect` to associate."));
#endif
#endif
#if ENABLE_CAMPUS_AUTH
  Serial.println(F(" Campus auth: campus status | campus login | campus logout | campus unblock"));
#if ENABLE_AUTO_CAMPUS_AUTH
  Serial.println(F(" Campus auth is AUTOMATIC (rate-limited); manual login stays available."));
#endif
#endif
  Serial.println(F("=========================================="));
  Serial.println(F("APP_BOOT_OK"));
  Serial.print(F("IR_UART_INIT baud="));
  Serial.println(_ir.baud());
}

void Cli::help() {
  Serial.println(F("Commands:"));
  Serial.println(F("  help            - show this help"));
  Serial.println(F("  status          - uptime / free heap / last DHT / IR baud"));
  Serial.println(F("  version         - firmware version"));
  Serial.println(F("  dht read        - queue one DHT11 read at the next safe interval (>=2.5s gate, Adafruit lib, D1/GPIO5)"));
  Serial.println(F("  dht test        - burst 12 reads @2.5s -> DHT_TEST_PASS/FAIL"));
  Serial.println(F("  ir probe        - scan baud rates, establish UART link (read-only)"));
  Serial.println(F("  ir info         - query module baud + address (read-only)"));
  Serial.println(F("  ir learn N      - enter learn mode for group N (0..6), needs remote"));
  Serial.println(F("  ir send N       - emit stored group N (0..6) once"));
  Serial.println(F("  ir cancel       - abort an active learn session"));
  Serial.println(F("  ir setbaud N    - set module baud index 0..4 (1=19200); sync ESP (mutating)"));
  Serial.println(F("  ir stressfixed N- 100-query first-attempt test, NO retry (gate: 0 fail)"));
  Serial.println(F("  ir longframe    - inject 800-byte external-code frame, verify parse"));
#if ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("  ir_learn_begin <session_id> - enter AFN=20H external learn mode (no replay)"));
  Serial.println(F("  ir_learn_status             - JSON-lines lab status"));
  Serial.println(F("  ir_learn_cancel             - send AFN=21H exit learn mode"));
  Serial.println(F("  ir_learn_export <session_id>- Base64 export captured AFN=22H frame"));
  Serial.println(F("  ir_learn_clear              - clear temporary captured frame"));
#endif
#if ENABLE_WIFI
  Serial.println(F("  wifi connect [ssid] - connect: no-arg uses local wifi_secrets.h (WPA)"));
  Serial.println(F("                       or explicit OPEN campus SSID (default stu-xdwlan)"));
  Serial.println(F("  wifi disconnect - drop Wi-Fi association"));
  Serial.println(F("  wifi scan       - list nearby APs (read-only)"));
  Serial.println(F("  wifi status     - NET_STATE / LOCAL_IP / MAC / SSID"));
  Serial.println(F("  net check       - captive-portal + internet reachability probe"));
#endif
#if ENABLE_CAMPUS_AUTH
  Serial.println(F("  campus status   - auth state (AUTH_BLOCKED if no creds)"));
  Serial.println(F("  campus login    - attempt srun login (needs creds in secrets.h)"));
  Serial.println(F("  campus logout   - best-effort srun logout"));
  Serial.println(F("  campus unblock  - clear a latched hard block, re-detect portal"));
#endif
  Serial.println(F("NOTE: learn/send require your explicit action & confirmation."));
}

void Cli::printStatus() {
  Serial.print(F("STATUS uptime_ms="));
  Serial.print(millis());
  Serial.print(F(" free_heap="));
  Serial.print(ESP.getFreeHeap());
  Serial.print(F(" reset_reason="));
  Serial.print(ESP.getResetReason());
#if !defined(DISABLE_DHT)
  Serial.print(F(" dht_pin=GPIO"));
  Serial.print(DHT_PIN);
  Serial.print(F(" dht_valid="));
  Serial.print(_dht.hasValidReading() ? 1 : 0);
  if (_dht.hasValidReading()) {
    Serial.print(F(" dht_temp_c="));
    Serial.print(_dht.temperatureC(), 1);
    Serial.print(F(" dht_hum_pct="));
    Serial.print(_dht.humidityPercent(), 1);
  }
  Serial.print(F(" dht_ok="));
  Serial.print(_dht.successCount());
  Serial.print(F(" dht_fail="));
  Serial.print(_dht.failureCount());
#endif
  Serial.print(F(" ir_baud="));
  Serial.print(_ir.baud());
  Serial.print(F(" ir_learn_active="));
  Serial.println(_learnActive ? 1 : 0);
#if ENABLE_IR_MUTATING_COMMANDS
  const PrivateIrCode* code = privateIrCodeCount() > 0 ? privateIrCodeAt(0) : nullptr;
  Serial.print(F(" ir_code_ready="));
  Serial.print(code ? 1 : 0);
  Serial.print(F(" ir_code_id="));
  Serial.print(code ? code->codeId : "");
  Serial.print(F(" ir_code_length="));
  Serial.print(code ? code->len : 0);
  Serial.print(F(" ir_code_sha256="));
  Serial.println(code ? code->sha256 : "");
#endif
#if ENABLE_WIFI
  if (_net) {
    Serial.print(F(" net_state="));
    Serial.print(WifiManager::stateStr(_net->state()));
    Serial.print(F(" net_ssid="));
    Serial.print(_net->ssid());
    if (_net->state() >= WIFI_DHCP_WAIT) {
      Serial.print(F(" net_local_ip="));
      Serial.print(_net->localIp());
    }
    Serial.println();
    // Phase 9: enhanced internet/MQTT gate diagnostics
    Serial.print(F(" WIFI_LINK="));
    Serial.print(_net->state() >= WIFI_DHCP_WAIT ? F("READY") : F("PENDING"));
    Serial.print(F(" INTERNET_READY="));
    Serial.print(_net->internetUp() ? F("TRUE") : F("FALSE"));
    Serial.print(F(" MQTT_START_ALLOWED="));
    Serial.print((_net->state() >= WIFI_ONLINE || _net->internetUp()) ? F("TRUE") : F("FALSE"));
    Serial.print(F(" AUTH_STATE="));
    Serial.print(WifiManager::stateStr(_net->state()));
    Serial.println();
  }
#endif
}

#if !defined(DISABLE_DHT)
void Cli::doDhtRead(bool isTest) {
  static uint16_t sampleNo = 0;
  const bool ok = _dht.read();
  // Single place that advances the shared DHT read timestamp, so every real
  // read (manual `dht read`, `dht test` burst, and periodic) keeps the same
  // safe 2.5s cadence and the next auto-read never fires immediately after a
  // test burst's final frame.
  _lastDhtMs = _dht.lastReadTimestamp();
  sampleNo++;
  if (ok) {
    Serial.print(F("DHT_READ_OK sample="));
    Serial.print(sampleNo);
    Serial.print(F(" temperature_c="));
    Serial.print(_dht.temperatureC(), 1);
    Serial.print(F(" humidity_pct="));
    Serial.print(_dht.humidityPercent(), 1);
    Serial.print(F(" free_heap="));
    Serial.println(ESP.getFreeHeap());
    if (isTest) _testValid++;
  } else {
    Serial.print(F("DHT_READ_FAIL sample="));
    Serial.print(sampleNo);
    Serial.print(F(" reason=nan (isnan temperature/humidity)"));
    Serial.print(F(" fail_count="));
    Serial.println(_dht.failureCount());
  }
}
#endif

bool Cli::parseGroup(const char* arg, uint8_t& group) {
  if (!arg || *arg == '\0') return false;
  // Only accept a single decimal digit 0..6, no extra chars.
  if (arg[0] < '0' || arg[0] > '9') return false;
  if (arg[1] != '\0') return false;
  uint8_t g = (uint8_t)(arg[0] - '0');
  if (g < IR_GROUP_MIN || g > IR_GROUP_MAX) return false;
  group = g;
  return true;
}

bool Cli::parseUint(const char* arg, uint32_t& val, uint32_t maxVal) {
  if (!arg || *arg == '\0') return false;
  uint32_t v = 0;
  for (const char* p = arg; *p; p++) {
    if (*p < '0' || *p > '9') return false;
    v = v * 10 + (uint32_t)(*p - '0');
    if (v > maxVal) return false;
  }
  val = v;
  return true;
}

void Cli::dispatch(const char* line) {
  char buf[CLI_LINE_MAX + 1];
  strncpy(buf, line, CLI_LINE_MAX);
  buf[CLI_LINE_MAX] = '\0';

  char* p = buf;
  while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') p++;
  char* end = p + strlen(p);
  while (end > p && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n')) *--end = '\0';
  if (*p == '\0') return;

  // Split into t1 (first token) and the rest (rest may contain a second token).
  char* t1 = p;
  char* sp = strchr(t1, ' ');
  char* rest = (char*)"";
  if (sp) { *sp = '\0'; rest = sp + 1; while (*rest == ' ') rest++; }

  if (strcmp(t1, "help") == 0) { help(); return; }
  if (strcmp(t1, "version") == 0) { Serial.println(F(FIRMWARE_VERSION)); return; }
  if (strcmp(t1, "status") == 0) { printStatus(); return; }
  if (strcmp(t1, "ir_learn_status") == 0) { doIrLearnStatus(); return; }
  if (strcmp(t1, "ir_learn_begin") == 0) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
      Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
      return;
#endif
      doIrLearnBegin(rest); return;
  }
  if (strcmp(t1, "ir_learn_cancel") == 0) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
      Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
      return;
#endif
      doIrLearnCancel(rest); return;
  }
  if (strcmp(t1, "ir_learn_export") == 0) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
      Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
      return;
#endif
      doIrLearnExport(rest); return;
  }
  if (strcmp(t1, "ir_learn_clear") == 0) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
      Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
      return;
#endif
      doIrLearnClear(); return;
  }

#if ENABLE_WIFI
  if (strcmp(t1, "wifi") == 0)   { doWifi(rest); return; }
  if (strcmp(t1, "net") == 0)    { doNet(rest); return; }
  // login-confirm-once must be checked BEFORE generic campus dispatch
  if (strcmp(t1, "campus") == 0 && strcmp(rest, "login-confirm-once") == 0) {
    #if !ENABLE_CONTROLLED_LIVE_AUTH
      Serial.println(F("LIVE_AUTH_BLOCKED_BY_BUILD_POLICY"));
      return;
    #endif
    if (DiagConsole::isLiveAuthAllowed()) { DiagConsole::cmdLoginConfirmOnce(); return; }
    Serial.println(F("LIVE_AUTH_BLOCKED_BY_BUILD_POLICY"));
    return;
  }
#if ENABLE_CAMPUS_AUTH
  if (strcmp(t1, "campus") == 0) {
    #if !ENABLE_CONTROLLED_LIVE_AUTH
      Serial.println(F("LIVE_AUTH_BLOCKED_BY_BUILD_POLICY"));
      return;
    #endif
    doCampus(rest); return;
  }
#endif
#endif

#if !defined(DISABLE_DHT)
  if (strcmp(t1, "dht") == 0) {
    if (strcmp(rest, "read") == 0) {
      // Share the same 2.5s gating as periodic reads: do NOT force a read now.
      _readRequested = true;
      return;
    }
    if (strcmp(rest, "test") == 0) {
      _testActive = true; _testCount = 0; _testValid = 0;
      // Align the first burst read to the same 2.5s cadence as periodic reads
      // (so we never read two frames back-to-back within DHT_READ_INTERVAL_MS).
      _testNextMs = _lastDhtMs + DHT_READ_INTERVAL_MS;
      Serial.println(F("DHT_TEST_START samples=12 interval_ms=2500"));
      return;
    }
    Serial.println(F("ERR unknown dht subcommand (use: read | test)"));
    return;
  }
#else
  if (strcmp(t1, "dht") == 0) {
    Serial.println(F("DHT11_DISABLED_FOR_IR_PROBE"));
    return;
  }
#endif

  if (strcmp(t1, "ir") == 0) {
    // Split rest into sub + arg.
    char* sub = rest;
    char* sp2 = strchr(sub, ' ');
    char* arg = (char*)"";
    if (sp2) { *sp2 = '\0'; arg = sp2 + 1; while (*arg == ' ') arg++; }
    if (strcmp(sub, "probe") == 0) { doIrProbe(); return; }
    if (strcmp(sub, "info") == 0)  { doIrInfo(); return; }
    if (strcmp(sub, "learn") == 0) {
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrLearn(arg); return;
    }
    if (strcmp(sub, "send") == 0)  {
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrSend(arg); return;
    }
    if (strcmp(sub, "cancel") == 0){
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrCancel(); return;
    }
    if (strcmp(sub, "stress") == 0) { doIrStress(arg); return; }
    if (strcmp(sub, "setbaud") == 0) {
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrSetBaud(arg); return;
    }
    if (strcmp(sub, "stressfixed") == 0) { doIrStressFixed(arg); return; }
    if (strcmp(sub, "stressbounded") == 0) { doIrStressBounded(arg); return; }
    if (strcmp(sub, "longframe") == 0)   { doIrLongFrame(); return; }
    if (strcmp(sub, "extlearn") == 0){
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrExtLearn(); return;
    }
    if (strcmp(sub, "extsend") == 0){
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrExtSend(); return;
    }
    if (strcmp(sub, "extload") == 0){
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrExtLoad(arg); return;
    }
    if (strcmp(sub, "stage") == 0){
      #if !ENABLE_IR_MUTATING_COMMANDS
        Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
        return;
      #endif
      doIrStage(arg); return;
    }
    // Fuzzy prefixes must NOT trigger: "ir l" / "ir s" are rejected.
    Serial.println(F("ERR unknown ir subcommand (use: probe|info|learn|send|cancel|stress|extlearn|extsend|stage)"));
    return;
  }

  // ---- Runtime diagnostic commands (v0.3.5) ----
  if (strcmp(t1, "run_all_safe") == 0)      { DiagConsole::cmdRunAllSafe(); return; }
  if (strcmp(t1, "dht_test") == 0)           { DiagConsole::cmdDhtTest(); return; }
  if (strcmp(t1, "ir_uart_probe") == 0)      { DiagConsole::cmdIrUartProbe(); return; }
  if (strcmp(t1, "wifi_scan") == 0)          { DiagConsole::cmdWifiScan(); return; }
  if (strcmp(t1, "wifi_assoc") == 0)         { DiagConsole::cmdWifiAssoc(); return; }
  if (strcmp(t1, "dhcp_info") == 0)          { DiagConsole::cmdDhcpInfo(); return; }
  if (strcmp(t1, "portal_probe") == 0)       { DiagConsole::cmdPortalProbe(); return; }
#if ENABLE_CAMPUS_AUTH
  if (strcmp(t1, "tls_pin_check") == 0)      { DiagConsole::cmdTlsPinCheck(); return; }
  if (strcmp(t1, "srun_vector") == 0)        { DiagConsole::cmdSrunVector(); return; }
  if (strcmp(t1, "auth_dry_run") == 0)       { DiagConsole::cmdAuthDryRun(); return; }
#endif
  if (strcmp(t1, "heap_status") == 0)        { DiagConsole::cmdHeapStatus(); return; }
  if (strcmp(t1, "reset_reason") == 0)       { DiagConsole::cmdResetReason(); return; }

  Serial.print(F("ERR unknown command: "));
  Serial.println(t1);
}

void Cli::doIrProbe() {
  // Candidates: manual default 115200 first, then .ino's 9600 (real working rate),
  // then the remaining documented rates.详见 IR_PROTOCOL_ANALYSIS.md §6.
  const uint32_t cands[] = {115200, 9600, 57600, 38400, 19200};
  const uint8_t  nc = sizeof(cands) / sizeof(cands[0]);
  Serial.println(F("IR_PROBE_START"));
  // Running-state snapshot (per requirement §五): reset reason / heap / uptime.
  Serial.print(F("IR_PROBE_ENV reset_reason="));
  Serial.print(ESP.getResetReason());
  Serial.print(F(" free_heap="));
  Serial.print(ESP.getFreeHeap());
  Serial.print(F(" uptime_ms="));
  Serial.println(millis());

  for (uint8_t i = 0; i < nc; i++) {
    uint32_t baud = cands[i];
    _ir.close();   // force a reopen at the new baud (lazy SoftwareSerial)
    Serial.print(F("IR_PROBE_TRY baud="));
    Serial.println(baud);
    _ir.begin(baud);
    delay(20);

    // Send read-only GET_BAUD query; capture RAW reply + run field checks.
    IrProbeResult pr;
    _ir.probeCapture(800, pr);   // IR_TX_FRAME printed inside sendFrame

    // IR_RX_FRAME + raw hex (same bytes, both required by spec §三.5).
    char hexbuf[IR_MAX_FRAME * 3 + 8];
    IrModule::frameToHex(pr.raw, (uint8_t)pr.rawLen, hexbuf, sizeof(hexbuf));
    Serial.print(F("IR_RX_FRAME "));
    Serial.println(hexbuf);
    Serial.print(F("IR_RX_BYTES="));
    Serial.println(pr.rawLen);
    Serial.print(F("IR_PROBE_BAUD="));
    Serial.println(baud);
    Serial.print(F("IR_PROBE_RAW="));
    Serial.println(hexbuf);

    // Per-field verification (header / length / addr / func / checksum / trailer).
    Serial.print(F("IR_VERIFY_HEADER="));
    Serial.println(pr.headerOk ? F("PASS") : F("FAIL"));
    Serial.print(F("IR_VERIFY_LENGTH="));
    Serial.println(pr.lengthOk ? F("PASS") : F("FAIL"));
    if (pr.headerOk) {
      Serial.print(F("IR_VERIFY_ADDR=PASS got=0x"));
      Serial.println(pr.addr, HEX);
      Serial.print(F("IR_VERIFY_FUNC=PASS afn=0x"));
      Serial.println(pr.afn, HEX);
      Serial.print(F("IR_VERIFY_CHECKSUM="));
      if (pr.checksumOk) {
        Serial.print(F("PASS calc=0x"));
        Serial.print(pr.checksum, HEX);
        Serial.print(F(" got=0x"));
        Serial.println(pr.recvChecksum, HEX);
      } else {
        Serial.print(F("FAIL calc=0x"));
        Serial.print(pr.checksum, HEX);
        Serial.print(F(" got=0x"));
        Serial.println(pr.recvChecksum, HEX);
      }
    } else {
      Serial.println(F("IR_VERIFY_ADDR=FAIL"));
      Serial.println(F("IR_VERIFY_FUNC=FAIL"));
      Serial.println(F("IR_VERIFY_CHECKSUM=FAIL"));
    }
    Serial.print(F("IR_VERIFY_TRAILER="));
    Serial.println(pr.tailOk ? F("PASS") : F("FAIL"));

    // A valid GET_BAUD reply (AFN=04, >=1 data byte = baud index) => link up.
    if (pr.frameValid && pr.afn == IR_AFN_GET_BAUD && pr.dataLen >= 1) {
      uint32_t actual = IrModule::baudIndexToValue(pr.baudIndex);
      Serial.print(F("IR_UART_PASS baud="));
      Serial.println(actual);
      _ir.close();   // stop RX timer
      return;
    }
  }
  Serial.println(F("IR_UART_FAIL"));
  Serial.println(F("  tried: 115200 9600 57600 38400 19200"));
  Serial.println(F("  no valid GET_BAUD reply on any rate (check wiring/power/TX-RX)"));
  _ir.close();   // stop RX timer
}

void Cli::doIrInfo() {
  Serial.println(F("IR_INFO_QUERY"));
  IrResult rb = _ir.queryBaud(800);
  if (rb.ok) {
    Serial.print(F("IR_BAUD index="));
    Serial.print(rb.status);
    Serial.print(F(" value="));
    Serial.println(IrModule::baudIndexToValue(rb.status));
  } else {
    Serial.println(F("IR_BAUD query=NO_RESPONSE"));
  }
  // Get module address (read-only, AFN=06)
  _ir.sendFrame(IR_AFN_GET_ADDR);
  IrFrame f;
  if (_ir.readFrame(800, f) && f.valid && f.afn == IR_AFN_GET_ADDR && f.dataLen >= 1) {
    Serial.print(F("IR_ADDR=0x"));
    Serial.println(f.data[0], HEX);
  } else {
    Serial.println(F("IR_ADDR query=NO_RESPONSE"));
  }
  Serial.print(F("IR_UART_BAUD_CURRENT="));
  Serial.println(_ir.baud());
  _ir.close();   // stop RX timer; keep DHT timing clean
}

void Cli::doIrLearn(const char* arg) {
  uint8_t group;
  if (!parseGroup(arg, group)) {
    Serial.println(F("ERR ir learn requires a single group index 0..6 (e.g. 'ir learn 0')"));
    return;
  }
  Serial.println(F("WARNING: ir learn will put the module into LEARN mode."));
  Serial.println(F("  - Point the AC remote at the BLACK IR receiver on the module."));
  Serial.println(F("  - Press the target key ONCE; the green LED should go OUT when learned."));
  Serial.println(F("  - The module may OVERWRITE internal group N. Confirm before proceeding."));
  Serial.print(F("IR_LEARN_REQUEST index="));
  Serial.println(group);

  IrResult r = _ir.enterLearn(group, IR_REPLY_TIMEOUT_MS);
  if (r.ok) {
    _learnActive = true;
    _learnGroup = group;
    _learnDeadline = millis() + IR_LEARN_REPORT_TIMEOUT_MS;
    Serial.print(F("IR_LEARN_WAITING_USER index="));
    Serial.println(group);
    Serial.println(F("  (press remote key now; or send 'ir cancel' to abort)"));
    // Keep the RX timer open while learn is active (reports arrive via pollLearn).
  } else {
    _ir.close();   // no learn session -> stop RX timer
    Serial.print(F("IR_LEARN_FAIL index="));
    Serial.print(group);
    Serial.println(F(" reason=no_ack_from_module"));
  }
}

void Cli::doIrSend(const char* arg) {
  uint8_t group;
  if (!parseGroup(arg, group)) {
    Serial.println(F("ERR ir send requires a single group index 0..6 (e.g. 'ir send 0')"));
    return;
  }
  Serial.println(F("WARNING: ir send will EMIT one IR code from internal group N."));
  Serial.println(F("  - Aim the CLEAR IR emitter at the AC receiver window."));
  Serial.println(F("  - The module accepts the command; AC response is confirmed by YOU, not by firmware."));
  Serial.print(F("IR_SEND_REQUEST index="));
  Serial.println(group);

  IrResult r = _ir.sendGroup(group, IR_REPLY_TIMEOUT_MS);
  if (r.ok) {
    Serial.print(F("IR_SEND_COMMAND_ACCEPTED index="));
    Serial.println(group);
    Serial.println(F("IR_PHYSICAL_RESULT_PENDING"));
    Serial.println(F("  (confirm AC actual response yourself; firmware will NOT auto-judge)"));
  } else {
    Serial.print(F("IR_SEND_COMMAND_FAILED index="));
    Serial.println(group);
  }
  _ir.close();   // one-shot emit done -> stop RX timer; keep DHT timing clean
}

void Cli::doIrCancel() {
  if (!_learnActive) {
    Serial.println(F("IR_NO_ACTIVE_LEARN_SESSION"));
    return;
  }
  IrResult r = _ir.exitLearn(IR_REPLY_TIMEOUT_MS);
  _learnActive = false;
  _ir.close();   // learn session ended -> stop RX timer
  Serial.print(F("IR_LEARN_CANCELLED index="));
  Serial.print(_learnGroup);
  Serial.print(F(" exit_ack="));
  Serial.println(r.ok ? 1 : 0);
}

void Cli::doIrStress(const char* arg) {
  uint32_t n = 100;
  if (*arg != '\0') {
    if (!parseUint(arg, n, 100000)) {
      Serial.println(F("ERR ir stress requires a positive integer (e.g. 'ir stress 100')"));
      return;
    }
  }
  Serial.println(F("IR_STRESS_NOTE non-blocking; runs while WiFi/MQTT/DHT keep servicing"));
  _ir.startStress((int)n);
}

void Cli::doIrSetBaud(const char* arg) {
  uint32_t idx;
  if (!parseUint(arg, idx, 4)) {
    Serial.println(F("ERR ir setbaud requires index 0..4 (0=9600 1=19200 2=38400 3=57600 4=115200)"));
    return;
  }
  Serial.print(F("IR_SET_BAUD_REQUEST index="));
  Serial.println(idx);
  IrResult r = _ir.setBaud((uint8_t)idx, IR_REPLY_TIMEOUT_MS);
  if (r.ok) {
    uint32_t nb = IrModule::baudIndexToValue((uint8_t)idx);
    // Keep ESP SoftwareSerial synchronized with the module (requirement #4).
    _ir.close();
    _ir.begin(nb);
    _ir.ensureOpen();
    Serial.print(F("IR_SET_BAUD_ACK_PASS=1 status="));
    Serial.println(r.status);
    Serial.print(F("IR_UART_BAUD_CURRENT="));
    Serial.println(_ir.baud());
  } else {
    Serial.print(F("IR_SET_BAUD_ACK_PASS=0 afn=0x"));
    Serial.println(r.afn, HEX);
  }
}

void Cli::doIrStressFixed(const char* arg) {
  uint32_t n = 100;
  if (*arg != '\0') {
    if (!parseUint(arg, n, 100000)) {
      Serial.println(F("ERR ir stressfixed requires a positive integer (e.g. 'ir stressfixed 100')"));
      return;
    }
  }
  Serial.println(F("IR_STRESS_FIXED_NOTE non-blocking; NO retry (first-attempt only)"));
  _ir.startStressFixed((int)n);
}

void Cli::doIrStressBounded(const char* arg) {
  uint32_t n = 100;
  if (*arg != '\0') {
    if (!parseUint(arg, n, 100000)) {
      Serial.println(F("ERR ir stressbounded requires a positive integer (e.g. 'ir stressbounded 100')"));
      return;
    }
  }
  Serial.println(F("IR_STRESS_BOUNDED_NOTE non-blocking; max 3 retries/query, explicit backoff, no infinite loop"));
  _ir.startStressBounded((int)n);
}

void Cli::doIrLongFrame() {
  _ir.selfTestLongFrame();
}

void Cli::doIrExtLearn() {
  Serial.println(F("WARNING: ir extlearn captures the EXTERNAL code (AFN=22H) for later saving."));
  Serial.println(F("  - Point remote at BLACK receiver; press target key ONCE when prompted."));
  Serial.println(F("  - Capture is saved by the host tool; NO auto-replay, NO cloud, NO AC send."));
  _ir.enterExtLearn();
}

void Cli::doIrExtSend() {
  Serial.println(F("WARNING: ir extsend re-injects the last captured external frame to the module."));
  Serial.println(F("  - This EMITS real IR. Aim CLEAR emitter at AC. Confirm AC response yourself."));
  Serial.println(F("  - This is the ONLY local-CLI replay path; never triggered automatically."));
  _ir.extSendCaptured();
}

// Load a previously saved external-code BIN for controlled replay, WITHOUT emitting.
//   ir extload <hexchunk>  -> append chunk to staging buffer (repeatable)
//   ir extload commit      -> finalize staging into m_extLearnBuf and echo it back
// Host verifies the echoed bytes match the source BIN before any ir extsend.
static uint8_t cliHexNibble(char c) {
  if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
  if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
  if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
  return 0xFF;
}

void Cli::doIrExtLoad(const char* arg) {
  if (arg != nullptr && strcmp(arg, "commit") == 0) {
    uint8_t out[IR_MAX_FRAME];
    uint16_t n = _ir.extLoadCommit();
    if (n == 0) {
      Serial.println(F("IR_EXTLOAD_FAIL reason=empty_or_invalid"));
      return;
    }
    uint16_t got = _ir.extLearnFrame(out, sizeof(out));
    Serial.print(F("IR_EXTLOAD_OK len="));
    Serial.println(got);
    // Echo the staged bytes so the host can verify byte-identical (no emit occurred).
    Serial.print(F("IR_EXTLOAD_ECHO "));
    for (uint16_t k = 0; k < got; k++) {
      if (k) Serial.write(' ');
      if (out[k] < 0x10) Serial.write('0');
      Serial.print(out[k], HEX);
    }
    Serial.println();
    return;
  }
  // Append a hex chunk.
  if (arg == nullptr || arg[0] == '\0') {
    Serial.println(F("IR_EXTLOAD_FAIL reason=empty_arg (use hex bytes or 'commit')"));
    return;
  }
  uint8_t buf[IR_MAX_FRAME];
  uint16_t n = 0;
  const char* p = arg;
  while (*p && n < IR_MAX_FRAME) {
    while (*p == ' ' || *p == '\t') p++;
    if (!*p) break;
    uint8_t hi = cliHexNibble(p[0]);
    uint8_t lo = cliHexNibble(p[1]);
    if (hi == 0xFF || lo == 0xFF) {
      Serial.print(F("IR_EXTLOAD_FAIL reason=bad_hex at_pos="));
      Serial.println(n);
      return;
    }
    buf[n++] = (uint8_t)((hi << 4) | lo);
    p += 2;
  }
  uint16_t stageLen = _ir.extLoadAppend(buf, n);
  if (stageLen == 0) {
    Serial.println(F("IR_EXTLOAD_FAIL reason=staging_overflow"));
    return;
  }
  Serial.print(F("IR_EXTLOAD_APPEND len="));
  Serial.println(stageLen);
}

// §十一: `ir stage clear|append|commit|info|send` — debug staging front-end.
//   clear   : discard staged bytes (no emit)
//   append  : add a hex chunk to the staging buffer (no emit)
//   commit  : finalize staging -> committed frame (echoes bytes, no emit)
//   info    : show staged / committed lengths
//   send    : write the committed 22H frame to the module and EMIT real IR
// (Legacy `ir extload`/`ir extsend` remain available; this is the renamed form.)
void Cli::doIrStage(const char* arg) {
  if (arg == nullptr) arg = (char*)"";
  char* sub2 = (char*)arg;
  char* sp = strchr(sub2, ' ');
  char* a2 = (char*)"";
  if (sp) { *sp = '\0'; a2 = sp + 1; while (*a2 == ' ') a2++; }

  if (strcmp(sub2, "clear") == 0) {
    _ir.extLoadClear();
    Serial.println(F("IR_STAGE_CLEAR"));
    return;
  }
  if (strcmp(sub2, "append") == 0) {
    doIrExtLoad(a2);   // staging only, no emit
    return;
  }
  if (strcmp(sub2, "commit") == 0) {
    doIrExtLoad("commit");  // finalize + echo, no emit
    return;
  }
  if (strcmp(sub2, "info") == 0) {
    doIrStageInfo();
    return;
  }
  if (strcmp(sub2, "send") == 0) {
    Serial.println(F("WARNING: ir stage send writes the committed 22H frame to the module and EMITS real IR."));
    Serial.println(F("  Aim CLEAR emitter at AC. Confirm AC response yourself. Debug path only (never automatic)."));
    _ir.extSendCaptured();
    return;
  }
  Serial.println(F("ERR unknown ir stage subcommand (use: clear|append|commit|info|send)"));
}

void Cli::doIrStageInfo() {
  Serial.print(F("IR_STAGE_STAGED_LEN="));
  Serial.println(_ir.extLoadStageLen());
  Serial.print(F("IR_STAGE_COMMITTED_LEN="));
  Serial.println(_ir.extLearnLen());
}

void Cli::doIrLearnBegin(const char* arg) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
  return;
#else
  char requestId[128];
  char sessionId[128];
  const char* p = arg;
  if (!nextLabToken(p, requestId, sizeof(requestId)) || !nextLabToken(p, sessionId, sizeof(sessionId)) || *p != '\0') {
    Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"bad_correlation_ids\"}"));
    return;
  }
  if (_learnActive || _labLearnActive || _ir.extLearnActive()) {
    Serial.print(F("{\"event\":\"ir.learn.error\",\"requestId\":\""));
    Serial.print(requestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(sessionId);
    Serial.println(F("\",\"reason\":\"busy\"}"));
    return;
  }
  _ir.clearExtLearnCapture();
  strncpy(_labLearnRequestId, requestId, sizeof(_labLearnRequestId) - 1);
  _labLearnRequestId[sizeof(_labLearnRequestId) - 1] = '\0';
  strncpy(_labLearnSessionId, sessionId, sizeof(_labLearnSessionId) - 1);
  _labLearnSessionId[sizeof(_labLearnSessionId) - 1] = '\0';
  _labLearnActive = true;
  _labLearnCaptured = false;
  _labLearnStartedAt = millis();
  if (!_ir.enterExtLearn()) {
    _labLearnActive = false;
    Serial.print(F("{\"event\":\"ir.learn.error\",\"requestId\":\""));
    Serial.print(_labLearnRequestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(_labLearnSessionId);
    Serial.println(F("\",\"reason\":\"enter_failed\"}"));
    return;
  }
  Serial.print(F("{\"event\":\"ir.learn.waiting\",\"requestId\":\""));
  Serial.print(_labLearnRequestId);
  Serial.print(F("\",\"sessionId\":\""));
  Serial.print(_labLearnSessionId);
  Serial.print(F("\",\"timeoutMs\":"));
  Serial.print(IR_LEARN_REPORT_TIMEOUT_MS);
  Serial.println(F("}"));
#endif
}

void Cli::doIrLearnStatus() {
#if !ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
  return;
#else
  uint8_t frame[IR_MAX_FRAME];
  uint16_t n = _ir.extLearnFrame(frame, sizeof(frame));
  char sha[65] = "";
  if (n > 0) sha256Hex(frame, n, sha);
  const char* state = "IDLE";
  if (_labLearnActive && _ir.extLearnActive()) state = "WAITING_FOR_REMOTE";
  else if (n > 0) state = "CAPTURE_SAVED";
  Serial.print(F("{\"event\":\"ir.learn.status\",\"ok\":true,\"deviceStatus\":{\"ok\":true},\"deviceType\":\"NodeMCU ESP8266\",\"requestId\":\""));
  Serial.print(_labLearnRequestId);
  Serial.print(F("\",\"sessionId\":\""));
  Serial.print(_labLearnSessionId);
  Serial.print(F("\",\"state\":\""));
  Serial.print(state);
  Serial.print(F("\",\"captureReady\":"));
  Serial.print(n > 0 ? F("true") : F("false"));
  Serial.print(F(",\"frameLength\":"));
  Serial.print(n);
  Serial.print(F(",\"frameSha256\":\""));
  Serial.print(sha);
  Serial.print(F("\",\"firmwareVersion\":\""));
  Serial.print(F(FIRMWARE_VERSION));
  Serial.print(F("\",\"firmwareCommit\":\""));
#ifdef GIT_COMMIT
  Serial.print(F(GIT_COMMIT));
#else
  Serial.print(F("unknown-local"));
#endif
  Serial.print(F("\",\"profile\":\""));
#if ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.print(F("ir-lab"));
#elif ENABLE_IR_MUTATING_COMMANDS
  Serial.print(F("private-production"));
#else
  Serial.print(F("safe"));
#endif
  Serial.print(F("\",\"firmwareProfile\":\""));
#if ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.print(F("ir-lab"));
#elif ENABLE_IR_MUTATING_COMMANDS
  Serial.print(F("private-production"));
#else
  Serial.print(F("safe"));
#endif
  // GATE: irReady computed from real state, not hardcoded
  bool _irUartConfigured = (_ir.baud() == 19200);
  bool _learningActive = _ir.extLearnActive() || _labLearnActive;
  bool _exitUnconfirmed = !_labLearnActive && _ir.extLearnActive();
  bool _irReady = _irUartConfigured && !_learningActive && !_exitUnconfirmed;
  Serial.print(F("\",\"moduleModel\":\"ZJ-IR-V2\",\"irModuleModel\":\"ZJ-IR-V2\",\"irUartConfigured\":"));
  Serial.print(_irUartConfigured ? F("true") : F("false"));
  Serial.print(F(",\"moduleResponsive\":\"unknown\",\"learningActive\":"));
  Serial.print(_learningActive ? F("true") : F("false"));
  Serial.print(F(",\"exitUnconfirmed\":"));
  Serial.print(_exitUnconfirmed ? F("true") : F("false"));
  Serial.print(F(",\"irReady\":"));
  Serial.print(_irReady ? F("true") : F("false"));
  Serial.print(F(",\"learningProtocolVersion\":\"2\",\"irUartBaud\":"));
  Serial.print(_ir.baud());
#if ENABLE_WIFI
  Serial.print(F(",\"mac\":\""));
  Serial.print(_net ? _net->macMasked() : "");
  Serial.print(F("\",\"deviceMac\":\""));
  Serial.print(WiFi.macAddress());
  Serial.print(F("\""));
#endif
  Serial.println(F("}"));
#endif  // ENABLE_IR_LAB_LEARNING_COMMANDS
}

void Cli::doIrLearnCancel(const char* arg) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
  return;
#else
  char requestId[128];
  char sessionId[128];
  const char* p = arg;
  if (!nextLabToken(p, requestId, sizeof(requestId)) || !nextLabToken(p, sessionId, sizeof(sessionId))) {
    strncpy(requestId, _labLearnRequestId, sizeof(requestId) - 1);
    requestId[sizeof(requestId) - 1] = '\0';
    strncpy(sessionId, _labLearnSessionId, sizeof(sessionId) - 1);
    sessionId[sizeof(sessionId) - 1] = '\0';
  }
  IrResult r = _ir.exitExtLearn(IR_REPLY_TIMEOUT_MS);
  _labLearnActive = false;
  Serial.print(F("{\"event\":\"ir.learn.cancelled\",\"requestId\":\""));
  Serial.print(requestId);
  Serial.print(F("\",\"sessionId\":\""));
  Serial.print(sessionId);
  Serial.print(F("\",\"exitConfirmed\":"));
  Serial.print(r.ok ? F("true") : F("false"));
  Serial.println(F("}"));
#endif
}

void Cli::doIrLearnExport(const char* arg) {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
  return;
#else
  char requestId[128];
  char sessionId[128];
  char exportId[128];
  const char* p = arg;
  if (!nextLabToken(p, requestId, sizeof(requestId)) ||
      !nextLabToken(p, sessionId, sizeof(sessionId)) ||
      !nextLabToken(p, exportId, sizeof(exportId)) ||
      *p != '\0' ||
      strcmp(requestId, _labLearnRequestId) != 0 ||
      strcmp(sessionId, _labLearnSessionId) != 0) {
    Serial.println(F("{\"event\":\"ir.learn.export.error\",\"reason\":\"session_mismatch\"}"));
    return;
  }
  uint8_t frame[IR_MAX_FRAME];
  uint16_t n = _ir.extLearnFrame(frame, sizeof(frame));
  if (n == 0) {
    Serial.print(F("{\"event\":\"ir.learn.export.error\",\"requestId\":\""));
    Serial.print(requestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(_labLearnSessionId);
    Serial.print(F("\",\"exportId\":\""));
    Serial.print(exportId);
    Serial.println(F("\",\"reason\":\"no_capture\"}"));
    return;
  }
  char sha[65];
  sha256Hex(frame, n, sha);
  const uint16_t chunkCount = (uint16_t)((n + IR_LAB_EXPORT_RAW_CHUNK - 1) / IR_LAB_EXPORT_RAW_CHUNK);
  const uint16_t totalEncodedChars = base64EncodedLength(n);
  Serial.print(F("{\"event\":\"ir.learn.export.begin\",\"requestId\":\""));
  Serial.print(requestId);
  Serial.print(F("\",\"sessionId\":\""));
  Serial.print(_labLearnSessionId);
  Serial.print(F("\",\"exportId\":\""));
  Serial.print(exportId);
  Serial.print(F("\",\"encoding\":\"base64"));
  Serial.print(F("\",\"frameLength\":"));
  Serial.print(n);
  Serial.print(F(",\"frameSha256\":\""));
  Serial.print(sha);
  Serial.print(F("\",\"chunkCount\":"));
  Serial.print(chunkCount);
  Serial.print(F(",\"totalEncodedChars\":"));
  Serial.print(totalEncodedChars);
  Serial.println(F("}"));
  for (uint16_t i = 0; i < chunkCount; i++) {
    const uint16_t offset = (uint16_t)(i * IR_LAB_EXPORT_RAW_CHUNK);
    const uint16_t remain = (uint16_t)(n - offset);
    const uint16_t rawLen = (remain > IR_LAB_EXPORT_RAW_CHUNK) ? IR_LAB_EXPORT_RAW_CHUNK : remain;
    String encoded = base64::encode(frame + offset, rawLen, false);
    Serial.print(F("{\"event\":\"ir.learn.export.chunk\",\"requestId\":\""));
    Serial.print(requestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(_labLearnSessionId);
    Serial.print(F("\",\"exportId\":\""));
    Serial.print(exportId);
    Serial.print(F("\",\"index\":"));
    Serial.print(i);
    Serial.print(F(",\"count\":"));
    Serial.print(chunkCount);
    Serial.print(F(",\"encoding\":\"base64\",\"data\":\""));
    Serial.print(encoded);
    Serial.println(F("\"}"));
    yield();
  }
  Serial.print(F("{\"event\":\"ir.learn.export.done\",\"requestId\":\""));
  Serial.print(requestId);
  Serial.print(F("\",\"sessionId\":\""));
  Serial.print(_labLearnSessionId);
  Serial.print(F("\",\"exportId\":\""));
  Serial.print(exportId);
  Serial.print(F("\",\"encoding\":\"base64"));
  Serial.print(F("\",\"frameLength\":"));
  Serial.print(n);
  Serial.print(F(",\"frameSha256\":\""));
  Serial.print(sha);
  Serial.print(F("\",\"chunkCount\":"));
  Serial.print(chunkCount);
  Serial.print(F(",\"totalEncodedChars\":"));
  Serial.print(totalEncodedChars);
  Serial.println(F("}"));
#endif
}

void Cli::doIrLearnClear() {
#if !ENABLE_IR_MUTATING_COMMANDS || !ENABLE_IR_LAB_LEARNING_COMMANDS
  Serial.println(F("{\"event\":\"ir.learn.error\",\"reason\":\"build_policy\"}"));
  return;
#else
  if (_ir.extLearnActive()) _ir.exitExtLearn(IR_REPLY_TIMEOUT_MS);
  _ir.clearExtLearnCapture();
  _labLearnActive = false;
  _labLearnCaptured = false;
  _labLearnStartedAt = 0;
  memset(_labLearnSessionId, 0, sizeof(_labLearnSessionId));
  memset(_labLearnRequestId, 0, sizeof(_labLearnRequestId));
  Serial.println(F("{\"event\":\"ir.learn.cleared\"}"));
#endif
}

void Cli::pollLabLearn() {
#if ENABLE_IR_MUTATING_COMMANDS && ENABLE_IR_LAB_LEARNING_COMMANDS
  if (!_labLearnActive) return;
  uint8_t frame[IR_MAX_FRAME];
  uint16_t n = _ir.extLearnFrame(frame, sizeof(frame));
  if (n > 0 && !_labLearnCaptured) {
    char sha[65];
    sha256Hex(frame, n, sha);
    _labLearnCaptured = true;
    Serial.print(F("{\"event\":\"ir.learn.captured\",\"requestId\":\""));
    Serial.print(_labLearnRequestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(_labLearnSessionId);
    Serial.print(F("\",\"length\":"));
    Serial.print(n);
    Serial.print(F(",\"sha256\":\""));
    Serial.print(sha);
    Serial.println(F("\",\"structureValid\":true}"));
    return;
  }
  if (!_ir.extLearnActive() && !_labLearnCaptured) {
    _labLearnActive = false;
    Serial.print(F("{\"event\":\"ir.learn.timeout\",\"requestId\":\""));
    Serial.print(_labLearnRequestId);
    Serial.print(F("\",\"sessionId\":\""));
    Serial.print(_labLearnSessionId);
    // GATE 02: timeout path — exitConfirmed=false because no 21H ACK received
    Serial.println(F("\",\"exitConfirmed\":false,\"moduleAckTimedOut\":true}"));
  }
#endif
}

void Cli::pollLearn() {
  IrFrame f;
  if (!_ir.readFrame(150, f) || !f.valid) {
    if (millis() >= _learnDeadline) {
      _learnActive = false;
      Serial.print(F("IR_LEARN_FAIL index="));
      Serial.print(_learnGroup);
      Serial.println(F(" reason=timeout_waiting_remote"));
    }
    return;
  }
  if (f.afn == IR_AFN_REPORT && f.dataLen >= 1) {
    uint8_t flag = f.data[0];
    uint8_t status = (f.dataLen >= 3) ? f.data[2] : 0;
    if (flag == 0x80 && status == 0) {
      _learnActive = false;
      Serial.print(F("IR_LEARN_PASS index="));
      Serial.println(_learnGroup);
    } else {
      _learnActive = false;
      Serial.print(F("IR_LEARN_FAIL index="));
      Serial.print(_learnGroup);
      Serial.print(F(" reason=report_flag=0x"));
      Serial.println(flag, HEX);
    }
  }
  // An ack (AFN=01) here is just the enter-learn echo; keep waiting for the report.
}

#if ENABLE_WIFI
void Cli::doWifi(const char* arg) {
  if (!_net) { Serial.println(F("ERR wifi manager not attached")); return; }
  // Split arg into sub + subarg.
  char buf[CLI_LINE_MAX + 1];
  strncpy(buf, arg, CLI_LINE_MAX); buf[CLI_LINE_MAX] = '\0';
  char* p = buf;
  while (*p == ' ' || *p == '\t') p++;
  char* sub = p;
  char* sp = strchr(sub, ' ');
  char* subarg = (char*)"";
  if (sp) { *sp = '\0'; subarg = sp + 1; while (*subarg == ' ') subarg++; }

  if (strcmp(sub, "connect") == 0) {
    if (*subarg) {
      // Explicit open SSID (e.g. campus): `wifi connect <ssid>`.
      _net->begin(subarg);
    } else {
#if ENABLE_WIFI_CREDENTIALS
      // No-argument `wifi connect`: use the compiled-in home/lab WPA/WPA2
      // credentials from wifi_secrets.h. A password is NEVER accepted on the
      // command line (it would land in the serial console / terminal history).
      _net->beginLocalWifi();
#else
      // No credentials build: fall back to the default campus OPEN SSID.
      _net->begin();
#endif
    }
    _net->connect();
    return;
  }
  if (strcmp(sub, "disconnect") == 0) { _net->disconnect(); return; }
  if (strcmp(sub, "scan") == 0)      { _net->scan(); return; }
  if (strcmp(sub, "status") == 0) {
    Serial.print(F("NET_STATE="));
    Serial.println(WifiManager::stateStr(_net->state()));
    Serial.print(F("NET_SOURCE="));
    Serial.println(_net->sourceStr());
    Serial.print(F("NET_SSID="));
    Serial.println(_net->ssid());
    Serial.print(F("LOCAL_IP="));
    Serial.println(_net->localIp());
    // 八.5: MAC is masked in all serial output.
    Serial.print(F("MAC="));
    Serial.println(_net->macMasked());
    if (_net->portalDetected()) {
      Serial.print(F("PORTAL_HOST="));
      Serial.println(_net->portalHost());
      if (_net->acId().length()) {
        Serial.print(F("AC_ID="));
        Serial.println(_net->acId());
      }
    }
    return;
  }
  Serial.println(F("ERR unknown wifi subcommand (use: connect|disconnect|scan|status)"));
}

void Cli::doNet(const char* arg) {
  if (!_net) { Serial.println(F("ERR wifi manager not attached")); return; }
  if (strcmp(arg, "check") != 0) {
    Serial.println(F("ERR unknown net subcommand (use: check)"));
    return;
  }
  bool portal = _net->portalDetected();
  bool inet   = _net->internetUp();
  Serial.print(F("CAPTIVE_PORTAL="));
  Serial.println(portal ? "YES" : "NO");
  if (portal) {
    Serial.print(F("PORTAL_HOST="));
    Serial.println(_net->portalHost());
    if (_net->acId().length()) {
      Serial.print(F("AC_ID="));
      Serial.println(_net->acId());
    }
  }
  Serial.print(F("INTERNET="));
  Serial.println(inet ? "UP" : "DOWN");
  if (portal && !inet) {
    Serial.println(F("NET_NEEDS_CAMPUS_AUTH"));
    #if ENABLE_CAMPUS_AUTH
    if (!CampusCredentials::ready()) {
      Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
    } else {
      Serial.println(F("CREDS_READY issue `campus login`"));
    }
    #endif
  } else if (!portal && inet) {
    Serial.println(F("NET_ONLINE_NO_AUTH_NEEDED"));
  } else if (!portal && !inet) {
    Serial.println(F("NET_ASSOCIATED_INTERNET_UNKNOWN"));
  }
}
#endif  // ENABLE_WIFI

#if ENABLE_CAMPUS_AUTH
void Cli::doCampus(const char* arg) {
  if (!_net) { Serial.println(F("ERR wifi manager not attached")); return; }
  if (strcmp(arg, "status") == 0) {
    Serial.print(F("AUTH_STATE="));
    Serial.println(WifiManager::stateStr(_net->state()));
    if (!CampusCredentials::ready()) {
      Serial.println(F("AUTH_BLOCKED_NEEDS_LOCAL_CREDENTIALS"));
    } else {
      Serial.println(F("CREDS_READY issue `campus login` to authenticate"));
    }
    return;
  }
  if (strcmp(arg, "login") == 0)  { _net->campusLogin(); return; }
  if (strcmp(arg, "logout") == 0) { _net->campusLogout(); return; }
  // Operator escape hatch for a latched hard block (BAD_CREDENTIALS /
  // WRONG_DOMAIN / TLS_PIN_MISMATCH). `campus login` also clears the latch, but
  // only when credentials are compiled in; without them it returns early, which
  // would leave a blocked device with no software recovery path at all.
  // `campus unblock` re-enters the pipeline at portal detection instead of
  // forcing an immediate login attempt.
  if (strcmp(arg, "unblock") == 0) { _net->campusUnblock(); return; }
  Serial.println(F("ERR unknown campus subcommand (use: status|login|logout|unblock)"));
}
#endif  // ENABLE_CAMPUS_AUTH

void Cli::handle() {
  // 1) Process USB Serial input (incl. 'ir cancel').
  while (Serial.available() > 0) {
    const int c = Serial.read();
    if (c < 0) break;
    if (c == '\n' || c == '\r') {
      if (_lineLen > 0) {
        _line[_lineLen] = '\0';
        dispatch(_line);
        _lineLen = 0;
      }
    } else if (_lineLen < CLI_LINE_MAX) {
      _line[_lineLen++] = (char)c;
    } else {
      _lineLen = 0;  // overflow guard
    }
  }

  // 2) IR learn state polling (responsive to cancel above).
  if (_learnActive) {
    pollLearn();
  }

  // 2b) Non-blocking IR stress + external-learn capture (run every loop;
  //     does NOT block MQTT/DHT — main loop services them after this return).
  if (_ir.stressActive()) {
    _ir.tickStress();
  }
  if (_ir.stressFixedActive()) {
    _ir.tickStressFixed();
  }
  if (_ir.stressBoundedActive()) {
    _ir.tickStressBounded();
  }
  if (_ir.extLearnActive()) {
    _ir.tickExtLearn();
  }
  if (_labLearnActive) {
    pollLabLearn();
  }

#if ENABLE_WIFI
  // 3) Wi-Fi state machine tick (no-op until `wifi connect` is issued).
  if (_net) {
    _net->update();
  }
#endif

#if !defined(DISABLE_DHT)
  const uint32_t now = millis();

  // 3) Manual one-shot read request — shares the SAME 2.5s gate as periodic
  //    reads, so we never force two frames within DHT_READ_INTERVAL_MS.
  if (_readRequested && now - _lastDhtMs >= DHT_READ_INTERVAL_MS) {
    doDhtRead(false);
    _readRequested = false;
    return;
  }

  // 4) DHT test burst (non-blocking), also gated on the same 2.5s cadence.
  if (_testActive) {
    if (now >= _testNextMs) {
      doDhtRead(true);
      _testCount++;
      _testNextMs = now + DHT_READ_INTERVAL_MS;
      if (_testCount >= 12) {
        _testActive = false;
        if (_testValid >= 10) {
          Serial.println(F("DHT_TEST_PASS"));
        } else {
          Serial.print(F("DHT_TEST_FAIL valid="));
          Serial.print(_testValid);
          Serial.print(F("/"));
          Serial.println(_testCount);
        }
      }
    }
    return;  // suspend auto-loop reads during a burst
  }

  // 5) Normal periodic DHT read (independent of IR state).
  if (now - _lastDhtMs >= DHT_READ_INTERVAL_MS) {
    doDhtRead(false);
  }
#endif
}
