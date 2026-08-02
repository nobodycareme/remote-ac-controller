#pragma once
/*
 * wifi_association_controller.h - PURE, host-testable association executor.
 *
 * v1.2.4: this controller is the SINGLE production function that turns a
 * WifiConnectRequest into concrete WiFi.begin() calls. WifiManager::connect()
 * calls this exact class and method; the integration host test calls the
 * SAME method with a FakeWifiStationAdapter. There is no copied/parallel
 * decision logic anywhere.
 *
 * The password VALUE is passed through to beginWpa() (the ESP8266 needs it)
 * but it is NEVER logged, stored in the outcome, or printed by this
 * controller. The fake adapter only records passwordWasProvided.
 */
#include "network/wifi_connect_plan.h"
#include "network/wifi_station_adapter.h"

struct WifiConnectRequest {
  WifiConnectionSource source;
  const char* ssid;        // authoritative SSID for the source
  const char* password;    // nullptr for open sources; local WPA value otherwise

  // Default member initializers would make this a non-aggregate in C++11 and
  // break brace-init in the host tests; use a constructor instead.
  WifiConnectRequest(WifiConnectionSource s = WIFI_SOURCE_NONE,
                     const char* s2 = nullptr, const char* p = nullptr)
      : source(s), ssid(s2), password(p) {}
};

struct WifiConnectOutcome {
  bool proceeded = false;            // true => a WiFi.begin() overload was called
  WifiConnectReason reason = WIFI_PLAN_OK;
  WifiSecurityType securityType = WIFI_SECURITY_OPEN;
  const char* effectiveSsid = "";    // the SSID that was (or would be) used
};

class WifiAssociationController {
public:
  explicit WifiAssociationController(WifiStationAdapter& adapter) : _adapter(adapter) {}

  // Build the plan from the request, run the guard, and (only when valid)
  // dispatch to the adapter. Returns the outcome the caller uses for state
  // transitions and logging.
  WifiConnectOutcome execute(const WifiConnectRequest& req) {
    const bool hasPassword = (req.password && req.password[0] != '\0');
    const WifiConnectPlan plan =
        makeWifiConnectPlan(req.source, req.ssid, hasPassword);

    WifiConnectOutcome out;
    out.reason = plan.reason;
    out.securityType = plan.securityType;
    out.effectiveSsid = plan.ssid ? plan.ssid : "";

    if (!plan.configurationValid) {
      out.proceeded = false;
      return out;
    }

    out.proceeded = true;
    if (plan.securityType == WIFI_SECURITY_WPA_OR_WPA2) {
      // Only the compiled local-WPA source reaches here; the password is the
      // compiled value passed in the request. Never logged by this class.
      _adapter.beginWpa(plan.ssid, req.password ? req.password : "");
    } else {
      _adapter.beginOpen(plan.ssid);
    }
    return out;
  }

private:
  WifiStationAdapter& _adapter;
};
