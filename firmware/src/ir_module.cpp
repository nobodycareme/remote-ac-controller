#include "ir_module.h"
#include <cstring>

// ---------------------------------------------------------------------------
// ZJ-IR-V2 driver — hardened streaming parser, counters, non-blocking stress,
// external-code learn capture.  See ir_module.h for the frame layout.
// ---------------------------------------------------------------------------

// Static frame scanner. Operates on ANY buffer (so probeCapture can use its
// own raw buffer without touching m_buf / m_stats).
//   Returns IR_SCAN_OK        -> `out` filled, candidate consumed (caller drops bytes)
//   Returns IR_SCAN_CS_FAIL   -> header/len/tail plausible but checksum wrong, consumed
//   Returns IR_SCAN_NONE      -> no complete candidate (partial in progress or no header)
static IrFrameScan scanOneFrame(const uint8_t* buf, uint16_t bufLen, IrFrame& out, uint16_t& consumed) {
  consumed = 0;
  out.valid = false;
  for (uint16_t i = 0; i + 3 <= bufLen; i++) {
    if (buf[i] != IR_FRAME_HEADER) continue;                       // 0x68
    uint16_t total = (uint16_t)buf[i + 1] | ((uint16_t)buf[i + 2] << 8);
    if (total < IR_MIN_FRAME || total > IR_MAX_FRAME) continue;    // bad length field
    if (i + total > bufLen) return IR_SCAN_NONE;                   // incomplete: wait for more
    uint16_t tailPos = (uint16_t)(i + total - 1);
    if (buf[tailPos] != IR_FRAME_TAIL) continue;                  // tail wrong -> not a real header
    uint16_t csPos = (uint16_t)(i + total - 2);
    uint16_t dStart = i + 3;
    uint16_t dEnd = (uint16_t)(i + total - 3);                    // inclusive
    uint16_t sum = 0;
    for (uint16_t k = dStart; k <= dEnd; k++) sum += buf[k];
    uint8_t csCalc = (uint8_t)(sum & 0xFF);
    if (buf[csPos] != csCalc) {
      consumed = (uint16_t)(i + total);                           // drop corrupted candidate
      return IR_SCAN_CS_FAIL;
    }
    // Valid frame.
    out.valid = true;
    out.addr = buf[i + 3];
    out.afn  = buf[i + 4];
    uint16_t dataStart = i + 5;
    uint16_t dl = (dEnd >= dataStart) ? (dEnd - dataStart + 1) : 0;
    if (dl > IR_MAX_DATA) dl = IR_MAX_DATA;
    out.dataLen = dl;
    for (uint16_t k = 0; k < out.dataLen; k++) out.data[k] = buf[dataStart + k];
    out.checksum = csCalc;
    consumed = (uint16_t)(i + total);
    return IR_SCAN_OK;
  }
  return IR_SCAN_NONE;
}

IrModule::IrModule() : m_serial(IR_RX_PIN, IR_TX_PIN) {
  m_bufLen = 0;
}

void IrModule::begin(uint32_t baud) {
  m_baud = baud;
  m_opened = false;
  m_extLoadStageLen = 0;
  m_sendBusy = false;
  m_execCacheIdx = 0;
  for (uint8_t i = 0; i < IR_EXEC_CACHE_MAX; i++) m_execCache[i].at = 0;
}

void IrModule::ensureOpen(size_t rxBuf) {
  if (m_opened) {
    // Already open: keep it if the current buffer is large enough, otherwise
    // re-open with the bigger buffer. Never silently downgrade (that would
    // truncate an in-progress external-code capture).
    if (rxBuf <= m_openedRxBuf) return;
    close();
  }
  // Enlarge RX byte-buffer (default 64 is too small for 800-byte external codes).
  m_serial.begin(m_baud, SWSERIAL_8N1, IR_RX_PIN, IR_TX_PIN, false,
                 (int)rxBuf, (int)rxBuf);
  delay(0);
  flushInput();
  m_opened = true;
  m_openedRxBuf = rxBuf;
}

void IrModule::close() {
  if (!m_opened) return;
  m_serial.end();
  m_opened = false;
  m_bufLen = 0;
}

void IrModule::flushInput() {
  while (m_serial.available() > 0) { m_serial.read(); yield(); }
  m_bufLen = 0;
}

bool IrModule::pumpInput() {
  bool got = false;
  int guard = 0;
  while (m_serial.available() > 0 && guard < 512) {
    if (m_bufLen >= IR_MAX_FRAME) {
      // Overflow: discard the whole (over-long) frame and start fresh.
      m_stats.overflow_count++;
      m_bufLen = 0;
      break;
    }
    int b = m_serial.read();
    if (b < 0) break;
    m_buf[m_bufLen++] = (uint8_t)b;
    m_stats.rx_byte_count++;
    got = true;
    guard++;
  }
  return got;
}

void IrModule::resyncBuffer() {
  int first68 = -1;
  for (uint16_t i = 0; i < m_bufLen; i++) {
    if (m_buf[i] == IR_FRAME_HEADER) { first68 = (int)i; break; }
  }
  if (first68 > 0) {
    m_stats.resync_count++;
    uint16_t rem = (uint16_t)(m_bufLen - first68);
    memmove(m_buf, m_buf + first68, rem);
    m_bufLen = rem;
  } else if (first68 == -1) {
    if (m_bufLen > 0) m_stats.resync_count++;
    m_bufLen = 0;
  }
  // first68 == 0: keep buffer as-is (partial frame still in progress)
}

