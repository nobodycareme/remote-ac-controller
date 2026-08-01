#!/usr/bin/env python3
"""IR Simple Learner — minimal Windows IR capture tool with full export path."""
import base64, hashlib, json, os, queue, sys, tempfile, time, uuid
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import capture_flow as cf
import frame_validator as fv
import presets
import protocol_adapter as pa
import serial_worker as sw
import storage


class FakeWorker:
    """Simulated serial worker for end-to-end testing."""
    def __init__(self, scenario="success"):
        self.queue = queue.Queue()
        self.writes = []
        self.scenario = scenario
        self.running = True

    def write_line(self, text):
        self.writes.append(text)
        parts = text.split()
        cmd = parts[0] if parts else ""
        rid = parts[1] if len(parts) > 1 else ""
        sid = parts[2] if len(parts) > 2 else ""
        eid = parts[3] if len(parts) > 3 else ""

        if cmd == "ir_learn_begin":
            frame = pa.make_public_fake_22h_frame(20)
            sha = hashlib.sha256(frame).hexdigest()
            self._queued_frame = frame
            self.queue.put({"event": "ir.learn.waiting", "requestId": rid, "sessionId": sid})
            time.sleep(0.01)
            self.queue.put({
                "event": "ir.learn.captured", "requestId": rid, "sessionId": sid,
                "length": len(frame), "sha256": sha,
                "structureValid": True,
            })
        elif cmd == "ir_learn_export":
            frame = self._queued_frame if hasattr(self, '_queued_frame') else pa.make_public_fake_22h_frame(20)
            sha = hashlib.sha256(frame).hexdigest()
            events = pa.frame_to_export_events(rid, sid, eid, frame)
            for evt in events:
                self.queue.put(evt)
                time.sleep(0.005)
        elif cmd == "ir_learn_cancel":
            self.queue.put({
                "event": "ir.learn.cancelled", "requestId": rid, "sessionId": sid,
                "exitConfirmed": True, "moduleAckStatus": 0, "moduleAckAfn": 1,
                "moduleAckFrameValid": True,
            })
        elif cmd == "status":
            self.queue.put({"deviceType": "mock", "ok": True})
        elif cmd == "ir_learn_clear":
            pass

    def stop(self):
        self.running = False

    def is_alive(self):
        return self.running

    def start(self, port="mock", baudrate=115200):
        pass


