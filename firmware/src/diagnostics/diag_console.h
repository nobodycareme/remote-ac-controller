// ============================================================
// diag_console.h — Diagnostics (static command impls, no Serial I/O)
// v0.3.5 — Commands are registered in Cli dispatch; this class
//          provides only the implementation functions.
// ============================================================
#pragma once
#include <Arduino.h>

struct DiagResult {
  bool pass;
  int  detail;
};

class DiagConsole {
public:
  // Individual diagnostics (callable from Cli dispatch)
  static void cmdHelp();
  static void cmdStatus();
  static void cmdDhtTest();
  static void cmdIrUartProbe();
  static void cmdWifiScan();
  static void cmdWifiAssoc();
  static void cmdDhcpInfo();
  static void cmdPortalProbe();
  static void cmdTlsPinCheck();
  static void cmdSrunVector();
  static void cmdAuthDryRun();
  static void cmdHeapStatus();
  static void cmdResetReason();
  static void cmdRunAllSafe();
  static void cmdLoginConfirmOnce();

  // Safety state (read-only)
  static bool isLiveAuthAllowed();
  static bool isIrMutatingAllowed();
};
