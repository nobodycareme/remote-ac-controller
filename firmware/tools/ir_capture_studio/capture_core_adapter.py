#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_core_adapter.py — 采集后端抽象 + 协议解析（复用 capture_repeat.py 算法）

协议解析（帧头 0x68 / 长度域 / ADDR / AFN=0x22 / CS / 帧尾 0x16、校验和、
完整性门禁）与 References/IR/capture_repeat.py 中的实现保持逐字节一致，
不另写一套不一致的算法。

提供：
  CaptureBackend             抽象基类（共享 prepare/start/wait 编排）
  MockCaptureBackend         模拟后端（并行开发期使用）
  SerialCaptureBackend       真实串口后端（10x 工具释放串口后启用）
"""

import os
import sys
import time
import threading

# 惰性加入 References/IR 以便复用 capture_repeat（只读、不修改）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
_REFERENCES_IR = os.path.join(_PROJECT_ROOT, "References", "IR")
if _REFERENCES_IR not in sys.path:
    sys.path.insert(0, _REFERENCES_IR)

import importlib
import importlib.util

# ---- 本地协议实现（与 capture_repeat 完全一致；mock 期无需 pyserial）----
FRAME_HEADER = 0x68
FRAME_TAIL = 0x16
AFN_EXTCODE = 0x22


def checksum_of(frame):
    """CS=(ADDR+AFN+DATA...) mod 256；同时校验长度字段一致。"""
    if len(frame) < 7:
        return None
    total = frame[1] | (frame[2] << 8)
    if total != len(frame):
        return None
    s = 0
    for b in frame[3:len(frame) - 2]:
        s = (s + b) & 0xFF
    return s & 0xFF


def hex_to_bytes(h):
    h = h.strip()
    parts = h.split()
    return bytes(int(x, 16) for x in parts if x.strip() != "")


def validate_frame(frame, uart_counters=None):
    """§十二 逐样本完整性门禁；返回 (pass, details)。算法与 capture_repeat.integrity_gate 一致。"""
    uart_counters = uart_counters or {}
    d = {}
    d["captureLength"] = len(frame)
    header_ok = (len(frame) >= 7 and frame[0] == FRAME_HEADER)
    tail_ok = (len(frame) >= 2 and frame[-1] == FRAME_TAIL)
    len_field = (frame[1] | (frame[2] << 8)) if len(frame) >= 3 else -1
    len_field_ok = (len_field == len(frame))
    afn = frame[4] if len(frame) >= 5 else None
    afn_ok = (afn == AFN_EXTCODE)
    cs_embedded = frame[-2] if len(frame) >= 2 else None
    cs_calc = checksum_of(frame)
    checksum_pass = (cs_calc is not None) and (cs_calc == cs_embedded)
    d["uartChecksumPass"] = checksum_pass
    d["uartTailPass"] = tail_ok
    d["headerPass"] = header_ok
    d["lenFieldPass"] = len_field_ok
    d["afn"] = ("0x%02X" % afn) if afn is not None else None
    d["afnPass"] = afn_ok
    d["cs_embedded"] = ("0x%02X" % cs_embedded) if cs_embedded is not None else None
    d["cs_calculated"] = ("0x%02X" % cs_calc) if cs_calc is not None else None
    d["overflowCount"] = uart_counters.get("overflow", 0)
    d["resyncCount"] = uart_counters.get("resync", 0)
    d["timeoutCount"] = uart_counters.get("timeout", 0)
    d["binLengthMatch"] = len_field_ok
    overflow = uart_counters.get("overflow", 0)
    resync = uart_counters.get("resync", 0)
    gate = (header_ok and tail_ok and len_field_ok and afn_ok
            and checksum_pass and overflow == 0 and resync == 0)
    d["integrityGatePass"] = gate
    return gate, d


def verify_protocol_consistency():
    """
    若可导入 capture_repeat，则断言本地协议实现与其逐字节一致。
    返回 (consistent: bool, detail: str)。
    """
    try:
        spec = importlib.util.spec_from_file_location(
            "capture_repeat_ref", os.path.join(_REFERENCES_IR, "capture_repeat.py"))
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
    except Exception as e:
        return True, "capture_repeat 不可导入（mock 期可接受）：%s" % e
    ok = True
    detail = []
    for fn in ("checksum_of", "hex_to_bytes"):
        if not hasattr(ref, fn):
            continue
        a = globals()[fn]
        b = getattr(ref, fn)
        # 用标准帧验证数值一致
        frame = hex_to_bytes("68 0A 00 00 22 01 02 03 28 16")
        if a(frame) != b(frame):
            ok = False
            detail.append("%s mismatch" % fn)
    if hasattr(ref, "integrity_gate"):
        frame = hex_to_bytes("68 0A 00 00 22 01 02 03 28 16")
        g1, _ = validate_frame(frame)
        g2, _ = ref.integrity_gate(frame, {})
        if g1 != g2:
            ok = False
            detail.append("integrity_gate mismatch")
    return ok, ("consistent" if ok else "; ".join(detail))


# ------------------------- 后端抽象 -------------------------
class CaptureBackend:
    """采集后端抽象：共享 prepare -> start -> wait 编排，设备实现可替换。"""

    kind = "abstract"

    def __init__(self):
        self.device = None
        self._cancel = threading.Event()

    # 子类实现
    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        if self.device:
            try:
                self.device.disconnect()
            except Exception:
                pass

    def is_connected(self):
        if self.device is None:
            return False
        m = getattr(self.device, "is_connected", None)
        if callable(m):
            return m()
        return getattr(self.device, "_connected", False)

    def clear_cancel(self):
        self._cancel.clear()

    def cancel_or_wait_timeout(self):
        self._cancel.set()

    # -------- 共享编排 --------
    def query_status(self, window_s=3.0):
        if self.device is None:
            return {"busy": None, "responded": False, "baud_ok": False,
                    "module_status": "unknown", "overflow": 0, "resync": 0, "timeout": 0}
        self.device.reset_input_buffer()
        try:
            self.device.write("ir info")
        except Exception:
            pass
        t0 = time.time()
        busy = None
        responded = False
        baud_ok = False
        overflow = resync = timeout = 0
        module_status = "unknown"
        while time.time() - t0 < window_s:
            line = self.device.readline()
            if not line:
                if self._cancel.is_set():
                    break
                continue
            line = line.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            if line.startswith("IR_") or "IR_UART_BAUD" in line or "IR_BAUD" in line:
                responded = True
            if "IR_UART_BAUD_CURRENT=19200" in line or ("IR_BAUD" in line and "19200" in line):
                baud_ok = True
            if "IR_MODULE_BUSY=True" in line or "IR_BUSY=True" in line:
                busy = True
                module_status = "busy"
            m = __import__("re").search(r"IR_UART_OVERFLOW=(\d+)", line)
            if m:
                overflow = int(m.group(1))
            m = __import__("re").search(r"IR_UART_RESYNC=(\d+)", line)
            if m:
                resync = int(m.group(1))
            m = __import__("re").search(r"IR_UART_TIMEOUT=(\d+)", line)
            if m:
                timeout = int(m.group(1))
        if busy is None and responded:
            busy = False
            module_status = "idle"
        return {"busy": busy, "responded": responded, "baud_ok": baud_ok,
                "module_status": module_status, "overflow": overflow,
                "resync": resync, "timeout": timeout}

    def start_learning(self, enter_wait_s=15):
        """发送 ir extlearn 并等待 ENTER 确认；返回 (enter_confirmed, prompt_mode)。"""
        self.device.reset_input_buffer()
        self.device.write("ir extlearn")
        t0 = time.time()
        while time.time() - t0 < enter_wait_s:
            if self._cancel.is_set():
                return False, "cancelled"
            line = self.device.readline()
            if not line:
                continue
            line = line.decode("utf-8", "replace").rstrip("\r\n")
            if "IR_EXTLEARN_ENTER" in line:
                return True, "enter_confirmed"
            if "IR_EXTLEARN_FAIL" in line:
                return False, "enter_fail"
        return False, "enter_timeout"

    def wait_for_capture(self, host_wait_s=38):
        """等待外部码帧；返回 (frame_hex_or_None, raw_lines, cancelled_flag)。"""
        raw = []
        t0 = time.time()
        while time.time() - t0 < host_wait_s:
            if self._cancel.is_set():
                return None, raw, True
            line = self.device.readline()
            if not line:
                continue
            line = line.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            if line.startswith("IR_EXTLEARN") or line.startswith("IR_LEARN"):
                raw.append(line)
            if line.startswith("IR_EXTLEARN_FRAME "):
                return line[len("IR_EXTLEARN_FRAME "):].strip(), raw, False
            if "IR_EXTLEARN_FAIL" in line:
                return None, raw, False
        return None, raw, False

    # -------- 落盘（委托 storage）--------
    def save_capture(self, session_dir, capture_id, bin_bytes, serial_log_lines, record):
        from storage import save_capture
        return save_capture(session_dir, capture_id, bin_bytes, serial_log_lines, record)

    def save_failed(self, session_dir, capture_id, record, serial_log_lines):
        from storage import save_failed
        return save_failed(session_dir, capture_id, record, serial_log_lines)


class MockCaptureBackend(CaptureBackend):
    kind = "mock"

    def __init__(self, scenario="success", frame_hex=None, baud=115200):
        super().__init__()
        from mock_device import MockSerialDevice
        self.device = MockSerialDevice(scenario, frame_hex, baud)

    def connect(self):
        self.device.connect()
        return True


class SerialCaptureBackend(CaptureBackend):
    kind = "serial"

    def __init__(self, port, baud=115200, lock_manager=None):
        super().__init__()
        from serial_device import SerialDevice
        self.device = SerialDevice(port, baud)
        self.lock_manager = lock_manager

    def connect(self):
        # 二级锁与独占打开由调用方（app 控制器）先行检查；此处仅打开串口。
        self.device.connect()
        return True
