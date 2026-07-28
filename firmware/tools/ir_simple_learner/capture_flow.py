"""Capture flow state machine. Handles captured→export→reassemble→validate→cancel→save."""
import time, uuid
from enum import Enum
import protocol_adapter as pa


class State(Enum):
    IDLE = "IDLE"
    WAITING_ENTER_ACK = "WAITING_ENTER_ACK"
    WAITING_REMOTE = "WAITING_REMOTE"
    CAPTURE_ANNOUNCED = "CAPTURE_ANNOUNCED"
    EXPORTING = "EXPORTING"
    EXITING = "EXITING"
    SAVING = "SAVING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    EXIT_UNCONFIRMED = "EXIT_UNCONFIRMED"


class CaptureContext:
    def __init__(self, capture_index):
        self.capture_index = capture_index
        self.request_id = "req-" + str(uuid.uuid4())[:8]
        self.session_id = "sess-" + str(uuid.uuid4())[:8]
        self.export_id = ""
        self.captured_length = 0
        self.captured_sha256 = ""
        self.pending_frame = None
        self.started_at = 0.0
        self.export_deadline = 0.0
        self.exit_deadline = 0.0
        self.state = State.IDLE
        self.error = ""
        self.exit_confirmed = False
        self.export_sent = False
        self.assembler = None
        self.metadata = {}


class CaptureFlow:
    """Orchestrates one capture cycle. GUI feeds events; flow manages state."""

    TIMEOUT_WAITING_REMOTE = 40.0
    TIMEOUT_EXPORT = 10.0
    TIMEOUT_EXIT = 3.0

    def __init__(self):
        self.active: CaptureContext = None

    def start(self, capture_index, write_fn):
        if self.active and self.active.state not in (State.IDLE, State.COMPLETED,
            State.CANCELLED, State.ERROR, State.EXIT_UNCONFIRMED):
            return None, "busy"
        ctx = CaptureContext(capture_index)
        ctx.started_at = time.monotonic()
        ctx.state = State.WAITING_ENTER_ACK
        self.active = ctx
        write_fn(f"ir_learn_begin {ctx.request_id} {ctx.session_id}")
        return ctx, "started"

    def handle_event(self, evt, write_fn):
        ctx = self.active
        if ctx is None:
            return

        name = evt.get("event", "")
        rid = evt.get("requestId", "")

        # ---- Waiting for enter ACK ----
        if ctx.state == State.WAITING_ENTER_ACK:
            if "ir.learn.waiting" in name or "EXTLEARN_ENTER" in name or name == "IR_EXTLEARN_ACK":
                ctx.state = State.WAITING_REMOTE
                ctx.started_at = time.monotonic()
            elif "error" in name:
                ctx.state = State.ERROR; ctx.error = evt.get("reason", "enter_failed")
            # Legacy: if no ACK at all, fall through to waiting_remote

        # ---- Waiting for remote press ----
        elif ctx.state == State.WAITING_REMOTE:
            if name == "ir.learn.captured" or name == "IR_EXTLEARN_CAPTURE":
                if rid and rid != ctx.request_id:
                    return
                sid = evt.get("sessionId", "")
                if sid and sid != ctx.session_id:
                    return
                ctx.captured_length = evt.get("length", 0)
                ctx.captured_sha256 = evt.get("sha256", "")
                struct_valid = evt.get("structureValid", True)
                if struct_valid is False:
                    ctx.state = State.ERROR; ctx.error = "structure_invalid"; return
                if not isinstance(ctx.captured_length, int) or ctx.captured_length < 7 or ctx.captured_length > 832:
                    ctx.state = State.ERROR; ctx.error = "bad_length"; return
                sha = str(ctx.captured_sha256)
                if len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
                    ctx.state = State.ERROR; ctx.error = "bad_sha"; return
                ctx.state = State.CAPTURE_ANNOUNCED
                if not ctx.export_sent:
                    self._request_export(ctx, write_fn)
            elif "ir.learn.waiting" in name:
                pass

        # ---- Exporting ----
        elif ctx.state in (State.CAPTURE_ANNOUNCED, State.EXPORTING):
            if name.startswith("ir.learn.export"):
                self._handle_export(evt, ctx, write_fn)

        # ---- Exiting ----
        elif ctx.state == State.EXITING:
            if name == "ir.learn.cancelled" or name == "IR_EXTLEARN_EXIT_ACK":
                if rid and rid != ctx.request_id:
                    return
                exit_ok = evt.get("exitConfirmed", False)
                if isinstance(exit_ok, str):
                    exit_ok = exit_ok.lower() == "true"
                ack_status = evt.get("moduleAckStatus", evt.get("ackStatus", 0))
                ctx.exit_confirmed = bool(exit_ok) and ack_status == 0
                if ctx.exit_confirmed and ctx.pending_frame:
                    ctx.state = State.COMPLETED
                elif ctx.exit_confirmed and not ctx.pending_frame:
                    ctx.state = State.CANCELLED
                else:
                    ctx.state = State.EXIT_UNCONFIRMED
                    ctx.error = "exit unconfirmed"

    def check_timeout(self):
        ctx = self.active
        if ctx is None:
            return None
        now = time.monotonic()
        if ctx.state == State.WAITING_ENTER_ACK:
            # Allow up to 3 seconds for enter ACK; then assume legacy firmware and move on
            if now - ctx.started_at > 3.0:
                ctx.state = State.WAITING_REMOTE
                ctx.started_at = time.monotonic()
                return "auto_progressed_to_waiting"
        elif ctx.state == State.WAITING_REMOTE:
            if now - ctx.started_at > self.TIMEOUT_WAITING_REMOTE:
                ctx.state = State.ERROR; ctx.error = "waiting_remote_timeout"
                return "timeout_waiting"
        elif ctx.state in (State.CAPTURE_ANNOUNCED, State.EXPORTING):
            if now - ctx.started_at > self.TIMEOUT_WAITING_REMOTE + self.TIMEOUT_EXPORT:
                ctx.state = State.ERROR; ctx.error = "export_timeout"
                return "timeout_export"
        elif ctx.state == State.EXITING:
            if now - ctx.started_at > self.TIMEOUT_WAITING_REMOTE + self.TIMEOUT_EXPORT + self.TIMEOUT_EXIT:
                ctx.state = State.EXIT_UNCONFIRMED; ctx.error = "exit_timeout"
                return "timeout_exit"
        return None

    def _request_export(self, ctx, write_fn):
        ctx.export_id = "exp-" + str(uuid.uuid4())[:8]
        ctx.assembler = pa.ExportAssembler(
            ctx.request_id, ctx.session_id, ctx.export_id,
            ctx.captured_length, ctx.captured_sha256
        )
        ctx.state = State.EXPORTING
        ctx.export_sent = True
        write_fn(f"ir_learn_export {ctx.request_id} {ctx.session_id} {ctx.export_id}")

    def _handle_export(self, evt, ctx, write_fn):
        if ctx.assembler is None:
            return
        try:
            result = ctx.assembler.process(evt)
        except pa.ExportProtocolError as e:
            ctx.state = State.ERROR; ctx.error = str(e)
            return
        if result is not None:
            # Export done successfully — now request cancel/exit
            ctx.pending_frame = result
            ctx.state = State.EXITING
            write_fn(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")

    def cancel(self, write_fn):
        ctx = self.active
        if ctx is None:
            return
        write_fn(f"ir_learn_cancel {ctx.request_id} {ctx.session_id}")
        ctx.state = State.CANCELLED
        ctx.pending_frame = None

    def reset(self):
        self.active = None
