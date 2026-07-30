"""ZJ-IR-V2 22H frame validator. Checks header/length/AFN/checksum/tail."""
import hashlib

FRAME_HEADER = 0x68
FRAME_TAIL = 0x16
AFN_EXT_SEND = 0x22
MIN_FRAME = 7
MAX_FRAME = 832


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_frame(frame: bytes) -> dict:
    """Validate a complete 22H frame. Returns result dict."""
    length = len(frame)
    r = {
        "valid": False, "length": length, "sha256": sha256hex(frame),
        "header_ok": False, "length_ok": False, "afn_ok": False,
        "checksum_ok": False, "tail_ok": False, "reason": "ok"
    }
    if length < MIN_FRAME:
        r["reason"] = "frame_too_short"; return r
    if length > MAX_FRAME:
        r["reason"] = "frame_too_long"; return r

    r["header_ok"] = frame[0] == FRAME_HEADER
    if not r["header_ok"]:
        r["reason"] = "bad_header"; return r

    declared = frame[1] | (frame[2] << 8)
    r["length_ok"] = declared == length
    if not r["length_ok"]:
        r["reason"] = "bad_length"; return r

    if length < 5:
        r["reason"] = "frame_too_short_for_afn"; return r
    r["afn_ok"] = frame[4] == AFN_EXT_SEND
    if not r["afn_ok"]:
        r["reason"] = "bad_afn"; return r

    if length < 2:
        r["reason"] = "frame_too_short_for_cs"; return r
    expected_cs = sum(frame[3:length - 2]) & 0xFF
    actual_cs = frame[length - 2]
    r["checksum_ok"] = expected_cs == actual_cs
    if not r["checksum_ok"]:
        r["reason"] = "bad_checksum"; return r

    r["tail_ok"] = frame[length - 1] == FRAME_TAIL
    if not r["tail_ok"]:
        r["reason"] = "bad_tail"; return r

    r["valid"] = True
    return r


def diff_frames(a: bytes, b: bytes) -> dict:
    """Compare two frames byte-by-byte."""
    max_len = max(len(a), len(b))
    offsets = []
    for i in range(max_len):
        av = a[i] if i < len(a) else None
        bv = b[i] if i < len(b) else None
        if av != bv:
            offsets.append(i)
    return {
        "same_length": len(a) == len(b),
        "same_content": not offsets and len(a) == len(b),
        "diff_count": len(offsets),
        "first_diff": offsets[0] if offsets else None,
        "last_diff": offsets[-1] if offsets else None,
        "diff_offsets": offsets[:20],
    }
