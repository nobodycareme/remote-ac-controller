// ============================================================
// main.cpp — Remote AC Controller v0.4.0-cloud-foundation
// Single serial router via Cli + Cloud auto-connectivity.
// ============================================================
#include <Arduino.h>

#include "config/hardware_config.h"
#include "board_pins.h"
#include "app_config.h"
#include "sensors/dht11_sensor.h"
#include "ir_module.h"
#include "serial_cli.h"
#include "network/wifi_manager.h"

// Cloud module (MQTT/telemetry/command) is WIP — gated on ENABLE_CLOUD (not defined by default).
// This preserves the cloud source for future development without breaking builds.
#if ENABLE_CLOUD
#include "cloud/connectivity_state_machine.h"
#include "cloud/mqtt_client.h"
#include "cloud/telemetry_service.h"
#include "cloud/command_service.h"
#endif

Dht11Sensor dht(DHT11_DATA_PIN);
IrModule ir;
Cli     gCli(dht, ir);
WifiManager net;

// Per-boot identifier (used as capture-file metadata; not security-critical).
uint32_t gBootId = 0;

#if ENABLE_CLOUD
ConnectivityStateMachine cloudSM;
MqttClientWrapper        mqtt;
TelemetryService         telemetry;
CommandService           commands;
static bool _wasWifiUp = false;  // for Wi-Fi reconnect counting in loop()
#endif

// === Cloud state machine callbacks ===
#if ENABLE_CLOUD
static bool cbWifiConnected() {
    return net.state() >= WIFI_DHCP_WAIT;
}

static bool cbDhcpReady() {
    return net.state() >= WIFI_DHCP_WAIT && net.localIp().length() > 0;
}

static bool cbDetectPortal() {
    return net.portalDetected();
}

static bool cbCampusAuth() {
    if (!CampusCredentials::ready()) return false;
    CampusAuthResult r = net.executeLogin();
    return (r == CAMPUS_AUTH_SUCCESS);
}

static bool cbCheckInternet() {
    return net.internetUp();
}

static bool cbMqttConnect() {
    if (!mqtt.isConnected()) {
        return mqtt.connect();
    }
    return true;
}

// Section 三: MQTT real-connection liveness supervision callbacks.
// The state machine's CS_CLOUD_ONLINE drives these instead of trusting isOnline().
static bool cbMqttConnected() {
    return mqtt.isConnected();
}

static bool cbMqttLoop() {
    // Drives PubSubClient loop(); returns true only if still connected after processing.
    MqttLoopResult r = mqtt.loop();
    return (r == MqttLoopResult::Ok);
}

static TelemetryPublishResult cbTelemetryTick() {
    TelemetryService::TickResult t = telemetry.tick();
    switch (t) {
        case TelemetryService::TickResult::NotDue:    return TelemetryPublishResult::NotDue;
        case TelemetryService::TickResult::Published: return TelemetryPublishResult::Published;
        default:                                      return TelemetryPublishResult::Failed;
    }
}

static void cbMqttDisconnect() {
    // Cleanly close a stale TLS socket before reconnect (only if still "connected"
    // to avoid touching a dead socket that could block).
    if (mqtt.isConnected()) mqtt.disconnect();
}

static int cbMqttErrorState() {
    return mqtt.lastErrorState();
}

static int cbMqttSslError() {
    return mqtt.lastSslError();
}
#endif

void setup() {
  gCli.begin();
  gCli.attachNetwork(net);
  ir.begin(IR_DEFAULT_BAUD);
  // Generate a stable-per-boot id for capture-file metadata.
  randomSeed((uint32_t)(ESP.getCycleCount() ^ ESP.getChipId()));
  gBootId = (uint32_t)random();
  gCli.banner();
  Serial.print(F("BOOT_ID=0x"));
  Serial.println(gBootId, HEX);
  dht.begin();
  Serial.print(F("DHT11_MODULE_READY pin=GPIO"));
  Serial.println(DHT11_DATA_PIN);
  Serial.print(F("IR_MODULE_READY rx=GPIO"));
  Serial.print(IR_RX_PIN);
  Serial.print(F(" tx=GPIO"));
  Serial.println(IR_TX_PIN);
  Serial.println(F("DIAGNOSTIC_CONSOLE_READY=YES"));
  Serial.println(F("SINGLE_SERIAL_ROUTER=TRUE"));

#if ENABLE_CLOUD
  // === Cloud module init (v0.4.0) ===
  MqttConfig mqttCfg;
#if ENABLE_CLOUD_CREDENTIALS
  if (CloudCredentials::available()) {
      mqttCfg.broker_host   = CloudCredentials::host();
      mqttCfg.broker_port   = CloudCredentials::port();
      mqttCfg.username      = CloudCredentials::username();
      mqttCfg.password      = CloudCredentials::password();
      mqttCfg.device_id     = CloudCredentials::deviceId();
      mqttCfg.tls_fingerprint = CloudCredentials::tlsFingerprint();
  }
#endif
  if (mqtt.begin(mqttCfg)) {
      Serial.println(F("CLOUD_MQTT_INIT_OK"));
      telemetry.begin(&dht, &mqtt);
      commands.begin(&mqtt);

      // Wire up state machine callbacks
      cloudSM.onCheckWifiConnected = cbWifiConnected;
      cloudSM.onCheckDhcpReady     = cbDhcpReady;
      cloudSM.onDetectPortal       = cbDetectPortal;
      cloudSM.onCampusAuth         = cbCampusAuth;
      cloudSM.onCheckInternet      = cbCheckInternet;
      cloudSM.onMqttConnect        = cbMqttConnect;
      cloudSM.onMqttConnected        = cbMqttConnected;
      cloudSM.onMqttLoop             = cbMqttLoop;
      cloudSM.onMqttPublishTelemetry = cbTelemetryTick;
      cloudSM.onMqttDisconnect       = cbMqttDisconnect;
      cloudSM.onMqttErrorState       = cbMqttErrorState;
      cloudSM.onMqttSslError         = cbMqttSslError;
      Serial.println(F("CLOUD_STATE_MACHINE_READY"));
      // Auto-initiate Wi-Fi association on cloud boot so the device self-recovers
      // after a power cycle WITHOUT a manual `wifi connect` (cold-boot recovery).
      // net.connect() uses the default campus SSID (CAMPUS_SSID); the cloud state
      // machine picks the association up on its next tick.
      net.connect();
      Serial.println(F("AUTO_WIFI_CONNECT_ISSUED"));
  } else {
      Serial.println(F("CLOUD_MQTT_INIT_SKIPPED (no cloud_secrets.h)"));
  }
#endif
}

void loop() {
  // 1) CLI handler (keeps serial responsive)
  gCli.handle();

#if ENABLE_CLOUD
  // 2) Cloud state machine tick (non-blocking).
  //    CS_CLOUD_ONLINE now drives mqtt.loop() + telemetry.tick() via its
  //    liveness-supervision callbacks (Section 三). Do NOT call them here too —
  //    that would double-drive the client and defeat disconnect detection.
  cloudSM.tick();

  // Track Wi-Fi reconnects for telemetry (false->true transition after a drop)
  bool wifiUp = net.state() >= WIFI_DHCP_WAIT;
  if (wifiUp && !_wasWifiUp) telemetry.incrementWifiReconnect();
  _wasWifiUp = wifiUp;
#endif

  yield();
}