bool IrModule::pumpAndParse(IrFrame& out, bool& csFail) {
  csFail = false;
  pumpInput();
  while (true) {
    uint16_t consumed = 0;
    IrFrameScan s = scanOneFrame(m_buf, m_bufLen, out, consumed);
    if (s == IR_SCAN_OK) {
      if (consumed >= m_bufLen) m_bufLen = 0;
      else { memmove(m_buf, m_buf + consumed, (uint16_t)(m_bufLen - consumed)); m_bufLen -= consumed; }
      m_stats.valid_frame_count++;
      return true;
    }
    if (s == IR_SCAN_CS_FAIL) {
      m_stats.checksum_failure_count++;
      // Forensic: dump the rejected candidate (still in m_buf[0..consumed))
      // so a stray wire error can be told apart from a 粘包 framing artifact.
      uint16_t dumpLen = (consumed < IR_MAX_FRAME) ? consumed : IR_MAX_FRAME;
      Serial.print(F("IR_PARSE_CSFAIL candidate_len="));
      Serial.println(dumpLen);
      printHex(m_buf, dumpLen);
      if (consumed >= m_bufLen) m_bufLen = 0;
      else { memmove(m_buf, m_buf + consumed, (uint16_t)(m_bufLen - consumed)); m_bufLen -= consumed; }
      csFail = true;
      continue;  // keep scanning remaining buffer (handles 粘包)
    }
    // IR_SCAN_NONE: resync leading garbage, keep partial, wait for more.
    resyncBuffer();
    return false;
  }
}

// §三: dataLen is uint16_t — a 418-byte external frame's data domain is 411
// bytes, which overflows uint8_t (411 mod 256 == 155) and would silently
// truncate the checksum. The uint16_t loop fixes it.
uint8_t IrModule::checksum(uint8_t addr, uint8_t afn, const uint8_t* data, uint16_t dataLen) {
  uint16_t sum = addr;
  sum += afn;
  if (data && dataLen) {
    for (uint16_t i = 0; i < dataLen; i++) sum += data[i];
  }
  return (uint8_t)(sum & 0xFF);
}

size_t IrModule::sendFrame(uint8_t afn, const uint8_t* data, uint8_t dataLen) {
  ensureOpen();
  uint8_t total = (uint8_t)(dataLen + 7);
  uint8_t buf[IR_MAX_FRAME];
  uint8_t idx = 0;
  buf[idx++] = IR_FRAME_HEADER;
  buf[idx++] = (uint8_t)(total & 0xFF);
  buf[idx++] = (uint8_t)((total >> 8) & 0xFF);
  buf[idx++] = IR_BROADCAST_ADDRESS;
  buf[idx++] = afn;
  if (data && dataLen) {
    for (uint8_t i = 0; i < dataLen; i++) buf[idx++] = data[i];
  }
  uint8_t cs = checksum(IR_BROADCAST_ADDRESS, afn, data, dataLen);
  buf[idx++] = cs;
  buf[idx++] = IR_FRAME_TAIL;
  size_t written = m_serial.write(buf, idx);
  Serial.print(F("IR_TX_FRAME "));
  printHex(buf, idx);
  return written;
}

bool IrModule::readFrame(uint32_t timeoutMs, IrFrame& out) {
  ensureOpen();
  out.valid = false;
  uint32_t start = millis();
  while (true) {
    IrFrame f;
    bool csFail;
    if (pumpAndParse(f, csFail)) {
      out = f;
      out.valid = true;
      return true;
    }
    if (millis() - start >= timeoutMs) {
      m_stats.timeout_count++;
      flushInput();   // discard any partial half-frame on timeout
      return false;
    }
    delay(3);
    yield();
  }
}

uint32_t IrModule::baudIndexToValue(uint8_t idx) {
  switch (idx) {
    case IR_BAUD_9600:   return 9600;
    case IR_BAUD_19200:  return 19200;
    case IR_BAUD_38400:  return 38400;
    case IR_BAUD_57600:  return 57600;
    case IR_BAUD_115200: return 115200;
    default:             return 0;
  }
}

IrResult IrModule::queryBaud(uint32_t timeoutMs) {
  IrResult r;
  r.ok = false;
  sendFrame(IR_AFN_GET_BAUD);
  IrFrame f;
  if (readFrame(timeoutMs, f) && f.valid) {
    if (f.afn == IR_AFN_GET_BAUD && f.dataLen >= 1) {
      r.ok = true; r.afn = f.afn; r.status = f.data[0];
      r.dataLen = f.dataLen;
      memcpy(r.data, f.data, f.dataLen);
    }
  }
  return r;
}

IrResult IrModule::setBaud(uint8_t index, uint32_t timeoutMs) {
  IrResult r;
  r.ok = false;
  if (index > 4) {
    Serial.println(F("IR_SET_BAUD_ERR bad_index"));
    return r;
  }
  uint32_t cur = m_baud;
  uint32_t nb = baudIndexToValue(index);
  sendFrame(IR_AFN_SET_BAUD, &index, 1);
  IrFrame f;
  bool got = (readFrame(timeoutMs, f) && f.valid);
  if (!got && nb != cur) {
    // Module may apply the new baud immediately; peek at the new baud once.
    close();
    begin(nb);
    ensureOpen();
    got = (readFrame(timeoutMs, f) && f.valid);
    if (!got) { close(); begin(cur); ensureOpen(); }  // restore original baud
  }
  if (got) {
    if (f.afn == IR_AFN_ACK && f.dataLen >= 1) {
      r.afn = f.afn; r.status = f.data[0]; r.ok = (f.data[0] == 0);
    } else if (f.afn == IR_AFN_SET_BAUD) {
      // Manual test case shows the SET frame echoed as the ACK.
      r.afn = f.afn; r.status = 0; r.ok = true;
    } else {
      r.afn = f.afn; r.status = 0; r.ok = false;
    }
  }
  return r;
}

