#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serial transport and learning workflow client for IR Learning Studio."""

from __future__ import annotations

import base64
import ctypes
import datetime as _dt
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import threading
import time
import uuid
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Tuple

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
    HAVE_PYSERIAL = True
except Exception:
    serial = None
    HAVE_PYSERIAL = False

import protocol

CH9102_VID = 0x1A86
CH9102_PID = 0x55D4
ESP_CLI_BAUD = 115200
MODULE_BAUD = 19200
STATE_IDLE = "IDLE"
STATE_DEFINED = "STATE_DEFINED"
STATE_DEVICE_CONNECTING = "DEVICE_CONNECTING"
STATE_DEVICE_READY = "DEVICE_READY"
STATE_ENTERING_LEARN_MODE = "ENTERING_LEARN_MODE"
STATE_WAITING_FOR_REMOTE = "WAITING_FOR_REMOTE"
STATE_FRAME_RECEIVING = "FRAME_RECEIVING"
STATE_FRAME_VALIDATING = "FRAME_VALIDATING"
STATE_CAPTURE_SAVED = "CAPTURE_SAVED"
STATE_WAITING_FOR_NEXT_CAPTURE = "WAITING_FOR_NEXT_CAPTURE"
STATE_CAPTURE_SET_COMPLETE = "CAPTURE_SET_COMPLETE"
STATE_CANONICAL_REVIEW = "CANONICAL_REVIEW"
STATE_APPROVED = "APPROVED"
STATE_CANCELLED = "CANCELLED"
STATE_TIMEOUT = "TIMEOUT"
STATE_ERROR = "ERROR"

NO_REPLAY_COUNTERS = {
    "LEARNING_WORKFLOW_UART_22H_WRITE_COUNT": 0,
    "LEARNING_WORKFLOW_REAL_IR_TRANSMIT_COUNT": 0,
    "IR_CAPTURE_22H_ECHO_BACK_COUNT": 0,
    "IR_CAPTURE_REAL_TRANSMIT_COUNT": 0,
}

COMMAND_DEVICE_STATUS = "device.status"
COMMAND_LEARN_BEGIN = "ir.learn.begin"
COMMAND_LEARN_STATUS = "ir.learn.status"
COMMAND_LEARN_CANCEL = "ir.learn.cancel"
COMMAND_LEARN_EXPORT = "ir.learn.export"
COMMAND_LEARN_CLEAR = "ir.learn.clear"

ALLOWED_PC_COMMANDS = {
    COMMAND_DEVICE_STATUS,
    COMMAND_LEARN_BEGIN,
    COMMAND_LEARN_STATUS,
    COMMAND_LEARN_CANCEL,
    COMMAND_LEARN_EXPORT,
    COMMAND_LEARN_CLEAR,
}

WRITE_DEVICE_STATUS = "DEVICE_STATUS"
WRITE_LEARN_BEGIN = "LEARN_BEGIN"
WRITE_LEARN_CANCEL = "LEARN_CANCEL"
WRITE_LEARN_STATUS = "LEARN_STATUS"
WRITE_LEARN_EXPORT = "LEARN_EXPORT"
WRITE_LEARN_CLEAR = "LEARN_CLEAR"
WRITE_UNKNOWN = "UNKNOWN"
WRITE_RAW_FRAME = "RAW_FRAME"
WRITE_REPLAY = "REPLAY"
WRITE_TRANSMIT = "TRANSMIT"

CMD_CONNECT = "CONNECT"
CMD_READ_STATUS = "READ_STATUS"
CMD_BEGIN_CAPTURE = "BEGIN_CAPTURE"
CMD_CANCEL_CAPTURE = "CANCEL_CAPTURE"
CMD_DISCONNECT = "DISCONNECT"
CMD_SHUTDOWN = "SHUTDOWN"

EV_CONNECTED = "CONNECTED"
EV_HANDSHAKE_OK = "HANDSHAKE_OK"
EV_HANDSHAKE_FAILED = "HANDSHAKE_FAILED"
EV_LEARN_ENTERED = "LEARN_ENTERED"
EV_WAITING_REMOTE = "WAITING_REMOTE"
EV_EXPORT_BEGIN = "EXPORT_BEGIN"
EV_EXPORT_PROGRESS = "EXPORT_PROGRESS"
EV_CAPTURE_VALIDATED = "CAPTURE_VALIDATED"
EV_CAPTURE_FAILED = "CAPTURE_FAILED"
EV_LEARN_EXITED = "LEARN_EXITED"
EV_CANCELLED = "CANCELLED"
EV_DISCONNECTED = "DISCONNECTED"
EV_ERROR = "ERROR"
EV_SHUTDOWN_COMPLETE = "SHUTDOWN_COMPLETE"
EV_WORKER_TERMINATED = "WORKER_TERMINATED"


@dataclass(frozen=True)
class RecordedWrite:
    timestamp: str
    thread_id: int
    command_name: str
    payload_length: int
    payload_sha256: str
    classification: str


@dataclass(frozen=True)
class HandshakeResult:
    ready: bool
    reasons: Tuple[str, ...]
    metadata: Dict[str, object]


