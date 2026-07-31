// ============================================================
// serial_cli.h - USB Serial text command interface
// ============================================================
#pragma once
#include <Arduino.h>
#if !defined(DISABLE_DHT)
#include "sensors/dht11_sensor.h"
#endif
#include "ir_module.h"
#if ENABLE_WIFI
#include "network/wifi_manager.h"
#endif

class Cli {
public:
#if !defined(DISABLE_DHT)
  Cli(Dht11Sensor& dht, IrModule& ir)
    : _dht(dht), _lastDhtMs(0), _testActive(false),
      _testCount(0), _testValid(0), _testNextMs(0), _readRequested(false),
      _ir(ir), _learnActive(false), _learnGroup(0), _learnDeadline(0),
      _labLearnActive(false), _labLearnCaptured(false), _labLearnStartedAt(0),
      _lineLen(0) {
    memset(_line, 0, sizeof(_line));
    memset(_labLearnSessionId, 0, sizeof(_labLearnSessionId));
    memset(_labLearnRequestId, 0, sizeof(_labLearnRequestId));
  }
#else
  // Probe build (DISABLE_DHT): DHT11 fully disabled, only IR + debug CLI.
  Cli(IrModule& ir)
    : _ir(ir),
      _learnActive(false), _learnGroup(0), _learnDeadline(0),
      _labLearnActive(false), _labLearnCaptured(false), _labLearnStartedAt(0),
      _lineLen(0) {
    memset(_line, 0, sizeof(_line));
    memset(_labLearnSessionId, 0, sizeof(_labLearnSessionId));
    memset(_labLearnRequestId, 0, sizeof(_labLearnRequestId));
  }
#endif

  void begin();
  void banner();
  void handle();   // call every loop: process input + periodic DHT reads + IR state

#if ENABLE_WIFI
  // Attach the Wi-Fi/campus network manager (constructed in main.cpp).
  // Calls are no-ops if never attached. All network commands are gated here.
  void attachNetwork(WifiManager& net) { _net = &net; }
#endif

private:
#if !defined(DISABLE_DHT)
  Dht11Sensor& _dht;
  uint32_t _lastDhtMs;
  bool     _testActive;
  uint8_t  _testCount;
  uint8_t  _testValid;
  uint32_t _testNextMs;
  bool     _readRequested;   // manual `dht read` one-shot, gated on _lastDhtMs
#endif
  IrModule& _ir;

#if ENABLE_WIFI
  WifiManager* _net = nullptr;

  // Network commands (wifi / net)
  void doWifi(const char* arg);
  void doNet(const char* arg);
#endif
#if ENABLE_CAMPUS_AUTH
  // Campus-auth subcommands (status / login / logout) — gated on campus auth.
  void doCampus(const char* arg);
#endif

  // IR learn state (set by `ir learn N`, polled in handle(), cleared by report/timeout/cancel)
  bool     _learnActive;
  uint8_t  _learnGroup;
  uint32_t _learnDeadline;
  bool     _labLearnActive;
  bool     _labLearnCaptured;
  char     _labLearnSessionId[128];
  char     _labLearnRequestId[128];
  uint32_t _labLearnStartedAt;

  char  _line[CLI_LINE_MAX + 1];
  uint8_t _lineLen;

  void dispatch(const char* line);
  void doDhtRead(bool isTest);
  void printStatus();
  static void help();

  // IR commands
  void doIrProbe();
  void doIrInfo();
  void doIrLearn(const char* arg);
  void doIrSend(const char* arg);
  void doIrCancel();
  void doIrStress(const char* arg);
  void doIrSetBaud(const char* arg);
  void doIrStressFixed(const char* arg);
  void doIrStressBounded(const char* arg);
  void doIrLongFrame();
  void doIrExtLearn();
  void doIrExtSend();
  void doIrExtLoad(const char* arg);
  void doIrStage(const char* arg);     // §十一: ir stage clear|append|commit|info|send
  void doIrStageInfo();
  void doIrLearnBegin(const char* arg);
  void doIrLearnStatus();
  void doIrLearnCancel(const char* arg);
  void doIrLearnExport(const char* arg);
  void doIrLearnClear();
  void pollLabLearn();
  void pollLearn();  // called from handle() while _learnActive

  // Parse a decimal integer argument (no extra chars); returns false on invalid.
  bool parseUint(const char* arg, uint32_t& val, uint32_t maxVal);

  // Parse a group index argument ("0".."6"); returns false on invalid/missing.
  bool parseGroup(const char* arg, uint8_t& group);
};