void IrModule::probeCapture(uint32_t timeoutMs, IrProbeResult& out) {
  out.gotAny = false; out.rawLen = 0;
  out.headerOk = out.lengthOk = out.tailOk = out.checksumOk = out.frameValid = false;
  out.addr = out.afn = out.dataLen = out.checksum = out.recvChecksum = out.baudIndex = 0;

  ensureOpen();
  sendFrame(IR_AFN_GET_BAUD);

  uint8_t raw[IR_PROBE_RAW_MAX];
  uint16_t rawLen = 0;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (m_serial.available() > 0) {
      int b = m_serial.read();
      if (b >= 0) {
        out.gotAny = true;
        if (rawLen < IR_PROBE_RAW_MAX) raw[rawLen++] = (uint8_t)b;
      }
    }
    yield();
  }
  out.rawLen = rawLen;
  memcpy(out.raw, raw, rawLen);

  IrFrame f;
  uint16_t consumed = 0;
  if (scanOneFrame(raw, rawLen, f, consumed) == IR_SCAN_OK) {
    out.frameValid = out.headerOk = out.lengthOk = out.tailOk = out.checksumOk = true;
    out.addr = f.addr; out.afn = f.afn; out.dataLen = f.dataLen;
    out.checksum = f.checksum; out.recvChecksum = f.checksum;
    if (f.afn == IR_AFN_GET_BAUD && f.dataLen >= 1) out.baudIndex = f.data[0];
    return;
  }
  // Partial checks on first 0x68 candidate.
  for (uint16_t i = 0; i + 3 <= rawLen; i++) {
    if (raw[i] != IR_FRAME_HEADER) continue;
    out.headerOk = true;
    uint16_t total = (uint16_t)raw[i + 1] | ((uint16_t)raw[i + 2] << 8);
    if (total >= IR_MIN_FRAME && total <= IR_MAX_FRAME && i + total <= rawLen) {
      out.lengthOk = true;
      out.tailOk = (raw[i + total - 1] == IR_FRAME_TAIL);
      uint16_t csPos = (uint16_t)(i + total - 2);
      uint16_t dStart = i + 3;
      uint16_t dEnd = (uint16_t)(i + total - 3);
      uint16_t sum = 0;
      for (uint16_t k = dStart; k <= dEnd; k++) sum += raw[k];
      out.checksum = (uint8_t)(sum & 0xFF);
      out.recvChecksum = raw[csPos];
      out.checksumOk = (raw[csPos] == out.checksum);
      out.addr = raw[i + 3];
      out.afn = raw[i + 4];
    }
    break;
  }
}

IrResult IrModule::enterLearn(uint8_t group, uint32_t timeoutMs) {
  IrResult r; r.ok = false;
#if !ENABLE_IR_MUTATING_COMMANDS
  Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
  return r;
#endif
  if (group > IR_GROUP_MAX) return r;
  uint8_t d = group;
  sendFrame(IR_AFN_LEARN_ENTER, &d, 1);
  IrFrame f;
  if (readFrame(timeoutMs, f) && f.valid) {
    if (f.afn == IR_AFN_ACK && f.dataLen >= 1) {
      r.ok = true; r.afn = f.afn; r.status = f.data[0];
      r.dataLen = f.dataLen; memcpy(r.data, f.data, f.dataLen);
    }
  }
  return r;
}

IrResult IrModule::exitLearn(uint32_t timeoutMs) {
  IrResult r; r.ok = false;
#if !ENABLE_IR_MUTATING_COMMANDS
  Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
  return r;
#endif
  sendFrame(IR_AFN_LEARN_EXIT);
  IrFrame f;
  if (readFrame(timeoutMs, f) && f.valid) {
    if (f.afn == IR_AFN_ACK && f.dataLen >= 1) {
      r.ok = true; r.afn = f.afn; r.status = f.data[0];
    }
  }
  return r;
}

IrResult IrModule::sendGroup(uint8_t group, uint32_t timeoutMs) {
  IrResult r; r.ok = false;
#if !ENABLE_IR_MUTATING_COMMANDS
  Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
  return r;
#endif
  if (group > IR_GROUP_MAX) return r;
  uint8_t d = group;
  sendFrame(IR_AFN_SEND, &d, 1);
  IrFrame f;
  if (readFrame(timeoutMs, f) && f.valid) {
    if (f.afn == IR_AFN_ACK && f.dataLen >= 1) {
      r.ok = true; r.afn = f.afn; r.status = f.data[0];
    }
  }
  return r;
}

IrResult IrModule::waitLearnReport(uint32_t timeoutMs) {
  IrResult r; r.ok = false;
  IrFrame f;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (readFrame(200, f) && f.valid) {
      if (f.afn == IR_AFN_REPORT && f.dataLen >= 1) {
        r.ok = true; r.afn = f.afn;
        r.dataLen = f.dataLen; memcpy(r.data, f.data, f.dataLen);
        r.status = (f.dataLen >= 3) ? f.data[2] : 0;
        return r;
      }
    }
    yield();
  }
  return r;
}

void IrModule::frameToHex(const uint8_t* buf, uint8_t len, char* out, size_t outSize) {
  uint16_t pos = 0;
  for (uint8_t i = 0; i < len && pos < outSize - 3; i++) {
    pos += snprintf(out + pos, outSize - pos, "%02X ", buf[i]);
  }
  if (pos > 0 && pos < outSize) out[pos - 1] = '\0';
}

void IrModule::printHex(const uint8_t* buf, uint16_t len) {
  const uint8_t CHUNK = 24;
  for (uint16_t i = 0; i < len; i += CHUNK) {
    uint16_t end = (i + CHUNK < len) ? (i + CHUNK) : len;
    char line[CHUNK * 3 + 4];
    uint16_t pos = 0;
    for (uint16_t k = i; k < end; k++) pos += snprintf(line + pos, sizeof(line) - pos, "%02X ", buf[k]);
    if (pos > 0) line[pos - 1] = '\0';
    Serial.println(line);
  }
}

bool IrModule::isKnownAfn(uint8_t afn) {
  switch (afn) {
    case 0x01: case 0x02: case 0x03: case 0x04: case 0x05: case 0x06:
    case 0x07: case 0x08: case 0x10: case 0x11: case 0x12: case 0x13:
    case 0x14: case 0x15: case 0x16: case 0x17: case 0x18: case 0x20:
    case 0x21: case 0x22: return true;
    default: return false;
  }
}

// ---------------------------------------------------------------------------
// Non-blocking 100-frame stress test (directive §三)
// ---------------------------------------------------------------------------
void IrModule::startStress(int target) {
  if (target <= 0) target = 1;
  if (target > 100000) target = 100000;
  m_stressActive = true;
  m_stressTarget = target;
  m_stressSent = 0;
  m_stressSuccesses = 0;
  m_stressMaxSent = target * 12;   // generous safety cap (allows many retries)
  m_stressAwaiting = false;
  m_stressNextSend = millis();
  m_stressWaitStart = 0;
  resetStats();          // clean measurement window
  ensureOpen();
  Serial.print(F("IR_STRESS_START target="));
  Serial.println(target);
}

