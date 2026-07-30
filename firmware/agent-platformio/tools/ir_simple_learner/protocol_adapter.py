"""Export protocol adapter: ExportAssembler for chunked base64 22H frame transfer."""
import base64, binascii, hashlib, time

# Protocol constants (match firmware)
MAX_FRAME_BYTES = 832
MAX_BASE64_CHARS = 8192
MAX_CHUNK_COUNT = 128
MAX_CHUNK_CHARS = 1024

EXPORT_BEGIN = "ir.learn.export.begin"
EXPORT_CHUNK = "ir.learn.export.chunk"
EXPORT_DONE  = "ir.learn.export.done"
EXPORT_ERROR = "ir.learn.export.error"

import frame_validator as fv


class ExportProtocolError(ValueError):
    """Protocol failure with structured fields."""
    def __init__(self, code, stage, reason, **details):
        self.code = code; self.stage = stage; self.reason = reason; self.details = details
        super().__init__(f"{code}: stage={stage} reason={reason} {details}")


def _required_str(evt, key, stage):
    val = evt.get(key)
    if not isinstance(val, str) or not val:
        raise ExportProtocolError("MISSING_KEY", stage, key)
    return val

def _required_int(evt, key, stage, min_val=0, max_val=None):
    val = evt.get(key)
    if not isinstance(val, int):
        raise ExportProtocolError("MISSING_INT", stage, key)
    if val < min_val:
        raise ExportProtocolError("VALUE_TOO_SMALL", stage, key, value=val)
    if max_val is not None and val > max_val:
        raise ExportProtocolError("VALUE_TOO_LARGE", stage, key, value=val)
    return val


class ExportAssembler:
    """Assembles one chunked base64 22H frame export under strict validation."""

    def __init__(self, request_id, session_id, export_id, captured_length, captured_sha256):
        self.request_id = request_id
        self.session_id = session_id
        self.export_id = export_id
        self.captured_length = captured_length
        self.captured_sha256 = captured_sha256.lower()
        self.begin = None
        self.chunks = {}
        self.done = False
        self.error = None

    def process(self, evt):
        """Process one export event. Returns bytes when done, None otherwise."""
        name = evt.get("event", "")
        if name == EXPORT_BEGIN:
            return self._begin(evt)
        if name == EXPORT_CHUNK:
            return self._chunk(evt)
        if name == EXPORT_DONE:
            return self._done(evt)
        if name == EXPORT_ERROR:
            self.error = evt.get("reason", "unknown")
            raise ExportProtocolError("EXPORT_ERROR", "event", self.error)
        return None

    def _check_ids(self, evt, stage):
        for key in ("requestId", "sessionId", "exportId"):
            val = evt.get(key, "")
            expected = getattr(self, {"requestId": "request_id", "sessionId": "session_id", "exportId": "export_id"}[key])
            if val != expected:
                raise ExportProtocolError("ID_MISMATCH", stage, key, got=val, expected=expected)

    def _begin(self, evt):
        if self.begin is not None:
            raise ExportProtocolError("DUPLICATE", "begin", "already_received")
        self._check_ids(evt, "begin")
        encoding = _required_str(evt, "encoding", "begin")
        if encoding != "base64":
            raise ExportProtocolError("BAD_ENCODING", "begin", encoding)

        chunk_count = _required_int(evt, "chunkCount", "begin", 1, MAX_CHUNK_COUNT)
        frame_len   = _required_int(evt, "frameLength", "begin", 1, MAX_FRAME_BYTES)
        sha         = _required_str(evt, "frameSha256", "begin")
        total_chars = _required_int(evt, "totalEncodedChars", "begin", 1, MAX_BASE64_CHARS)

        if len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
            raise ExportProtocolError("BAD_SHA256", "begin", sha)
        sha = sha.lower()

        if frame_len != self.captured_length:
            raise ExportProtocolError("LENGTH_MISMATCH", "begin",
                f"captured={self.captured_length} begin={frame_len}")
        if sha != self.captured_sha256:
            raise ExportProtocolError("SHA_MISMATCH", "begin",
                f"captured={self.captured_sha256[:16]} begin={sha[:16]}")

        self.begin = {
            "chunk_count": chunk_count, "frame_length": frame_len,
            "frame_sha256": sha, "total_chars": total_chars,
        }
        return None

    def _chunk(self, evt):
        if self.begin is None:
            raise ExportProtocolError("CHUNK_BEFORE_BEGIN", "chunk", "no_begin")
        self._check_ids(evt, "chunk")
        idx   = _required_int(evt, "index", "chunk", 0, self.begin["chunk_count"] - 1)
        cnt   = _required_int(evt, "count", "chunk")

        if cnt != self.begin["chunk_count"]:
            raise ExportProtocolError("CHUNK_COUNT_MISMATCH", "chunk",
                got=cnt, expected=self.begin["chunk_count"])

        encoding = evt.get("encoding", "")
        data     = evt.get("data", "")
        if encoding != "base64" or not isinstance(data, str):
            raise ExportProtocolError("BAD_CHUNK_FORMAT", "chunk", str(idx))

        try:
            data.encode("ascii")
        except UnicodeEncodeError:
            raise ExportProtocolError("CHUNK_NOT_ASCII", "chunk", str(idx))

        if len(data) > MAX_CHUNK_CHARS:
            raise ExportProtocolError("CHUNK_TOO_LARGE", "chunk", str(idx), length=len(data))

        if idx in self.chunks:
            raise ExportProtocolError("DUPLICATE_CHUNK", "chunk", str(idx))

        # Strict sequential order
        if idx != len(self.chunks):
            raise ExportProtocolError("CHUNK_OUT_OF_ORDER", "chunk", str(idx),
                expected=str(len(self.chunks)), got=str(idx))

        # Size check
        current_total = sum(len(v) for v in self.chunks.values()) + len(data)
        if current_total > self.begin["total_chars"]:
            raise ExportProtocolError("CHUNK_OVERFLOW", "chunk",
                current=current_total, max=self.begin["total_chars"])

        self.chunks[idx] = data
        return None

    def _done(self, evt):
        if self.begin is None:
            raise ExportProtocolError("DONE_BEFORE_BEGIN", "done", "no_begin")
        self._check_ids(evt, "done")

        # Verify done metadata matches begin
        chk = _required_int(evt, "chunkCount", "done")
        fl  = _required_int(evt, "frameLength", "done")
        sha = _required_str(evt, "frameSha256", "done").lower()
        tc  = _required_int(evt, "totalEncodedChars", "done")

        if (chk != self.begin["chunk_count"] or fl != self.begin["frame_length"]
            or sha != self.begin["frame_sha256"] or tc != self.begin["total_chars"]):
            raise ExportProtocolError("DONE_METADATA_MISMATCH", "done",
                begin_chunks=self.begin["chunk_count"], done_chunks=chk)

        # Check all chunks present
        if len(self.chunks) != self.begin["chunk_count"]:
            raise ExportProtocolError("MISSING_CHUNKS", "done", "incomplete",
                have=len(self.chunks), need=self.begin["chunk_count"])

        # Concatenate and decode
        encoded = "".join(self.chunks[i] for i in range(self.begin["chunk_count"]))
        if len(encoded) != tc:
            raise ExportProtocolError("ENCODED_LEN_MISMATCH", "done",
                got=len(encoded), expected=tc)

        raw = _strict_base64_decode(encoded)
        if len(raw) != fl:
            raise ExportProtocolError("RAW_LEN_MISMATCH", "done",
                got=len(raw), expected=fl)

        raw_sha = hashlib.sha256(raw).hexdigest()
        if raw_sha != sha:
            raise ExportProtocolError("RAW_SHA_MISMATCH", "done",
                got=raw_sha[:16], expected=sha[:16])

        # Validate 22H frame structure
        vr = fv.validate_frame(raw)
        if not vr["valid"]:
            raise ExportProtocolError("FRAME_INVALID", "done", vr["reason"])

        self.done = True
        return raw


