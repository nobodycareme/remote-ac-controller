#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — 红外学习采集台 — ZJ-IR-V2（主窗口）

硬约束（第二十五节）：
  ALLOW_IR_REPLAY = False
  ALLOW_CLOUD_IR  = False
  命令白名单仅允许：ir info / ir extlearn / status

并行开发纪律（第一节）：
  PARALLEL_DEVELOPMENT_MODE = "mock_only"
  REAL_SERIAL_ACCESS_ALLOWED = False
  → 仅使用 MockCaptureBackend；不连接真机、不执行真实学习、不回放。

单次采集必须由用户点击“开始本次采集”才会进入学习态（第十二节）。
所有耗时串口操作在后台线程执行，GUI 仅通过 queue + after 更新。
"""

import os
import sys
import json
import time
import queue
import threading
import datetime
import tkinter as tk
from tkinter import ttk

# ---------------- 路径 ----------------
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(TOOL_DIR))))
STUDIO_DIR = os.path.join(PROJECT_ROOT, "References", "IR", "captures", "studio")
USER_SETTINGS_PATH = os.path.join(TOOL_DIR, "user_settings.json")

# ---------------- 并行开发模式开关 ----------------
PARALLEL_DEVELOPMENT_MODE = "mock_only"
REAL_SERIAL_ACCESS_ALLOWED = False   # 10x 工具释放串口前必须为 False

# ---------------- 硬门禁 ----------------
ALLOW_IR_REPLAY = False
ALLOW_CLOUD_IR = False

# ---------------- 时序（第十九节）----------------
FIRMWARE_LEARN_TIMEOUT_S = 30        # 固件学习窗口（不支持可变时长，保留 30s）
HOST_WAIT_S = 38                     # 主机等待帧/失败（略大于固件窗口）
ENTER_WAIT_S = 15                    # 等待 IR_EXTLEARN_ENTER 确认上限

# ---------------- 导入本地模块 ----------------
sys.path.insert(0, TOOL_DIR)
import models
import storage
import widgets
from capture_core_adapter import (
    CaptureBackend, MockCaptureBackend, SerialCaptureBackend,
    hex_to_bytes, validate_frame, checksum_of, verify_protocol_consistency,
)
from serial_device import SerialDevice, LockManager, CH9102_VID, CH9102_PID
from models import (IR_MODULE_BAUD, ESP_CLI_BAUD, MODES, FANS, SWINGS,
                    ONOFF_UNK, POWER_AFTER, TEMPERATURES, TEMP_SPECIAL,
                    TASK_TYPE_LABELS)

# 状态字段定义（前后态共用选项，电源后态多一个 unchanged）
FIELD_DEFS = [
    ("power", "电源", ONOFF_UNK, POWER_AFTER),
    ("mode", "模式", MODES, MODES),
    ("temperatureC", "温度℃", TEMPERATURES + TEMP_SPECIAL, TEMPERATURES + TEMP_SPECIAL),
    ("fan", "风速", FANS, FANS),
    ("swingVertical", "上下扫风", SWINGS, SWINGS),
    ("swingHorizontal", "左右扫风", SWINGS, SWINGS),
    ("quiet", "静音", ONOFF_UNK, ONOFF_UNK),
    ("turbo", "强力", ONOFF_UNK, ONOFF_UNK),
    ("sleep", "睡眠", ONOFF_UNK, ONOFF_UNK),
]


def _now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def beep_press():
    """进入学习态后提示按键（第十四节）。任何异常都不允许使程序崩溃。"""
    try:
        import winsound
        winsound.Beep(1500, 150)
        time.sleep(0.05)
        winsound.Beep(2300, 250)
    except Exception:
        try:
            import winsound
            winsound.MessageBeep()
        except Exception:
            pass


class IRCaptureStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("红外学习采集台 — ZJ-IR-V2")
        self.root.configure(bg="#1f1f1f")

        self.backend = None
        self.lock_manager = LockManager()
        self.queue = queue.Queue()
        self.worker = None
        self.capturing = False
        self.exiting = False
        self.task_built = False

        # 任务与计数
        self.task_config = None
        self.session_dir = None
        self.session_id = None
        self.target_valid = 0
        self.valid = 0
        self.attempts = 0
        self.failed = 0
        self.sample_number = 1
        self.attempt_number = 0
        self.current_capture_id = ""

        self._build_widgets()
        self._load_user_settings()

        # 并行开发期：默认使用模拟后端
        if not REAL_SERIAL_ACCESS_ALLOWED:
            self._init_mock_backend()
        self._poll_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.safe_exit)

    # ============ 后端 ============
    def _init_mock_backend(self):
        scenario = getattr(self, "mock_scenario_var", None)
        sc = scenario.get() if scenario is not None else "success"
        self.backend = MockCaptureBackend(scenario=sc)
        try:
            self.backend.connect()
        except Exception:
            pass
        self._set_device_status("模拟设备", "MOCK", IR_MODULE_BAUD, "空闲")

    def _ensure_real_connection(self):
        ports = SerialDevice.detect_ports()
        if not ports:
            self.log.append("[ERR] 未发现 CH9102 设备（VID=1A86 PID=55D4）。")
            return False
        if len(ports) > 1:
            port = self._ask_port_choice(ports)
            if not port:
                return False
        else:
            port = ports[0]["device"]
        ok, reason = self.lock_manager.acquire(port)
        if not ok:
            self.log.append("[ERR] 串口被占用或存在活跃锁：%s" % reason)
            self.log.append("[ERR] 请先关闭另一个采集/监控工具，不要抢占串口。")
            return False
        self.backend = SerialCaptureBackend(port, ESP_CLI_BAUD, self.lock_manager)
        try:
            self.backend.connect()
        except Exception as e:
            self.log.append("[ERR] 连接失败：%s" % e)
            self.lock_manager.release()
            return False
        self._set_device_status("已连接", port, IR_MODULE_BAUD, "空闲")
        self.log.append("[OK] 已连接 %s @%d（ESP CLI）/ 模块 IR UART %d" % (port, ESP_CLI_BAUD, IR_MODULE_BAUD))
        return True

    # ============ UI 构建 ============
    def _build_widgets(self):
        # 设备状态
        dev = ttk.LabelFrame(self.root, text="设备连接状态", padding=6)
        dev.pack(fill="x", padx=8, pady=4)
        self.dev_ch9102_var = tk.StringVar(value="未连接")
        self.dev_port_var = tk.StringVar(value="—")
        self.dev_baud_var = tk.StringVar(value=str(IR_MODULE_BAUD))
        self.dev_mod_var = tk.StringVar(value="未知")
        ttk.Label(dev, text="CH9102：").grid(row=0, column=0, sticky="e")
        ttk.Label(dev, textvariable=self.dev_ch9102_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(dev, text="串口：").grid(row=0, column=2, sticky="e")
        ttk.Label(dev, textvariable=self.dev_port_var, width=10).grid(row=0, column=3, sticky="w")
        ttk.Label(dev, text="IR波特率：").grid(row=1, column=0, sticky="e")
        ttk.Label(dev, textvariable=self.dev_baud_var, width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(dev, text="模块状态：").grid(row=1, column=2, sticky="e")
        ttk.Label(dev, textvariable=self.dev_mod_var, width=10).grid(row=1, column=3, sticky="w")
        ttk.Button(dev, text="重新扫描设备", command=self._rescan).grid(row=0, column=4, rowspan=2, padx=8)

        if not REAL_SERIAL_ACCESS_ALLOWED:
            ttk.Label(dev, text="（并行开发模拟模式）").grid(row=2, column=0, columnspan=5, sticky="w")
            f, self.mock_scenario_var = widgets.make_combo(
                dev, "模拟场景", ["success", "bad_checksum", "timeout", "busy", "occupied"],
                "success", width=12)
            f.grid(row=3, column=0, columnspan=5, sticky="w", pady=2)

        # 采集任务设置
        task = ttk.LabelFrame(self.root, text="采集任务设置", padding=6)
        task.pack(fill="x", padx=8, pady=4)
        self.brand_var = tk.StringVar(value="海信")
        self.ac_model_var = tk.StringVar(value="")
        self.remote_model_var = tk.StringVar(value="")
        self.task_type_var = tk.StringVar(value=TASK_TYPE_LABELS[0])
        self.custom_var = tk.StringVar(value="")
        self.button_var = tk.StringVar(value="电源键")
        self.notes_var = tk.StringVar(value="")
        self.count_var = tk.StringVar(value="3")

        r = 0
        for lbl, var in [("品牌", self.brand_var), ("空调型号", self.ac_model_var),
                         ("遥控器型号", self.remote_model_var)]:
            ttk.Label(task, text=lbl + "：").grid(row=r, column=0, sticky="e")
            ttk.Entry(task, textvariable=var, width=16).grid(row=r, column=1, sticky="w")
            r += 1
        ttk.Label(task, text="任务类型：").grid(row=r, column=0, sticky="e")
        ttk.Combobox(task, textvariable=self.task_type_var, values=TASK_TYPE_LABELS,
                     width=16, state="readonly").grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(task, text="自定义名称：").grid(row=r, column=0, sticky="e")
        ttk.Entry(task, textvariable=self.custom_var, width=16).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(task, text="按下按键：").grid(row=r, column=0, sticky="e")
        ttk.Entry(task, textvariable=self.button_var, width=16).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(task, text="备注：").grid(row=r, column=0, sticky="e")
        ttk.Entry(task, textvariable=self.notes_var, width=16).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(task, text="采集次数：").grid(row=r, column=0, sticky="e")
        ttk.Combobox(task, textvariable=self.count_var,
                     values=[str(i) for i in range(1, 21)], width=6,
                     state="readonly").grid(row=r, column=1, sticky="w")
        r += 1

        # 前后状态网格
        state = ttk.LabelFrame(self.root, text="空调完整状态（前态 / 后态）", padding=6)
        state.pack(fill="x", padx=8, pady=4)
        ttk.Label(state, text="字段", width=10).grid(row=0, column=0)
        ttk.Label(state, text="前态", width=14).grid(row=0, column=1)
        ttk.Label(state, text="后态", width=14).grid(row=0, column=2)
        self.before_vars = {}
        self.after_vars = {}
        rr = 1
        for key, label, before_opts, after_opts in FIELD_DEFS:
            ttk.Label(state, text=label + "：").grid(row=rr, column=0, sticky="e")
            bv = tk.StringVar(value=models.DEFAULT_STATE[key])
            av = tk.StringVar(value=models.DEFAULT_STATE[key])
            self.before_vars[key] = bv
            self.after_vars[key] = av
            ttk.Combobox(state, textvariable=bv, values=before_opts, width=12,
                         state="readonly").grid(row=rr, column=1)
            ttk.Combobox(state, textvariable=av, values=after_opts, width=12,
                         state="readonly").grid(row=rr, column=2)
            rr += 1

        # 预设
        presets = ttk.LabelFrame(self.root, text="快捷预设（仅填写表单，不自动开始）", padding=6)
        presets.pack(fill="x", padx=8, pady=4)
        ttk.Button(presets, text="预设1 海信制冷24静音全开",
                   command=lambda: self._apply_preset("preset1")).pack(side="left", padx=3)
        ttk.Button(presets, text="预设2 关机",
                   command=lambda: self._apply_preset("preset2")).pack(side="left", padx=3)
        ttk.Button(presets, text="预设3 制冷温度采集",
                   command=lambda: self._apply_preset("preset3")).pack(side="left", padx=3)
        ttk.Button(presets, text="预设4 自定义",
                   command=lambda: self._apply_preset("preset4")).pack(side="left", padx=3)
        ttk.Button(presets, text="重置表单",
                   command=self._reset_form).pack(side="left", padx=3)

        # 控制按钮
        ctrl = ttk.Frame(self.root, padding=6)
        ctrl.pack(fill="x", padx=8, pady=4)
        self.build_btn = ttk.Button(ctrl, text="建立采集任务", command=self.build_task)
        self.start_btn = ttk.Button(ctrl, text="开始本次采集", command=self.start_capture,
                                    state="disabled")
        self.cancel_btn = ttk.Button(ctrl, text="取消等待", command=self.cancel_wait,
                                     state="disabled")
        self.open_btn = ttk.Button(ctrl, text="打开保存目录", command=self.open_save_dir)
        self.exit_btn = ttk.Button(ctrl, text="安全退出", command=self.safe_exit)
        for i, b in enumerate([self.build_btn, self.start_btn, self.cancel_btn,
                               self.open_btn, self.exit_btn]):
            b.grid(row=0, column=i, padx=4)

        # 进度
        prog = ttk.Frame(self.root, padding=4)
        prog.pack(fill="x", padx=8)
        self.progress_var = tk.StringVar(value="当前进度：0 / 0")
        self.stat_var = tk.StringVar(value="目标有效样本：0   当前有效：0   总尝试：0   失败：0")
        ttk.Label(prog, textvariable=self.progress_var, font=("Microsoft YaHei", 10, "bold")
                  ).pack(anchor="w")
        ttk.Label(prog, textvariable=self.stat_var, foreground="#cccccc").pack(anchor="w")

        # 大状态标签
        self.status_label = widgets.BigStatusLabel(self.root)
        self.status_label.pack(fill="x", padx=8, pady=6)

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=4)
        log_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.log = widgets.ScrolledLog(log_frame, height=10)
        self.log.pack(fill="both", expand=True)

        self.log.append("[INIT] 红外学习采集台已启动。")
        self.log.append("[INIT] 并行开发模式=%s，真机串口访问=%s" % (
            PARALLEL_DEVELOPMENT_MODE, REAL_SERIAL_ACCESS_ALLOWED))
        self.log.append("[INIT] 回放禁用=%s，云端禁用=%s" % (ALLOW_IR_REPLAY, ALLOW_CLOUD_IR))

    # ============ 表单读写 ============
    def _read_form(self):
        sb = {k: self.before_vars[k].get() for k, *_ in FIELD_DEFS}
        sa = {k: self.after_vars[k].get() for k, *_ in FIELD_DEFS}
        try:
            count = max(1, min(20, int(self.count_var.get())))
        except Exception:
            count = 3
        return {
            "brand": self.brand_var.get(),
            "acModel": self.ac_model_var.get(),
            "remoteModel": self.remote_model_var.get(),
            "taskType": self.task_type_var.get(),
            "customTaskName": self.custom_var.get(),
            "buttonPressed": self.button_var.get(),
            "notes": self.notes_var.get(),
            "captureCount": count,
            "stateBefore": sb,
            "stateAfter": sa,
            "learnTimeoutSeconds": FIRMWARE_LEARN_TIMEOUT_S,
        }

    def _apply_preset(self, key):
        p = models.PRESETS.get(key)
        if not p:
            return
        self.brand_var.set(p["brand"])
        self.ac_model_var.set(p["acModel"])
        self.remote_model_var.set(p["remoteModel"])
        self.task_type_var.set(p["taskType"])
        self.custom_var.set(p["customTaskName"])
        self.button_var.set(p["buttonPressed"])
        self.count_var.set(str(p["captureCount"]))
        for k in self.before_vars:
            self.before_vars[k].set(p["stateBefore"].get(k, models.DEFAULT_STATE[k]))
            self.after_vars[k].set(p["stateAfter"].get(k, models.DEFAULT_STATE[k]))
        self.log.append("[PRESET] 已套用预设 %s（请检查后点击“建立采集任务”）" % key)

    def _reset_form(self):
        self.brand_var.set("海信")
        self.ac_model_var.set("")
        self.remote_model_var.set("")
        self.task_type_var.set(TASK_TYPE_LABELS[0])
        self.custom_var.set("")
        self.button_var.set("电源键")
        self.notes_var.set("")
        self.count_var.set("3")
        for k in self.before_vars:
            self.before_vars[k].set(models.DEFAULT_STATE[k])
            self.after_vars[k].set(models.DEFAULT_STATE[k])
        self.log.append("[FORM] 表单已重置。")

    # ============ 设备状态 ============
    def _set_device_status(self, ch9102, port, baud, module_status):
        self.dev_ch9102_var.set(ch9102)
        self.dev_port_var.set(port)
        self.dev_baud_var.set(str(baud))
        self.dev_mod_var.set(module_status)

    def _rescan(self):
        if REAL_SERIAL_ACCESS_ALLOWED:
            ports = SerialDevice.detect_ports()
            if not ports:
                self._set_device_status("未连接", "—", IR_MODULE_BAUD, "未知")
                self.log.append("[SCAN] 未发现 CH9102 设备。")
            else:
                self.log.append("[SCAN] 发现 %d 个匹配设备：%s" % (
                    len(ports), ", ".join(p["device"] for p in ports)))
        else:
            self.log.append("[SCAN] 模拟模式：无需扫描真实设备。")

    def _ask_port_choice(self, ports):
        # 简单弹窗选择
        win = tk.Toplevel(self.root)
        win.title("选择串口")
        win.grab_set()
        var = tk.StringVar(value=ports[0]["device"])
        for p in ports:
            ttk.Radiobutton(win, text="%s  %s  %s" % (p["device"], p["vid"], p["pid"]),
                            variable=var, value=p["device"]).pack(anchor="w", padx=8, pady=2)
        sel = {"port": None}

        def ok():
            sel["port"] = var.get()
            win.destroy()

        ttk.Button(win, text="确定", command=ok).pack(pady=6)
        self.root.wait_window(win)
        return sel["port"]

    # ============ 任务建立 ============
    def build_task(self):
        if self.capturing:
            self.log.append("[WARN] 当前正在采集，请稍后再建立新任务。")
            return
        task = self._read_form()
        when = datetime.datetime.now()
        sid = models.build_session_id(task["brand"], task["stateBefore"],
                                      task["stateAfter"], task["taskType"],
                                      task["customTaskName"], when)
        try:
            self.session_dir, self.session_id = storage.safe_session_dir(STUDIO_DIR, sid)
        except Exception as e:
            self.log.append("[ERR] 创建会话目录失败：%s" % e)
            return
        task["sessionId"] = self.session_id
        self.task_config = task
        self.target_valid = task["captureCount"]
        self.valid = 0
        self.attempts = 0
        self.failed = 0
        self.sample_number = 1
        self.attempt_number = 0
        self.task_built = True
        self._save_session_json()
        self._update_progress()
        self.status_label.set_phase("IDLE")
        self.start_btn.config(state="normal")
        self.log.append("[TASK] 已建立采集任务：%s" % self.session_id)
        self.log.append("[TASK] 保存目录：%s" % self.session_dir)
        self.log.append("[TASK] 目标有效样本：%d。请点击“开始本次采集”。" % self.target_valid)
        self._save_user_settings()

    # ============ 单次采集（必须手动点击）============
    def start_capture(self):
        if not self.task_built:
            self.log.append("[WARN] 请先点击“建立采集任务”。")
            return
        if self.capturing:
            return
        if REAL_SERIAL_ACCESS_ALLOWED and (self.backend is None or not self.backend.is_connected()):
            if not self._ensure_real_connection():
                return
        self.capturing = True
        self.attempts += 1
        self.attempt_number += 1
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        click_ts = time.time()
        capture_id = models.build_capture_filename(
            self.task_config["brand"], self.task_config["stateBefore"],
            self.task_config["stateAfter"], self.task_config["taskType"],
            self.task_config["customTaskName"], self.sample_number)
        self.current_capture_id = capture_id
        cfg = dict(self.task_config)
        cfg["sampleNumber"] = self.sample_number
        cfg["attemptNumber"] = self.attempt_number
        cfg["clickTimestamp"] = datetime.datetime.fromtimestamp(click_ts).strftime("%Y-%m-%dT%H:%M:%S")
        cfg["serialPort"] = getattr(getattr(self.backend, "device", None), "port", "MOCK")
        cfg["firmwareSha256"] = "unknown"
        self.log.append("[CAPTURE] 第 %d/%d 次：%s" % (self.sample_number, self.target_valid, capture_id))
        self.backend.clear_cancel()
        t = threading.Thread(target=self._worker, args=(click_ts, cfg, capture_id), daemon=True)
        t.start()

    def _worker(self, click_ts, cfg, capture_id):
        self.queue.put(("log", "[%s] [PREPARING] 检查模块空闲与波特率..." % _now()))
        self.queue.put(("phase", "PREPARING"))
        status = self.backend.query_status(window_s=3.0)
        if self.backend._cancel.is_set():
            self._finish_fail("user_cancelled", status, click_ts, cfg, capture_id, [])
            return
        if status["busy"] is True:
            self._finish_fail("module_busy", status, click_ts, cfg, capture_id, [])
            return
        self.queue.put(("log", "[%s] [PREPARING] 模块空闲，发送 ir extlearn" % _now()))
        cmd_ts = time.time()
        enter_ok, prompt_mode = self.backend.start_learning(enter_wait_s=ENTER_WAIT_S)
        if not enter_ok:
            reason = "user_cancelled" if prompt_mode == "cancelled" else "learn_command_not_acknowledged"
            self._finish_fail(reason, status, click_ts, cfg, capture_id, [],
                              command_sent_ts=cmd_ts)
            return
        learn_confirmed_ts = time.time()
        # LEARNING
        self.queue.put(("phase", "LEARNING"))
        local_prompt_ts = time.time()
        self.queue.put(("log", "[%s] [LEARNING] 现在按遥控器！只短按一次。" % _now()))
        beep_press()
        frame_hex, raw, cancelled = self.backend.wait_for_capture(host_wait_s=HOST_WAIT_S)
        if cancelled:
            self._finish_fail("user_cancelled", status, click_ts, cfg, capture_id, raw,
                              command_sent_ts=cmd_ts, learn_confirmed_ts=learn_confirmed_ts,
                              local_prompt_ts=local_prompt_ts)
            return
        if frame_hex is None:
            self._finish_fail("timeout_waiting_remote", status, click_ts, cfg, capture_id, raw,
                              command_sent_ts=cmd_ts, learn_confirmed_ts=learn_confirmed_ts,
                              local_prompt_ts=local_prompt_ts)
            return
        # SAVING
        self.queue.put(("phase", "SAVING"))
        self.queue.put(("log", "[%s] [SAVING] 收到数据，校验与保存中..." % _now()))
        capture_complete_ts = time.time()
        frame = hex_to_bytes(frame_hex)
        gate, gd = validate_frame(frame, {
            "overflow": status.get("overflow", 0),
            "resync": status.get("resync", 0),
            "timeout": status.get("timeout", 0),
        })
        record = models.build_sample_record_base(cfg)
        self._fill_record_timing(record, click_ts, cmd_ts, learn_confirmed_ts,
                                 local_prompt_ts, capture_complete_ts, capture_id)
        self._fill_record_gate(record, gd)
        if not gate:
            reason = self._gate_reason(gd)
            self._finish_fail(reason, status, click_ts, cfg, capture_id, raw,
                              command_sent_ts=cmd_ts, learn_confirmed_ts=learn_confirmed_ts,
                              local_prompt_ts=local_prompt_ts, capture_complete_ts=capture_complete_ts,
                              frame=frame, gd=gd, record=record)
            return
        try:
            res = self.backend.save_capture(self.session_dir, capture_id, frame, raw, record)
        except Exception as e:
            self._finish_fail("file_write_failure", status, click_ts, cfg, capture_id, raw,
                              command_sent_ts=cmd_ts, learn_confirmed_ts=learn_confirmed_ts,
                              local_prompt_ts=local_prompt_ts, capture_complete_ts=capture_complete_ts,
                              frame=frame, gd=gd, record=record)
            return
        self.queue.put(("phase", "SUCCESS"))
        self.queue.put(("log", "[%s] [SUCCESS] %s 长度=%d SHA256=%s" % (
            _now(), capture_id, len(frame), res["binSha256"][:16])))
        self.queue.put(("result_success", {
            "capture_id": capture_id, "length": len(frame),
            "sha256": res["binSha256"], "paths": res,
        }))

    def _fill_record_timing(self, record, click_ts, cmd_ts, learn_ts, prompt_ts, done_ts, capture_id):
        record["captureId"] = capture_id
        record["captureTime"] = datetime.datetime.fromtimestamp(done_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["clickTimestamp"] = datetime.datetime.fromtimestamp(click_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["commandSentTimestamp"] = datetime.datetime.fromtimestamp(cmd_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["learningConfirmedTimestamp"] = datetime.datetime.fromtimestamp(learn_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["localPromptTimestamp"] = datetime.datetime.fromtimestamp(prompt_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["captureCompleteTimestamp"] = datetime.datetime.fromtimestamp(done_ts).strftime("%Y-%m-%dT%H:%M:%S")
        record["commandToPromptMs"] = int((prompt_ts - cmd_ts) * 1000)
        record["captureDurationMs"] = int((done_ts - click_ts) * 1000)

    def _fill_record_gate(self, record, gd):
        record["moduleAckReceived"] = True
        record["learnResultReceived"] = True
        record["AFN"] = gd["afn"]
        record["externalCodeLength"] = gd["captureLength"]
        record["checksumExpected"] = gd["cs_embedded"]
        record["checksumActual"] = gd["cs_calculated"]
        record["checksumPass"] = gd["uartChecksumPass"]
        record["frameHeaderPass"] = gd["headerPass"]
        record["frameTailPass"] = gd["uartTailPass"]
        record["binLengthMatch"] = gd["binLengthMatch"]
        record["uartOverflowCount"] = gd["overflowCount"]
        record["uartResyncCount"] = gd["resyncCount"]
        record["uartTimeoutCount"] = gd["timeoutCount"]
        record["uartChecksumFailureCount"] = 0 if gd["uartChecksumPass"] else 1

    def _gate_reason(self, gd):
        if not gd["headerPass"]:
            return "invalid_frame_header"
        if not gd["uartTailPass"]:
            return "invalid_frame_tail"
        if not gd["lenFieldPass"]:
            return "invalid_length"
        if not gd["afnPass"]:
            return "ambiguous_result"
        if not gd["uartChecksumPass"]:
            return "checksum_failure"
        if gd["overflowCount"] > 0:
            return "uart_overflow"
        return "ambiguous_result"

    def _finish_fail(self, reason, status, click_ts, cfg, capture_id, raw,
                     command_sent_ts=None, learn_confirmed_ts=None,
                     local_prompt_ts=None, capture_complete_ts=None,
                     frame=None, gd=None, record=None):
        if record is None:
            record = models.build_sample_record_base(cfg)
            self._fill_record_timing(record, click_ts,
                                     command_sent_ts or click_ts,
                                     learn_confirmed_ts or click_ts,
                                     local_prompt_ts or click_ts,
                                     capture_complete_ts or click_ts, capture_id)
        record["captureResult"] = "failed"
        record["failureReason"] = reason
        record["replayed"] = False
        record["cloudTriggered"] = False
        record["moduleAckReceived"] = (status.get("responded", False) if status else False)
        record["learnResultReceived"] = (frame is not None)
        if gd is not None:
            self._fill_record_gate(record, gd)
        try:
            self.backend.save_failed(self.session_dir, capture_id, record, raw or [])
        except Exception as e:
            self.queue.put(("log", "[ERR] 失败诊断写入异常：%s" % e))
        self.queue.put(("phase", "FAILED"))
        self.queue.put(("log", "[%s] [FAILED] %s 原因=%s" % (_now(), capture_id, reason)))
        self.queue.put(("result_fail", {"capture_id": capture_id, "reason": reason}))

    # ============ 队列轮询（主线程）============
    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "phase":
                    self.status_label.set_phase(item[1])
                elif kind == "log":
                    self.log.append(item[1])
                elif kind == "result_success":
                    self._on_success(item[1])
                elif kind == "result_fail":
                    self._on_fail(item[1])
        except queue.Empty:
            pass
        if not self.exiting:
            self.root.after(120, self._poll_queue)

    def _on_success(self, info):
        self.valid += 1
        self.log.append("[STAT] 有效样本 %d/%d，总尝试 %d，失败 %d" % (
            self.valid, self.target_valid, self.attempts, self.failed))
        if self.valid >= self.target_valid:
            self.log.append("[DONE] 任务完成：有效 %d/%d。已保存，未回放。" % (
                self.valid, self.target_valid))
            self.start_btn.config(state="disabled")
        else:
            self.sample_number += 1
            self.attempt_number = 0
            self.log.append("[NEXT] 请调整遥控器状态，准备第 %d/%d 次后点击“开始本次采集”。" % (
                self.sample_number, self.target_valid))
        self._update_progress()
        self._save_session_json()
        self._finish_common()

    def _on_fail(self, info):
        self.failed += 1
        self.log.append("[STAT] 有效样本 %d/%d，总尝试 %d，失败 %d（失败不计入有效）" % (
            self.valid, self.target_valid, self.attempts, self.failed))
        self.log.append("[RETRY] 可点击“开始本次采集”重试当前样本；或调整状态后继续。")
        self._update_progress()
        self._save_session_json()
        self._finish_common()

    def _finish_common(self):
        self.capturing = False
        self.cancel_btn.config(state="disabled")
        if self.start_btn.cget("state") == "disabled" and self.valid < self.target_valid:
            self.start_btn.config(state="normal")

    def _update_progress(self):
        self.progress_var.set("当前进度：%d / %d" % (self.sample_number, self.target_valid))
        self.stat_var.set("目标有效样本：%d   当前有效：%d   总尝试：%d   失败：%d" % (
            self.target_valid, self.valid, self.attempts, self.failed))

    # ============ 取消 / 退出 ============
    def cancel_wait(self):
        if not self.capturing:
            return
        self.log.append("[CANCEL] 用户取消等待。")
        if self.status_label.cget("text").startswith("正在检查"):
            self.log.append("[CANCEL] 尚未发送学习命令，直接取消。")
        else:
            self.log.append("[CANCEL] 等待模块安全退出学习态...")
        self.backend.cancel_or_wait_timeout()

    def open_save_dir(self):
        d = self.session_dir or STUDIO_DIR
        try:
            os.startfile(d)
        except Exception:
            self.log.append("[INFO] 保存目录：%s" % d)

    def safe_exit(self):
        if self.exiting:
            return
        self.exiting = True
        self.log.append("[EXIT] 安全退出中...")
        if self.capturing and self.worker is not None:
            self.backend.cancel_or_wait_timeout()
            self.worker.join(timeout=45)
        if self.backend is not None:
            try:
                self.backend.disconnect()
            except Exception:
                pass
        self.lock_manager.release()
        self._save_session_json()
        self.log.append("[EXIT] 已释放锁、关闭串口、保存会话。未执行任何回放。")
        try:
            self.root.destroy()
        except Exception:
            pass

    # ============ 用户设置 ============
    def _load_user_settings(self):
        try:
            if os.path.exists(USER_SETTINGS_PATH):
                with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.brand_var.set(d.get("brand", "海信"))
                self.ac_model_var.set(d.get("acModel", ""))
                self.remote_model_var.set(d.get("remoteModel", ""))
                for k in self.before_vars:
                    if k in d.get("state", {}):
                        self.before_vars[k].set(d["state"][k])
                        self.after_vars[k].set(d["state"][k])
                self.count_var.set(str(d.get("captureCount", 3)))
        except Exception:
            pass

    def _save_user_settings(self):
        try:
            d = {
                "brand": self.brand_var.get(),
                "acModel": self.ac_model_var.get(),
                "remoteModel": self.remote_model_var.get(),
                "captureCount": self.count_var.get(),
                "state": {k: self.before_vars[k].get() for k in self.before_vars},
                "lastSaveDir": self.session_dir or "",
            }
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_session_json(self):
        if not self.session_dir:
            return
        rec = {
            "sessionId": self.session_id,
            "createdAt": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "brand": self.task_config["brand"] if self.task_config else "",
            "taskType": self.task_config["taskType"] if self.task_config else "",
            "targetValid": self.target_valid,
            "valid": self.valid,
            "attempts": self.attempts,
            "failed": self.failed,
            "moduleModel": models.MODULE_MODEL,
            "moduleUartBaud": IR_MODULE_BAUD,
            "replayed": False,
            "cloudTriggered": False,
        }
        try:
            storage.save_session_json(self.session_dir, rec)
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = IRCaptureStudio(root)
    # 启动时校验协议一致性（不阻塞）
    try:
        ok, detail = verify_protocol_consistency()
        if not ok:
            app.log.append("[WARN] 协议一致性校验未通过：%s" % detail)
    except Exception:
        pass
    root.mainloop()


if __name__ == "__main__":
    main()
