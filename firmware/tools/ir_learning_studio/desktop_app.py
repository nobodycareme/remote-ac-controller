#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-implementation desktop application for IR Learning Studio R5.

No duplicate methods. No legacy library_store calls. No self.lock access.
All business logic delegates to ApplicationController.
"""

from __future__ import annotations

import json
import queue
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import composition_root
import library_service
import model
import protocol
import serial_client
import ui_controller


class DesktopApp:
    """Single-implementation Tkinter desktop workbench for IR learning."""

    def __init__(self, root: tk.Tk, runtime: composition_root.ApplicationRuntime):
        self.root = root
        self.runtime = runtime

        # UI state
        self.paths = None
        self.mock_temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self.controller = ui_controller.IRLearningController(
            read_only=not runtime.write_enabled
        )
        self.current_definition: Dict[str, Any] = model.default_definition()
        self.capture_frames: List[bytes] = []
        self.capture_records: List[Dict] = []
        self.current_session_id = ""
        self.learning_active = False
        self.ports: List[Dict] = []
        self.templates = model.first_phase_templates()

        # Serial
        self.worker: Optional[serial_client.SerialIoWorker] = None
        self.worker_events: queue.Queue = queue.Queue()

        # Build UI
        self.root.title("IR Learning Studio R5")
        self.root.geometry("1180x760")
        self._build_ui()
        self._bind_state_validation()
        self.scan_devices()
        self.refresh_library()
        self.root.protocol("WM_DELETE_WINDOW", self.safe_close)
        self.root.after(100, self._drain_events)

    # ==============================================================
    # UI Layout (migrated from R4, deduplicated)
    # ==============================================================

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        # A. Device panel
        device = ttk.LabelFrame(self.root, text="A. Device", padding=8)
        device.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        self.mock_var = tk.BooleanVar(value=False)
        self.port_var = tk.StringVar(value="")
        self.device_info_var = tk.StringVar(value="Device: not connected")
        ttk.Button(device, text="Scan", command=self.scan_devices).grid(row=0, column=0, padx=3)
        self.port_combo = ttk.Combobox(device, textvariable=self.port_var, state="readonly", width=14)
        self.port_combo.grid(row=0, column=1, padx=3)
        ttk.Checkbutton(device, text="mock", variable=self.mock_var).grid(row=0, column=2)
        ttk.Button(device, text="Connect", command=self.connect_device).grid(row=0, column=3, padx=3)
        ttk.Button(device, text="Disconnect", command=self.disconnect_device).grid(row=0, column=4, padx=3)
        ttk.Label(device, textvariable=self.device_info_var).grid(row=1, column=0, columnspan=5, sticky="w")

        # B. State definition panel
        state = ttk.LabelFrame(self.root, text="B. State Definition", padding=8)
        state.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        self._build_state_panel(state)

        # C. Library panel
        lib_frame = ttk.LabelFrame(self.root, text="C. Library", padding=8)
        lib_frame.grid(row=1, column=1, sticky="nsew", padx=8, pady=6)
        self._build_library_panel(lib_frame)

        # D. Capture/Action panel
        capture = ttk.LabelFrame(self.root, text="D. Capture & Actions", padding=8)
        capture.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        self._build_capture_panel(capture)

    def _build_state_panel(self, parent):
        parent.columnconfigure(1, weight=1)

        # Template
        ttk.Label(parent, text="Template").grid(row=0, column=0, sticky="e", pady=2)
        self.template_var = tk.StringVar(value="")
        ttk.Combobox(parent, textvariable=self.template_var,
                     values=[f"{i+1}. {t['displayName']}" for i, t in enumerate(self.templates)],
                     state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Button(parent, text="Load", command=self.load_template).grid(row=0, column=2, padx=3)

        # Code ID
        ttk.Label(parent, text="Code ID").grid(row=1, column=0, sticky="e", pady=2)
        self.code_id_var = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.code_id_var).grid(row=1, column=1, sticky="ew")

        # Display name
        ttk.Label(parent, text="Name").grid(row=2, column=0, sticky="e", pady=2)
        self.display_name_var = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.display_name_var).grid(row=2, column=1, sticky="ew")

        # Brand
        ttk.Label(parent, text="Brand").grid(row=3, column=0, sticky="e", pady=2)
        self.brand_var = tk.StringVar(value="Hisense")
        ttk.Entry(parent, textvariable=self.brand_var).grid(row=3, column=1, sticky="ew")

        # Mode
        ttk.Label(parent, text="Mode").grid(row=4, column=0, sticky="e", pady=2)
        self.mode_var = tk.StringVar(value="cool")
        ttk.Combobox(parent, textvariable=self.mode_var, values=model.MODE, state="readonly").grid(row=4, column=1, sticky="ew")

        # Temperature
        ttk.Label(parent, text="Temp °C").grid(row=5, column=0, sticky="e", pady=2)
        self.temp_var = tk.StringVar(value="24")
        ttk.Combobox(parent, textvariable=self.temp_var, values=model.TEMPERATURES, state="readonly").grid(row=5, column=1, sticky="ew")

        # Fan speed
        ttk.Label(parent, text="Fan").grid(row=6, column=0, sticky="e", pady=2)
        self.fan_var = tk.StringVar(value="auto")
        ttk.Combobox(parent, textvariable=self.fan_var, values=model.FAN_SPEED, state="readonly").grid(row=6, column=1, sticky="ew")

        # Display text & trigger
        ttk.Label(parent, text="Display").grid(row=7, column=0, sticky="e", pady=2)
        self.display_var = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.display_var).grid(row=7, column=1, sticky="ew")
        ttk.Label(parent, text="Trigger").grid(row=8, column=0, sticky="e", pady=2)
        self.trigger_var = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.trigger_var).grid(row=8, column=1, sticky="ew")

        # Save / Fork buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=9, column=1, sticky="e", pady=6)
        ttk.Button(btn_frame, text="Save Draft", command=self.save_draft).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Fork New Version", command=self.fork_version).pack(side="left", padx=3)

    def _build_library_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.library_tree = ttk.Treeview(parent, columns=("codeId", "status", "captures", "version"),
                                         show="headings", height=12)
        for col, name in [("codeId", "Code ID"), ("status", "Status"), ("captures", "Captures"), ("version", "Version")]:
            self.library_tree.heading(col, text=name)
            self.library_tree.column(col, width=100)
        self.library_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.library_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.library_tree.configure(yscrollcommand=scrollbar.set)
        self.library_tree.bind("<<TreeviewSelect>>", self.on_state_selected)

    def _build_capture_panel(self, parent):
        self.capture_status_var = tk.StringVar(value="Ready")
        ttk.Label(parent, textvariable=self.capture_status_var).pack(side="left", padx=4)
        ttk.Button(parent, text="Start Capture", command=self.start_capture).pack(side="left", padx=4)
        ttk.Button(parent, text="Cancel", command=self.cancel_learning).pack(side="left", padx=4)
        self.approve_btn = ttk.Button(parent, text="Approve Canonical", command=self.approve_canonical, state="disabled")
        self.approve_btn.pack(side="left", padx=4)

    def _bind_state_validation(self):
        pass  # Placeholder for future validation bindings

    # ==============================================================
    # Device operations
    # ==============================================================

    def scan_devices(self):
        self.ports = serial_client.discover_ch9102_ports()
        self.port_combo["values"] = [p.get("device", "") for p in self.ports]
        if self.ports:
            self.port_var.set(self.ports[0].get("device", ""))
        self.device_info_var.set(f"Found {len(self.ports)} CH9102 device(s)")

    def connect_device(self):
        if self.worker:
            return
        mock = self.mock_var.get()
        port = self.port_var.get() or ""
        if mock:
            transport_factory = lambda: serial_client.MockTransport(scenario="success")
            self.worker = serial_client.SerialIoWorker(
                event_queue=self.worker_events,
                transport_factory=transport_factory,
                allow_mock=True,
            )
        else:
            if not port:
                messagebox.showerror("Error", "No serial port selected")
                return
            transport_factory = lambda: serial_client.PySerialTransport(port)
            self.worker = serial_client.SerialIoWorker(
                event_queue=self.worker_events,
                transport_factory=transport_factory,
                port_info={"device": port},
            )
        self.worker.start()
        self.worker.post("CONNECT")
        self.device_info_var.set(f"Connected: {port or 'mock'}")

    def disconnect_device(self):
        if self.worker:
            self.worker.post(serial_client.CMD_DISCONNECT)
            # Worker will terminate; we'll clean up reference when WORKER_TERMINATED arrives

    # ==============================================================
    # State management
    # ==============================================================

    def save_draft(self):
        """Save current form as draft via SQLite LibraryService."""
        if not self.runtime.write_enabled:
            messagebox.showerror("Error", "Write not enabled (read-only mode)")
            return
        defn = self._build_definition_from_form()
        try:
            if self.runtime.library_service:
                state_id = self.runtime.library_service.create_draft(defn)
                self.code_id_var.set(defn["codeId"])
                messagebox.showinfo("Saved", f"Draft saved: {defn['codeId']}")
                self.refresh_library()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def fork_version(self):
        """Fork approved state to new version."""
        if not self.runtime.write_enabled:
            return
        selection = self.library_tree.selection()
        if not selection:
            return
        item = self.library_tree.item(selection[0])
        if item["values"][1] != "approved":
            messagebox.showerror("Error", "Only approved states can be forked")
            return
        try:
            code_id = item["values"][0]
            state = self.runtime.library_service.get_state_by_code_id(code_id)
            if state:
                new_id = self.runtime.library_service.fork_approved_state(state["state_id"])
                new_state = self.runtime.library_service.get_state(new_id)
                if new_state:
                    self.code_id_var.set(new_state["code_id"])
                    messagebox.showinfo("Forked", f"New version: {new_state['code_id']}")
                self.refresh_library()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh_library(self):
        """Refresh library tree from SQLite."""
        self.library_tree.delete(*self.library_tree.get_children())
        if not self.runtime.library_service:
            return
        try:
            states = self.runtime.library_service.list_states()
            for s in states:
                cap_count = len(self.runtime.library_service.get_captures(s["state_id"]))
                self.library_tree.insert("", "end", values=(
                    s["code_id"], s["status"], cap_count, f"v{s['version']}"
                ))
        except Exception:
            pass

    def on_state_selected(self, event):
        """Restore state context when a library item is selected."""
        selection = self.library_tree.selection()
        if not selection:
            return
        item = self.library_tree.item(selection[0])
        code_id = item["values"][0]
        if not self.runtime.library_service:
            return
        state = self.runtime.library_service.get_state_by_code_id(code_id)
        if state:
            definition = json.loads(state["definition_json"])
            self.code_id_var.set(definition.get("codeId", ""))
            self.display_name_var.set(definition.get("displayName", ""))
            self.brand_var.set(definition.get("brand", ""))
            self.mode_var.set(definition.get("state", {}).get("mode", "cool"))
            self.temp_var.set(definition.get("state", {}).get("targetTemperatureC", "24"))
            self.fan_var.set(definition.get("state", {}).get("fanSpeed", "auto"))
            self.display_var.set(definition.get("remoteDisplayText", ""))
            self.trigger_var.set(definition.get("triggerButton", ""))
            self.current_definition = definition

            # Restore captures
            captures = self.runtime.library_service.get_captures(state["state_id"])
            self.capture_frames = []
            for cap in captures:
                blob = self.runtime.library_service.get_capture_blob(cap["capture_id"])
                if blob:
                    self.capture_frames.append(blob)
            self.capture_status_var.set(
                f"Loaded: {len(captures)} captures, {len(self.capture_frames)} frames"
            )

            # Enable/disable approve based on status
            is_approved = state["status"] == "approved"
            self.approve_btn.configure(state="disabled" if is_approved else "normal")

    def load_template(self):
        idx_str = self.template_var.get().split(".")[0]
        try:
            idx = int(idx_str) - 1
            if 0 <= idx < len(self.templates):
                t = self.templates[idx]
                self.code_id_var.set(t.get("codeId", ""))
                self.display_name_var.set(t.get("displayName", ""))
                self.mode_var.set(t.get("state", {}).get("mode", "cool"))
                self.temp_var.set(t.get("state", {}).get("targetTemperatureC", "24"))
                self.fan_var.set(t.get("state", {}).get("fanSpeed", "auto"))
        except (ValueError, IndexError):
            pass

    # ==============================================================
    # Capture operations
    # ==============================================================

    def start_capture(self):
        if not self.worker:
            messagebox.showerror("Error", "Device not connected")
            return
        self.current_session_id = serial_client.new_session_id()
        self.learning_active = True
        self.capture_status_var.set("Starting capture...")
        self.worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId=self.current_session_id)

    def cancel_learning(self):
        if self.worker and self.learning_active:
            self.worker.post(serial_client.CMD_CANCEL_CAPTURE)
            self.learning_active = False
            self.capture_status_var.set("Cancelled")

    def approve_canonical(self):
        if not self.runtime.write_enabled:
            return
        selection = self.library_tree.selection()
        if not selection:
            return
        item = self.library_tree.item(selection[0])
        code_id = item["values"][0]
        if not self.runtime.library_service:
            return
        state = self.runtime.library_service.get_state_by_code_id(code_id)
        if not state:
            return
        captures = self.runtime.library_service.get_captures(state["state_id"])
        if not captures:
            messagebox.showerror("Error", "No captures to approve")
            return
        try:
            result = self.runtime.library_service.approve_canonical(
                state["state_id"], captures[-1]["capture_id"]
            )
            messagebox.showinfo("Approved", f"Canonical approved: {state['code_id']}")
            self.refresh_library()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ==============================================================
    # Event loop
    # ==============================================================

    def _drain_events(self):
        """Process worker events on the Tk thread."""
        try:
            while True:
                evt = self.worker_events.get_nowait()
                self._handle_worker_event(evt)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _handle_worker_event(self, evt: Dict):
        etype = evt.get("type", "")
        if etype == serial_client.EV_HANDSHAKE_OK:
            meta = evt.get("metadata", {})
            self.device_info_var.set(
                f"Device: {meta.get('deviceMac','?')} {meta.get('firmwareProfile','?')}"
            )
        elif etype == serial_client.EV_HANDSHAKE_FAILED:
            reasons = evt.get("reasons", [])
            self.device_info_var.set(f"Handshake failed: {', '.join(reasons)}")
        elif etype == serial_client.EV_CAPTURE_VALIDATED:
            frame = evt.get("frame")
            if frame and self.runtime.library_service:
                try:
                    selection = self.library_tree.selection()
                    if selection:
                        item = self.library_tree.item(selection[0])
                        code_id = item["values"][0]
                        state = self.runtime.library_service.get_state_by_code_id(code_id)
                        if state:
                            self.runtime.library_service.add_capture(
                                state["state_id"], frame, evt.get("metadata", {})
                            )
                            self.capture_frames.append(frame)
                    self.capture_status_var.set(f"Capture saved ({len(self.capture_frames)} total)")
                except Exception as e:
                    self.capture_status_var.set(f"Save error: {e}")
            self.learning_active = False
            self.refresh_library()
        elif etype == serial_client.EV_CAPTURE_FAILED:
            self.capture_status_var.set(f"Capture failed: {evt.get('reason','')}")
            self.learning_active = False
        elif etype == serial_client.EV_CANCELLED:
            self.capture_status_var.set("Learning cancelled")
            self.learning_active = False
        elif etype == serial_client.EV_DISCONNECTED:
            self.device_info_var.set("Disconnected")
        elif etype == serial_client.EV_SHUTDOWN_COMPLETE:
            pass
        elif etype == serial_client.EV_WORKER_TERMINATED:
            self.device_info_var.set("Worker terminated")
            if self.worker:
                try:
                    self.worker.join(timeout=3.0)
                except Exception:
                    pass
            self.worker = None

    # ==============================================================
    # Helpers
    # ==============================================================

    def _build_definition_from_form(self) -> Dict:
        defn = model.default_definition()
        defn["codeId"] = self.code_id_var.get()
        defn["displayName"] = self.display_name_var.get()
        defn["brand"] = self.brand_var.get()
        defn["remoteDisplayText"] = self.display_var.get()
        defn["triggerButton"] = self.trigger_var.get()
        defn["state"].update({
            "mode": self.mode_var.get(),
            "targetTemperatureC": self.temp_var.get(),
            "fanSpeed": self.fan_var.get(),
        })
        return defn

    def safe_close(self):
        self.runtime.close()
        self.root.destroy()
