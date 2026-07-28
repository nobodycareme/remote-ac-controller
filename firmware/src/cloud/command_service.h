#pragma once
/*
 * command_service.h — MQTT command dispatch and ACK service (v0.4.0)
 *
 * Receives control commands via MQTT, validates them, and dispatches ACKs.
 * Currently IR mutating commands are BLOCKED by policy.
 * All commands go through validation: command_id uniqueness, expiry, schema.
 */
#include <Arduino.h>
#include "cloud/mqtt_client.h"

// Command action types
enum class CommandAction : uint8_t {
    UNKNOWN = 0,
    SET_POWER,
    SET_TEMPERATURE,
    SET_MODE,
    SET_FAN_SPEED,
    SET_STATE,
    IR_ACTION            // §六: external 22H frame replay (real IR emit)
};

// Command validation result
enum class CommandStatus : uint8_t {
    PENDING = 0,
    ACCEPTED_MOCK,       // accepted but not executed (IR disabled)
    BLOCKED_BY_IR_POLICY,// IR mutations disabled
    REJECTED_INVALID,    // schema/validation failure
    REJECTED_EXPIRED,    // expires_at in the past
    REJECTED_DUPLICATE,  // command_id already seen
    REJECTED_OUT_OF_RANGE,// temperature/mode out of allowed range
    IR_EXECUTED,         // §六: full 22H frame written to module (asked to emit once)
    IR_UNKNOWN_CODE,     // ir_action_id not found in registry
    IR_MODULE_BUSY,      // module busy / commandId recently executed
    IR_EXECUTE_FAILED    // UART write short / other failure
};

// Incoming command structure (parsed from JSON)
struct CloudCommand {
    String    command_id;        // unique ID from cloud
    uint64_t  expires_at;        // Unix timestamp in ms (backend Date.now) or seconds
    CommandAction action = CommandAction::UNKNOWN;
    bool      power = false;     // true = on, false = off
    float     target_temperature_c = 26.0f;
    String    raw_json;          // original JSON for ACK echo
    // §六: IR action fields
    String    type;              // protocol type, e.g. "ir_action"
    String    ir_action_id;      // short codeId, e.g. hisense_cool_24_..._v1
};

class CommandService {
public:
    CommandService();

    // Attach MQTT client and begin listening
    void begin(MqttClientWrapper* mqtt);

    // Process incoming MQTT messages — called from MQTT callback
    void handleMessage(const char* topic, const uint8_t* payload, unsigned int length);

    // Stats
    uint32_t commandsReceived() const { return _received; }
    uint32_t commandsAccepted() const { return _accepted; }
    uint32_t commandsBlocked()  const { return _blocked; }
    uint32_t commandsRejected() const { return _rejected; }

    // Last command info
    const CloudCommand& lastCommand() const { return _lastCmd; }
    CommandStatus lastStatus() const { return _lastStatus; }

private:
    MqttClientWrapper* _mqtt;

    // Deduplication: store up to 32 recent command_ids
    static const uint8_t MAX_RECENT = 32;
    String _recentIds[MAX_RECENT];
    uint8_t _recentIdx;

    void sendAck(const CloudCommand& cmd, CommandStatus status, const char* detail);
    bool isDuplicate(const String& cmdId);
    void recordCommandId(const String& cmdId);
    // §六: execute a validated IR action exactly once (one-shot 22H replay).
    void dispatchIrAction(const CloudCommand& cmd, CommandStatus validation);

    CommandStatus validateCommand(const CloudCommand& cmd);
    bool parseCommand(const String& json, CloudCommand& cmd);

    uint32_t _received;
    uint32_t _accepted;
    uint32_t _blocked;
    uint32_t _rejected;
    CloudCommand _lastCmd;
    CommandStatus _lastStatus;
};