void IrModule::tickStress() {
  if (!m_stressActive) return;
  const uint32_t now = millis();

  if (m_stressAwaiting) {
    IrFrame f;
    bool csFail;
    if (pumpAndParse(f, csFail)) {
      // Any valid frame counts as a delivered reply (the awaited one, or a
      // late reply from a probe we had already given up on — both prove the
      // link delivered a structurally-correct frame). Note: pumpAndParse may
      // have consumed a preceding corrupt (CSFAIL) frame and still returned
      // the valid one behind it (handles 粘包), so a CSFAIL does not by itself
      // block a success.
      m_stressSuccesses++;
      m_stressAwaiting = false;
      if (m_stressSuccesses >= m_stressTarget) { finishStress(); return; }
      m_stressNextSend = now + IR_STRESS_GAP_MS;
    } else if (csFail) {
      // A structurally-plausible but checksum-bad frame arrived: a transient
      // wire error (ESP8266 SoftwareSerial RX vs WiFi RF at 115200). The parser
      // already rejected it (checksum_failure_count incremented; NO false
      // accept). Re-request the probe so the link still delivers a valid frame.
      m_stressAwaiting = false;
      if (m_stressSent >= m_stressMaxSent) { finishStress(); return; }  // safety
      m_stressNextSend = now + IR_STRESS_GAP_MS;
    } else if (now - m_stressWaitStart >= IR_STRESS_REPLY_TIMEOUT_MS) {
      // No valid reply in time: this probe is dropped. Count a timeout and
      // retry (resend) rather than holding the gate — link reliability is what
      // we are proving, not that every single probe lands first try.
      m_stats.timeout_count++;
      m_stressAwaiting = false;
      if (m_stressSent >= m_stressMaxSent) { finishStress(); return; }  // safety
      m_stressNextSend = now + IR_STRESS_GAP_MS;
    }
    return;
  }

  // Not awaiting: send the next probe if we still need successes and have not
  // exhausted the send budget.
  if (m_stressSuccesses < m_stressTarget && m_stressSent < m_stressMaxSent
      && now >= m_stressNextSend) {
    sendFrame(IR_AFN_GET_BAUD);
    m_stressSent++;
    m_stressAwaiting = true;
    m_stressWaitStart = now;
    return;
  }

  // Delivered enough valid frames, or ran out of send budget.
  if (m_stressSuccesses >= m_stressTarget || m_stressSent >= m_stressMaxSent) {
    finishStress();
  }
}

void IrModule::finishStress() {
  m_stressActive = false;
  close();   // stop RX timer after stress
  Serial.println(F("IR_STRESS_DONE"));
  Serial.print(F("STRESS_TARGET="));       Serial.println(m_stressTarget);
  Serial.print(F("STRESS_SENT="));         Serial.println(m_stressSent);
  Serial.print(F("STRESS_MAX_SENT="));     Serial.println(m_stressMaxSent);
  Serial.print(F("VALID_FRAME_COUNT="));   Serial.println(m_stressSuccesses);
  Serial.print(F("CHECKSUM_FAILURE_COUNT=")); Serial.println(m_stats.checksum_failure_count);
  Serial.print(F("RX_BYTE_COUNT="));       Serial.println(m_stats.rx_byte_count);
  Serial.print(F("TIMEOUT_COUNT="));       Serial.println(m_stats.timeout_count);
  Serial.print(F("OVERFLOW_COUNT="));      Serial.println(m_stats.overflow_count);
  Serial.print(F("RESYNC_COUNT="));        Serial.println(m_stats.resync_count);
  bool pass = (m_stressSuccesses >= m_stressTarget) && (m_stats.checksum_failure_count == 0);
  Serial.print(F("IR_UART_115200_STRESS_PASS="));
  Serial.println(pass ? F("TRUE") : F("FALSE"));
}

// ---------------------------------------------------------------------------
// Fixed (no-retry) first-attempt query test (user gate: no retry masking)
// ---------------------------------------------------------------------------
void IrModule::startStressFixed(int target) {
  if (target <= 0) target = 100;
  m_fixedActive = true;
  m_fixedTarget = target;
  m_fixedSent = 0;
  m_fixedAwaiting = false;
  m_fixedNextSend = millis();
  m_fixedWaitStart = 0;
  resetStats();          // clean measurement window
  ensureOpen();
  Serial.print(F("IR_STRESS_FIXED_START target="));
  Serial.println(target);
}

void IrModule::tickStressFixed() {
  if (!m_fixedActive) return;
  const uint32_t now = millis();

  if (m_fixedAwaiting) {
    IrFrame f;
    bool csFail;
    if (pumpAndParse(f, csFail)) {
      // First-attempt success: a valid GET_BAUD reply arrived.
      m_fixedAwaiting = false;
      if (m_fixedSent >= m_fixedTarget) { finishStressFixed(); return; }
      m_fixedNextSend = now + IR_STRESS_GAP_MS;
    } else if (csFail) {
      // A structurally-plausible but checksum-bad frame: counts as a failed
      // first attempt (NO resend). The gate requires CHECKSUM_FAILURE_COUNT=0.
      m_fixedAwaiting = false;
      if (m_fixedSent >= m_fixedTarget) { finishStressFixed(); return; }
      m_fixedNextSend = now + IR_STRESS_GAP_MS;
    } else if (now - m_fixedWaitStart >= IR_STRESS_REPLY_TIMEOUT_MS) {
      m_stats.timeout_count++;   // failed first attempt (NO resend)
      m_fixedAwaiting = false;
      if (m_fixedSent >= m_fixedTarget) { finishStressFixed(); return; }
      m_fixedNextSend = now + IR_STRESS_GAP_MS;
    }
    return;
  }

  // Not awaiting: send the next query (exactly one attempt each).
  if (m_fixedSent < m_fixedTarget && now >= m_fixedNextSend) {
    sendFrame(IR_AFN_GET_BAUD);
    m_fixedSent++;
    m_fixedAwaiting = true;
    m_fixedWaitStart = now;
    return;
  }

  if (m_fixedSent >= m_fixedTarget) finishStressFixed();
}

