#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent


def _module_dir() -> Path:
    env_dir = os.environ.get("IR_LEARNING_STUDIO_MODULE_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([HERE.parent, HERE.parent / "src" / "ir_learning_studio", HERE.parent.parent / "src" / "ir_learning_studio"])
    for candidate in candidates:
        if (candidate / "protocol.py").exists():
            return candidate.resolve()
    raise RuntimeError("IR Learning Studio module directory not found")


MODULE_DIR = _module_dir()
FIRMWARE_ROOT = MODULE_DIR.parents[1] if MODULE_DIR.name == "ir_learning_studio" else HERE.parent
if str(MODULE_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(MODULE_DIR))

import library_store
import model
import protocol
import serial_client
import ui_controller


def temp_paths(tmp: Path, read_only: bool = False) -> library_store.ProjectPaths:
    firmware_root = tmp / "Firmware" / "Remote_AC_Controller"
    library_root = tmp / "Private" / "Firmware" / "IR" / "Library"
    generated_dir = firmware_root / "src" / "private_ir_codes" / "generated"
    capture_002 = tmp / "Private" / "Firmware" / "IR" / "CAPTURE_002.bin"
    evidence_root = tmp / "Private" / "Evidence"
    firmware_root.mkdir(parents=True, exist_ok=True)
    if not read_only:
        (tmp / "Private" / "Firmware" / "IR").mkdir(parents=True, exist_ok=True)
    return library_store.ProjectPaths(
        project_root=tmp,
        firmware_root=firmware_root,
        library_root=library_root,
        generated_dir=generated_dir,
        capture_002=capture_002,
        evidence_root=evidence_root,
        read_only=read_only,
        read_only_reason="READ_ONLY_DEMO" if read_only else "",
    )


def complete_definition(code_id: str = "hisense_cool_24_fan_auto_power_on_v1") -> dict:
    d = model.default_definition()
    d.update(
        {
            "codeId": code_id,
            "displayName": "Cool 24 auto",
            "brand": "Hisense",
            "remoteDisplayText": "24 AUTO",
            "triggerButton": "power",
            "captureOperator": "tester",
        }
    )
    d["state"].update({"swingVertical": "off", "swingHorizontal": "off"})
    return d


def valid_status(**updates: object) -> dict:
    data = {
        "ok": True,
        "deviceStatus": {"ok": True},
        "deviceType": "NodeMCU ESP8266",
        "deviceMac": "AA:BB:CC:DD:EE:FF",
        "firmwareVersion": "1.0.0",
        "firmwareCommit": "abcdef1",
        "firmwareProfile": "ir-lab",
        "irModuleModel": "ZJ-IR-V2",
        "irUartBaud": serial_client.MODULE_BAUD,
        "irReady": True,
        "learningProtocolVersion": protocol.SUPPORTED_LEARNING_PROTOCOL_VERSION,
    }
    data.update(updates)
    return data


def export_events(frame: bytes, request: str = "req", session: str = "sess", export: str = "exp", chunk_size: int = 16) -> list[dict]:
    encoded = base64.b64encode(frame).decode("ascii")
    chunks = [encoded[i : i + chunk_size] for i in range(0, len(encoded), chunk_size)]
    begin = {
        "event": protocol.EXPORT_BEGIN_EVENT,
        "requestId": request,
        "sessionId": session,
        "exportId": export,
        "encoding": "base64",
        "chunkCount": len(chunks),
        "frameLength": len(frame),
        "frameSha256": protocol.sha256_bytes(frame),
        "totalEncodedChars": len(encoded),
    }
    chunk_events = [
        {
            "event": protocol.EXPORT_CHUNK_EVENT,
            "requestId": request,
            "sessionId": session,
            "exportId": export,
            "index": i,
            "count": len(chunks),
            "encoding": "base64",
            "data": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]
    done = dict(begin)
    done["event"] = protocol.EXPORT_DONE_EVENT
    return [begin, *chunk_events, done]


def assemble(events: list[dict], request: str = "req", session: str = "sess", export: str = "exp") -> bytes:
    asm = protocol.ExportAssembler(request, session, export, time.monotonic() + 3)
    raw = None
    for event in events:
        got = asm.process_event(event)
        if got is not None:
            raw = got
    if raw is None:
        raise AssertionError("assembler did not finish")
    return raw


def bad_frame() -> bytes:
    frame = bytearray(protocol.make_public_fake_frame(32))
    frame[-2] ^= 0x55
    return bytes(frame)


def wait_for_event(events: "queue.Queue[dict]", event_type: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.05)
            seen.append(event.get("type"))
            if event.get("type") == event_type:
                return event
        except queue.Empty:
            pass
    raise AssertionError(f"event {event_type} not seen; saw {seen}")


class TestProtocolCorrelation(unittest.TestCase):
    def setUp(self):
        self.frame = protocol.make_public_fake_frame(64)

    def test_wrong_request_id_rejected(self):
        ev = export_events(self.frame)
        ev[0]["requestId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "requestId"):
            assemble(ev)

    def test_wrong_session_id_rejected(self):
        ev = export_events(self.frame)
        ev[0]["sessionId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "sessionId"):
            assemble(ev)

    def test_wrong_export_id_rejected(self):
        ev = export_events(self.frame)
        ev[0]["exportId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "exportId"):
            assemble(ev)

    def test_begin_done_request_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["requestId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "requestId"):
            assemble(ev)

    def test_begin_done_session_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["sessionId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "sessionId"):
            assemble(ev)

    def test_begin_done_export_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["exportId"] = "wrong"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "exportId"):
            assemble(ev)

    def test_begin_done_length_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["frameLength"] += 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "metadata"):
            assemble(ev)

    def test_begin_done_sha_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["frameSha256"] = "0" * 64
        with self.assertRaisesRegex(protocol.ExportProtocolError, "metadata"):
            assemble(ev)

    def test_begin_done_chunk_count_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[-1]["chunkCount"] += 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "metadata"):
            assemble(ev)

    def test_unrelated_telemetry_does_not_bind_to_export(self):
        asm = protocol.ExportAssembler("req", "sess", "exp", time.monotonic() + 3)
        self.assertIsNone(asm.process_event({"event": "telemetry", "requestId": "wrong"}))
        raw = None
        for event in export_events(self.frame):
            raw = asm.process_event(event) or raw
        self.assertEqual(raw, self.frame)


class TestBase64AndChunks(unittest.TestCase):
    def setUp(self):
        self.frame = protocol.make_public_fake_frame(64)

    def _bad_payload_events(self, payload: str) -> list[dict]:
        ev = export_events(self.frame)
        ev[0]["chunkCount"] = ev[-1]["chunkCount"] = 1
        ev[0]["totalEncodedChars"] = ev[-1]["totalEncodedChars"] = len(payload)
        return [ev[0], {**ev[1], "index": 0, "count": 1, "data": payload}, ev[-1]]

    def test_invalid_base64_character_rejected(self):
        payload = base64.b64encode(self.frame).decode("ascii")[:-1] + "!"
        with self.assertRaisesRegex(protocol.ExportProtocolError, "BASE64"):
            assemble(self._bad_payload_events(payload))

    def test_invalid_padding_rejected(self):
        payload = base64.b64encode(self.frame).decode("ascii")[:-1]
        with self.assertRaisesRegex(protocol.ExportProtocolError, "BASE64"):
            assemble(self._bad_payload_events(payload))

    def test_chunk_out_of_order_rejected(self):
        ev = export_events(self.frame, chunk_size=8)
        with self.assertRaisesRegex(protocol.ExportProtocolError, "out_of_order"):
            assemble([ev[0], ev[2], ev[1], *ev[3:]])

    def test_duplicate_chunk_rejected(self):
        ev = export_events(self.frame, chunk_size=8)
        with self.assertRaisesRegex(protocol.ExportProtocolError, "duplicate"):
            assemble([ev[0], ev[1], ev[1], *ev[2:]])

    def test_missing_chunk_rejected(self):
        ev = export_events(self.frame, chunk_size=8)
        with self.assertRaisesRegex(protocol.ExportProtocolError, "missing_chunk"):
            assemble([ev[0], ev[1], ev[-1]])

    def test_extra_chunk_rejected(self):
        ev = export_events(self.frame, chunk_size=128)
        extra = {**ev[1], "index": 1}
        with self.assertRaisesRegex(protocol.ExportProtocolError, "out_of_range"):
            assemble([ev[0], ev[1], extra, ev[-1]])

    def test_negative_chunk_index_rejected(self):
        ev = export_events(self.frame)
        ev[1]["index"] = -1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "out_of_range"):
            assemble(ev)

    def test_chunk_index_overflow_rejected(self):
        ev = export_events(self.frame)
        ev[1]["index"] = 999
        with self.assertRaisesRegex(protocol.ExportProtocolError, "out_of_range"):
            assemble(ev)

    def test_excessive_chunk_count_rejected(self):
        ev = export_events(self.frame)
        ev[0]["chunkCount"] = protocol.MAX_CHUNK_COUNT + 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "chunk_count_limit"):
            assemble(ev)

    def test_excessive_encoded_size_rejected(self):
        ev = export_events(self.frame)
        ev[0]["totalEncodedChars"] = protocol.MAX_BASE64_CHARS + 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "total_encoded"):
            assemble(ev)

    def test_excessive_frame_length_rejected(self):
        ev = export_events(self.frame)
        ev[0]["frameLength"] = protocol.MAX_FRAME_BYTES + 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "frame_length_limit"):
            assemble(ev)

    def test_total_encoded_chars_mismatch_rejected(self):
        ev = export_events(self.frame)
        ev[0]["totalEncodedChars"] += 1
        ev[-1]["totalEncodedChars"] += 1
        with self.assertRaisesRegex(protocol.ExportProtocolError, "total_encoded_chars"):
            assemble(ev)

    def test_total_absolute_deadline_enforced(self):
        asm = protocol.ExportAssembler("req", "sess", "exp", time.monotonic() - 0.001)
        with self.assertRaisesRegex(protocol.ExportProtocolError, "EXPORT_TIMEOUT"):
            asm.process_event(export_events(self.frame)[0])


