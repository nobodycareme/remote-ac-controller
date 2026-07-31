// ============================================================
// RemoteACApp.cpp — Shared application entry points
// Remote AC Controller v0.4.0-cloud-foundation
//
// Used by both PlatformIO (agent-platformio) and Arduino IDE builds.
// Contains all business logic previously in main.cpp.
// ============================================================
#include <Arduino.h>
#include "RemoteACApp.h"

#include "config/hardware_config.h"
#include "board_pins.h"
#include "app_config.h"
#include "sensors/dht11_sensor.h"
#include "ir_module.h"
#if ENABLE_CLOUD
#include "serial_cli.h"
#include "network/wifi_manager.h"
#endif

// Cloud module (MQTT/telemetry/command) gated on ENABLE_CLOUD
#if ENABLE_CLOUD
#include "cloud/connectivity_state_machine.h"
#include "cloud/mqtt_client.h"
#include "cloud/telemetry_service.h"
#include "cloud/command_service.h"
#endif

// ---- Global instances ----
static Dht11Sensor dht(DHT11_DATA_PIN);
static IrModule    ir;
static Cli         gCli(dht, ir);
#if ENABLE_CLOUD
static WifiManager net;
#endif

uint32_t gBootId = 0;

#if ENABLE_CLOUD
static ConnectivityStateMachine cloudSM;
static MqttClientWrapper        mqtt;
static TelemetryService         telemetry;
static CommandService           commands;
static bool _wasWifiUp = false;
#endif

// ---- Cloud state machine callbacks ----
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

static bool cbMqttConnected() {
    return mqtt.isConnected();
}

static bool cbMqttLoop() {
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
    if (mqtt.isConnected()) mqtt.disconnect();
}

static int cbMqttErrorState() {
    return mqtt.lastErrorState();
}

static int cbMqttSslError() {
    return mqtt.lastSslError();
}
#endif

// ---- Entry Points ----

void appSetup(void) {
  gCli.begin();
#if ENABLE_CLOUD
  gCli.attachNetwork(net);
#endif
  ir.begin(IR_DEFAULT_BAUD);

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
      net.connect();
      Serial.println(F("AUTO_WIFI_CONNECT_ISSUED"));
  } else {
      Serial.println(F("CLOUD_MQTT_INIT_SKIPPED (no cloud_secrets.h)"));
  }
#endif
}

void appLoop(void) {
  gCli.handle();

#if ENABLE_CLOUD
  cloudSM.tick();

  bool wifiUp = net.state() >= WIFI_DHCP_WAIT;
  if (wifiUp && !_wasWifiUp) telemetry.incrementWifiReconnect();
  _wasWifiUp = wifiUp;
#endif

  yield();
}