void IrModule::finishStressFixed() {
  m_fixedActive = false;
  close();
  Serial.println(F("IR_STRESS_FIXED_DONE"));
  Serial.print(F("STRESS_FIXED_TARGET="));          Serial.println(m_fixedTarget);
  Serial.print(F("STRESS_FIXED_SENT="));            Serial.println(m_fixedSent);
  Serial.print(F("FIRST_ATTEMPT_SUCCESS_COUNT="));  Serial.println(m_stats.valid_frame_count);
  Serial.print(F("TIMEOUT_COUNT="));                Serial.println(m_stats.timeout_count);
  Serial.print(F("CHECKSUM_FAILURE_COUNT="));       Serial.println(m_stats.checksum_failure_count);
  Serial.print(F("OVERFLOW_COUNT="));               Serial.println(m_stats.overflow_count);
  Serial.print(F("RESYNC_COUNT="));                 Serial.println(m_stats.resync_count);
  bool pass = (m_stats.valid_frame_count >= m_fixedTarget)
            && (m_stats.timeout_count == 0)
            && (m_stats.checksum_failure_count == 0)
            && (m_stats.overflow_count == 0)
            && (m_stats.resync_count == 0);
  Serial.print(F("IR_UART_19200_STRESS_PASS="));
  Serial.println(pass ? F("TRUE") : F("FALSE"));
}

// ---------------------------------------------------------------------------
// Bounded-retry (max 3) query reliability test (user engineering acceptance)
// ---------------------------------------------------------------------------
void IrModule::startStressBounded(int target) {
  if (target <= 0) target = 100;
  if (target > 100000) target = 100000;
  m_boundedActive = true;
  m_boundedTarget = target;
  m_boundedQuery = 0;
  m_boundedAttempt = 0;
  m_boundedFirstSuccess = 0;
  m_boundedFinalSuccess = 0;
  m_boundedFailures = 0;
  m_boundedTotalAttempts = 0;
  m_boundedAwaiting = false;
  m_boundedNextSend = millis();
  m_boundedWaitStart = 0;
  resetStats();          // clean measurement window
  ensureOpen();
  Serial.print(F("IR_STRESS_BOUNDED_START target="));
  Serial.println(target);
  Serial.print(F("IR_STRESS_BOUNDED_MAX_RETRY="));
  Serial.println((int)IR_BOUNDED_MAX_RETRY);
}

void IrModule::tickStressBounded() {
  if (!m_boundedActive) return;
  const uint32_t now = millis();

  if (m_boundedAwaiting) {
    IrFrame f;
    bool csFail;
    if (pumpAndParse(f, csFail)) {
      // This attempt delivered a structurally-valid frame.
      if (m_boundedAttempt == 0) m_boundedFirstSuccess++;
      m_boundedFinalSuccess++;
      m_boundedAwaiting = false;
      m_boundedQuery++;
      m_boundedAttempt = 0;
      if (m_boundedQuery >= m_boundedTarget) { finishStressBounded(); return; }
      m_boundedNextSend = now + IR_STRESS_GAP_MS;
    } else if (csFail) {
      // Checksum-bad frame: failed attempt. Rejected (NO false accept).
      m_boundedAttempt++;
      m_boundedAwaiting = false;
      if (m_boundedAttempt >= IR_BOUNDED_MAX_RETRY) {
        m_boundedFailures++;          // hard failure: explicit, no save
        m_boundedQuery++;
        m_boundedAttempt = 0;
        if (m_boundedQuery >= m_boundedTarget) { finishStressBounded(); return; }
      }
      m_boundedNextSend = now + IR_STRESS_GAP_MS * (1u << m_boundedAttempt); // backoff
    } else if (now - m_boundedWaitStart >= IR_STRESS_REPLY_TIMEOUT_MS) {
      // No valid reply in time: failed attempt (timeout).
      m_stats.timeout_count++;
      m_boundedAttempt++;
      m_boundedAwaiting = false;
      if (m_boundedAttempt >= IR_BOUNDED_MAX_RETRY) {
        m_boundedFailures++;          // hard failure: explicit, no save
        m_boundedQuery++;
        m_boundedAttempt = 0;
        if (m_boundedQuery >= m_boundedTarget) { finishStressBounded(); return; }
      }
      m_boundedNextSend = now + IR_STRESS_GAP_MS * (1u << m_boundedAttempt); // backoff
    }
    return;
  }

  // Not awaiting: send the next attempt if queries remain and gap elapsed.
  if (m_boundedQuery < m_boundedTarget && now >= m_boundedNextSend) {
    sendFrame(IR_AFN_GET_BAUD);
    m_boundedTotalAttempts++;
    m_boundedAwaiting = true;
    m_boundedWaitStart = now;
    return;
  }

  if (m_boundedQuery >= m_boundedTarget) finishStressBounded();
}

void IrModule::finishStressBounded() {
  m_boundedActive = false;
  close();
  Serial.println(F("IR_STRESS_BOUNDED_DONE"));
  int target = m_boundedTarget;
  uint32_t firstRate = (target > 0) ? (uint32_t)m_boundedFirstSuccess * 100u / (uint32_t)target : 0;
  uint32_t afterRate = (target > 0) ? (uint32_t)m_boundedFinalSuccess * 100u / (uint32_t)target : 0;
  uint32_t timeoutRate = (m_boundedTotalAttempts > 0)
      ? (uint32_t)m_stats.timeout_count * 100u / (uint32_t)m_boundedTotalAttempts : 0;
  Serial.print(F("IR_UART_BAUD="));                   Serial.println(m_baud);
  Serial.print(F("IR_UART_TARGET="));                 Serial.println(target);
  Serial.print(F("IR_UART_TOTAL_ATTEMPTS="));         Serial.println(m_boundedTotalAttempts);
  Serial.print(F("IR_UART_FIRST_ATTEMPT_SUCCESS_COUNT=")); Serial.println(m_boundedFirstSuccess);
  Serial.print(F("IR_UART_FIRST_ATTEMPT_SUCCESS_RATE="));   Serial.print(firstRate); Serial.println(F("%"));
  Serial.print(F("IR_UART_TIMEOUT_COUNT="));          Serial.println(m_stats.timeout_count);
  Serial.print(F("IR_UART_TIMEOUT_RATE="));           Serial.print(timeoutRate); Serial.println(F("%"));
  Serial.print(F("IR_UART_CHECKSUM_FAILURE_COUNT=")); Serial.println(m_stats.checksum_failure_count);
  Serial.print(F("IR_UART_FALSE_ACCEPT_COUNT="));     Serial.println(m_stats.false_accept_count);
  Serial.print(F("IR_UART_OVERFLOW_COUNT="));         Serial.println(m_stats.overflow_count);
  Serial.print(F("IR_UART_RESYNC_COUNT="));           Serial.println(m_stats.resync_count);
  Serial.print(F("IR_UART_MAX_RETRY="));              Serial.println((int)IR_BOUNDED_MAX_RETRY);
  Serial.print(F("IR_UART_FINAL_SUCCESS_COUNT="));    Serial.println(m_boundedFinalSuccess);
  Serial.print(F("IR_UART_SUCCESS_AFTER_RETRY_RATE=")); Serial.print(afterRate); Serial.println(F("%"));
  Serial.print(F("IR_UART_HARD_FAILURES="));          Serial.println(m_boundedFailures);
  // Engineering acceptance (user gate, refined): first-round >=95%, post-retry
  // 100%, and zero checksum / false-accept / overflow. First-round stats are
  // KEPT SEPARATE from post-retry (never reported as 100/100).
  bool pass = (firstRate >= 95)
            && (m_stats.checksum_failure_count == 0)
            && (m_stats.false_accept_count == 0)
            && (m_stats.overflow_count == 0)
            && (m_boundedFinalSuccess >= target)
            && (m_boundedFailures == 0);
  Serial.print(F("IR_UART_BOUNDED_RETRY_PASS="));
  Serial.println(pass ? F("TRUE") : F("FALSE"));
}

