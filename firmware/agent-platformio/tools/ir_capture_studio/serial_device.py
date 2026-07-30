#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serial_device.py — 真实 CH9102 串口设备 + 两级并行冲突保护（第十六节）

第一级：独占打开串口，失败即报“被占用”。
第二级：进程互斥锁文件 Private/Locks/ir_capture.lock + 命名互斥量
        Local\\RemoteACController_IR_Capture。检测到活跃锁时禁止连接真机。

pyserial 仅在方法内惰性导入，模块加载阶段不强制依赖（便于 mock 期导入测试）。
"""

import os
import sys
import json
import time
import threading

try:
    import serial
    import serial.tools.list_ports
    _HAVE_PYSERIAL = True
except Exception:
    serial = None
    _HAVE_PYSERIAL = False

CH9102_VID = 0x1A86
CH9102_PID = 0x55D4
TOOL_NAME = "ir_capture_studio"
MUTEX_NAME = "Local\\RemoteACController_IR_Capture"

# 锁文件默认位置（可被测试覆盖）
DEFAULT_LOCKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))),  # 项目根
    "Private", "Locks")


def _pid_alive(pid):
    """跨平台判断进程是否存活（保守实现）。"""
    if pid is None:
        return False
    try:
        if sys.platform.startswith("win"):
            import ctypes
            k = ctypes.windll.kernel32
            k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
            k.OpenProcess.restype = ctypes.c_void_p
            k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            k.GetExitCodeProcess.restype = ctypes.c_int
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle.restype = ctypes.c_int
            PROCESS_QUERY_INFORMATION = 0x0400
            h = k.OpenProcess(PROCESS_QUERY_INFORMATION, False, int(pid))
            if h == 0 or h is None:
                return False
            ec = ctypes.c_uint32()
            k.GetExitCodeProcess(h, ctypes.byref(ec))
            k.CloseHandle(h)
            return ec.value == 259  # STILL_ACTIVE
        else:
            import os as _os
            _os.kill(int(pid), 0)
            return True
    except Exception:
        return False


class LockManager:
    """两级锁：锁文件 + Windows 命名互斥量。"""

    def __init__(self, locks_dir=DEFAULT_LOCKS_DIR):
        self.locks_dir = locks_dir
        self.lock_path = os.path.join(locks_dir, "ir_capture.lock")
        self._mutex_handle = None
        self._owned = False

    def acquire(self, serial_port=""):
        """尝试获取锁。返回 (ok, reason)。若被其他活跃进程占用则 ok=False。"""
        if not self._try_mutex():
            return False, "named_mutex_busy"
        # 互斥量已持有；检查锁文件
        if os.path.exists(self.lock_path):
            try:
                with open(self.lock_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("pid") != os.getpid() and _pid_alive(data.get("pid")):
                    self._release_mutex()
                    return False, "lock_file_active:%s" % data.get("toolName", "?")
            except Exception:
                # 锁文件损坏：覆盖重建（保留告警）
                pass
        os.makedirs(self.locks_dir, exist_ok=True)
        rec = {
            "pid": os.getpid(),
            "toolName": TOOL_NAME,
            "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "serialPort": serial_port,
            "host": os.uname().nodename if hasattr(os, "uname") else "",
        }
        with open(self.lock_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        self._owned = True
        return True, "ok"

    def release(self):
        if self._mutex_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None
        if self._owned and os.path.exists(self.lock_path):
            try:
                os.remove(self.lock_path)
            except Exception:
                pass
        self._owned = False

    def _try_mutex(self):
        if not sys.platform.startswith("win"):
            # 非 Windows：仅靠锁文件（命名互斥量不适用）
            return True
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k.CreateMutexW.restype = ctypes.c_void_p
            k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
            k.OpenMutexW.restype = ctypes.c_void_p
            k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k.WaitForSingleObject.restype = ctypes.c_uint32
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle.restype = ctypes.c_int
            # 先尝试以“非拥有”方式打开已存在的命名互斥量
            h = k.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
            if h == 0 or h is None:
                # 不存在 -> 我们创建并持有
                h = k.CreateMutexW(None, True, MUTEX_NAME)
                if h == 0 or h is None:
                    return False
                self._mutex_handle = h
                return True
            # 已存在：立即尝试加锁（不等待）
            wait = k.WaitForSingleObject(h, 0)
            k.CloseHandle(h)
            if wait == 0:  # WAIT_OBJECT_0 -> 我们拿到了
                h = k.CreateMutexW(None, True, MUTEX_NAME)
                if h == 0 or h is None:
                    return False
                self._mutex_handle = h
                return True
            return False  # 被其他实例持有
        except Exception:
            return True  # 保守：命名互斥量不可用时仅依赖锁文件

    def is_active(self):
        return os.path.exists(self.lock_path)


class SerialDevice:
    """真实 CH9102 串口设备（独占打开 + 命令白名单）。"""

    # 命令白名单（第二十五节）：仅允许只读/学习链路
    _WHITELIST_PREFIX = ("ir extlearn", "ir info", "status")
    _BLOCK_SUBSTR = ("send", "extsend", "replay", "cloud", "mqtt",
                     "emit", "transmit", "ir send", "ir extsend")

    def __init__(self, port, baud=115200):
        self.port = port
        self.baud = baud
        self.ser = None
        self._lock = threading.Lock()

    # -------- 动态探测（第十五节）--------
    @staticmethod
    def detect_ports():
        """返回匹配 VID=1A86 PID=55D4 的端口列表（dict: device/vid/pid/desc）。"""
        hits = []
        if not _HAVE_PYSERIAL:
            return hits
        for p in serial.tools.list_ports.comports():
            vid = getattr(p, "vid", None)
            pid = getattr(p, "pid", None)
            if vid is None or pid is None:
                hw = (getattr(p, "hwid", "") or "").upper()
                if ("VID_1A86" in hw or "VID_01A86" in hw) and "PID_55D4" in hw:
                    vid, pid = CH9102_VID, CH9102_PID
            if vid == CH9102_VID and pid == CH9102_PID:
                hits.append({
                    "device": p.device, "vid": "0x%04X" % vid,
                    "pid": "0x%04X" % pid, "description": p.description or "",
                })
        return hits

    # -------- 连接 --------
    def connect(self):
        if not _HAVE_PYSERIAL:
            raise RuntimeError("PYSERIAL_MISSING: 未安装 pyserial，无法连接真机")
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1.0)
            try:
                self.ser.dtr = False
                self.ser.rts = False
            except Exception:
                pass
        except Exception as e:
            raise RuntimeError("SERIAL_OPEN_FAILED: %s" % e)
        return True

    def disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def is_connected(self):
        return self.ser is not None

    def reset_input_buffer(self):
        if self.ser:
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass

    @property
    def in_waiting(self):
        if self.ser:
            try:
                return self.ser.in_waiting
            except Exception:
                return 0
        return 0

    # -------- 白名单命令发送（硬门禁）--------
    def write(self, cmd):
        if isinstance(cmd, bytes):
            c = cmd.decode("utf-8", "replace")
        else:
            c = str(cmd)
        c_lower = c.strip().lower()
        for bad in self._BLOCK_SUBSTR:
            if bad in c_lower:
                raise RuntimeError("REPLAY_BLOCKED: 命令含禁止子串 '%s'" % bad)
        ok = any(c_lower.startswith(pre) for pre in self._WHITELIST_PREFIX)
        if not ok:
            raise RuntimeError("COMMAND_NOT_ALLOWED: '%s' 不在白名单" % c.strip())
        if self.ser is None:
            raise RuntimeError("SERIAL_NOT_CONNECTED")
        self.ser.write((c.strip() + "\n").encode("utf-8"))
        self.ser.flush()

    def readline(self):
        if self.ser is None:
            return b""
        return self.ser.readline()
