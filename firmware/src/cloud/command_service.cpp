// ============================================================
// command_service.cpp — v0.4.0 cloud foundation
// ============================================================
#include "cloud/command_service.h"
#include <cstring>
#include <time.h>

// §六: real IR replay (private / ir-lab build only).
#if ENABLE_IR_MUTATING_COMMANDS
#include <pgmspace.h>
#include "ir_module.h"
#include "private_ir_codes/ir_code_registry.h"
extern IrModule ir;  // global in main.cpp
#endif

// Lightweight JSON number parsing (no ArduinoJson dependency)
static int64_t jsonGetInt(const String& json, const char* key, int64_t def = 0) {
    String pat = "\"" + String(key) + "\":";
    int pos = json.indexOf(pat);
    if (pos < 0) return def;
    pos += pat.length();
    while (pos < (int)json.length() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    bool neg = false;
    if (json[pos] == '-') { neg = true; pos++; }
    int64_t val = 0;
    while (pos < (int)json.length() && json[pos] >= '0' && json[pos] <= '9') {
        val = val * 10 + (json[pos] - '0');
        pos++;
    }
    return neg ? -val : val;
}

static String jsonGetStr(const String& json, const char* key, const String& def = "") {
    String pat = "\"" + String(key) + "\":\"";
    int pos = json.indexOf(pat);
    if (pos < 0) return def;
    pos += pat.length();
    int end = json.indexOf('"', pos);
    if (end < 0 || end <= pos) return def;
    return json.substring(pos, end);
}

// Is the command's expires_at in the past? Accepts either seconds or ms epoch.
static bool isExpired(uint64_t expiresAt) {
    if (expiresAt == 0) return false; // no expiry set -> accept
    time_t now = time(nullptr);
    if (now < 100000) return false;   // clock not synced -> don't false-reject (NTP pending)
    const uint64_t nowSec = (uint64_t)now;
    if (expiresAt > 4000000000ULL) {
        return nowSec * 1000ULL > expiresAt;
    }
    return nowSec > expiresAt;
}

// Static pointer for PubSubClient callback forwarding
static CommandService* g_activeCmd = nullptr;

static void cmdCallback(const char* topic, const uint8_t* payload, unsigned int length) {
    if (g_activeCmd) {
        g_activeCmd->handleMessage(topic, payload, length);
    }
}

CommandService::CommandService()
    : _mqtt(nullptr), _recentIdx(0),
      _received(0), _accepted(0), _blocked(0), _rejected(0),
      _lastStatus(CommandStatus::PENDING)
{}

void CommandService::begin(MqttClientWrapper* mqtt) {
    _mqtt = mqtt;
    if (_mqtt) {
        g_activeCmd = this;
        _mqtt->onMessage(cmdCallback);
    }
    Serial.println(F("CMD_SERVICE_READY"));
}

bool CommandService::parseCommand(const String& json, CloudCommand& cmd) {
    cmd.command_id    = jsonGetStr(json, "command_id");
    int64_t rawExpiry = jsonGetInt(json, "expires_at");
    cmd.expires_at    = rawExpiry > 0 ? (uint64_t)rawExpiry : 0ULL;
    String action_str = jsonGetStr(json, "action");
    cmd.power         = jsonGetInt(json, "power", 0) != 0;
    cmd.target_temperature_c = (float)jsonGetInt(json, "target_temperature_c", 26);
    cmd.raw_json      = json;

    // Parse action (protocol primary action is "set_state")
    // §六: type=ir_action (action field carries the short codeId) OR
    //      action=ir_action (ir_action_id field carries the short codeId).
    cmd.type = jsonGetStr(json, "type");
    if (cmd.type == "ir_action") {
        cmd.action = CommandAction::IR_ACTION;
        cmd.ir_action_id = action_str;                 // codeId lives in "action"
    } else if (action_str == "ir_action") {
        cmd.action = CommandAction::IR_ACTION;
        cmd.ir_action_id = jsonGetStr(json, "ir_action_id");
    } else if (action_str == "set_state")            cmd.action = CommandAction::SET_STATE;
    else if (action_str == "set_power")       cmd.action = CommandAction::SET_POWER;
    else if (action_str == "set_temperature") cmd.action = CommandAction::SET_TEMPERATURE;
    else return false; // unknown action

    // Validate command_id is not empty
    if (cmd.command_id.length() == 0) return false;
    return true;
}

CommandStatus CommandService::validateCommand(const CloudCommand& cmd) {
    // 1. Check expiry
    if (isExpired(cmd.expires_at)) {
        return CommandStatus::REJECTED_EXPIRED;
    }

    // 2. Check duplicate
    if (isDuplicate(cmd.command_id)) {
        return CommandStatus::REJECTED_DUPLICATE;
    }

    // §六: IR action — validate code existence / policy, then let handleMessage
    // execute exactly once (returning ACCEPTED_MOCK means "validation passed,
    // proceed to emit"). No emit happens here (§五: never emit during validation).
    if (cmd.action == CommandAction::IR_ACTION) {
        #if ENABLE_IR_MUTATING_COMMANDS
            if (!findPrivateIrCode(cmd.ir_action_id.c_str())) {
                return CommandStatus::IR_UNKNOWN_CODE;
            }
            return CommandStatus::ACCEPTED_MOCK;  // proceed to one-shot emit
        #else
            return CommandStatus::BLOCKED_BY_IR_POLICY;
        #endif
    }

    // 3. Validate temperature range (set_state and set_temperature)
    if (cmd.action == CommandAction::SET_STATE || cmd.action == CommandAction::SET_TEMPERATURE) {
        float t = cmd.target_temperature_c;
        if (t < 16.0f || t > 30.0f) {
            return CommandStatus::REJECTED_OUT_OF_RANGE;
        }
    }

    // 4. IR policy gate — ALL mutating commands are blocked
    #if ENABLE_IR_MUTATING_COMMANDS
        // In future: real IR execution would happen here
        return CommandStatus::ACCEPTED_MOCK; // still mock for now
    #else
        return CommandStatus::BLOCKED_BY_IR_POLICY;
    #endif

    return CommandStatus::ACCEPTED_MOCK;
}

void CommandService::handleMessage(const char* topic, const uint8_t* payload, unsigned int length) {
    if (!_mqtt) return;

    // Convert payload to string
    String json;
    json.reserve(length + 1);
    for (unsigned int i = 0; i < length; i++) {
        json += (char)payload[i];
    }

    _received++;
    Serial.print(F("CMD_RECEIVED topic="));
    Serial.println(topic);

    // Parse command
    CloudCommand cmd;
    if (!parseCommand(json, cmd)) {
        _rejected++;
        _lastCmd = cmd;
        _lastStatus = CommandStatus::REJECTED_INVALID;
        sendAck(cmd, CommandStatus::REJECTED_INVALID, "invalid_schema");
        return;
    }

    // Validate and dispatch
    CommandStatus result = validateCommand(cmd);
    _lastCmd = cmd;
    _lastStatus = result;

    // §六: IR action is executed (one-shot) here, after validation. It is the
    // ONLY place sendExternalFrameOnce is called — never on boot / Wi-Fi or MQTT
    // reconnect / web refresh / status query (§五).
    if (cmd.action == CommandAction::IR_ACTION) {
        dispatchIrAction(cmd, result);
        return;
    }

    switch (result) {
        case CommandStatus::ACCEPTED_MOCK:
            _accepted++;
            recordCommandId(cmd.command_id);
            sendAck(cmd, result, "mock_accepted");
            break;
        case CommandStatus::BLOCKED_BY_IR_POLICY:
            _blocked++;
            recordCommandId(cmd.command_id);
            sendAck(cmd, result, "real_ir_control_disabled");
            break;
        case CommandStatus::REJECTED_EXPIRED:
            _rejected++;
            sendAck(cmd, result, "expired");
            break;
        case CommandStatus::REJECTED_DUPLICATE:
            _rejected++;
            sendAck(cmd, result, "duplicate");
            break;
        case CommandStatus::REJECTED_INVALID:
            _rejected++;
            sendAck(cmd, result, "invalid_schema");
            break;
        case CommandStatus::REJECTED_OUT_OF_RANGE:
            _rejected++;
            sendAck(cmd, result, "temperature_out_of_range");
            break;
        default:
            _rejected++;
            sendAck(cmd, CommandStatus::REJECTED_INVALID, "unknown");
            break;
    }
}

void CommandService::sendAck(const CloudCommand& cmd, CommandStatus status, const char* reason) {
    if (!_mqtt || !_mqtt->isConnected()) return;

    // Canonical status strings (must match web/backend expectations)
    const char* statusStr = "rejected";
    switch (status) {
        case CommandStatus::ACCEPTED_MOCK:          statusStr = "accepted_mock"; break;
        case CommandStatus::BLOCKED_BY_IR_POLICY:   statusStr = "blocked_by_ir_policy"; break;
        case CommandStatus::REJECTED_EXPIRED:       statusStr = "expired"; break;
        case CommandStatus::REJECTED_DUPLICATE:     statusStr = "duplicate"; break;
        case CommandStatus::IR_EXECUTED:            statusStr = "ir_executed"; break;
        case CommandStatus::IR_UNKNOWN_CODE:        statusStr = "ir_unknown_code"; break;
        case CommandStatus::IR_MODULE_BUSY:         statusStr = "ir_module_busy"; break;
        case CommandStatus::IR_EXECUTE_FAILED:      statusStr = "ir_execute_failed"; break;
        case CommandStatus::REJECTED_INVALID:
        case CommandStatus::REJECTED_OUT_OF_RANGE:
        default:                                    statusStr = "rejected"; break;
    }

    String ack;
    ack.reserve(192);
    ack = "{\"schema\":1";
    ack += ",\"command_id\":\"" + cmd.command_id + "\"";
    ack += ",\"status\":\"" + String(statusStr) + "\"";
    ack += ",\"reason\":\"" + String(reason) + "\"";
    ack += ",\"received_uptime_s\":" + String((uint32_t)(millis() / 1000));
    ack += "}";

    _mqtt->publishAck(ack.c_str());
    Serial.print(F("CMD_ACK command_id="));
    Serial.print(cmd.command_id);
    Serial.print(F(" status="));
    Serial.println(statusStr);
}

bool CommandService::isDuplicate(const String& cmdId) {
    for (uint8_t i = 0; i < MAX_RECENT; i++) {
        if (_recentIds[i] == cmdId) return true;
    }
    return false;
}

// §六: execute a validated IR action exactly once.
// `validation` is the result of validateCommand() (already covers expiry,
// duplicate, unknown-code, and build policy). This function NEVER emits during
// boot / reconnect / refresh (§五) — it is only reached from a fresh command.
void CommandService::dispatchIrAction(const CloudCommand& cmd, CommandStatus validation) {
    // Validation already failed -> ack and return (no emit).
    if (validation == CommandStatus::BLOCKED_BY_IR_POLICY) {
        _blocked++; recordCommandId(cmd.command_id);
        sendAck(cmd, CommandStatus::BLOCKED_BY_IR_POLICY, "real_ir_control_disabled");
        return;
    }
    if (validation == CommandStatus::IR_UNKNOWN_CODE) {
        _rejected++; recordCommandId(cmd.command_id);
        sendAck(cmd, CommandStatus::IR_UNKNOWN_CODE, "unknown_ir_code");
        return;
    }
    if (validation == CommandStatus::REJECTED_EXPIRED) {
        _rejected++; sendAck(cmd, CommandStatus::REJECTED_EXPIRED, "expired");
        return;
    }
    if (validation == CommandStatus::REJECTED_DUPLICATE) {
        _rejected++; sendAck(cmd, CommandStatus::REJECTED_DUPLICATE, "duplicate");
        return;
    }

    // ACCEPTED_MOCK -> proceed to one-shot emit (mutating build only).
    #if ENABLE_IR_MUTATING_COMMANDS
        const PrivateIrCode* code = findPrivateIrCode(cmd.ir_action_id.c_str());
        if (!code) {
            _rejected++; recordCommandId(cmd.command_id);
            sendAck(cmd, CommandStatus::IR_UNKNOWN_CODE, "unknown_ir_code");
            return;
        }
        // Copy PROGMEM frame -> RAM buffer (ESP8266 flash is memory-mapped, but
        // memcpy_P is the portable/correct way to read PROGMEM).
        static uint8_t frameBuf[IR_MAX_FRAME];
        memcpy_P(frameBuf, code->frame, code->len);
        IrSendOnceResult res = ir.sendExternalFrameOnce(
            frameBuf, code->len, code->codeId, cmd.command_id.c_str());
        recordCommandId(cmd.command_id);  // MQTT-level dedupe
        if (res.ok) {
            _accepted++;
            // §九: "ir_executed" = module was asked to emit once. NOT proof the
            // AC responded. reason reflects best-effort module ACK.
            sendAck(cmd, CommandStatus::IR_EXECUTED,
                    res.moduleAcked ? "ir_module_ack" : "ir_module_pending_no_ack");
        } else if (res.busy) {
            _blocked++;
            sendAck(cmd, CommandStatus::IR_MODULE_BUSY,
                    res.rejectReason ? res.rejectReason : "busy");
        } else {
            _rejected++;
            sendAck(cmd, CommandStatus::IR_EXECUTE_FAILED,
                    res.rejectReason ? res.rejectReason : "send_failed");
        }
    #endif
}

void CommandService::recordCommandId(const String& cmdId) {
    _recentIds[_recentIdx % MAX_RECENT] = cmdId;
    _recentIdx++;
}