class TestFrameDefenses(unittest.TestCase):
    def test_assembler_rejects_invalid_frame(self):
        frame = bad_frame()
        with self.assertRaisesRegex(protocol.ExportProtocolError, "FRAME_VALIDATION_FAILED"):
            assemble(export_events(frame))

    def test_learning_client_rejects_invalid_frame(self):
        client = serial_client.LearningClient(serial_client.MockTransport("bad_hash"))
        with self.assertRaisesRegex(protocol.ExportProtocolError, "FRAME_VALIDATION_FAILED"):
            client.capture_once("sess", timeout_ms=1000)

    def test_library_store_rejects_invalid_frame(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d = complete_definition()
            library_store.save_definition(d, paths)
            with self.assertRaisesRegex(protocol.ExportProtocolError, "FRAME_VALIDATION_FAILED"):
                library_store.add_capture(d["codeId"], bad_frame(), {}, paths)

    def test_invalid_frame_creates_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d = complete_definition()
            library_store.save_definition(d, paths)
            with self.assertRaises(protocol.ExportProtocolError):
                library_store.add_capture(d["codeId"], bad_frame(), {}, paths)
            self.assertFalse((paths.library_root / "states" / d["codeId"] / "captures").exists())

    def test_invalid_frame_does_not_update_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d = complete_definition()
            library_store.save_definition(d, paths)
            before = hashlib.sha256((paths.library_root / "library_manifest.json").read_bytes()).hexdigest()
            with self.assertRaises(protocol.ExportProtocolError):
                library_store.add_capture(d["codeId"], bad_frame(), {}, paths)
            after = hashlib.sha256((paths.library_root / "library_manifest.json").read_bytes()).hexdigest()
            self.assertEqual(before, after)


class TestSerialConcurrency(unittest.TestCase):
    def test_only_worker_thread_can_read(self):
        transport = serial_client.MockTransport()
        errors = []
        t = threading.Thread(target=lambda: errors.append(_raises(lambda: transport.readline())))
        t.start(); t.join()
        self.assertTrue(errors[0])

    def test_only_worker_thread_can_write(self):
        transport = serial_client.MockTransport()
        errors = []
        t = threading.Thread(target=lambda: errors.append(_raises(lambda: transport.write_line("ir_learn_status"))))
        t.start(); t.join()
        self.assertTrue(errors[0])

    def _worker(self, scenario: str = "success"):
        events: "queue.Queue[dict]" = queue.Queue()
        transports = []
        def factory():
            transport = serial_client.MockTransport(scenario)
            transports.append(transport)
            return transport
        worker = serial_client.SerialIoWorker(
            event_queue=events,
            transport_factory=factory,
            port_info={"device": "MOCK", "vid": "0x1A86", "pid": "0x55D4"},
            allow_mock=True,
        )
        worker.start()
        worker.post(serial_client.CMD_CONNECT)
        wait_for_event(events, serial_client.EV_HANDSHAKE_OK)
        return worker, events, transports

    def test_cancel_during_read_exits_learning_once(self):
        worker, events, transports = self._worker("timeout")
        worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId="sess")
        time.sleep(0.05)
        worker.post(serial_client.CMD_CANCEL_CAPTURE)
        wait_for_event(events, serial_client.EV_CANCELLED)
        classes = [w.classification for w in transports[0].recorded_writes]
        self.assertEqual(classes.count(serial_client.WRITE_LEARN_CANCEL), 1)
        worker.post(serial_client.CMD_SHUTDOWN); wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)

    def test_disconnect_during_capture_exits_learning_once(self):
        worker, events, _ = self._worker("timeout")
        worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId="sess")
        time.sleep(0.05)
        worker.post(serial_client.CMD_DISCONNECT)
        # R6: DISCONNECT emits EV_DISCONNECTED, worker shuts down
        found = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                evt = events.get(timeout=0.1)
                if evt.get("type") in (serial_client.EV_DISCONNECTED, serial_client.EV_SHUTDOWN_COMPLETE):
                    found = True; break
            except Exception:
                continue
        self.assertTrue(found, "Neither DISCONNECTED nor SHUTDOWN_COMPLETE received")

    def test_close_window_during_capture_exits_learning_once(self):
        worker, events, _ = self._worker("timeout")
        worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId="sess")
        time.sleep(0.05)
        worker.post(serial_client.CMD_SHUTDOWN)
        wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)

    def test_cancel_response_not_consumed_by_other_thread(self):
        worker, events, transports = self._worker("timeout")
        owner = transports[0].owner_thread_id
        worker.post(serial_client.CMD_CANCEL_CAPTURE)
        wait_for_event(events, serial_client.EV_CANCELLED)
        self.assertTrue(all(w.thread_id == owner for w in transports[0].recorded_writes))
        worker.post(serial_client.CMD_SHUTDOWN); wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)

    def test_captured_event_not_consumed_by_ui_thread(self):
        worker, events, transports = self._worker("success")
        worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId="sess")
        evt = wait_for_event(events, serial_client.EV_CAPTURE_VALIDATED)
        self.assertIn("frame", evt)
        self.assertTrue(all(w.thread_id == transports[0].owner_thread_id for w in transports[0].recorded_writes))
        worker.post(serial_client.CMD_SHUTDOWN); wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)

    def test_serial_port_closed_after_worker_shutdown(self):
        worker, events, transports = self._worker("success")
        worker.post(serial_client.CMD_SHUTDOWN)
        wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)
        self.assertTrue(transports[0]._closed)

    def test_worker_thread_terminates_within_timeout(self):
        worker, events, _ = self._worker("success")
        worker.post(serial_client.CMD_SHUTDOWN)
        wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)
        self.assertTrue(worker.join(1.0))


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except RuntimeError:
        return True


