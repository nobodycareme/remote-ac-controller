#pragma once
#include <Arduino.h>
#include <SoftwareSerial.h>
#include "board_pins.h"
#include "app_config.h"

// ---------------------------------------------------------------------------
// ZJ-IR-V2 IR learn/emit module driver  (hardened streaming parser + counters)
// Protocol: 红外学习模块使用说明书 V1.0.6 (智家物联科技)
// Frame: 68 | LEN_LO | LEN_HI | ADDR | AFN | DATA... | CS | 16
//   LEN = total frame byte count (little-endian, 2 bytes), incl. header & tail
//   CS  = (ADDR + AFN + all DATA bytes) mod 256  (low 8 bits)
//   Downlink ADDR = 0xFF (broadcast) accepted; uplink ADDR = module's own (0x00).
// ---------------------------------------------------------------------------

// Function codes (AFN)
enum IrAfn : uint8_t {
  IR_AFN_ACK         = 0x01,  // response to control commands (status byte)
  IR_AFN_REPORT      = 0x02,  // unsolicited report (learn success / power-on send)
  IR_AFN_SET_BAUD    = 0x03,  // set baud rate (data: baud index)
  IR_AFN_GET_BAUD    = 0x04,  // get baud rate (no data)
  IR_AFN_SET_ADDR    = 0x05,  // set module address (FORBIDDEN without auth)
  IR_AFN_GET_ADDR    = 0x06,  // get module address (no data)
  IR_AFN_RESET       = 0x07,  // reset (FORBIDDEN)
  IR_AFN_FORMAT      = 0x08,  // format (FORBIDDEN)
  IR_AFN_LEARN_ENTER = 0x10,  // enter internal-code learn mode (data: group 0..6)
  IR_AFN_LEARN_EXIT  = 0x11,  // exit internal-code learn mode (no data)
  IR_AFN_SEND        = 0x12,  // send internal stored code (data: group 0..6)
  IR_AFN_SET_PWR_SEND = 0x13, // set power-on auto-send (FORBIDDEN)
  IR_AFN_GET_PWR_SEND = 0x14, // get power-on auto-send
  IR_AFN_SET_DELAY   = 0x15,  // set power-on send delay
  IR_AFN_GET_DELAY   = 0x16,  // get power-on send delay
  IR_AFN_WRITE_CODE  = 0x17,  // write internal code (FORBIDDEN)
  IR_AFN_READ_CODE   = 0x18,  // read internal code
  IR_AFN_EXT_LEARN_ENTER = 0x20, // enter EXTERNAL-code learn (no data) -> code streamed via AFN=22H
  IR_AFN_EXT_LEARN_EXIT  = 0x21, // exit external-code learn (no data)
  IR_AFN_EXT_SEND        = 0x22  // external code frame: learn stream OR re-injected send
};

// Baud-rate index table (manual p.12-14)
enum IrBaud : uint8_t {
  IR_BAUD_9600   = 0,
  IR_BAUD_19200  = 1,
  IR_BAUD_38400  = 2,
  IR_BAUD_57600  = 3,
  IR_BAUD_115200 = 4
};

// --- Bounds ---------------------------------------------------------------
// External-code buffer on the module is 800 bytes (manual p.5); a streamed
// AFN=22H frame can therefore be up to ~807 bytes. The parser buffer and the
// parsed-frame data field must accommodate that.
// §三: vendor external-code buffer is 800 B -> a streamed AFN=0x22H frame can
// be up to ~807 B. IR_MAX_FRAME must be >= 807 to accept the largest possible
// frame. 832 gives clean head-room. (Was 820, already >= 807 but bumped for
// unambiguous margin and to match the user's ">= 807 (832/1024)" requirement.)
static const uint16_t IR_MAX_FRAME  = 832;   // max total frame length we accept
static const uint16_t IR_MIN_FRAME  = 7;     // 68 + len(2) + addr + afn + cs + 16
static const uint16_t IR_MAX_DATA   = 810;   // parsed-frame data domain (external code)
static const uint8_t  IR_RESULT_DATA_MAX = 64; // small command responses (ack/baud)
static const uint16_t IR_PROBE_RAW_MAX   = 64; // probe only ever sees tiny frames
// SoftwareSerial RX byte-buffer capacity.
//  - IR_UART_RX_BUFFER      = full 1024 B, only needed when capturing an
//    EXTERNAL code (AFN=22H) that can be up to ~800 B.
//  - IR_UART_RX_BUFFER_SMALL = 128 B, ample for normal command replies (8 B for
//    GET_BAUD, <= ~20 B for others) AND for the 100-frame stress test. Using the
//    small buffer during the stress keeps ~1.5 KB of heap free so the concurrent
//    MQTT-TLS handshake (needs ~21 KB + a 3080-byte block) does not OOM.
static const int IR_UART_RX_BUFFER = 1024;
static const int IR_UART_RX_BUFFER_SMALL = 128;