// ---------------------------------------------------------------------------
// 800-byte external-code frame parser self-test (injected; no real IR used)
// ---------------------------------------------------------------------------
bool IrModule::selfTestLongFrame() {
  // Build an ~800-byte external-code frame (AFN=22H) with valid length/CS/tail
  // and feed it through the SAME static scanner (scanOneFrame) the UART path
  // uses. Proves the parser + IR_MAX_FRAME buffer handle an 800-byte frame.
  const uint16_t dataLen = 800;
  uint8_t frame[IR_MAX_FRAME];
  uint16_t pos = 0;
  frame[pos++] = IR_FRAME_HEADER;
  uint16_t total = (uint16_t)(dataLen + 7);
  frame[pos++] = (uint8_t)(total & 0xFF);
  frame[pos++] = (uint8_t)((total >> 8) & 0xFF);
  frame[pos++] = IR_BROADCAST_ADDRESS;
  frame[pos++] = IR_AFN_EXT_SEND;
  uint16_t sum = IR_BROADCAST_ADDRESS + IR_AFN_EXT_SEND;
  for (uint16_t k = 0; k < dataLen; k++) {
    uint8_t b = (uint8_t)(k & 0xFF);   // synthetic compressed-code bytes
    frame[pos++] = b;
    sum += b;
  }
  frame[pos++] = (uint8_t)(sum & 0xFF);   // checksum
  frame[pos++] = IR_FRAME_TAIL;
  uint16_t frameLen = pos;

  IrFrame out;
  uint16_t consumed = 0;
  IrFrameScan s = scanOneFrame(frame, frameLen, out, consumed);
  bool lenOk = (frameLen == total);
  bool tailOk = (frame[frameLen - 1] == IR_FRAME_TAIL);
  bool csOk = (s == IR_SCAN_OK);
  Serial.println(F("IR_LONGFRAME_SELFTEST"));
  Serial.print(F("LONGFRAME_LEN="));       Serial.println(frameLen);
  Serial.print(F("LONGFRAME_DATA_LEN="));  Serial.println(out.dataLen);
  Serial.print(F("LONGFRAME_AFN=0x"));     Serial.println(out.afn, HEX);
  Serial.print(F("LONGFRAME_LENGTH_OK=")); Serial.println(lenOk ? F("PASS") : F("FAIL"));
  Serial.print(F("LONGFRAME_CHECKSUM_OK=")); Serial.println(csOk ? F("PASS") : F("FAIL"));
  Serial.print(F("LONGFRAME_TAIL_OK="));   Serial.println(tailOk ? F("PASS") : F("FAIL"));
  bool pass = lenOk && csOk && tailOk && (out.dataLen == dataLen)
            && (out.afn == IR_AFN_EXT_SEND);
  Serial.print(F("IR_800_BYTE_FRAME_PASS="));
  Serial.println(pass ? F("TRUE") : F("FALSE"));
  return pass;
}

// ---------------------------------------------------------------------------
// External-code learn capture — GATE 01/02: real 20H/21H ACK required.
// ---------------------------------------------------------------------------
ModuleCommandResult IrModule::enterExtLearnConfirmed() {
  ModuleCommandResult r; r.commandAfn = IR_AFN_EXT_LEARN_ENTER;
#if !ENABLE_IR_MUTATING_COMMANDS
  r.errorCode = 4; return r;
#endif
  r.startedAt = millis();
  m_extLearnActive = true;
  m_extLearnDeadline = millis() + IR_LEARN_REPORT_TIMEOUT_MS;
  m_extLearnLen = 0;
  m_extLearnChecksum = 0;
  m_extLoadStageLen = 0;
  ensureOpen(IR_UART_RX_BUFFER);
  sendFrame(IR_AFN_EXT_LEARN_ENTER);
  r.sent = true;

  // Wait for valid 01H ACK with status=0
  IrFrame ack;
  uint32_t deadline = millis() + IR_DEFAULT_TIMEOUT_MS;
  while (millis() < deadline) {
    if (readFrame(IR_DEFAULT_TIMEOUT_MS, ack) && ack.valid) {
      if (ack.afn == IR_AFN_ACK) {
        r.ackReceived = true;
        r.ackFrameValid = true;
        r.ackAfn = ack.afn;
        if (ack.dataLen > 0) r.ackStatus = ack.data[0];
        r.completedAt = millis();
        r.ok = (r.ackStatus == 0);
        r.errorCode = r.ok ? 0 : 1;
        break;
      }
    }
  }
  if (!r.ackReceived) { r.timedOut = true; r.errorCode = 2; r.ok = false; }
  if (!r.ok) { m_extLearnActive = false; }
  return r;
}

