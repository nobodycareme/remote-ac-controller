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

        self._build_ui()
        self._scan_ports()
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
        ttk.Button(dev, text="连接", command=self._connect).pack(side="left", padx=2)
        ttk.Button(dev, text="断开", command=self._disconnect).pack(side="left", padx=2)
        self.dev_status_var = tk.StringVar(value="未连接")
        ttk.Label(dev, textvariable=self.dev_status_var).pack(side="left", padx=10)

        state_frame = ttk.LabelFrame(self.root, text="空调状态", padding=5)
        state_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=3)
        self._build_state_panel(state_frame)

        right = ttk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=5, pady=3)
        self._build_capture_panel(right)

        logf = ttk.LabelFrame(self.root, text="日志", padding=3)
        logf.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        self.log_text = tk.Text(logf, height=6, state="disabled")
        self.log_text.pack(fill="both", expand=True)

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
        for label, vname, vals in [("电源", "power_var", ["on","off"]),
            ("模式", "mode_var", ["cool","heat","dry","fan","auto"]),
            ("温度°C", "temp_var", ["16","17","18","19","20","21","22","23","24","25","26","27","28","29","30","N/A"]),
            ("风速", "fan_var", ["auto","silent","low","medium","high","turbo"])]:
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="e", pady=1); r += 1
            v = tk.StringVar(); setattr(self, vname, v)
            ttk.Combobox(parent, textvariable=v, values=vals, state="readonly", width=12).grid(row=r-1, column=1, sticky="w", pady=1)
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
        port = self.port_var.get()
        if not port:
            return
        self.worker = sw.SerialWorker()
        self.worker.start(port, 115200)
        time.sleep(0.3)
        if self.worker.ser is None or not self.worker.ser.is_open:
            self._log(f"Failed to open {port} — port may be in use by another program")
            self.dev_status_var.set(f"{port} open failed")
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
            self.dev_status_var.set("Disconnected")
        self._update_buttons()

    # ---- Preset ----
    def _on_preset(self, event=None):
        try:
            idx = int(self.preset_var.get().split(".")[0]) - 1
            if 0 <= idx < len(self.preset_list):
                p = self.preset_list[idx]
                self.name_var.set(p["name"]); self.code_id_var.set(p.get("codeId",""))
                self.power_var.set(p.get("power","on")); self.mode_var.set(p.get("mode","cool"))
                self.temp_var.set(p.get("temp","24")); self.fan_var.set(p.get("fan","auto"))
                self.turbo_var.set(p.get("turbo",False)); self.quiet_var.set(p.get("quiet",False))
                self.sleep_var.set(p.get("sleep",False))
                self.swing_v_var.set(p.get("swingV","unknown")=="on"); self.swing_h_var.set(p.get("swingH","unknown")=="on")
        except (ValueError, IndexError):
            pass

    # ---- Capture ----
    def _start_capture(self, index):
        if not self.worker or not self.worker.is_alive():
            self._log("Device not connected"); return
        active = self.flow.active
        if active and active.state == cf.State.EXIT_UNCONFIRMED:
            self._log("Exit unconfirmed — reconnect device to continue"); return
        ctx, status = self.flow.start(index, lambda t: self.worker.write_line(t))
        if status != "started":
            self._log(f"Cannot start: {status}"); return
        self._log(f"Capture {index}: started (WAITING_ENTER_ACK)")
        self.progress_var.set(f"Capture {index}: waiting for device ACK...")
        self._update_buttons()

    def _cancel(self):
        self.flow.cancel(lambda t: self.worker.write_line(t) if self.worker else None)
        self._log("Cancelled"); self.progress_var.set("Cancelled")
        self._update_buttons()

    def _approve(self):
        try:
            idx = int(self.canonical_var.get())
            if idx in self.captures:
                state_id = self.code_id_var.get() or f"ac_state_{int(time.time())}"
                frame = self.captures[idx]
                p = storage.save_canonical(state_id, idx, frame)
                self._log(f"Canonical saved: capture_{idx:03d}.bin -> canonical.bin")
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
            self._log(f"Capture {idx}: {len(a)} bytes, SHA256={sha[:16]}...")
        keys = sorted(self.captures)
        diffs = []
        for i in range(len(keys)-1):
            d = fv.diff_frames(self.captures[keys[i]], self.captures[keys[i+1]])
            diffs.append(d)
            self._log(f"  {keys[i]} vs {keys[i+1]}: {d['diff_count']} byte diffs")
        all_same = all(d["same_content"] for d in diffs)
        self._log(f"All same: {all_same}")
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

    # ---- Event handling ----
    def _drain(self):
        if self.worker is None:
            if self.root:
                self.root.after(100, self._drain)
            return
        try:
            while True:
                evt = self.worker.queue.get_nowait()
                self._handle(evt)
        except queue.Empty:
            pass
        if self.root:
            self.root.after(50, self._drain)

    def _handle(self, evt):
        if self.flow.active is None:
            if "deviceType" in evt or "ok" in evt:
                self.dev_status_var.set(f"Device: {evt.get('deviceType','ESP8266')} OK")
            return

        ctx = self.flow.active
        prev_state = ctx.state
        name = evt.get("event", "")

        # Feed event to flow
        self.flow.handle_event(evt, lambda t: self.worker.write_line(t) if self.worker else None)

        new_state = ctx.state
        self._log(f"[{name}] {prev_state.value} -> {new_state.value}")

        if new_state == cf.State.WAITING_REMOTE:
            self.progress_var.set(f"Capture {ctx.capture_index}: please press remote ({int(self.flow.TIMEOUT_WAITING_REMOTE)}s timeout)")
        elif new_state == cf.State.EXPORTING:
            self.progress_var.set(f"Capture {ctx.capture_index}: receiving frame data...")
        elif new_state == cf.State.EXITING:
            self.progress_var.set(f"Capture {ctx.capture_index}: exiting learn mode...")
        elif new_state == cf.State.COMPLETED:
            self._do_save(ctx)
            self.progress_var.set(f"Capture {ctx.capture_index}: saved!")
        elif new_state == cf.State.CANCELLED:
            self.progress_var.set("Cancelled")
        elif new_state == cf.State.ERROR:
            self.progress_var.set(f"Error: {ctx.error}")
            # Try to cancel
            if self.worker:
                self.worker.write_line(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")
        elif new_state == cf.State.EXIT_UNCONFIRMED:
            self.progress_var.set("Exit NOT confirmed — reconnect device!")
            self._log("EXIT_UNCONFIRMED: reconnect/repower device before next capture")
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
            self._log(f"SAVE VERIFICATION FAILED for idx={ctx.capture_index}")
            return
        if hashlib.sha256(saved).hexdigest() != sha:
            self._log("SAVE SHA MISMATCH")
            return

        # Store in fixed slot
        self.captures[ctx.capture_index] = frame
        self.capture_metas[ctx.capture_index] = meta
        self._log(f"Capture {ctx.capture_index} saved: {len(frame)} bytes, SHA256={sha[:16]}...")
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
            reason = self.flow.check_timeout()
            if reason:
                self._log(f"Timeout: {reason}")
                if self.worker:
                    ctx = self.flow.active
                    if ctx:
                        self.worker.write_line(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")
            self._update_buttons()
        if self.root:
            self.root.after(500, self._check_timeout)

    # ---- Helpers ----
    def _log(self, msg):
        if self.root is None:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_buttons(self):
        if self.root is None:
            return
        active = self.flow.active
        busy = active and active.state not in (cf.State.IDLE, cf.State.COMPLETED, cf.State.CANCELLED, cf.State.ERROR)
        unconfirmed = active and active.state == cf.State.EXIT_UNCONFIRMED
        connected = self.worker is not None
        state = "disabled" if (busy or unconfirmed or not connected) else "normal"
        for b in self.cap_btns.values():
            b.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.approve_btn.configure(state="normal" if self.canonical_var.get() else "disabled")

    def close(self):
        if self.flow.active and self.flow.active.state not in (cf.State.IDLE, cf.State.COMPLETED):
            self.flow.cancel(lambda t: self.worker.write_line(t) if self.worker else None)
        if self.worker:
            self.worker.stop()
        if self.root:
            self.root.destroy()


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


def main():
    if "--simulate-capture" in sys.argv:
        out = tempfile.mkdtemp()
        storage.LEARNED_ROOT = Path(out)
        code = simulate_capture(out)
        print(f"OUTPUT_DIR={out}")
        sys.exit(code)
    if "--self-test" in sys.argv:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
            str(ROOT / "tests"), "-p", "test_*.py", "-v"])
        sys.exit(r.returncode)
    root = tk.Tk()
    app = SimpleLearner(root)
    try:
        root.mainloop()
    finally:
        app.close()


if __name__ == "__main__":
    main()