// Stress-test timing (non-blocking). 200ms spacing: (a) gives the module
// ample time to finish transmitting its previous reply before the next query
// arrives (it was still dropping queries at 30ms and occasionally at 120ms);
// (b) lowers the per-second SoftwareSerial TX rate so ESP8266 WiFi RF bursts
// are less likely to collide with a probe send. Retries absorb the rare
// dropped/corrupt probe, so the test proves the link can deliver 100 VALID
// frames rather than merely that 100 probes were sent.
static const uint32_t IR_STRESS_GAP_MS = 200;          // gap between probe frames
static const uint32_t IR_STRESS_REPLY_TIMEOUT_MS = 2500; // per-response wait (module occasionally late; no retry)

// Parsed frame
struct IrFrame {
  bool     valid   = false;
  uint8_t  addr    = 0;
  uint8_t  afn     = 0;
  uint8_t  data[IR_MAX_DATA];
  uint16_t dataLen = 0;   // 800-byte external code needs >255; was uint8_t (BUG: truncated 800->32)
  uint8_t  checksum = 0;
};

// Read-only probe result
struct IrProbeResult {
  bool     gotAny     = false;
  uint8_t  raw[IR_PROBE_RAW_MAX];
  uint16_t rawLen     = 0;
  bool     headerOk   = false;
  bool     lengthOk   = false;
  bool     tailOk     = false;
  bool     checksumOk = false;
  bool     frameValid = false;
  uint8_t  addr       = 0;
  uint8_t  afn        = 0;
  uint8_t  dataLen    = 0;
  uint8_t  checksum   = 0;
  uint8_t  recvChecksum = 0;
  uint8_t  baudIndex  = 0;
};

// Result of a high-level operation (legacy, kept for compatibility)
struct IrResult {
  bool    ok       = false;
  uint8_t afn      = 0;
  uint8_t status   = 0;
  uint8_t data[IR_RESULT_DATA_MAX];
  uint8_t dataLen  = 0;
  uint32_t elapsedMs = 0;
};

// Module command result with ACK tracking (GATE 01/02)
struct ModuleCommandResult {
  uint8_t  commandAfn = 0;
  bool     sent = false;
  bool     ackReceived = false;
  bool     ackFrameValid = false;
  uint8_t  ackAfn = 0;
  uint8_t  ackStatus = 0;
  bool     timedOut = false;
  uint32_t startedAt = 0;
  uint32_t completedAt = 0;
  bool     ok = false;
  uint8_t  errorCode = 0;  // 0=OK, 1=rejected, 2=timeout, 3=bad_ack
};