// Legacy compatibility — use enterExtLearnConfirmed instead
bool IrModule::enterExtLearn() {
  ModuleCommandResult r = enterExtLearnConfirmed();
  if (r.ok) { Serial.println(F("IR_EXTLEARN_ENTER wait_for_remote")); return true; }
  Serial.print(F("IR_EXTLEARN_ENTER_FAILED error=")); Serial.println(r.errorCode);
  return false;
}

IrResult IrModule::exitExtLearn(uint32_t timeoutMs) {
  IrResult r; r.ok = false;
#if !ENABLE_IR_MUTATING_COMMANDS
  Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
  return r;
#endif
  m_extLearnActive = false;
  ensureOpen(IR_UART_RX_BUFFER_SMALL);
  sendFrame(IR_AFN_EXT_LEARN_EXIT);
  IrFrame f;
  if (readFrame(timeoutMs, f) && f.valid) {
    r.afn = f.afn;
    if (f.dataLen > 0) {
      r.status = f.data[0];
      r.dataLen = (f.dataLen > IR_RESULT_DATA_MAX) ? IR_RESULT_DATA_MAX : (uint8_t)f.dataLen;
      memcpy(r.data, f.data, r.dataLen);
    }
    // GATE 02: Only success if AFN=01H AND status=0 AND frame valid
    r.ok = (f.afn == IR_AFN_ACK && r.status == 0 && f.valid);
  }
  close();
  return r;
}

void IrModule::tickExtLearn() {
  if (!m_extLearnActive) return;
  IrFrame f;
  bool csFail;
  if (pumpAndParse(f, csFail)) {
    if (f.afn == IR_AFN_EXT_SEND) {     // AFN=22H streamed code
      // Reconstruct the full frame bytes (header..tail) for saving.
      uint16_t total = (uint16_t)(f.dataLen + 7);
      uint16_t idx = 0;
      m_extLearnBuf[idx++] = IR_FRAME_HEADER;
      m_extLearnBuf[idx++] = (uint8_t)(total & 0xFF);
      m_extLearnBuf[idx++] = (uint8_t)((total >> 8) & 0xFF);
      m_extLearnBuf[idx++] = f.addr;
      m_extLearnBuf[idx++] = f.afn;
      for (uint16_t k = 0; k < f.dataLen; k++) m_extLearnBuf[idx++] = f.data[k];
      m_extLearnBuf[idx++] = f.checksum;
      m_extLearnBuf[idx++] = IR_FRAME_TAIL;
      m_extLearnLen = idx;
      m_extLearnChecksum = f.checksum;
      m_extLearnActive = false;
      IrResult exit = exitExtLearn(IR_REPLY_TIMEOUT_MS);
      Serial.print(F("IR_EXTLEARN_CAPTURE afn=0x22 len="));
      Serial.println(idx);
      Serial.print(F("IR_EXTLEARN_CS=0x"));
      Serial.println(f.checksum, HEX);
      Serial.print(F("IR_EXTLEARN_EXIT_ACK="));
      Serial.println(exit.ok ? 1 : 0);
      Serial.println(F("IR_EXTLEARN_DONE replay=forbidden"));
      return;
    }
    // An ack (AFN=01) just means learn mode entered; keep waiting for the code.
    if (f.afn == IR_AFN_ACK) {
      Serial.println(F("IR_EXTLEARN_ACK received, waiting for code frame"));
      return;
    }
    return;
  }
  if (millis() >= m_extLearnDeadline) {
    m_extLearnActive = false;
    IrResult exit = exitExtLearn(IR_REPLY_TIMEOUT_MS);
    Serial.print(F("IR_EXTLEARN_FAIL reason=timeout_waiting_remote exit_ack="));
    Serial.println(exit.ok ? 1 : 0);
  }
}

void IrModule::clearExtLearnCapture() {
  m_extLearnActive = false;
  m_extLearnLen = 0;
  m_extLearnChecksum = 0;
  m_extLoadStageLen = 0;
  memset(m_extLearnBuf, 0, sizeof(m_extLearnBuf));
  memset(m_extLoadStaging, 0, sizeof(m_extLoadStaging));
  close();
}

uint16_t IrModule::extLearnFrame(uint8_t* outBuf, uint16_t outMax) const {
  if (m_extLearnLen == 0 || m_extLearnLen > outMax) return 0;
  memcpy(outBuf, m_extLearnBuf, m_extLearnLen);
  return m_extLearnLen;
}

// ---------------------------------------------------------------------------
// Chunked external-code load (controlled single-shot replay). NO emit.
// Host: `ir extload <hexchunk>` (one or more) -> extLoadAppend; `ir extload
// commit` -> extLoadCommit copies staging into m_extLearnBuf (the same buffer
// extSendCaptured() forwards to the module). Commit never triggers a transmit.
// ---------------------------------------------------------------------------
uint16_t IrModule::extLoadAppend(const uint8_t* buf, uint16_t len) {
  if (buf == nullptr || len == 0) return 0;
  if (m_extLoadStageLen + len > IR_MAX_FRAME) return 0;  // overflow guard
  memcpy(m_extLoadStaging + m_extLoadStageLen, buf, len);
  m_extLoadStageLen += len;
  return m_extLoadStageLen;
}

uint16_t IrModule::extLoadCommit() {
  if (m_extLoadStageLen < IR_MIN_FRAME) {  // too short to be a valid 68..16 frame
    m_extLoadStageLen = 0;
    return 0;
  }
  memcpy(m_extLearnBuf, m_extLoadStaging, m_extLoadStageLen);
  m_extLearnLen = m_extLoadStageLen;
  m_extLearnChecksum = m_extLoadStaging[m_extLoadStageLen - 2];  // CS byte (before tail 0x16)
  m_extLearnActive = false;  // staged, not actively learning
  uint16_t n = m_extLoadStageLen;
  m_extLoadStageLen = 0;
  return n;
}

void IrModule::extLoadClear() {
  m_extLoadStageLen = 0;
}