def _strict_base64_decode(encoded):
    try:
        encoded.encode("ascii")
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as e:
        raise ExportProtocolError("BASE64_DECODE_FAILED", "base64", type(e).__name__)


def make_public_fake_22h_frame(payload_len=20):
    """Build a public test 22H frame for simulated capture. NOT a real IR code."""
    payload = bytes([(i * 17 + 3) & 0xFF for i in range(payload_len)])
    total = len(payload) + 7
    frame = bytearray([0x68, total & 0xFF, (total >> 8) & 0xFF, 0x00, 0x22])
    frame.extend(payload)
    frame.append(sum(frame[3:]) & 0xFF)
    frame.append(0x16)
    return bytes(frame)


def frame_to_export_events(request_id, session_id, export_id, frame):
    """Convert a frame to a sequence of export events (begin + chunks + done)."""
    import math
    raw = bytes(frame)
    encoded = base64.b64encode(raw).decode("ascii")
    chunk_count = max(1, math.ceil(len(encoded) / 900))
    chunk_size = math.ceil(len(encoded) / chunk_count)
    sha = hashlib.sha256(raw).hexdigest()

    events = [{
        "event": EXPORT_BEGIN, "requestId": request_id, "sessionId": session_id,
        "exportId": export_id, "encoding": "base64", "frameLength": len(raw),
        "frameSha256": sha, "chunkCount": chunk_count, "totalEncodedChars": len(encoded),
    }]
    for i in range(chunk_count):
        chunk_data = encoded[i * chunk_size: (i + 1) * chunk_size]
        events.append({
            "event": EXPORT_CHUNK, "requestId": request_id, "sessionId": session_id,
            "exportId": export_id, "index": i, "count": chunk_count,
            "encoding": "base64", "data": chunk_data,
        })
    events.append({
        "event": EXPORT_DONE, "requestId": request_id, "sessionId": session_id,
        "exportId": export_id, "encoding": "base64", "frameLength": len(raw),
        "frameSha256": sha, "chunkCount": chunk_count, "totalEncodedChars": len(encoded),
    })
    return events
