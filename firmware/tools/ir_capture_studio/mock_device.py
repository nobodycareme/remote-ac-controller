#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mock_device.py — 模拟 CH9102 + ESP8266 + ZJ-IR-V2 设备（并行开发期唯一可用后端）

不接触真实串口、不加载 pyserial。
提供与真实设备一致的行协议输出：
  IR_UART_BAUD_CURRENT=19200
  IR_MODULE_BUSY=True/False
  IR_UART_OVERFLOW / RESYNC / TIMEOUT
  IR_EXTLEARN_ENTER
  IR_EXTLEARN_FRAME <hex>
  IR_EXTLEARN_FAIL <reason>
"""

import time

VALID_FRAME_HEX = "68 0A 00 00 22 01 02 03 28 16"   # 校验通过的外部码帧
BAD_FRAME_HEX = "68 0A 00 00 22 01 02 03 00 16"     # 校验和错误的帧


class MockSerialDevice:
    def __init__(self, scenario="success", frame_hex=None, baud=115200):
        """
        scenario:
          success        — 正常：ENTER 后返回有效帧
          bad_checksum  — ENTER 后返回校验失败帧
          timeout       — ENTER 后无帧（等待超时）
          busy          — 模块忙碌（query 返回 BUSY）
          occupied      — 串口被占用（connect 直接失败）
        """
        self.scenario = scenario
        self.frame_hex = frame_hex or VALID_FRAME_HEX
        self.baud = baud
        self._pending = []          # list of (text, delay_seconds)
        self._connected = False

    # -------- 连接 --------
    def connect(self):
        if self.scenario == "occupied":
            raise RuntimeError("SERIAL_BUSY: CH9102 被另一个采集工具或监控程序占用")
        self._connected = True
        self._pending = []

    def disconnect(self):
        self._connected = False
        self._pending = []

    def reset_input_buffer(self):
        self._pending = []

    @property
    def in_waiting(self):
        return 0

    # -------- 写命令（触发模拟响应）--------
    def write(self, cmd):
        if isinstance(cmd, bytes):
            c = cmd.decode("utf-8", "replace")
        else:
            c = str(cmd)
        c = c.strip().lower()
        if c.startswith("ir info"):
            self._schedule_info()
        elif c.startswith("ir extlearn"):
            self._schedule_extlearn()
        elif c.startswith("status"):
            self._schedule_status()

    def readline(self):
        if self._pending:
            text, delay = self._pending.pop(0)
            if delay:
                time.sleep(delay)
            return (text + "\n").encode("utf-8")
        time.sleep(0.05)
        return b""

    def query_module_state(self):
        """模拟模块状态查询（便于 MockCaptureBackend 直接复用）。"""
        busy = (self.scenario == "busy")
        return {
            "busy": busy, "responded": True, "baud_ok": True,
            "module_status": "busy" if busy else "idle",
            "overflow": 0, "resync": 0, "timeout": 0,
        }

    # -------- 内部调度 --------
    def _schedule_info(self):
        busy = (self.scenario == "busy")
        self._pending = [
            ("IR_UART_BAUD_CURRENT=19200", 0),
            ("IR_MODULE_BUSY=%s" % ("True" if busy else "False"), 0),
            ("IR_UART_OVERFLOW=0", 0),
            ("IR_UART_RESYNC=0", 0),
            ("IR_UART_TIMEOUT=0", 0),
        ]

    def _schedule_status(self):
        self._pending = [
            ("STATUS uptime_ms=12345", 0),
            ("net_state=unknown", 0),
            ("ir_baud=19200", 0),
        ]

    def _schedule_extlearn(self):
        self._pending = [("IR_EXTLEARN_ENTER", 0.05)]
        if self.scenario == "success":
            self._pending.append(("IR_EXTLEARN_FRAME " + self.frame_hex, 0.3))
        elif self.scenario == "bad_checksum":
            self._pending.append(("IR_EXTLEARN_FRAME " + BAD_FRAME_HEX, 0.3))
        elif self.scenario == "timeout":
            # 不再入队任何帧 -> 主机等待超时
            pass
        elif self.scenario == "busy":
            self._pending.append(("IR_EXTLEARN_FAIL module_busy", 0.1))
        # occupied 不会到这（connect 已失败）