class CommandNotAllowed(RuntimeError):
    pass


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def new_request_id() -> str:
    return "req-" + uuid.uuid4().hex


def new_session_id() -> str:
    return "sess-" + uuid.uuid4().hex


def new_export_id() -> str:
    return "exp-" + uuid.uuid4().hex


def encode_command(command_name: str, **kwargs: str) -> str:
    if command_name not in ALLOWED_PC_COMMANDS:
        raise CommandNotAllowed(f"COMMAND_NOT_ALLOWED: {command_name}")
    request_id = kwargs.get("request_id") or kwargs.get("requestId") or ""
    session_id = kwargs.get("session_id") or kwargs.get("sessionId") or ""
    export_id = kwargs.get("export_id") or kwargs.get("exportId") or ""
    if command_name in {COMMAND_LEARN_BEGIN, COMMAND_LEARN_CANCEL}:
        _require_token(request_id, "requestId")
        _require_token(session_id, "sessionId")
    if command_name == COMMAND_LEARN_EXPORT:
        _require_token(request_id, "requestId")
        _require_token(session_id, "sessionId")
        _require_token(export_id, "exportId")
    if command_name in {COMMAND_DEVICE_STATUS, COMMAND_LEARN_STATUS}:
        return "ir_learn_status"
    if command_name == COMMAND_LEARN_BEGIN:
        return f"ir_learn_begin {request_id} {session_id}"
    if command_name == COMMAND_LEARN_CANCEL:
        return f"ir_learn_cancel {request_id} {session_id}"
    if command_name == COMMAND_LEARN_EXPORT:
        return f"ir_learn_export {request_id} {session_id} {export_id}"
    if command_name == COMMAND_LEARN_CLEAR:
        return "ir_learn_clear"
    raise CommandNotAllowed(f"COMMAND_NOT_ALLOWED: {command_name}")


def classify_serial_write(line: str) -> Tuple[str, str]:
    text = line.strip()
    lower = text.lower()
    if re.fullmatch(r"(?:[0-9a-f]{2}\s*){7,}", lower):
        return (WRITE_RAW_FRAME, "raw.hex")
    if any(word in lower for word in ("replay", "raw.send", "frame.write", "sendexternalframeonce")):
        return (WRITE_REPLAY, "blocked.replay")
    if lower.startswith("ir send") or lower.startswith("ir extsend") or lower.startswith("ir stage send"):
        return (WRITE_TRANSMIT, "blocked.transmit")
    if lower.startswith("ir_learn_begin"):
        return (WRITE_LEARN_BEGIN, COMMAND_LEARN_BEGIN)
    if lower.startswith("ir_learn_cancel"):
        return (WRITE_LEARN_CANCEL, COMMAND_LEARN_CANCEL)
    if lower.startswith("ir_learn_export"):
        return (WRITE_LEARN_EXPORT, COMMAND_LEARN_EXPORT)
    if lower.startswith("ir_learn_status"):
        return (WRITE_LEARN_STATUS, COMMAND_LEARN_STATUS)
    if lower.startswith("ir_learn_clear"):
        return (WRITE_LEARN_CLEAR, COMMAND_LEARN_CLEAR)
    if lower.startswith("status"):
        return (WRITE_DEVICE_STATUS, COMMAND_DEVICE_STATUS)
    return (WRITE_UNKNOWN, "unknown")