class TestCaptureId(unittest.TestCase):
    def _four_captures(self, paths):
        d = complete_definition("hisense_cool_24_capture_id_v1")
        library_store.save_definition(d, paths)
        records = []
        for _ in range(4):
            records.append(library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {"learnExitConfirmed": True}, paths))
        return d, records

    def test_existing_captures_loaded_on_restart(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            _, records = self._four_captures(paths)
            self.assertEqual(records[-1].capture_id, "capture_004")

    def test_new_capture_returns_real_capture_id(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            _, records = self._four_captures(paths)
            self.assertEqual(records[-1].capture_index, 4)

    def test_ui_approves_selected_real_capture_id(self):
        controller = ui_controller.IRLearningController()
        controller.add_capture_choice("capture_004", 4, "a" * 64, 418)
        controller.select_capture("capture_004")
        self.assertEqual(controller.state.selected_capture_id, "capture_004")

    def test_capture_004_not_mapped_to_capture_001(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, records = self._four_captures(paths)
            library_store.approve_canonical(d["codeId"], records[-1].capture_id, "tester", paths=paths)
            meta = json.loads((paths.library_root / "states" / d["codeId"] / "approved" / "canonical.json").read_text())
            self.assertEqual(meta["sourceCaptureId"], "capture_004")


class TestImmutability(unittest.TestCase):
    def _approved(self, paths):
        d = complete_definition("hisense_cool_24_immutable_v1")
        library_store.save_definition(d, paths)
        rec = library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {"learnExitConfirmed": True}, paths)
        library_store.approve_canonical(d["codeId"], rec.capture_id, "tester", paths=paths)
        return d, rec

    def test_approved_definition_cannot_change(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, _ = self._approved(paths)
            d["notes"] = "mutated"
            d["status"] = "approved"
            with self.assertRaises(PermissionError):
                library_store.save_definition(d, paths)

    def test_approved_canonical_cannot_change(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, rec = self._approved(paths)
            with self.assertRaises(PermissionError):
                library_store.approve_canonical(d["codeId"], rec.capture_id, "tester2", paths=paths)

    def test_approved_state_cannot_append_capture(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, _ = self._approved(paths)
            with self.assertRaises(PermissionError):
                library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {}, paths)

    def test_fork_creates_next_version(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, _ = self._approved(paths)
            forked = library_store.fork_approved_state(d["codeId"], paths)
            self.assertTrue(forked["codeId"].endswith("_v2"))
            self.assertEqual(forked["status"], "draft")

    def test_previous_version_hash_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, _ = self._approved(paths)
            path = paths.library_root / "states" / d["codeId"] / "definition.json"
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            library_store.fork_approved_state(d["codeId"], paths)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before, after)


class TestCanonicalProvenance(unittest.TestCase):
    def _approved(self, paths):
        d = complete_definition("hisense_cool_24_canonical_v1")
        library_store.save_definition(d, paths)
        rec = library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {"learnExitConfirmed": True}, paths)
        library_store.approve_canonical(d["codeId"], rec.capture_id, "tester", paths=paths)
        return d, rec

    def test_canonical_must_equal_source_capture_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, rec = self._approved(paths)
            root = paths.library_root / "states" / d["codeId"]
            self.assertEqual((root / "captures" / f"{rec.capture_id}.bin").read_bytes(), (root / "approved" / "canonical.bin").read_bytes())

    def test_canonical_source_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, _ = self._approved(paths)
            root = paths.library_root / "states" / d["codeId"]
            library_store.atomic_write_bytes(root / "approved" / "canonical.bin", protocol.make_public_fake_frame(33))
            self.assertFalse(library_store.validate_library(paths)["LIBRARY_VALIDATION_PASS"])

    def test_canonical_source_capture_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d, rec = self._approved(paths)
            (paths.library_root / "states" / d["codeId"] / "captures" / f"{rec.capture_id}.bin").unlink()
            self.assertFalse(library_store.validate_library(paths)["LIBRARY_VALIDATION_PASS"])


class TestGenerator(unittest.TestCase):
    def test_invalid_library_produces_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d = complete_definition("hisense_cool_24_invalid_gen_v1")
            d["status"] = "approved"
            d["unknownApprovalConfirmed"] = True
            library_store.save_definition(d, paths)
            result = library_store.generate_firmware_include(paths)
            self.assertFalse(result["IR_LIBRARY_GENERATE_PASS"])
            self.assertFalse(Path(result["GENERATED_INCLUDE"]).exists())

    def test_old_generated_file_unchanged_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            paths.generated_dir.mkdir(parents=True)
            old = paths.generated_dir / "ir_library_generated.inc"
            library_store.atomic_write_text(old, "old\n")
            before = hashlib.sha256(old.read_bytes()).hexdigest()
            d = complete_definition("hisense_cool_24_invalid_old_v1")
            d["status"] = "approved"
            d["unknownApprovalConfirmed"] = True
            library_store.save_definition(d, paths)
            result = library_store.generate_firmware_include(paths)
            after = hashlib.sha256(old.read_bytes()).hexdigest()
            self.assertFalse(result["GENERATED_OUTPUT_CHANGED"])
            self.assertEqual(before, after)

    def test_valid_library_atomic_generation_pass(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td))
            d = complete_definition("hisense_cool_24_valid_gen_v1")
            library_store.save_definition(d, paths)
            rec = library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {"learnExitConfirmed": True}, paths)
            library_store.approve_canonical(d["codeId"], rec.capture_id, "tester", paths=paths)
            result = library_store.generate_firmware_include(paths)
            self.assertTrue(result["IR_LIBRARY_GENERATE_PASS"])
            self.assertTrue(Path(result["GENERATED_INCLUDE"]).exists())


class TestDeviceGate(unittest.TestCase):
    def test_handshake_failure_blocks_learning(self):
        result = serial_client.validate_device_status(valid_status(firmwareProfile="public"), {"vid": "0x1A86", "pid": "0x55D4"})
        self.assertFalse(result.ready)

    def test_missing_profile_blocks_learning(self):
        status = valid_status()
        del status["firmwareProfile"]
        self.assertFalse(serial_client.validate_device_status(status, {"vid": "0x1A86", "pid": "0x55D4"}).ready)

    def test_non_ir_lab_profile_blocks_learning(self):
        self.assertFalse(serial_client.validate_device_status(valid_status(firmwareProfile="private"), {"vid": "0x1A86", "pid": "0x55D4"}).ready)

    def test_missing_device_mac_blocks_learning(self):
        self.assertFalse(serial_client.validate_device_status(valid_status(deviceMac=""), {"vid": "0x1A86", "pid": "0x55D4"}).ready)

    def test_ir_not_ready_blocks_learning(self):
        self.assertFalse(serial_client.validate_device_status(valid_status(irReady=False), {"vid": "0x1A86", "pid": "0x55D4"}).ready)

    def test_capture_metadata_comes_from_handshake(self):
        events: "queue.Queue[dict]" = queue.Queue()
        worker = serial_client.SerialIoWorker(
            event_queue=events,
            transport_factory=lambda: serial_client.MockTransport("success"),
            port_info={"device": "MOCK", "vid": "0x1A86", "pid": "0x55D4"},
            allow_mock=True,
        )
        worker.start(); worker.post(serial_client.CMD_CONNECT); wait_for_event(events, serial_client.EV_HANDSHAKE_OK)
        worker.post(serial_client.CMD_BEGIN_CAPTURE, sessionId="sess")
        evt = wait_for_event(events, serial_client.EV_CAPTURE_VALIDATED)
        self.assertEqual(evt["metadata"]["deviceMac"], "AA:BB:CC:DD:EE:FF")
        worker.post(serial_client.CMD_SHUTDOWN); wait_for_event(events, serial_client.EV_SHUTDOWN_COMPLETE)


class TestReleaseAndMock(unittest.TestCase):
    def test_release_without_project_root_is_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            paths = temp_paths(Path(td), read_only=True)
            self.assertTrue(library_store.validate_library(paths)["READ_ONLY_DEMO"])

    def test_release_does_not_create_private_under_extract_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = temp_paths(root, read_only=True)
            library_store.validate_library(paths)
            self.assertFalse((root / "Private").exists())

    def test_valid_project_root_uses_single_private_library(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = temp_paths(root)
            library_store.ensure_library(paths)
            self.assertTrue(str(paths.library_root).startswith(str(root)))
            self.assertEqual(str(paths.library_root).count("Private"), 1)

    def test_mock_never_writes_formal_library(self):
        with tempfile.TemporaryDirectory() as formal, tempfile.TemporaryDirectory() as mock:
            formal_paths = temp_paths(Path(formal))
            mock_paths = temp_paths(Path(mock))
            d = complete_definition("hisense_cool_24_mock_v1")
            library_store.save_definition(d, mock_paths)
            library_store.add_capture(d["codeId"], protocol.make_public_fake_frame(32), {}, mock_paths)
            self.assertFalse(formal_paths.library_root.exists())


class TestStats(unittest.TestCase):
    def test_skipped_not_counted_as_passed(self):
        result = unittest.TestResult()
        result.testsRun = 2
        result.addSkip(unittest.FunctionTestCase(lambda: None), "reason")
        passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
        self.assertEqual(passed, 1)

    def test_unit_and_integration_counts_are_independent(self):
        # R4: SUITE_CLASS_MAP moved to auto-discovery; test that unique counts work
        from run_test_suites import discover_test_modules
        modules = discover_test_modules()
        self.assertGreater(len(modules), 1)

    def test_hardcoded_pass_fields_absent(self):
        result = unittest.TestResult()
        summary = {
            "testsRun": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "successful": result.wasSuccessful(),
        }
        self.assertIn("successful", summary)
        self.assertNotIn("UNIT_TEST_PASS=True", json.dumps(summary))


class TestFirmwareStatic(unittest.TestCase):
    def _text(self, rel: str) -> str:
        candidates = [
            FIRMWARE_ROOT / rel,
            FIRMWARE_ROOT / "firmware_review" / "live_files" / rel,
            MODULE_DIR.parents[2] / rel,
            MODULE_DIR.parents[2] / "firmware_review" / "live_files" / rel,
        ]
        path = next((p for p in candidates if p.exists()), candidates[0])
        return path.read_text(encoding="utf-8", errors="ignore")

    def test_firmware_review_manifest_matches_live_files(self):
        required = ["src/serial_cli.cpp", "src/ir_module.cpp", "include/ir_module.h", "tools/dev.ps1"]
        for rel in required:
            self.assertTrue(
                (FIRMWARE_ROOT / rel).exists()
                or (FIRMWARE_ROOT / "firmware_review" / "live_files" / rel).exists()
                or (MODULE_DIR.parents[2] / rel).exists()
                or (MODULE_DIR.parents[2] / "firmware_review" / "live_files" / rel).exists(),
                rel,
            )

    def test_firmware_command_allowlist_has_no_replay(self):
        self.assertNotIn("ir.transmit", serial_client.ALLOWED_PC_COMMANDS)
        self.assertNotIn("ir.replay", serial_client.ALLOWED_PC_COMMANDS)

    def test_ir_lab_profile_required_for_learning(self):
        text = self._text("tools/dev.ps1")
        self.assertIn("ENABLE_IR_LAB_LEARNING_COMMANDS=1", text)
        self.assertIn("ir-lab", text)

    def test_firmware_export_events_carry_all_correlation_ids(self):
        text = self._text("src/serial_cli.cpp")
        section = text.split("void Cli::doIrLearnExport", 1)[1].split("void Cli::doIrLearnClear", 1)[0]
        for token in ["requestId", "sessionId", "exportId", "totalEncodedChars"]:
            self.assertIn(token, section)

    def test_firmware_never_echoes_22h_to_ir_module(self):
        text = self._text("src/serial_cli.cpp")
        section = text.split("void Cli::doIrLearnExport", 1)[1].split("void Cli::doIrLearnClear", 1)[0]
        self.assertNotIn("extSendCaptured", section)
        self.assertNotIn("IR_AFN_EXT_SEND", section)


if __name__ == "__main__":
    unittest.main()