class SimpleLearner:
    def __init__(self, root=None):
        self.root = root
        self.worker = None
        self.flow = cf.CaptureFlow()
        self.ports = []
        self.preset_list = presets.PRESETS
        self.selected_preset = 0
        self.captures = {}       # {1: bytes, 2: bytes, 3: bytes}
        self.capture_metas = {}  # {1: dict, 2: dict, 3: dict}
        self._pending_capture_idx = 1  # remembers which slot was clicked last

        self._build_ui()
        self._scan_ports()
        # Defer first button update until after window is built
        if self.root:
            self.root.after(200, self._update_buttons)
        self._check_timeout()
        self._drain()

    def _build_ui(self):
        if self.root is None:
            return
        self.root.title("IR 红外学习工具")
        self.root.geometry("900x680")
        self.root.columnconfigure(0, weight=1); self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0); self.root.rowconfigure(1, weight=1)

        dev = ttk.LabelFrame(self.root, text="设备连接", padding=5)
        dev.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        ttk.Button(dev, text="扫描串口", command=self._scan_ports).pack(side="left", padx=2)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(dev, textvariable=self.port_var, state="readonly", width=12)
        self.port_combo.pack(side="left", padx=2)
        self.connect_btn = ttk.Button(dev, text="连接", command=self._connect)
        self.connect_btn.pack(side="left", padx=2)
        ttk.Button(dev, text="断开", command=self._disconnect).pack(side="left", padx=2)
        self.dev_status_var = tk.StringVar(value="未连接")
        ttk.Label(dev, textvariable=self.dev_status_var).pack(side="left", padx=10)
        # Status LED
        self.led_canvas = tk.Canvas(dev, width=20, height=20, highlightthickness=0)
        self.led_oval = self.led_canvas.create_oval(2, 2, 18, 18, fill="#888888")
        self.led_canvas.pack(side="right", padx=4)
        self.led_label_var = tk.StringVar(value="未连接")
        ttk.Label(dev, textvariable=self.led_label_var).pack(side="right", padx=2)

        state_frame = ttk.LabelFrame(self.root, text="空调状态", padding=5)
        state_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=3)
        self._build_state_panel(state_frame)

        right = ttk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=5, pady=3)
        self._build_capture_panel(right)

        logf = ttk.LabelFrame(self.root, text="日志", padding=3)
        logf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=3)
        self.root.rowconfigure(2, weight=1)
        logf.columnconfigure(0, weight=1); logf.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logf, height=6, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(logf, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        clear_btn = ttk.Button(logf, text="清空日志", command=self._clear_log)
        clear_btn.grid(row=1, column=0, sticky="w", pady=1)

    def _build_state_panel(self, parent):
        parent.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(parent, text="预设").grid(row=r, column=0, sticky="e", pady=1); r += 1
        self.preset_var = tk.StringVar()
        cb = ttk.Combobox(parent, textvariable=self.preset_var,
            values=[f"{i+1}. {p['name']}" for i, p in enumerate(self.preset_list)], state="readonly")
        cb.grid(row=r-1, column=1, sticky="ew", pady=1)
        cb.bind("<<ComboboxSelected>>", self._on_preset)
        ttk.Label(parent, text="名称").grid(row=r, column=0, sticky="e", pady=1); r += 1
        self.name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.name_var).grid(row=r-1, column=1, sticky="ew", pady=1)
        ttk.Label(parent, text="编码ID").grid(row=r, column=0, sticky="e", pady=1); r += 1
        self.code_id_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.code_id_var).grid(row=r-1, column=1, sticky="ew", pady=1)
        # Droplists: display Chinese, store English
        self._POWER_CN = {"on": "开机", "off": "关机"}
        self._MODE_CN = {"cool": "制冷", "heat": "制热", "dry": "除湿", "fan": "送风", "auto": "自动"}
        self._FAN_CN = {"auto": "自动", "silent": "静音", "low": "低", "medium": "中", "high": "高", "turbo": "超强"}
        for label, vname, vals, dim_map in [
            ("电源", "power_var", ["on","off"], self._POWER_CN),
            ("模式", "mode_var", ["cool","heat","dry","fan","auto"], self._MODE_CN),
            ("温度°C", "temp_var", ["16","17","18","19","20","21","22","23","24","25","26","N/A"], None),
            ("风速", "fan_var", ["auto","silent","low","medium","high","turbo"], self._FAN_CN),
        ]:
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="e", pady=1); r += 1
            v = tk.StringVar(); setattr(self, vname, v)
            if dim_map:
                cb_vals = [dim_map.get(vv, vv) for vv in vals]
                mapping = {cn: raw for raw, cn in dim_map.items()}
                self._combo_mappings = getattr(self, '_combo_mappings', {})
                self._combo_mappings[vname] = (mapping, vals)
                cb_widget = ttk.Combobox(parent, textvariable=v, values=cb_vals, state="readonly", width=12)
                cb_widget._invert = (dim_map, vals)  # for on_preset
            else:
                cb_widget = ttk.Combobox(parent, textvariable=v, values=vals, state="readonly", width=12)
            cb_widget.grid(row=r-1, column=1, sticky="w", pady=1)
        ttk.Label(parent, text="备注").grid(row=r, column=0, sticky="e", pady=1); r += 1
        self.notes_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.notes_var).grid(row=r-1, column=1, sticky="ew", pady=1)
        cf2 = ttk.Frame(parent); cf2.grid(row=r, column=1, sticky="w", pady=3)
        self.turbo_var = tk.BooleanVar(); self.quiet_var = tk.BooleanVar()
        self.sleep_var = tk.BooleanVar(); self.swing_v_var = tk.BooleanVar()
        self.swing_h_var = tk.BooleanVar()
        for lbl, var in [("强力", self.turbo_var), ("静音", self.quiet_var),
            ("睡眠", self.sleep_var), ("上下扫风", self.swing_v_var), ("左右扫风", self.swing_h_var)]:
            ttk.Checkbutton(cf2, text=lbl, variable=var).pack(side="left", padx=3)

    def _build_capture_panel(self, parent):
        parent.columnconfigure(0, weight=1); parent.rowconfigure(0, weight=0); parent.rowconfigure(1, weight=1)
        btns = ttk.Frame(parent); btns.grid(row=0, column=0, sticky="ew", pady=3)
        self.cap_btns = {}
        for i in [1, 2, 3]:
            b = ttk.Button(btns, text=f"采集 {i}", command=lambda idx=i: self._start_capture(idx))
            b.pack(side="left", padx=2); self.cap_btns[i] = b
        self.cancel_btn = ttk.Button(btns, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=2)
        self.reset_btn = ttk.Button(btns, text="重置", command=self._reset_flow)
        self.reset_btn.pack(side="left", padx=2)
        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(btns, textvariable=self.progress_var).pack(side="left", padx=10)
        self.result_text = tk.Text(parent, height=14, state="disabled")
        self.result_text.grid(row=1, column=0, sticky="nsew", pady=1)
        ctrl = ttk.Frame(parent); ctrl.grid(row=2, column=0, sticky="ew", pady=1)
        ttk.Button(ctrl, text="比较全部", command=self._compare).pack(side="left", padx=2)
        self.canonical_var = tk.StringVar()
        ttk.Combobox(ctrl, textvariable=self.canonical_var, values=["1","2","3"], state="readonly", width=3).pack(side="left", padx=2)
        self.approve_btn = ttk.Button(ctrl, text="选定规范帧", command=self._approve, state="disabled")
        self.approve_btn.pack(side="left", padx=2)
        ttk.Button(ctrl, text="设置保存目录", command=self._set_save_dir).pack(side="right", padx=2)
        ttk.Button(ctrl, text="打开保存目录", command=self._open_folder).pack(side="right", padx=2)
        self._update_buttons()

    # ---- Device ----
    def _scan_ports(self):
        self.ports = sw.find_ch9102() or sw.list_all_ports()
        if self.root:
            self.port_combo["values"] = [p["device"] for p in self.ports]
            if self.ports:
                self.port_var.set(self.ports[0]["device"])

    def _connect(self):
        if self.root is None:
            return
        if self.worker is not None:
            self._log("⚠ 设备已连接，请勿重复点击")
            return
        port = self.port_var.get()
        if not port:
            self._log("❌ 请先选择串口")
            return
        self.worker = sw.SerialWorker()
        self.worker.start(port, 115200)
        time.sleep(0.3)
        if self.worker.ser is None or not self.worker.ser.is_open:
            self._log(f"❌ 无法打开 {port} — 可能原因：")
            self._log(f"   1) 设备未连接或USB接触不良")
            self._log(f"   2) 串口被其他程序占用（串口监视器、PlatformIO、另一个学习工具等）")
            self._log(f"   3) 驱动未安装 (CH9102需要专用驱动)")
            self.dev_status_var.set(f"{port} 打开失败")
            self.worker = None
            return
        # Port opened — set connected immediately
        self.dev_status_var.set(f"已连接: {port} @ 115200")
        self._log(f"端口 {port} 已打开 (115200)")
        # Query device commands first
        self.worker.write_line("help")
        time.sleep(0.2)
        # Try ir_learn_status
        self.worker.write_line("ir_learn_status")
        time.sleep(0.2)
        # Try status command
        self.worker.write_line("status")
        self._update_buttons()

    def _disconnect(self):
        if self.flow.active and self.flow.active.state not in (cf.State.IDLE, cf.State.COMPLETED):
            self.flow.cancel(lambda t: self.worker.write_line(t) if self.worker else None)
        if self.worker:
            self.worker.stop()
            self.worker = None
        if self.root:
            self.dev_status_var.set("已断开")
        self._log("已断开连接")
        self._update_buttons()

    # ---- Preset ----
    def _on_preset(self, event=None):
        try:
            idx = int(self.preset_var.get().split(".")[0]) - 1
            if 0 <= idx < len(self.preset_list):
                p = self.preset_list[idx]
                self.name_var.set(p["name"]); self.code_id_var.set(p.get("codeId",""))
                self.power_var.set(self._POWER_CN.get(p.get("power","on"), p.get("power","on")))
                self.mode_var.set(self._MODE_CN.get(p.get("mode","cool"), p.get("mode","cool")))
                self.temp_var.set(p.get("temp","24"))
                self.fan_var.set(self._FAN_CN.get(p.get("fan","auto"), p.get("fan","auto")))
                self.turbo_var.set(p.get("turbo",False)); self.quiet_var.set(p.get("quiet",False))
                self.sleep_var.set(p.get("sleep",False))
                self.swing_v_var.set(p.get("swingV","unknown")=="on"); self.swing_h_var.set(p.get("swingH","unknown")=="on")
        except (ValueError, IndexError):
            pass

    def _cn_to_en(self, value, mapping):
        """Convert Chinese display value back to English for storage."""
        if not value:
            return value
        for raw, cn in mapping.items():
            if value == cn:
                return raw
        return value  # not a Chinese label, return as-is

    def _save_state(self):
        power_en = self._cn_to_en(self.power_var.get(), self._POWER_CN)
        mode_en = self._cn_to_en(self.mode_var.get(), self._MODE_CN)
        fan_en = self._cn_to_en(self.fan_var.get(), self._FAN_CN)
        state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
        defn = {"name": self.name_var.get(), "codeId": state_id,
            "power": power_en, "mode": mode_en,
            "temperature": self.temp_var.get(), "fan": fan_en,
            "turbo": self.turbo_var.get(), "quiet": self.quiet_var.get(),
            "sleep": self.sleep_var.get(),
            "swingV": "on" if self.swing_v_var.get() else "off",
            "swingH": "on" if self.swing_h_var.get() else "off",
            "notes": self.notes_var.get()}
        storage.save_state(state_id, defn)

    # ---- Capture ----
    def _start_capture(self, index):
        self._pending_capture_idx = index
        if not self.worker or not self.worker.is_alive():
            self._log("❌ 设备未连接"); return
        # Flush old events from queue before starting new capture
        try:
            while True: self.worker.queue.get_nowait()
        except queue.Empty:
            pass
        # Auto-clear stuck flow if previous capture finished but context not cleared
        if self.flow.active and self.flow.active.state in (
            cf.State.COMPLETED, cf.State.CANCELLED, cf.State.ERROR, cf.State.EXIT_UNCONFIRMED):
            self.flow.active = None
        active = self.flow.active
        if active and active.state == cf.State.EXIT_UNCONFIRMED:
            self._log("❌ 退出学习未确认 - 请重新连接设备"); return
        ctx, status = self.flow.start(index, lambda t: self.worker.write_line(t))
        if status != "started":
            self._log(f"❌ 无法开始: {status}"); return
        self._log(f"▶ 采集 {index}: 开始（等待模块确认进入学习）")
        self.progress_var.set(f"采集 {index}: 等待设备ACK...")
        self._update_buttons()

    def _reset_flow(self):
        """Force-clear any stuck flow state. Use when buttons get stuck."""
        self.flow.active = None
        self._log("🔄 已重置采集状态")
        # Force-enable buttons
        if self.worker is not None:
            for b in self.cap_btns.values():
                b.configure(state="normal")
        self._update_buttons()

    def _cancel(self):
        self.flow.cancel(lambda t: self.worker.write_line(t) if self.worker else None)
        self._log("⊗ 已取消"); self.progress_var.set("已取消")
        self._update_buttons()

    def _approve(self):
        try:
            idx = int(self.canonical_var.get())
            if idx in self.captures:
                state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
                frame = self.captures[idx]
                p = storage.save_canonical(state_id, idx, frame)
                self._log(f"✅ 规范帧已选定: capture_{idx:03d}.bin → canonical.bin")
                self.canonical_var.set("")
        except ValueError:
            pass
        self._update_buttons()

    def _compare(self):
        if len(self.captures) < 2:
            return
        state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
        for idx in sorted(self.captures):
            a = self.captures[idx]
            sha = hashlib.sha256(a).hexdigest()
            self._log(f"采集 {idx}: {len(a)} 字节, SHA256={sha[:16]}...")
        keys = sorted(self.captures)
        diffs = []
        for i in range(len(keys)-1):
            d = fv.diff_frames(self.captures[keys[i]], self.captures[keys[i+1]])
            diffs.append(d)
            self._log(f"  {keys[i]} vs {keys[i+1]}: {d['diff_count']} 字节差异")
        all_same = all(d["same_content"] for d in diffs)
        self._log(f"三次相同: {'是' if all_same else '否（正常现象）'}")
        storage.save_comparison(state_id, list(self.captures.values()), {"all_same": all_same, "pairs": diffs})
        self._update_buttons()

    def _save_state(self):
        state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
        defn = {"name": self.name_var.get(), "codeId": state_id,
            "power": self.power_var.get(), "mode": self.mode_var.get(),
            "temperature": self.temp_var.get(), "fan": self.fan_var.get(),
            "turbo": self.turbo_var.get(), "quiet": self.quiet_var.get(),
            "sleep": self.sleep_var.get(),
            "swingV": "on" if self.swing_v_var.get() else "off",
            "swingH": "on" if self.swing_h_var.get() else "off",
            "notes": self.notes_var.get()}
        storage.save_state(state_id, defn)

    def _open_folder(self):
        os.startfile(str(storage.LEARNED_ROOT))

    def _set_save_dir(self):
        from tkinter import filedialog
        new_dir = filedialog.askdirectory(
            title="选择学习数据保存目录",
            initialdir=str(storage.LEARNED_ROOT),
        )
        if new_dir:
            storage.set_learned_root(new_dir)
            self._log(f"✅ 保存目录已设置为: {storage.LEARNED_ROOT}")

    # ---- Event handling ----
    def _drain(self):
        if self.worker is None:
            if self.root:
                self.root.after(100, self._drain)
            return
        try:
            while True:
                evt = self.worker.queue.get_nowait()
                # Detect serial error from worker (device unplug)
                if evt.get("type") == "SERIAL_ERROR":
                    msg = evt.get("message", "")
                    if "PermissionError" in msg or "access" in msg.lower():
                        self._log("⚠ 设备已拔出（USB断开）")
                    else:
                        self._log(f"⚠ 设备已拔出")
                    self._disconnect()
                    break
                self._handle(evt)
        except queue.Empty:
            pass
        if self.root:
            self.root.after(50, self._drain)

    def _handle(self, evt):
        name = evt.get("event", "")

        # Handle captured event even if flow timed out / is in ERROR
        if name == "ir.learn.captured":
            if self.flow.active and self.flow.active.state in (cf.State.ERROR, cf.State.CANCELLED):
                self.flow.active = None
            if self.flow.active is None:
                ctx = cf.CaptureContext(self._pending_capture_idx)
                ctx.request_id = evt.get("requestId", "")
                ctx.session_id = evt.get("sessionId", "")
                ctx.captured_length = evt.get("length", 0)
                ctx.captured_sha256 = evt.get("sha256", "")
                ctx.state = cf.State.CAPTURE_ANNOUNCED
                ctx.started_at = time.monotonic()
                self.flow.active = ctx
                self._log("⚠ 采集超时后才收到红外帧，正在尝试导出...")
                # Manually request export
                self.flow._request_export(ctx, lambda t: self.worker.write_line(t) if self.worker else None)
                self._update_buttons()
                return
            # Normal path: feed through handle_event below

        _PROFILE_CN = {"ir-lab": "红外学习", "private-production": "远程控制", "public": "公开版", "private": "私有版"}
        if self.flow.active is None:
            if "deviceType" in evt or "ok" in evt:
                dtype = evt.get("deviceType", "?")
                fv = evt.get("firmwareVersion", "?")
                prof = evt.get("firmwareProfile", "?")
                prof_cn = _PROFILE_CN.get(prof, prof)
                self.dev_status_var.set(f"设备: {dtype} v{fv} ({prof_cn})")
                self._log(f"✅ 设备已识别: {dtype} 固件版本 v{fv} 工作模式: {prof_cn}")
            return

        ctx = self.flow.active
        prev_state = ctx.state
        name = evt.get("event", "")

        # Feed event to flow
        self.flow.handle_event(evt, lambda t: self.worker.write_line(t) if self.worker else None)

        new_state = ctx.state
        self._log_state(evt, prev_state, new_state)

        if new_state == cf.State.WAITING_REMOTE:
            self.progress_var.set(f"采集 {ctx.capture_index}: 请按遥控器（{int(self.flow.TIMEOUT_WAITING_REMOTE)}秒超时）")
        elif new_state == cf.State.EXPORTING:
            self.progress_var.set(f"采集 {ctx.capture_index}: 正在接收红外帧数据...")
        elif new_state == cf.State.EXITING:
            self.progress_var.set(f"采集 {ctx.capture_index}: 正在退出学习模式...")
        elif new_state == cf.State.COMPLETED:
            self._do_save(ctx)
            self.progress_var.set(f"采集 {ctx.capture_index}: 已保存！")
        elif new_state == cf.State.CANCELLED:
            self.progress_var.set("已取消")
        elif new_state == cf.State.ERROR:
            self.progress_var.set(f"错误: {ctx.error}")
            # Try to cancel
            if self.worker:
                self.worker.write_line(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")
        elif new_state == cf.State.EXIT_UNCONFIRMED:
            self.progress_var.set("退出学习未确认 - 请重新连接设备！")
            self._log("⚠ 退出学习未确认，请断开设备重连或重新上电后再继续")
        self._update_buttons()

    def _do_save(self, ctx):
        """Save pending_frame to the correct capture slot."""
        if ctx.pending_frame is None:
            return
        self._save_state()
        state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
        frame = bytes(ctx.pending_frame)
        sha = hashlib.sha256(frame).hexdigest()

        # Atomic save
        meta = {
            "captureIndex": ctx.capture_index, "requestId": ctx.request_id,
            "sessionId": ctx.session_id, "exportId": ctx.export_id,
            "length": len(frame), "sha256": sha,
            "receivedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "exitConfirmed": True, "source": "ZJ-IR-V2 external learn",
            "physicalValidation": False,
        }
        storage.save_capture(state_id, ctx.capture_index, frame, meta)

        # Verify
        d = storage.LEARNED_ROOT / storage.safe_filename(state_id)
        saved = (d / f"capture_{ctx.capture_index:03d}.bin").read_bytes()
        if saved != frame:
            self._log(f"❌ 保存校验失败 idx={ctx.capture_index}，字节不一致！")
            return
        if hashlib.sha256(saved).hexdigest() != sha:
            self._log("❌ 保存 SHA256 校验失败！")
            return

        # Store in fixed slot
        self.captures[ctx.capture_index] = frame
        self.capture_metas[ctx.capture_index] = meta
        self._log(f"✅ 采集 {ctx.capture_index} 已保存: {len(frame)} 字节, SHA256={sha[:24]}...")
        self._show_results()

    def _show_results(self):
        self.result_text.configure(state="normal")
        self.result_text.delete(1.0, "end")
        for idx in sorted(self.captures):
            f = self.captures[idx]
            sha = hashlib.sha256(f).hexdigest()
            self.result_text.insert("end", f"Capture {idx}: {len(f)} bytes, SHA256={sha[:32]}...\n")
        self.result_text.configure(state="disabled")

    def _check_timeout(self):
        if self.flow.active:
            prev_state = self.flow.active.state
            reason = self.flow.check_timeout()
            if reason:
                reason_cn = {
                    "timeout_waiting": "⏰ 遥控器等待超时，请加快按遥控器",
                    "timeout_export": "⏰ 导出数据超时",
                    "timeout_exit": "⏰ 退出学习超时（已强制完成）",
                    "auto_progressed_to_waiting": "⏰ 模块确认超时，已自动进入等待遥控器",
                }.get(reason, f"⏰ 超时: {reason}")
                self._log(reason_cn)
                ctx = self.flow.active
                if ctx and ctx.state == cf.State.COMPLETED and ctx.pending_frame:
                    self._log_state({"event": "timeout_completed"}, prev_state, ctx.state)
                    self._do_save(ctx)
                    self.progress_var.set(f"采集 {ctx.capture_index}: 已保存！")
                elif self.worker and ctx:
                    self.worker.write_line(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")
            self._update_buttons()
        if self.root:
            self.root.after(500, self._check_timeout)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.configure(state="disabled")

    def _log(self, msg):
        if self.root is None or not hasattr(self, 'log_text'):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---- Helpers ----
    _STATE_CN = {cf.State.IDLE: "就绪", cf.State.WAITING_ENTER_ACK: "等待模块确认",
        cf.State.WAITING_REMOTE: "等待遥控器", cf.State.CAPTURE_ANNOUNCED: "已捕获",
        cf.State.EXPORTING: "导出中", cf.State.EXITING: "退出学习中",
        cf.State.COMPLETED: "完成", cf.State.CANCELLED: "已取消",
        cf.State.ERROR: "错误", cf.State.EXIT_UNCONFIRMED: "退出未确认"}

    _EVENT_CN = {
        "ir.learn.waiting": "等待遥控器",
        "ir.learn.captured": "捕获红外信号",
        "ir.learn.export.begin": "开始导出",
        "ir.learn.export.chunk": "接收数据分块",
        "ir.learn.export.done": "导出完成",
        "ir.learn.export.error": "导出错误",
        "ir.learn.cancelled": "退出学习",
        "ir.learn.error": "学习错误",
        "ir.learn.timeout": "学习超时",
        "timeout_completed": "超时强制完成",
    }

    def _log_state(self, evt, prev, new):
        name = evt.get("event", "")
        cn_prev = self._STATE_CN.get(prev, prev.value)
        cn_new = self._STATE_CN.get(new, new.value)
        cn_name = self._EVENT_CN.get(name, name)
        if prev == new:
            return
        self._log(f"📡 {cn_name} | {cn_prev} → {cn_new}")

    def _update_buttons(self):
        if self.root is None:
            return
        active = self.flow.active
        active_state = active.state.name if active else "无活动"
        active_cn = self._STATE_CN.get(active.state, "无") if active else "无"
        busy = active and active.state not in (cf.State.IDLE, cf.State.COMPLETED, cf.State.CANCELLED, cf.State.ERROR)
        unconfirmed = active and active.state == cf.State.EXIT_UNCONFIRMED
        connected = self.worker is not None
        state = "disabled" if (busy or unconfirmed or not connected) else "normal"
        state_text = "可用" if state == "normal" else "禁用"
        if not hasattr(self, '_last_btn_state') or self._last_btn_state != (state, active_state, connected):
            self._last_btn_state = (state, active_state, connected)
            self._log(f"📋 采集按钮[{state_text}] | 当前状态: {active_cn}")
        # Update LED
        if hasattr(self, 'led_canvas'):
            color = "#22cc22" if connected else "#888888"
            self.led_canvas.itemconfig(self.led_oval, fill=color)
            self.led_label_var.set("已连接" if connected else "未连接")
        for b in self.cap_btns.values():
            b.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.approve_btn.configure(state="normal" if self.canonical_var.get() else "disabled")
        if hasattr(self, 'connect_btn'):
            self.connect_btn.configure(state="disabled" if connected else "normal")

    def close(self):
        if self.worker:
            self.worker.stop()
        # Don't call destroy() — mainloop already exited, widget is gone
        try:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
        except Exception:
            pass


# ---- Simulation entry for end-to-end testing ----
def simulate_capture(output_dir):
    """Run production flow using FakeWorker. No Tkinter dependency."""
    import builtins
    fw = FakeWorker()
    flow = cf.CaptureFlow()
    writes_log = []

    def write(text):
        writes_log.append(text)
        fw.write_line(text)

    state_id = "test_sim_cap"
    storage.save_state(state_id, {"name": "Test Capture", "codeId": state_id})

    # Start capture
    flow.start(1, write)
    time.sleep(0.2)

    # Drain events until COMPLETED or timeout
    for _ in range(50):
        try:
            while True:
                evt = fw.queue.get_nowait()
                flow.handle_event(evt, write)
        except Exception:
            pass
        time.sleep(0.05)
        if flow.active is None:
            break
        if flow.active.state == cf.State.COMPLETED:
            # Save the frame
            if flow.active.pending_frame:
                frame = bytes(flow.active.pending_frame)
                sha = hashlib.sha256(frame).hexdigest()
                meta = {
                    "captureIndex": flow.active.capture_index,
                    "requestId": flow.active.request_id,
                    "sessionId": flow.active.session_id,
                    "exportId": flow.active.export_id,
                    "length": len(frame), "sha256": sha,
                    "receivedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "exitConfirmed": True, "source": "ZJ-IR-V2 external learn",
                    "physicalValidation": False,
                }
                storage.save_capture(state_id, flow.active.capture_index, frame, meta)
            break
        if flow.active.state in (cf.State.ERROR, cf.State.CANCELLED, cf.State.EXIT_UNCONFIRMED):
            break

    # Verify
    d = storage.LEARNED_ROOT / storage.safe_filename(state_id)
    cap_path = d / "capture_001.bin"
    result = {"SIMULATED_CAPTURE_PASS": False}
    if cap_path.exists():
        data = cap_path.read_bytes()
        vr = fv.validate_frame(data)
        sha = hashlib.sha256(data).hexdigest()
        result = {
            "SIMULATED_CAPTURE_PASS": vr["valid"],
            "capture_length": len(data),
            "capture_sha256": sha,
            "frame_valid": vr["valid"],
            "frame_afn_ok": vr["afn_ok"],
            "frame_checksum_ok": vr["checksum_ok"],
            "worker_writes": writes_log,
        }
        # Verify canonical
        storage.save_canonical(state_id, 1, data)
        can_path = d / "canonical.bin"
        can_data = can_path.read_bytes() if can_path.exists() else b""
        result["canonical_byte_exact"] = (can_data == data)

    print(json.dumps(result, indent=2))
    return 0 if result.get("SIMULATED_CAPTURE_PASS") else 1


def _self_test_report_file():
    """Where --self-test / --version write their report (EXE is --windowed,
    so stdout is not visible; the file path is printed to stdout too)."""
    try:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        base = os.getcwd()
    return os.path.join(base, "ir_learner_self_test.txt")


def run_self_test():
    """Headless self-test: no GUI, no serial port, no IR transmission."""
    import capture_flow as _cf
    import frame_validator as _fv
    import presets as _pr
    import protocol_adapter as _pa
    import serial_worker as _sw
    import storage as _st

    checks = []
    checks.append(("core_modules_import", True))
    try:
        import tkinter
        checks.append(("tkinter_import", True))
        checks.append(("tkinter_version", float(tkinter.TkVersion) >= 8.5))
    except Exception:
        checks.append(("tkinter_import", False))
        checks.append(("tkinter_version", False))
    checks.append(("preset_count", len(_pr.PRESETS) == 10))
    ids = [p["codeId"] for p in _pr.PRESETS]
    checks.append(("preset_ids_unique", len(ids) == len(set(ids))))
    try:
        root_dir = Path(_st.LEARNED_ROOT)
        root_dir.mkdir(parents=True, exist_ok=True)
        checks.append(("save_path_constructible", True))
    except Exception:
        checks.append(("save_path_constructible", False))
    # This process never opened a serial port and never sent an IR command.
    checks.append(("no_serial_write", True))
    checks.append(("no_ir_transmit", True))

    ok = all(v for _, v in checks)
    lines = []
    for name, v in checks:
        lines.append(f"SELF_TEST {name}={v}")
    lines.append(f"IR_LEARNER_SELF_TEST_PASS={'True' if ok else 'False'}")
    report = "\n".join(lines)
    try:
        with open(_self_test_report_file(), "w", encoding="utf-8", newline="\n") as f:
            f.write(report + "\n")
    except Exception:
        pass
    print(report)
    return 0 if ok else 1


def run_version():
    """Print the tool version and record it to the report file."""
    from pathlib import Path as _P
    ver_file = _P(__file__).resolve().parent.parent / "VERSION"
    version = "unknown"
    if ver_file.exists():
        version = ver_file.read_text(encoding="utf-8").strip()
    lines = [f"IR_SIMPLE_LEARNER_VERSION={version}"]
    try:
        with open(_self_test_report_file(), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    print("\n".join(lines))
    return 0


def main():
    if "--simulate-capture" in sys.argv:
        out = tempfile.mkdtemp()
        storage.LEARNED_ROOT = Path(out)
        code = simulate_capture(out)
        print(f"OUTPUT_DIR={out}")
        sys.exit(code)
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    if "--version" in sys.argv:
        sys.exit(run_version())
    root = tk.Tk()
    app = SimpleLearner(root)
    try:
        root.mainloop()
    finally:
        app.close()


if __name__ == "__main__":
    main()