def validate_device_status(
    status: Dict,
    port_info: Optional[Dict[str, str]] = None,
    allow_mock: bool = False,
) -> HandshakeResult:
    reasons: List[str] = []
    metadata: Dict[str, object] = dict(status)
    vid = (port_info or {}).get("vid", "")
    pid = (port_info or {}).get("pid", "")
    if not allow_mock:
        if vid.upper() not in {"0X1A86", "1A86"}:
            reasons.append("USB_VID_NOT_CH9102")
        if pid.upper() not in {"0X55D4", "55D4"}:
            reasons.append("USB_PID_NOT_CH9102")
    device_status = status.get("deviceStatus")
    device_ok = device_status.get("ok") if isinstance(device_status, dict) else None
    if status.get("ok") is not True and device_ok is not True:
        reasons.append("DEVICE_STATUS_NOT_OK")
    device_type = str(status.get("deviceType", ""))
    if "ESP8266" not in device_type and "NodeMCU" not in device_type:
        reasons.append("DEVICE_TYPE_MISMATCH")
    mac = str(status.get("deviceMac") or status.get("mac") or "")
    if not re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", mac):
        reasons.append("DEVICE_MAC_MISSING_OR_INVALID")
    if not str(status.get("firmwareVersion", "")).strip():
        reasons.append("FIRMWARE_VERSION_MISSING")
    if not str(status.get("firmwareCommit", "")).strip():
        reasons.append("FIRMWARE_COMMIT_MISSING")
    profile = status.get("firmwareProfile") or status.get("profile")
    if profile != "ir-lab":
        reasons.append("FIRMWARE_PROFILE_NOT_IR_LAB")
    module = status.get("irModuleModel") or status.get("moduleModel")
    if module != "ZJ-IR-V2":
        reasons.append("IR_MODULE_MODEL_MISMATCH")
    if int(status.get("irUartBaud") or 0) != MODULE_BAUD:
        reasons.append("IR_UART_BAUD_MISMATCH")
    # R3: irReady is no longer a gate — computed from real state fields
    ir_ready = status.get("irReady")
    ir_uart_configured = status.get("irUartConfigured")
    module_responsive = status.get("moduleResponsive")
    learning_active = status.get("learningActive")
    # If firmware doesn't report real sub-fields, flag MODULE_RESPONSIVENESS_UNKNOWN
    if ir_uart_configured is None and module_responsive is None and learning_active is None:
        if ir_ready is not True and not allow_mock:
            reasons.append("IR_NOT_READY")
        metadata["moduleResponsive"] = "LEGACY_IR_READY_FLAG" if ir_ready is True else "MODULE_RESPONSIVENESS_UNKNOWN"
    else:
        if ir_uart_configured is not True:
            reasons.append("IR_UART_NOT_CONFIGURED")
        if module_responsive is True and learning_active is True:
            reasons.append("IR_MODULE_LEARNING_ACTIVE")
        metadata["irUartConfigured"] = bool(ir_uart_configured)
        metadata["moduleResponsive"] = bool(module_responsive) if module_responsive is not None else "UNKNOWN"
        metadata["learningActive"] = bool(learning_active)
    version = str(status.get("learningProtocolVersion", ""))
    if version != protocol.SUPPORTED_LEARNING_PROTOCOL_VERSION:
        reasons.append("LEARNING_PROTOCOL_VERSION_UNSUPPORTED")
    metadata.update(
        {
            "deviceMac": mac,
            "firmwareProfile": profile or "",
            "irModuleModel": module or "",
            "irUartBaud": int(status.get("irUartBaud") or 0),
            "usbVid": "1A86" if allow_mock else vid.replace("0x", "").replace("0X", ""),
            "usbPid": "55D4" if allow_mock else pid.replace("0x", "").replace("0X", ""),
        }
    )
    return HandshakeResult(ready=not reasons, reasons=tuple(reasons), metadata=metadata)


def _require_token(value: str, name: str) -> None:
    if not value or not re.fullmatch(r"[A-Za-z0-9_.-]{1,127}", value):
        raise CommandNotAllowed(f"COMMAND_ID_INVALID: {name}")


def discover_ch9102_ports() -> List[Dict[str, str]]:
    if not HAVE_PYSERIAL:
        return []
    ports = []
    for info in serial.tools.list_ports.comports():
        vid = getattr(info, "vid", None)
        pid = getattr(info, "pid", None)
        hwid = (getattr(info, "hwid", "") or "").upper()
        if vid is None or pid is None:
            if ("VID_1A86" in hwid or "VID_01A86" in hwid) and "PID_55D4" in hwid:
                vid, pid = CH9102_VID, CH9102_PID
        if vid == CH9102_VID and pid == CH9102_PID:
            ports.append(
                {
                    "device": info.device,
                    "vid": f"0x{vid:04X}",
                    "pid": f"0x{pid:04X}",
                    "description": getattr(info, "description", "") or "",
                }
            )
    return ports


class SingleInstanceLock:
    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self._owned = False

    def acquire(self, project_root: Path, serial_port: str = "", session_id: str = "") -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists() and self._is_stale():
            try:
                self.lock_path.unlink()
            except Exception:
                pass
        if self.lock_path.exists():
            return False
        rec = {
            "pid": os.getpid(),
            "startedAt": utc_now(),
            "projectRoot": str(project_root),
            "serialPort": serial_port,
            "sessionId": session_id,
        }
        try:
            self.lock_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            self._owned = True
            return True
        except Exception:
            return False

    def update(self, serial_port: str = "", session_id: str = "") -> None:
        if not self._owned or not self.lock_path.exists():
            return
        try:
            rec = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except Exception:
            rec = {}
        rec.update({"serialPort": serial_port, "sessionId": session_id})
        self.lock_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    def release(self) -> None:
        if self._owned and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except Exception:
                pass
        self._owned = False

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            if pid <= 0:
                return True
            if os.name == "nt":
                return not _windows_pid_alive(pid)
            return not _unix_pid_alive(pid)
        except Exception:
            return True


def _windows_pid_alive(pid: int) -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        process = kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        code = ctypes.c_uint32()
        kernel32.GetExitCodeProcess(process, ctypes.byref(code))
        kernel32.CloseHandle(process)
        return code.value == 259
    except Exception:
        return False


def _unix_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


class SerialTransport(Protocol):
    def readline(self) -> bytes: ...

    def write_line(self, line: str) -> None: ...

    def close(self) -> None: ...

    def reset_input_buffer(self) -> None: ...

    def reset_output_buffer(self) -> None: ...