// ---------------------------------------------------------------------------
// §二: Result of sendExternalFrameOnce() — layered, unambiguous.
//   ok                : the COMPLETE 22H frame was written to the module UART
//                       (byte count matched). This is the "we asked the module
//                       to emit" signal — NOT proof the AC responded.
//   frameValid        : the frame passed all structural checks (hdr/len/addr/
//                       afn/cs/tail) before being sent.
//   moduleAcked       : best-effort — we received *some* valid frame from the
//                       module within the ACK wait window after writing.
//   busy              : module was busy / commandId recently executed -> rejected.
//   mayHaveTransmitted: full frame written but NO module ACK observed. The IR
//                       may or may not have been emitted (ambiguous). Per §八,
//                       this is reported and NOT retried.
//   bytesWritten / frameLength : for audit.
// ---------------------------------------------------------------------------
struct IrSendOnceResult {
  bool     ok                 = false;
  bool     frameValid         = false;
  bool     moduleAcked        = false;
  bool     busy               = false;
  bool     mayHaveTransmitted = false;
  uint16_t bytesWritten       = 0;
  uint16_t frameLength        = 0;
  const char* codeId          = nullptr;
  const char* rejectReason    = nullptr;
};

// Streaming UART statistics (directive §三 counters)
struct IrUartStats {
  uint32_t rx_byte_count         = 0;
  uint32_t valid_frame_count     = 0;
  uint32_t checksum_failure_count= 0;
  uint32_t timeout_count         = 0;
  uint32_t overflow_count        = 0;
  uint32_t resync_count          = 0;
  // Frames accepted (IR_SCAN_OK) that should have been rejected. By parser
  // design scanOneFrame only returns OK after a passing checksum, so this is
  // and stays 0 (the gate's "false_accept=0" / "resync must not mis-receive"
  // requirement is satisfied structurally, not by masking).
  uint32_t false_accept_count    = 0;
};

// Frame-scan outcome
enum IrFrameScan : uint8_t {
  IR_SCAN_NONE   = 0,  // no complete candidate yet (partial in progress / no header)
  IR_SCAN_OK     = 1,  // a structurally valid frame was consumed
  IR_SCAN_CS_FAIL= 2   // a header/len/tail-plausible candidate failed checksum (consumed)
};

// Default operation timeout
static const uint32_t IR_DEFAULT_TIMEOUT_MS = 800;
static const uint32_t IR_LEARN_REPORT_TIMEOUT_MS = 30000;

class IrModule {
public:
  IrModule();

  void begin(uint32_t baud);
  // Open the UART with a chosen RX buffer. Default is the SMALL buffer (command
  // replies + stress). Pass IR_UART_RX_BUFFER when about to receive an 800-byte
  // external code. Never downgrades an already-open larger buffer.
  void ensureOpen(size_t rxBuf = IR_UART_RX_BUFFER_SMALL);
  void close();
  uint32_t baud() const { return m_baud; }

  size_t sendFrame(uint8_t afn, const uint8_t* data, uint8_t dataLen);
  size_t sendFrame(uint8_t afn) { return sendFrame(afn, nullptr, 0); }

  // §三: dataLen is uint16_t — an external 22H frame's data field can be 411+
  // bytes, which overflows uint8_t and would silently truncate the checksum.
  static uint8_t checksum(uint8_t addr, uint8_t afn, const uint8_t* data, uint16_t dataLen);

  // Blocking read of one valid frame within timeoutMs. Fills out on success.
  bool readFrame(uint32_t timeoutMs, IrFrame& out);