bool IrModule::extSendCaptured() {
#if !ENABLE_IR_MUTATING_COMMANDS
  Serial.println(F("IR_MUTATING_COMMAND_BLOCKED_BY_BUILD_POLICY"));
  return false;
#endif
  if (m_extLearnLen == 0) {
    Serial.println(F("IR_EXTSEND_FAIL reason=no_captured_frame"));
    return false;
  }
  ensureOpen();
  size_t written = m_serial.write(m_extLearnBuf, m_extLearnLen);
  Serial.print(F("IR_EXTSEND_REQUESTED bytes="));
  Serial.println(m_extLearnLen);
  Serial.println(F("IR_PHYSICAL_RESULT_PENDING (confirm AC response yourself)"));
  close();
  return written == m_extLearnLen;
}

// ---------------------------------------------------------------------------
// §二 / §八 helpers
// ---------------------------------------------------------------------------
bool IrModule::commandIdRecentlyExecuted(const char* id) const {
  if (!id || !*id) return false;
  uint32_t now = millis();
  for (uint8_t i = 0; i < IR_EXEC_CACHE_MAX; i++) {
    if (m_execCache[i].at == 0) continue;
    if (now - m_execCache[i].at > IR_EXEC_TTL_MS) continue;     // stale -> not a dup
    if (strcmp(m_execCache[i].id, id) == 0) return true;
  }
  return false;
}

void IrModule::recordExecutedCommandId(const char* id) {
  if (!id || !*id) return;
  IrExecRecord& r = m_execCache[m_execCacheIdx % IR_EXEC_CACHE_MAX];
  strncpy(r.id, id, sizeof(r.id) - 1);
  r.id[sizeof(r.id) - 1] = '\0';
  r.at = millis();
  m_execCacheIdx++;
}

// Validate a full external 22H frame structurally (§二 steps 4-9) WITHOUT sending.
bool IrModule::validateExternalFrame(const uint8_t* frame, uint16_t frameLength) const {
  if (!frame) return false;
  if (frameLength < IR_MIN_FRAME || frameLength > IR_MAX_FRAME) return false;
  if (frame[0] != IR_FRAME_HEADER) return false;                       // 0x68
  uint16_t total = (uint16_t)frame[1] | ((uint16_t)frame[2] << 8);
  if (total != frameLength) return false;                              // LEN field matches
  if (frame[3] != IR_MODULE_ADDRESS) return false;                     // ADDR == module (0x00)
  if (frame[4] != IR_AFN_EXT_SEND) return false;                       // AFN == 0x22
  uint16_t tailPos = (uint16_t)(total - 1);
  if (frame[tailPos] != IR_FRAME_TAIL) return false;                   // 0x16
  // CS = (ADDR + AFN + DATA) mod 256, over bytes [3 .. total-3)
  uint16_t sum = 0;
  for (uint16_t k = 3; k <= total - 3; k++) sum += frame[k];
  uint8_t csCalc = (uint8_t)(sum & 0xFF);
  if (frame[total - 2] != csCalc) return false;                       // CS matches
  return true;
}

// ---------------------------------------------------------------------------
// §二: sendExternalFrameOnce — write the COMPLETE external 22H frame verbatim
// to the module UART. Per ZJ-IR-V2 V1.0.6 (A-level evidence), sending the full
// 22H frame back to the module makes it extract the IR data and emit ONCE.
// There is NO separate store-then-emit step. 18-step flow; executes exactly
// once; NO auto-retry. Layered result.
// §五: ONLY call this from a validated, unexpired, owner-authorized command
//      path. Never on boot / Wi-Fi or MQTT reconnect / web refresh / status.
// ---------------------------------------------------------------------------
IrSendOnceResult IrModule::sendExternalFrameOnce(const uint8_t* frame, size_t frameLength,
                                                 const char* codeId, const char* commandId) {
  IrSendOnceResult r;
  r.codeId = codeId;

  // 1-3. Non-null, length sane, <= IR_MAX_FRAME.
  if (!frame) { r.rejectReason = "null_frame"; return r; }
  if (frameLength < IR_MIN_FRAME || frameLength > IR_MAX_FRAME) {
    r.rejectReason = "bad_length"; return r;
  }
  r.frameLength = (uint16_t)frameLength;

  // 4-9. Structural validation (header / LEN / ADDR / AFN / CS / tail).
  if (!validateExternalFrame(frame, (uint16_t)frameLength)) {
    r.rejectReason = "invalid_frame_structure"; return r;
  }
  r.frameValid = true;

  // 10. Module not already busy with a send.
  if (m_sendBusy) { r.busy = true; r.rejectReason = "module_busy"; return r; }

  // 11. commandId not recently executed (TTL dedupe -> blocks double-click &
  //     accidental replays within the window, §八).
  if (commandIdRecentlyExecuted(commandId)) {
    r.busy = true; r.rejectReason = "command_id_recently_executed"; return r;
  }

  // 12. Open the UART with the LARGE RX buffer so any module echo/ACK (which
  //     may itself be a ~418-byte 22H frame) is captured rather than dropped.
  ensureOpen(IR_UART_RX_BUFFER);

  // 13. Write the COMPLETE frame verbatim. NO re-wrapping, NO second 68..16.
  m_sendBusy = true;
  size_t written = m_serial.write(frame, frameLength);
  r.bytesWritten = (uint16_t)written;

  // 14. Byte-count verification.
  if (written != frameLength) {
    m_sendBusy = false;
    r.rejectReason = "uart_write_short";
    close();
    return r;
  }

  // 15. Flush + wait (best-effort) for a module ACK. The module emits IR and
  //     may respond with a report/echo frame. NO auto-retry either way (§八).
  m_serial.flush();
  IrFrame ack;
  bool got = readFrame(IR_REPLY_TIMEOUT_MS, ack);
  r.moduleAcked = got;

  // 16-17. Single execution complete. Record commandId, clear busy.
  recordExecutedCommandId(commandId);
  m_sendBusy = false;
  close();

  // 18. Layered result. ok=true means the module was asked to emit once (NOT
  //     that the AC responded). If no ACK arrived, it is ambiguous.
  r.ok = true;
  if (!got) r.mayHaveTransmitted = true;
  Serial.print(F("IR_SEND_ONCE codeId="));
  Serial.print(codeId ? codeId : "?");
  Serial.print(F(" bytes="));
  Serial.print((int)written);
  Serial.print(F(" moduleAcked="));
  Serial.println(got ? F("true") : F("false (ambiguous, no auto-retry)"));
  return r;
}