class PySerialTransport(SerialTransport):
    def __init__(self, port: str, baud: int = ESP_CLI_BAUD):
        if not HAVE_PYSERIAL:
            raise RuntimeError("pyserial is not available")
        self.port = port
        self.baud = baud
        self.owner_thread_id = threading.get_ident()
        self.recorded_writes: List[RecordedWrite] = []
        self.ser = serial.Serial(port, baud, timeout=0.1)
        try:
            self.ser.dtr = False
            self.ser.rts = False
        except Exception:
            self._last_line_state = "dtr_rts_unsupported"
        self.reset_input_buffer()

    def _assert_owner_thread(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("SERIAL_IO_OWNER_VIOLATION")

    def readline(self) -> bytes:
        self._assert_owner_thread()
        return self.ser.readline()

    def write_line(self, line: str) -> None:
        self._assert_owner_thread()
        self._record_write(line)
        if not line.endswith("\n"):
            line += "\n"
        self.ser.write(line.encode("utf-8"))
        self.ser.flush()

    def close(self) -> None:
        self._assert_owner_thread()
        try:
            self.ser.close()
        except Exception:
            self._last_line_state = "close_ignored_error"

    def reset_input_buffer(self) -> None:
        self._assert_owner_thread()
        self.ser.reset_input_buffer()

    def reset_output_buffer(self) -> None:
        self._assert_owner_thread()
        self.ser.reset_output_buffer()

    def _record_write(self, line: str) -> None:
        classification, command_name = classify_serial_write(line)
        if classification in {WRITE_RAW_FRAME, WRITE_REPLAY, WRITE_TRANSMIT, WRITE_UNKNOWN}:
            raise CommandNotAllowed(f"COMMAND_NOT_ALLOWED: {classification}")
        payload = line.strip().encode("utf-8")
        self.recorded_writes.append(
            RecordedWrite(
                timestamp=utc_now(),
                thread_id=threading.get_ident(),
                command_name=command_name,
                payload_length=len(payload),
                payload_sha256=protocol.sha256_bytes(payload),
                classification=classification,
            )
        )


class MockTransport(SerialTransport):
    """Deterministic, no-hardware transport for tests and UI smoke checks."""

    def __init__(self, scenario: str = "success", frame: Optional[bytes] = None):
        self.scenario = scenario
        self.frame = frame or protocol.make_public_fake_frame(11)
        self.writes: List[str] = []
        self.recorded_writes: List[RecordedWrite] = []
        self.owner_thread_id = threading.get_ident()
        self._queue: List[bytes] = []
        self._capture_ready = False
        self._closed = False

    def _assert_owner_thread(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("SERIAL_IO_OWNER_VIOLATION")

    def readline(self) -> bytes:
        self._assert_owner_thread()
        if self._queue:
            return self._queue.pop(0)
        time.sleep(0.01)
        return b""

    def write_line(self, line: str) -> None:
        self._assert_owner_thread()
        self._record_write(line)
        self.writes.append(line.strip())
        text = line.strip()
        parts = text.split()
        if text.startswith("status") or text.startswith("ir_learn_status"):
            self._queue.extend(
                [
                    _json_line(
                        {
                            "event": "ir.learn.status",
                            "ok": True,
                            "deviceStatus": {"ok": True},
                            "deviceType": "NodeMCU ESP8266 mock",
                            "firmwareProfile": "ir-lab",
                            "profile": "ir-lab",
                            "irModuleModel": "ZJ-IR-V2",
                            "moduleModel": "ZJ-IR-V2",
                            "firmwareVersion": "mock-2",
                            "firmwareCommit": "mockcommit",
                            "deviceMac": "AA:BB:CC:DD:EE:FF",
                            "mac": "AA:BB:CC:DD:EE:FF",
                            "irUartBaud": MODULE_BAUD,
                            "irReady": True,
                            "learningProtocolVersion": protocol.SUPPORTED_LEARNING_PROTOCOL_VERSION,
                            "state": STATE_WAITING_FOR_REMOTE,
                            "captureReady": self._capture_ready,
                        }
                    ),
                ]
            )
        elif text.startswith("ir_learn_begin"):
            rid = parts[1] if len(parts) > 2 else "mock-request"
            sid = parts[2] if len(parts) > 2 else (parts[1] if len(parts) > 1 else "mock")
            self._queue.extend(
                [
                    _json_line({"event": "ir.learn.waiting", "requestId": rid, "sessionId": sid, "timeoutMs": 30000}),
                    _plain_line("IR_LEARN_READY"),
                ]
            )
            if self.scenario == "timeout":
                return
            if self.scenario == "cancelled":
                self._queue.append(_json_line({"event": "ir.learn.cancelled", "requestId": rid, "sessionId": sid, "exitConfirmed": True}))
                return
            if self.scenario == "bad_hash":
                broken = bytearray(self.frame)
                broken[-2] ^= 0xFF
                self.frame = bytes(broken)
            self._capture_ready = True
            self._queue.append(
                _json_line(
                    {
                        "event": "ir.learn.captured",
                        "requestId": rid,
                        "sessionId": sid,
                        "length": len(self.frame),
                        "sha256": protocol.sha256_bytes(self.frame),
                        "structureValid": True,
                    }
                )
            )
        elif text.startswith("ir_learn_status"):
            self._queue.append(
                _json_line(
                    {
                        "event": "ir.learn.status",
                        "state": STATE_FRAME_VALIDATING if self._capture_ready else STATE_WAITING_FOR_REMOTE,
                        "captureReady": self._capture_ready,
                        "ok": True,
                        "deviceStatus": {"ok": True},
                        "deviceType": "NodeMCU ESP8266 mock",
                        "profile": "ir-lab",
                        "firmwareProfile": "ir-lab",
                        "moduleModel": "ZJ-IR-V2",
                        "irModuleModel": "ZJ-IR-V2",
                        "firmwareVersion": "mock-2",
                        "firmwareCommit": "mockcommit",
                        "deviceMac": "AA:BB:CC:DD:EE:FF",
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "irUartBaud": MODULE_BAUD,
                        "irReady": True,
                        "learningProtocolVersion": protocol.SUPPORTED_LEARNING_PROTOCOL_VERSION,
                    }
                )
            )
        elif text.startswith("ir_learn_export"):
            rid = parts[1] if len(parts) > 3 else "mock-request"
            sid = parts[2] if len(parts) > 3 else (parts[1] if len(parts) > 1 else "mock")
            eid = parts[3] if len(parts) > 3 else "mock-export"
            if self.scenario == "missing_export":
                self._queue.append(
                    _json_line({"event": "ir.learn.export.error", "requestId": rid, "sessionId": sid, "exportId": eid, "reason": "missing"})
                )
                return
            payload = base64.b64encode(self.frame).decode("ascii")
            chunk_size = 80
            chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
            self._queue.append(
                _json_line(
                    {
                        "event": "ir.learn.export.begin",
                        "requestId": rid,
                        "sessionId": sid,
                        "exportId": eid,
                        "encoding": "base64",
                        "frameLength": len(self.frame),
                        "frameSha256": protocol.sha256_bytes(self.frame),
                        "chunkCount": len(chunks),
                        "totalEncodedChars": len(payload),
                    }
                )
            )
            for i, chunk in enumerate(chunks):
                self._queue.append(
                    _json_line(
                        {
                            "event": "ir.learn.export.chunk",
                            "requestId": rid,
                            "sessionId": sid,
                            "exportId": eid,
                            "index": i,
                            "count": len(chunks),
                            "encoding": "base64",
                            "data": chunk,
                        }
                    )
                )
            self._queue.append(
                _json_line(
                    {
                        "event": "ir.learn.export.done",
                        "requestId": rid,
                        "sessionId": sid,
                        "exportId": eid,
                        "encoding": "base64",
                        "frameLength": len(self.frame),
                        "frameSha256": protocol.sha256_bytes(self.frame),
                        "chunkCount": len(chunks),
                        "totalEncodedChars": len(payload),
                    }
                )
            )
        elif text.startswith("ir_learn_cancel"):
            rid = parts[1] if len(parts) > 2 else "mock-request"
            sid = parts[2] if len(parts) > 2 else "mock"
            self._queue.append(_json_line({"event": "ir.learn.cancelled", "requestId": rid, "sessionId": sid, "exitConfirmed": True}))
        elif text.startswith("ir_learn_clear"):
            self._capture_ready = False
            self._queue.append(_json_line({"event": "ir.learn.cleared"}))
        elif text.startswith("ir send") or text.startswith("ir extsend") or "replay" in text:
            self._queue.append(_json_line({"event": "blocked", "reason": "replay-disabled"}))

    def close(self) -> None:
        self._assert_owner_thread()
        self._closed = True

    def reset_input_buffer(self) -> None:
        self._assert_owner_thread()
        self._queue.clear()

    def reset_output_buffer(self) -> None:
        self._assert_owner_thread()

    def cancel_read(self) -> None:
        self._queue.append(b"")

    def _record_write(self, line: str) -> None:
        classification, command_name = classify_serial_write(line)
        if classification in {WRITE_RAW_FRAME, WRITE_REPLAY, WRITE_TRANSMIT, WRITE_UNKNOWN}:
            raise CommandNotAllowed(f"COMMAND_NOT_ALLOWED: {classification}")
        payload = line.strip().encode("utf-8")
        self.recorded_writes.append(
            RecordedWrite(
                timestamp=utc_now(),
                thread_id=threading.get_ident(),
                command_name=command_name,
                payload_length=len(payload),
                payload_sha256=protocol.sha256_bytes(payload),
                classification=classification,
            )
        )


def _plain_line(text: str) -> bytes:
    return (text + "\n").encode("utf-8")


def _json_line(data: Dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


class LearningClient:
    def __init__(self, transport: SerialTransport):
        self.transport = transport
        self.state = STATE_IDLE
        self.last_status: Dict = {}
        self._latest_capture: Optional[bytes] = None
        self._latest_meta: Dict = {}
        self.no_replay_counters = dict(NO_REPLAY_COUNTERS)

    def send(self, line: str) -> None:
        classification, _command_name = classify_serial_write(line)
        if classification in {WRITE_RAW_FRAME, WRITE_REPLAY, WRITE_TRANSMIT, WRITE_UNKNOWN}:
            self.no_replay_counters["LEARNING_WORKFLOW_UART_22H_WRITE_COUNT"] = 0
            self.no_replay_counters["LEARNING_WORKFLOW_REAL_IR_TRANSMIT_COUNT"] = 0
            self.no_replay_counters["IR_CAPTURE_22H_ECHO_BACK_COUNT"] = 0
            self.no_replay_counters["IR_CAPTURE_REAL_TRANSMIT_COUNT"] = 0
            raise CommandNotAllowed(f"COMMAND_NOT_ALLOWED: {classification}")
        self.transport.write_line(line)

    def begin(self, session_id: str, timeout_ms: int = 30000, request_id: Optional[str] = None) -> str:
        request_id = request_id or new_request_id()
        self.state = STATE_ENTERING_LEARN_MODE
        self.send(encode_command(COMMAND_LEARN_BEGIN, request_id=request_id, session_id=session_id))
        self._read_until(
            lambda e: e.get("event") == "ir.learn.waiting"
            and e.get("sessionId") == session_id
            and e.get("requestId") in (request_id, None),
            timeout_ms / 1000.0,
        )
        self.state = STATE_WAITING_FOR_REMOTE
        return request_id

    def poll_status(self) -> Dict:
        self.send(encode_command(COMMAND_LEARN_STATUS))
        evt = self._read_until(lambda e: e.get("event") == "ir.learn.status", 2.0)
        self.last_status = evt
        return evt

    def export_capture(
        self,
        session_id: str,
        timeout_ms: int = 10000,
        request_id: Optional[str] = None,
        export_id: Optional[str] = None,
        progress: Optional[Callable[[Dict], None]] = None,
    ) -> bytes:
        request_id = request_id or new_request_id()
        export_id = export_id or new_export_id()
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        assembler = protocol.ExportAssembler(request_id, session_id, export_id, deadline)
        self.send(encode_command(COMMAND_LEARN_EXPORT, request_id=request_id, session_id=session_id, export_id=export_id))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("EXPORT_TIMEOUT")
            evt = self._read_until(
                lambda e: str(e.get("event", "")).startswith("ir.learn.export"),
                remaining,
                deadline=deadline,
            )
            if progress:
                progress(evt)
            raw = assembler.process_event(evt)
            if raw is not None:
                break
        protocol.validate_frame_or_raise("learning_client", raw)
        self._latest_capture = raw
        self._latest_meta = {
            "requestId": request_id,
            "sessionId": session_id,
            "exportId": export_id,
            "frameLength": len(raw),
            "frameSha256": protocol.sha256_bytes(raw),
        }
        return raw

    def cancel(self, request_id: Optional[str] = None, session_id: str = "") -> Dict:
        request_id = request_id or new_request_id()
        session_id = session_id or self._latest_meta.get("sessionId", "") or "unknown"
        self.state = STATE_CANCELLED
        self.send(encode_command(COMMAND_LEARN_CANCEL, request_id=request_id, session_id=session_id))
        return self._read_until(lambda e: e.get("event") == "ir.learn.cancelled", 2.0)

    def clear(self) -> Dict:
        self.send(encode_command(COMMAND_LEARN_CLEAR))
        return self._read_until(lambda e: e.get("event") == "ir.learn.cleared", 2.0)

    def capture_once(
        self,
        session_id: str,
        timeout_ms: int = 40000,
        cancel_event: Optional[threading.Event] = None,
        progress: Optional[Callable[[str, Dict], None]] = None,
    ) -> Tuple[bytes, Dict]:
        request_id = new_request_id()
        export_id = new_export_id()
        try:
            self.begin(session_id, timeout_ms=min(timeout_ms, 30000), request_id=request_id)
            if progress:
                progress(EV_LEARN_ENTERED, {"requestId": request_id, "sessionId": session_id})
            self.state = STATE_WAITING_FOR_REMOTE
            if progress:
                progress(EV_WAITING_REMOTE, {"requestId": request_id, "sessionId": session_id})
            capture_evt = self._read_until(
                lambda e: e.get("event") == "ir.learn.captured",
                timeout_ms / 1000.0,
                cancel_event=cancel_event,
            )
            self.state = STATE_FRAME_VALIDATING
            raw = self.export_capture(
                session_id,
                timeout_ms=timeout_ms,
                request_id=request_id,
                export_id=export_id,
                progress=(lambda evt: progress(EV_EXPORT_PROGRESS, evt) if progress else None),
            )
            protocol.validate_frame_or_raise("learning_client", raw)
            cancel_evt = self.cancel(request_id=request_id, session_id=session_id)
            self.clear()
            self.state = STATE_CAPTURE_SAVED
            return raw, {
                "capture": capture_evt,
                "cancel": cancel_evt,
                "requestId": request_id,
                "sessionId": session_id,
                "exportId": export_id,
                "export": dict(self._latest_meta),
            }
        except Exception as exc:
            if isinstance(exc, InterruptedError) or (cancel_event and cancel_event.is_set()):
                raise
            try:
                self.cancel(request_id=request_id, session_id=session_id)
            except Exception as cancel_exc:
                self.last_status = {"cleanupError": str(cancel_exc)}
            self.state = STATE_TIMEOUT
            raise

    def _read_until(
        self,
        predicate: Callable[[Dict], bool],
        timeout_s: float,
        deadline: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict:
        deadline = deadline if deadline is not None else time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("CAPTURE_CANCELLED")
            line = self.transport.readline()
            if not line:
                continue
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            evt = _parse_json_line(text)
            if evt is None:
                continue
            if predicate(evt):
                return evt
            self.last_status = evt
        raise TimeoutError("serial event timeout")

    def close(self) -> None:
        try:
            self.transport.close()
        finally:
            self.state = STATE_IDLE


class SerialIoWorker:
    """Single owner of one serial transport. It never calls Tkinter.

    R3 fixes:
    - Command generation tracking prevents stale cancels from clearing active begins
    - _begin_capture checks generations before sending 20H
    - cancel_event is NOT unconditionally cleared; only reset on fresh begin
    - DISCONNECT performs safe 21H exit, closes serial, signals WORKER_TERMINATED
    - join() timeout is not silently ignored
    """

    def __init__(
        self,
        command_queue: Optional["queue.Queue[Dict]"] = None,
        event_queue: Optional["queue.Queue[Dict]"] = None,
        transport_factory: Optional[Callable[[], SerialTransport]] = None,
        port_info: Optional[Dict[str, str]] = None,
        allow_mock: bool = False,
    ):
        self.command_queue = command_queue or queue.Queue()
        self.event_queue = event_queue or queue.Queue()
        self.transport_factory = transport_factory
        self.port_info = port_info or {}
        self.allow_mock = allow_mock
        self.cancel_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="IRSerialIoWorker", daemon=True)
        self.transport: Optional[SerialTransport] = None
        self.client: Optional[LearningClient] = None
        self.handshake: Optional[HandshakeResult] = None
        self._shutdown_requested = False
        self._cancel_sent = False

        # R3: command generation tracking for cancel/disconnect/shutdown ordering
        self._command_sequence: int = 0
        self._latest_begin_generation: int = 0
        self._latest_cancel_generation: int = 0
        self._latest_disconnect_generation: int = 0
        self._latest_shutdown_generation: int = 0
        self._active_begin_generation: int = 0

    def start(self) -> None:
        self.thread.start()

    def post(self, command_type: str, **payload: object) -> None:
        self._command_sequence += 1
        seq = self._command_sequence
        if command_type == CMD_CANCEL_CAPTURE:
            self._latest_cancel_generation = seq
            self.cancel_event.set()
            self._wake_reader()
        elif command_type == CMD_DISCONNECT:
            self._latest_disconnect_generation = seq
            self.cancel_event.set()
            self._wake_reader()
        elif command_type == CMD_SHUTDOWN:
            self._latest_shutdown_generation = seq
            self.cancel_event.set()
            self._wake_reader()
        elif command_type == CMD_BEGIN_CAPTURE:
            self._latest_begin_generation = seq
        self.command_queue.put({"type": command_type, "generation": seq, **payload})

    def join(self, timeout: float = 5.0) -> bool:
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def _emit(self, event_type: str, **payload: object) -> None:
        self.event_queue.put({"type": event_type, **payload})

    def _run(self) -> None:
        while not self._shutdown_requested:
            try:
                command = self.command_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                self._handle_command(command)
            except Exception as exc:
                self._emit(EV_ERROR, message=str(exc))
        # R3: clean shutdown sequence
        self._clean_exit()
        self._safe_close(send_shutdown=True)

    def _handle_command(self, command: Dict) -> None:
        ctype = command.get("type")
        gen = int(command.get("generation", 0))
        if ctype == CMD_CONNECT:
            self._connect()
        elif ctype == CMD_READ_STATUS:
            self._read_status()
        elif ctype == CMD_BEGIN_CAPTURE:
            self._begin_capture(str(command.get("sessionId") or new_session_id()), gen)
        elif ctype == CMD_CANCEL_CAPTURE:
            self._cancel_capture()
        elif ctype == CMD_DISCONNECT:
            self._disconnect()
        elif ctype == CMD_SHUTDOWN:
            self._shutdown_requested = True
        else:
            self._emit(EV_ERROR, message=f"unknown worker command: {ctype}")

    def _connect(self) -> None:
        if self.client:
            self._emit(EV_CONNECTED, alreadyConnected=True)
            return
        if not self.transport_factory:
            port = self.port_info.get("device") or ""
            if not port:
                raise RuntimeError("serial port is required")
            self.transport_factory = lambda: PySerialTransport(port)
        self.transport = self.transport_factory()
        self.client = LearningClient(self.transport)
        self._emit(EV_CONNECTED)
        self._read_status()

    def _read_status(self) -> None:
        if not self.client:
            raise RuntimeError("device is not connected")
        status = self.client.poll_status()
        self.handshake = validate_device_status(status, self.port_info, allow_mock=self.allow_mock)
        if self.handshake.ready:
            self._emit(EV_HANDSHAKE_OK, status=status, metadata=self.handshake.metadata)
        else:
            self._emit(EV_HANDSHAKE_FAILED, status=status, reasons=list(self.handshake.reasons))

    def _begin_capture(self, session_id: str, generation: int = 0) -> None:
        """R3: Check generations before sending 20H; do NOT unconditionally clear cancel_event."""
        if not self.client:
            raise RuntimeError("device is not connected")
        if not self.handshake or not self.handshake.ready:
            self._emit(EV_CAPTURE_FAILED, reason="DEVICE_NOT_VERIFIED")
            return

        # R3: Check if superseded by a more recent cancel/disconnect/shutdown
        if self._latest_cancel_generation >= generation and generation > 0:
            self._emit(EV_CAPTURE_FAILED, reason="BEGIN_SUPERSEDED_BY_CANCEL")
            return
        if self._latest_disconnect_generation >= generation and generation > 0:
            self._emit(EV_CAPTURE_FAILED, reason="BEGIN_SUPERSEDED_BY_DISCONNECT")
            return
        if self._latest_shutdown_generation >= generation and generation > 0:
            self._emit(EV_CAPTURE_FAILED, reason="BEGIN_SUPERSEDED_BY_SHUTDOWN")
            return

        # R3: Only clear cancel_event when starting a truly fresh begin
        # that is newer than any existing cancel request
        self._active_begin_generation = generation
        if generation > self._latest_cancel_generation:
            self.cancel_event.clear()
        self._cancel_sent = False

        def progress(event_type: str, payload: Dict) -> None:
            if event_type == EV_EXPORT_PROGRESS and payload.get("event") == protocol.EXPORT_BEGIN_EVENT:
                self._emit(EV_EXPORT_BEGIN, event=payload)
            elif event_type == EV_EXPORT_PROGRESS:
                self._emit(EV_EXPORT_PROGRESS, event=payload)
            else:
                self._emit(event_type, **payload)

        try:
            raw, events = self.client.capture_once(
                session_id,
                cancel_event=self.cancel_event,
                progress=progress,
            )
            # R3: Verify exit confirmation before emitting CAPTURE_VALIDATED
            cancel_data = events.get("cancel", {})
            exit_confirmed = bool(cancel_data.get("exitConfirmed", False))
            if not exit_confirmed:
                self._emit(EV_CAPTURE_FAILED, reason="EXIT_UNCONFIRMED")
                return

            metadata = dict(self.handshake.metadata)
            metadata.update(
                {
                    "capturedAt": utc_now(),
                    "learnSessionId": session_id,
                    "learnExitConfirmed": exit_confirmed,
                    "requestId": events.get("requestId", ""),
                    "exportId": events.get("exportId", ""),
                }
            )
            self._emit(EV_CAPTURE_VALIDATED, frame=raw, metadata=metadata, events=events)
        except InterruptedError:
            self._cancel_capture()
            self._emit(EV_CANCELLED, sessionId=session_id)
        except Exception as exc:
            self._emit(EV_CAPTURE_FAILED, reason=str(exc))

    def _cancel_capture(self) -> None:
        self.cancel_event.set()
        if self.client and not self._cancel_sent:
            try:
                self.client.cancel(session_id=self.client._latest_meta.get("sessionId", "") or "cancelled")
                self._cancel_sent = True
            except Exception as exc:
                self._emit(EV_ERROR, message=f"cancel cleanup failed: {exc}")
        self._emit(EV_CANCELLED)

    def _disconnect(self) -> None:
        """R6: Safe disconnect with 21H exit + EV_DISCONNECTED + EV_WORKER_TERMINATED."""
        self.cancel_event.set()
        self._wake_reader()

        # Attempt safe 21H exit if client is connected
        if self.client and not self._cancel_sent:
            try:
                self.client.cancel(session_id=self.client._latest_meta.get("sessionId", "") or "disconnect")
                self._cancel_sent = True
            except Exception as exc:
                self._emit(EV_ERROR, message=f"disconnect cleanup failed: {exc}")

        # Emit DISCONNECTED before entering shutdown
        self._emit(EV_DISCONNECTED)

        # Close serial and mark shutdown
        self._safe_close(send_shutdown=False)
        self._shutdown_requested = True

    def _clean_exit(self) -> None:
        """R6: Final cleanup before worker thread exits. Emits WORKER_TERMINATED."""
        if self.client and not self._cancel_sent:
            try:
                self.client.cancel(session_id=self.client._latest_meta.get("sessionId", "") or "shutdown")
                self._cancel_sent = True
            except Exception:
                pass
        # Emit WORKER_TERMINATED so GUI can join and clean up
        self._emit(EV_WORKER_TERMINATED)

    def _safe_close(self, send_shutdown: bool) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception as exc:
                self._emit(EV_ERROR, message=f"close failed: {exc}")
        self.client = None
        self.transport = None
        if send_shutdown:
            self._emit(EV_SHUTDOWN_COMPLETE)

    def _wake_reader(self) -> None:
        transport = self.transport
        if transport and hasattr(transport, "cancel_read"):
            try:
                getattr(transport, "cancel_read")()
            except Exception as exc:
                self._emit(EV_ERROR, message=f"cancel_read failed: {exc}")


def _parse_json_line(text: str) -> Optional[Dict]:
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None
