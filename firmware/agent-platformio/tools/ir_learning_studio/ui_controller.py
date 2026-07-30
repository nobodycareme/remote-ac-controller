#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tk-free state controller for IR Learning Studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import serial_client


@dataclass
class CaptureChoice:
    capture_id: str
    label: str
    sha256: str
    length: int


@dataclass
class ControllerState:
    device_connected: bool = False
    device_ready: bool = False
    learning_active: bool = False
    cancelling: bool = False
    disconnecting: bool = False
    read_only: bool = False
    status: str = serial_client.STATE_IDLE
    prompt: str = ""
    handshake_reasons: List[str] = field(default_factory=list)
    capture_choices: List[CaptureChoice] = field(default_factory=list)
    selected_capture_id: str = ""

    @property
    def begin_capture_enabled(self) -> bool:
        return (
            self.device_connected
            and self.device_ready
            and not self.learning_active
            and not self.cancelling
            and not self.disconnecting
            and not self.read_only
        )

    @property
    def cancel_enabled(self) -> bool:
        return self.learning_active and not self.cancelling

    @property
    def disconnect_enabled(self) -> bool:
        return self.device_connected and not self.disconnecting

    @property
    def approve_enabled(self) -> bool:
        return bool(self.selected_capture_id) and not self.read_only and not self.learning_active


class IRLearningController:
    def __init__(self, read_only: bool = False):
        self.state = ControllerState(read_only=read_only)

    def handle_event(self, event: Dict) -> ControllerState:
        etype = event.get("type")
        if etype == serial_client.EV_CONNECTED:
            self.state.device_connected = True
            self.state.status = serial_client.STATE_DEVICE_CONNECTING
        elif etype == serial_client.EV_HANDSHAKE_OK:
            self.state.device_ready = True
            self.state.handshake_reasons = []
            self.state.status = serial_client.STATE_DEVICE_READY
        elif etype == serial_client.EV_HANDSHAKE_FAILED:
            self.state.device_ready = False
            self.state.handshake_reasons = list(event.get("reasons", []))
            self.state.status = "DEVICE_CONNECTED_BUT_UNVERIFIED"
        elif etype in {serial_client.EV_LEARN_ENTERED, serial_client.EV_WAITING_REMOTE}:
            self.state.learning_active = True
            self.state.cancelling = False
            self.state.status = serial_client.STATE_WAITING_FOR_REMOTE
        elif etype == serial_client.EV_CAPTURE_VALIDATED:
            self.state.learning_active = False
            self.state.cancelling = False
            self.state.status = serial_client.STATE_CAPTURE_SAVED
        elif etype == serial_client.EV_CAPTURE_FAILED:
            self.state.learning_active = False
            self.state.cancelling = False
            self.state.status = serial_client.STATE_ERROR
            self.state.prompt = str(event.get("reason", "capture failed"))
        elif etype == serial_client.EV_CANCELLED:
            self.state.learning_active = False
            self.state.cancelling = False
            self.state.status = serial_client.STATE_CANCELLED
        elif etype == serial_client.EV_DISCONNECTED:
            self.state.device_connected = False
            self.state.device_ready = False
            self.state.disconnecting = False
            self.state.learning_active = False
            self.state.status = serial_client.STATE_IDLE
        elif etype == serial_client.EV_ERROR:
            self.state.learning_active = False
            self.state.status = serial_client.STATE_ERROR
            self.state.prompt = str(event.get("message", "worker error"))
        elif etype == serial_client.EV_SHUTDOWN_COMPLETE:
            self.state.device_connected = False
            self.state.device_ready = False
            self.state.learning_active = False
            self.state.status = serial_client.STATE_IDLE
        return self.state

    def begin_capture_requested(self) -> bool:
        if not self.state.begin_capture_enabled:
            return False
        self.state.learning_active = True
        self.state.status = serial_client.STATE_ENTERING_LEARN_MODE
        return True

    def cancel_requested(self) -> bool:
        if not self.state.cancel_enabled:
            return False
        self.state.cancelling = True
        return True

    def disconnect_requested(self) -> bool:
        if not self.state.disconnect_enabled:
            return False
        self.state.disconnecting = True
        return True

    def add_capture_choice(self, capture_id: str, capture_index: int, sha256: str, length: int) -> None:
        label = f"#{capture_index} · {capture_id} · {sha256[:12]}"
        self.state.capture_choices.append(CaptureChoice(capture_id, label, sha256, length))
        self.state.selected_capture_id = capture_id

    def select_capture(self, capture_id: str) -> None:
        if capture_id not in {c.capture_id for c in self.state.capture_choices}:
            raise ValueError(f"unknown capture id: {capture_id}")
        self.state.selected_capture_id = capture_id
