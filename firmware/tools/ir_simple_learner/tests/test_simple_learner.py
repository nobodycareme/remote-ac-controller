"""End-to-end tests for IR Simple Learner export path."""
import hashlib, json, os, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import capture_flow as cf
import frame_validator as fv
import presets
import protocol_adapter as pa
import storage
from simple_ir_learner import FakeWorker


class _NoGuiApp:
    """Minimal learner-like controller for testing without Tk."""
    def __init__(self):
        self.flow = cf.CaptureFlow()
        self.worker = FakeWorker()
        self.captures = {}
        self.writes_log = []

    def write(self, text):
        self.writes_log.append(text)
        self.worker.write_line(text)

    def start_capture(self, idx):
        self.flow.start(idx, self.write)

    def drain_until(self, state_or_check, max_loops=40):
        for _ in range(max_loops):
            try:
                while True:
                    evt = self.worker.queue.get_nowait()
                    self.flow.handle_event(evt, self.write)
            except Exception:
                pass
            time.sleep(0.05)
            ctx = self.flow.active
            if ctx is None:
                break
            if callable(state_or_check) and state_or_check(ctx):
                return True
            if ctx.state == state_or_check:
                return True
        return False


class TestEndToEndExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = storage.LEARNED_ROOT
        storage.LEARNED_ROOT = Path(self.tmp.name)

    def tearDown(self):
        storage.LEARNED_ROOT = self.old_root
        self.tmp.cleanup()

    def test_A_real_event_sequence_saves_capture(self):
        """TEST_A: full flow produces valid frame, then save it."""
        app = _NoGuiApp()
        state_id = "test_a"
        storage.save_state(state_id, {"name": "Test A", "codeId": state_id})
        app.start_capture(1)
        ok = app.drain_until(cf.State.COMPLETED, max_loops=50)
        self.assertTrue(ok, f"Flow did not complete. State: {app.flow.active.state if app.flow.active else 'none'}")
        # Flow completed - now save the frame
        ctx = app.flow.active
        self.assertIsNotNone(ctx.pending_frame, "No pending frame after export")
        frame = bytes(ctx.pending_frame)
        storage.save_capture(state_id, 1, frame, {
            "requestId": ctx.request_id, "sessionId": ctx.session_id,
            "exportId": ctx.export_id, "exitConfirmed": True,
        })
        d = storage.LEARNED_ROOT / state_id
        self.assertTrue((d / "capture_001.bin").exists(), "capture_001.bin not created")
        data = (d / "capture_001.bin").read_bytes()
        vr = fv.validate_frame(data)
        self.assertTrue(vr["valid"], f"Frame invalid: {vr['reason']}")
        # Verify 22H frame
        self.assertEqual(data[4], 0x22)
        self.assertEqual(data[0], 0x68)
        self.assertEqual(data[-1], 0x16)
        # No dangerous writes
        for w in app.writes_log:
            self.assertNotIn("ir extsend", w)
            self.assertNotIn("ir send", w)

    def test_B_capture_triggers_one_export(self):
        """TEST_B: duplicate captured does not trigger second export."""
        app = _NoGuiApp()
        storage.save_state("test_b", {"name": "Test B", "codeId": "test_b"})
        app.start_capture(1)
        # Wait for export to be sent
        time.sleep(0.3)
        for _ in range(20):
            try:
                while True:
                    evt = app.worker.queue.get_nowait()
                    app.flow.handle_event(evt, app.write)
            except Exception:
                pass
            time.sleep(0.02)
            if app.flow.active and app.flow.active.state == cf.State.COMPLETED:
                break
        # Count export commands
        export_count = sum(1 for w in app.writes_log if w.startswith("ir_learn_export"))
        self.assertEqual(export_count, 1, f"Expected 1 export, got {export_count}")

    def test_C_out_of_order_chunks(self):
        """TEST_C: out-of-order chunks rejected."""
        frame = pa.make_public_fake_22h_frame(20)
        sha = hashlib.sha256(frame).hexdigest()
        encoded = __import__('base64').b64encode(frame).decode()
        chunk1 = encoded[:300]; chunk2 = encoded[300:]

        asm = pa.ExportAssembler("r1", "s1", "e1", len(frame), sha)
        asm.process({"event": pa.EXPORT_BEGIN, "requestId": "r1", "sessionId": "s1",
            "exportId": "e1", "encoding": "base64", "frameLength": len(frame),
            "frameSha256": sha, "chunkCount": 2, "totalEncodedChars": len(encoded)})
        # Send chunk[1] before chunk[0] = out of order
        with self.assertRaises(pa.ExportProtocolError):
            asm.process({"event": pa.EXPORT_CHUNK, "requestId": "r1", "sessionId": "s1",
                "exportId": "e1", "index": 1, "count": 2, "encoding": "base64", "data": chunk2})

    def test_D_wrong_correlation_ids(self):
        """TEST_D: wrong requestId rejected."""
        frame = pa.make_public_fake_22h_frame(20)
        sha = hashlib.sha256(frame).hexdigest()
        asm = pa.ExportAssembler("r1", "s1", "e1", len(frame), sha)
        with self.assertRaises(pa.ExportProtocolError):
            asm.process({"event": pa.EXPORT_BEGIN, "requestId": "wrong", "sessionId": "s1",
                "exportId": "e1", "encoding": "base64", "frameLength": len(frame),
                "frameSha256": sha, "chunkCount": 1, "totalEncodedChars": 10})

    def test_E_strict_base64_rejected(self):
        """TEST_E: invalid base64 rejected."""
        frame = pa.make_public_fake_22h_frame(20)
        sha = hashlib.sha256(frame).hexdigest()
        encoded = __import__('base64').b64encode(frame).decode()
        asm = pa.ExportAssembler("r1", "s1", "e1", len(frame), sha)
        asm.process({"event": pa.EXPORT_BEGIN, "requestId": "r1", "sessionId": "s1",
            "exportId": "e1", "encoding": "base64", "frameLength": len(frame),
            "frameSha256": sha, "chunkCount": 1, "totalEncodedChars": len(encoded)})
        with self.assertRaises(pa.ExportProtocolError):
            asm.process({"event": pa.EXPORT_DONE, "requestId": "r1", "sessionId": "s1",
                "exportId": "e1", "encoding": "base64", "frameLength": len(frame),
                "frameSha256": sha, "chunkCount": 1, "totalEncodedChars": len(encoded)})
            # Missing chunk data before done

    def test_F_length_hash_frame_failures(self):
        """TEST_F: wrong length, SHA, or bad checksum rejected."""
        frame = pa.make_public_fake_22h_frame(20)
        wrong_sha = hashlib.sha256(b"wrong").hexdigest()
        asm = pa.ExportAssembler("r1", "s1", "e1", len(frame), wrong_sha)
        with self.assertRaises(pa.ExportProtocolError) as cm:
            asm.process({"event": pa.EXPORT_BEGIN, "requestId": "r1", "sessionId": "s1",
                "exportId": "e1", "encoding": "base64", "frameLength": len(frame),
                "frameSha256": hashlib.sha256(frame).hexdigest(), "chunkCount": 1,
                "totalEncodedChars": 10})
        self.assertIn("SHA_MISMATCH", str(cm.exception))

    def test_G_exit_unconfirmed_no_save(self):
        """TEST_G: exitConfirmed=false does not save."""
        app = _NoGuiApp()
        storage.save_state("test_g", {"name": "Test G", "codeId": "test_g"})
        # Override cancel response to return exitConfirmed=false
        old_write = app.worker.write_line
        def bad_write(text):
            old_write(text)
            if "ir_learn_cancel" in text:
                app.worker.queue.put({
                    "event": "ir.learn.cancelled", "exitConfirmed": False,
                    "requestId": text.split()[1], "sessionId": text.split()[2],
                })
        app.worker.write_line = bad_write
        app.start_capture(1)
        time.sleep(0.5)
        for _ in range(30):
            try:
                while True:
                    evt = app.worker.queue.get_nowait()
                    app.flow.handle_event(evt, app.write)
            except Exception:
                pass
            time.sleep(0.02)
            if app.flow.active and app.flow.active.state == cf.State.EXIT_UNCONFIRMED:
                break
        # No capture file should exist
        d = storage.LEARNED_ROOT / "test_g"
        self.assertFalse((d / "capture_001.bin").exists(), "capture saved despite exit unconfirmed")

    def test_H_capture_slot_order(self):
        """TEST_H: capture saves in correct slot regardless of order."""
        for idx in [3, 1, 2]:
            state_name = f"test_h_{idx}"
            app = _NoGuiApp()
            storage.save_state(state_name, {"name": f"Test H {idx}", "codeId": state_name})
            app.start_capture(idx)
            ok = app.drain_until(cf.State.COMPLETED, max_loops=50)
            self.assertTrue(ok, f"Slot {idx} not completed. State: {app.flow.active.state if app.flow.active else 'none'}")
            ctx = app.flow.active
            self.assertIsNotNone(ctx.pending_frame)
            storage.save_capture(state_name, idx, bytes(ctx.pending_frame), {
                "requestId": ctx.request_id, "sessionId": ctx.session_id, "exitConfirmed": True,
            })
            d = storage.LEARNED_ROOT / state_name
            expected = d / f"capture_{idx:03d}.bin"
            self.assertTrue(expected.exists(), f"capture_{idx:03d}.bin missing for slot {idx}")
            vr = fv.validate_frame(expected.read_bytes())
            self.assertTrue(vr["valid"], f"Bad frame for slot {idx}: {vr['reason']}")

    def test_I_canonical_exact_slot_copy(self):
        """TEST_I: canonical byte-exact to chosen capture."""
        frame = pa.make_public_fake_22h_frame(20)
        storage.save_state("test_i", {"name": "Test I", "codeId": "test_i"})
        storage.save_capture("test_i", 2, frame, {"session": "abc"})
        storage.save_canonical("test_i", 2, frame)
        d = storage.LEARNED_ROOT / "test_i"
        can = (d / "canonical.bin").read_bytes()
        cap2 = (d / "capture_002.bin").read_bytes()
        self.assertEqual(can, cap2)

    def test_J_no_dangerous_writes(self):
        """TEST_J: FakeWorker writes never include 22H or replay."""
        app = _NoGuiApp()
        storage.save_state("test_j", {"name": "Test J", "codeId": "test_j"})
        app.start_capture(1)
        time.sleep(0.5)
        for _ in range(30):
            try:
                while True:
                    evt = app.worker.queue.get_nowait()
                    app.flow.handle_event(evt, app.write)
            except Exception:
                pass
            time.sleep(0.02)
            if app.flow.active and app.flow.active.state == cf.State.COMPLETED:
                break
        for w in app.writes_log:
            self.assertNotIn("ir extsend", w)
            self.assertNotIn("ir send", w)
            self.assertNotIn("replay", w)
            self.assertNotIn("22H", w)
        # Only allowed commands
        for w in app.writes_log:
            cmd = w.split()[0]
            self.assertIn(cmd, ["ir_learn_begin", "ir_learn_export", "ir_learn_cancel"])


class TestPresets(unittest.TestCase):
    def test_preset_count(self):
        self.assertEqual(len(presets.PRESETS), 15)


if __name__ == "__main__":
    unittest.main()