  IrResult queryBaud(uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  // Set module baud rate (AFN=03H, data=baud index 0..4). Mutating; caller
  // must switch ESP SoftwareSerial to the new baud afterward to stay synced.
  IrResult setBaud(uint8_t index, uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  void probeCapture(uint32_t timeoutMs, IrProbeResult& out);

  IrResult enterLearn(uint8_t group, uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  IrResult exitLearn(uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  IrResult sendGroup(uint8_t group, uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  IrResult waitLearnReport(uint32_t timeoutMs);

  static uint32_t baudIndexToValue(uint8_t idx);

  static bool mutatingCommandsAllowed() {
#if ENABLE_IR_MUTATING_COMMANDS
    return true;
#else
    return false;
#endif
  }

  static void frameToHex(const uint8_t* buf, uint8_t len, char* out, size_t outSize);
  // Chunked hex printer (no large stack buffer) — safe for big external-code frames.
  static void printHex(const uint8_t* buf, uint16_t len);

  // ---- Streaming parser + counters (directive §三) ----
  // Pump available bytes into m_buf (bounded; overflow discards whole frame).
  // Returns true if any byte was read.
  bool pumpInput();
  // Scan m_buf for one frame. On OK/CS_FAIL consumes the candidate bytes.
  // Updates counters. Returns the outcome; on OK fills `out`.
  bool pumpAndParse(IrFrame& out, bool& csFail);
  const IrUartStats& stats() const { return m_stats; }
  void resetStats() { m_stats = IrUartStats(); }

  // ---- Non-blocking 100-frame stress test (directive §三) ----
  void startStress(int target);
  void tickStress();          // call every loop() iteration while active
  bool stressActive() const { return m_stressActive; }
  int  stressSuccesses() const { return m_stressSuccesses; }

  // ---- Fixed (no-retry) first-attempt 100-query test (user gate) ----
  // Sends exactly `target` GET_BAUD queries once each; counts first-attempt
  // successes, timeouts, checksum failures, overflows, resyncs. No resend.
  void startStressFixed(int target);
  void tickStressFixed();
  bool stressFixedActive() const { return m_fixedActive; }

  // ---- Bounded-retry (max 3) query reliability test (user engineering gate) ----
  // Performs `target` logical GET_BAUD queries; each gets up to 3 attempts with
  // explicit doubling backoff. Tracks first-attempt vs post-retry success, and
  // raw timeout / checksum / overflow / false_accept counts. No infinite loop;
  // on exhausted retries it records a hard failure and does NOT save a half-frame.
  void startStressBounded(int target);
  void tickStressBounded();
  bool stressBoundedActive() const { return m_boundedActive; }
  uint32_t falseAcceptCount() const { return m_stats.false_accept_count; }

  // ---- 800-byte external-code frame parser self-test (injected, no real IR) ----
  // Builds an ~800-byte AFN=22H frame and validates length/CS/tail via the
  // same static scanner the UART path uses.
  bool selfTestLongFrame();

  // ---- External-code learn capture (directive §五/§六 preparation) ----
  // Enters AFN=20H learn; captures the AFN=22H streamed frame. NO replay.
  bool enterExtLearn();
  ModuleCommandResult enterExtLearnConfirmed();
  IrResult exitExtLearn(uint32_t timeoutMs = IR_DEFAULT_TIMEOUT_MS);
  void tickExtLearn();         // call every loop() iteration while active
  bool extLearnActive() const { return m_extLearnActive; }
  void clearExtLearnCapture();
  // Last captured external frame (full bytes incl. header..tail), 0 if none.
  uint16_t extLearnFrame(uint8_t* outBuf, uint16_t outMax) const;
  uint8_t  extLearnChecksum() const { return m_extLearnChecksum; }

  // Re-inject a previously captured external frame (send). Gated, NOT auto-called.
  bool extSendCaptured();

  // ---- §二: ONE-SHOT external 22H frame replay (vendor-confirmed emit path) ----
  // Writes the COMPLETE 22H frame (header..tail, verbatim) to the module UART.
  // Per ZJ-IR-V2 V1.0.6 (A-level): sending the complete 22H frame back to the
  // module makes it extract the IR data and emit ONCE. There is NO separate
  // "store then emit" step.  18-step validation + layered result. Executes
  // exactly once, NO auto-retry. Only call this from a validated, unexpired,
  // owner-authorized command path (NEVER on boot / Wi-Fi or MQTT reconnect /
  // web refresh / status query — §五).
  IrSendOnceResult sendExternalFrameOnce(const uint8_t* frame, size_t frameLength,
                                         const char* codeId, const char* commandId);

  // Chunked external-code load for controlled single-shot replay (directive §四/§六).
  // Does NOT emit: only stages bytes that extSendCaptured() will later forward to the module.
  // Host sends `ir extload <hexchunk>` (one or more) then `ir extload commit`.
  uint16_t extLoadAppend(const uint8_t* buf, uint16_t len);  // append a chunk; returns new stage len, 0 on overflow
  uint16_t extLoadCommit();                                  // finalize staging -> m_extLearnBuf; returns len, 0 if invalid
  void     extLoadClear();                                   // §十一: discard staged bytes (no emit)
  uint16_t extLoadStageLen() const { return m_extLoadStageLen; }
  uint16_t extLearnLen() const { return m_extLearnLen; }

  static bool isKnownAfn(uint8_t afn);

private:
  SoftwareSerial m_serial;
  uint32_t m_baud = 0;
  bool     m_opened = false;
  size_t   m_openedRxBuf = 0;
  uint8_t  m_buf[IR_MAX_FRAME];
  uint16_t m_bufLen = 0;
  IrUartStats m_stats;

  void flushInput();
  // Drop leading non-0x68 garbage; keep a trailing partial header. Counts resync.
  void resyncBuffer();

  // Stress state
  bool    m_stressActive = false;
  int     m_stressTarget = 0;     // gate: number of VALID frames required
  int     m_stressSent = 0;       // total probe frames sent (incl. retries)
  int     m_stressSuccesses = 0;  // valid frames actually received (gate target)
  int     m_stressMaxSent = 0;    // safety cap to avoid an endless retry loop
  uint32_t m_stressNextSend = 0;
  bool    m_stressAwaiting = false;
  uint32_t m_stressWaitStart = 0;
  void finishStress();

  // Fixed (no-retry) stress state
  bool    m_fixedActive = false;
  int     m_fixedTarget = 0;
  int     m_fixedSent = 0;
  uint32_t m_fixedNextSend = 0;
  bool    m_fixedAwaiting = false;
  uint32_t m_fixedWaitStart = 0;
  void finishStressFixed();

  // Bounded-retry (max 3) stress state
  static const uint8_t IR_BOUNDED_MAX_RETRY = 3;  // attempts per logical query
  bool    m_boundedActive = false;
  int     m_boundedTarget = 0;       // logical queries to perform
  int     m_boundedQuery  = 0;       // current logical query index (0-based)
  uint8_t m_boundedAttempt= 0;       // attempt within current query (0-based)
  int     m_boundedFirstSuccess = 0; // logical queries OK on attempt 0 (first-round)
  int     m_boundedFinalSuccess = 0; // logical queries OK within MAX_RETRY
  int     m_boundedFailures = 0;     // logical queries that exhausted retries (hard fail)
  int     m_boundedTotalAttempts = 0;// total attempts sent (for timeout rate)
  uint32_t m_boundedNextSend = 0;
  bool    m_boundedAwaiting = false;
  uint32_t m_boundedWaitStart = 0;
  void finishStressBounded();

  // External-learn capture state
  bool    m_extLearnActive = false;
  uint32_t m_extLearnDeadline = 0;
  uint8_t  m_extLearnBuf[IR_MAX_FRAME];
  uint16_t m_extLearnLen = 0;
  uint8_t  m_extLearnChecksum = 0;

  // Staging buffer for chunked `ir extload` (no emit until extSendCaptured()).
  uint8_t  m_extLoadStaging[IR_MAX_FRAME];
  uint16_t m_extLoadStageLen = 0;

  // ---- §二 / §八: one-shot external-send guards ----
  bool    m_sendBusy = false;            // true while a send is in flight
  // Recently-executed commandId cache (per-boot RAM; TTL-gated dedupe so a
  // command is never replayed within its lifetime, and double-clicks are blocked).
  static const uint8_t  IR_EXEC_CACHE_MAX = 8;
  static const uint32_t IR_EXEC_TTL_MS    = 30000;  // 30 s (§八 TTL window)
  struct IrExecRecord { char id[44]; uint32_t at; };
  IrExecRecord m_execCache[IR_EXEC_CACHE_MAX];
  uint8_t      m_execCacheIdx = 0;

  bool    commandIdRecentlyExecuted(const char* id) const;
  void    recordExecutedCommandId(const char* id);
  // Validate a full external 22H frame structurally (steps 4-9 of §二) without
  // sending. Returns true if header/LEN/ADDR/AFN/CS/tail all check out.
  bool    validateExternalFrame(const uint8_t* frame, uint16_t frameLength) const;
};
