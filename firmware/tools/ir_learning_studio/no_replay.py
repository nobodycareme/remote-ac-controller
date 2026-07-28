#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instrumented write recorder for No-Replay enforcement.

Every PC-side serial write is recorded through this module.
The recorder computes real aggregate counters from its own log,
never from hardcoded constants.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RecordedWrite:
    timestamp: str
    monotonic_ns: int
    thread_id: int
    command_sequence: int
    command_name: str
    payload_length: int
    payload_sha256: str
    classification: str
    request_id: str = ""
    session_id: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class NoReplayRecorder:
    """Thread-safe write recorder for No-Replay proof generation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sequence: int = 0
        self._writes: List[RecordedWrite] = []

        # Classification counts (computed on demand, never hardcoded)
        self._counts: Dict[str, int] = {
            "DEVICE_STATUS": 0,
            "LEARN_BEGIN_20H": 0,
            "LEARN_EXIT_21H": 0,
            "LEARN_STATUS": 0,
            "LEARN_EXPORT_REQUEST": 0,
            "UNKNOWN": 0,
            "RAW_22H_FRAME": 0,
            "REPLAY_COMMAND": 0,
            "TRANSMIT_COMMAND": 0,
        }

    def record(
        self,
        command_name: str,
        classification: str,
        payload: bytes = b"",
        request_id: str = "",
        session_id: str = "",
    ) -> RecordedWrite:
        """Record a serial write with full metadata."""
        with self._lock:
            self._sequence += 1
            rw = RecordedWrite(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                monotonic_ns=time.monotonic_ns(),
                thread_id=threading.get_ident(),
                command_sequence=self._sequence,
                command_name=command_name,
                payload_length=len(payload),
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                classification=classification,
                request_id=request_id,
                session_id=session_id,
            )
            self._writes.append(rw)

            if classification in self._counts:
                self._counts[classification] += 1
            # Cross-classify 20H and 21H
            if classification == "LEARN_BEGIN":
                self._counts["LEARN_BEGIN_20H"] += 1
            if classification == "LEARN_CANCEL":
                self._counts["LEARN_EXIT_21H"] += 1
            if classification == "LEARN_EXPORT":
                self._counts["LEARN_EXPORT_REQUEST"] += 1

            return rw

    def get_counts(self) -> Dict[str, int]:
        """Get current classification counts (thread-safe snapshot)."""
        with self._lock:
            return dict(self._counts)

    def compute_results(self) -> Dict:
        """Compute No-Replay results from recorded data.

        NEVER hardcodes any count — all values come from actual records.
        """
        with self._lock:
            counts = dict(self._counts)

        return {
            "TOTAL_SERIAL_WRITE_COUNT": len(self._writes),
            "DEVICE_STATUS_WRITE_COUNT": counts.get("DEVICE_STATUS", 0),
            "LEARN_BEGIN_WRITE_COUNT": counts.get("LEARN_BEGIN_20H", 0),
            "LEARN_EXIT_WRITE_COUNT": counts.get("LEARN_EXIT_21H", 0),
            "LEARN_STATUS_WRITE_COUNT": counts.get("LEARN_STATUS", 0),
            "LEARN_EXPORT_REQUEST_WRITE_COUNT": counts.get("LEARN_EXPORT_REQUEST", 0),
            "RAW_22H_FRAME_WRITE_COUNT": counts.get("RAW_22H_FRAME", 0),
            "REPLAY_COMMAND_WRITE_COUNT": counts.get("REPLAY_COMMAND", 0),
            "TRANSMIT_COMMAND_WRITE_COUNT": counts.get("TRANSMIT_COMMAND", 0),
            "UNKNOWN_WRITE_COUNT": counts.get("UNKNOWN", 0),
            # Derived verdict
            "NO_REPLAY_PASS": (
                counts.get("RAW_22H_FRAME", 0) == 0
                and counts.get("REPLAY_COMMAND", 0) == 0
                and counts.get("TRANSMIT_COMMAND", 0) == 0
            ),
        }

    def write_results(self, output_path: Path) -> Dict:
        """Write results JSON and return the computed results."""
        results = self.compute_results()
        results["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        results["write_count"] = len(self._writes)

        with self._lock:
            results["write_log"] = [w.to_dict() for w in self._writes]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return results

    def reset(self) -> None:
        """Reset all counters (for test isolation)."""
        with self._lock:
            self._sequence = 0
            self._writes.clear()
            for k in self._counts:
                self._counts[k] = 0


# Global singleton for the test recorder
_GLOBAL_RECORDER: Optional[NoReplayRecorder] = None


def get_recorder() -> NoReplayRecorder:
    global _GLOBAL_RECORDER
    if _GLOBAL_RECORDER is None:
        _GLOBAL_RECORDER = NoReplayRecorder()
    return _GLOBAL_RECORDER


def reset_recorder() -> None:
    global _GLOBAL_RECORDER
    _GLOBAL_RECORDER = NoReplayRecorder()
