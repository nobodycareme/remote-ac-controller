#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZJ-IR-V2 external 22H frame helpers used by the local learning tool."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import time
from typing import Dict, Iterable, List, Optional

FRAME_HEADER = 0x68
FRAME_TAIL = 0x16
AFN_EXT_LEARNED_FRAME = 0x22
IR_MIN_FRAME = 7
IR_MAX_FRAME = 832
MAX_FRAME_BYTES = IR_MAX_FRAME
MAX_BASE64_CHARS = 8192
MAX_CHUNK_COUNT = 128
MAX_CHUNK_CHARS = 1024
SUPPORTED_LEARNING_PROTOCOL_VERSION = "2"

EXPORT_BEGIN_EVENT = "ir.learn.export.begin"
EXPORT_CHUNK_EVENT = "ir.learn.export.chunk"
EXPORT_DONE_EVENT = "ir.learn.export.done"
EXPORT_ERROR_EVENT = "ir.learn.export.error"


class ExportProtocolError(ValueError):
    """Sanitized protocol failure. Never includes raw frame bytes."""

    def __init__(self, code: str, stage: str, reason: str, **details: object):
        self.code = code
        self.stage = stage
        self.reason = reason
        self.details = dict(details)
        suffix = " ".join(f"{k}={v}" for k, v in sorted(self.details.items()))
        message = f"{code}: stage={stage} reason={reason}"
        if suffix:
            message += f" {suffix}"
        super().__init__(message)


@dataclass(frozen=True)
class ExportMetadata:
    request_id: str
    session_id: str
    export_id: str
    encoding: str
    chunk_count: int
    frame_length: int
    frame_sha256: str
    total_encoded_chars: int


@dataclass(frozen=True)
class FrameValidation:
    frame_length: int
    frame_sha256: str
    header_valid: bool
    length_field_valid: bool
    afn22_valid: bool
    checksum_valid: bool
    tail_valid: bool
    full_frame_valid: bool
    declared_length: Optional[int]
    checksum_expected: Optional[int]
    checksum_actual: Optional[int]
    reason: str

    def as_metadata(self) -> dict:
        return {
            "frameLength": self.frame_length,
            "frameSha256": self.frame_sha256,
            "headerValid": self.header_valid,
            "lengthFieldValid": self.length_field_valid,
            "afn22Valid": self.afn22_valid,
            "checksumValid": self.checksum_valid,
            "tailValid": self.tail_valid,
            "fullFrameValid": self.full_frame_valid,
            "declaredLength": self.declared_length,
            "checksumExpected": _hex_or_none(self.checksum_expected),
            "checksumActual": _hex_or_none(self.checksum_actual),
            "validationReason": self.reason,
        }


def _hex_or_none(value: Optional[int]) -> Optional[str]:
    return None if value is None else f"0x{value:02X}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum(frame: bytes) -> Optional[int]:
    if len(frame) < IR_MIN_FRAME:
        return None
    declared = frame[1] | (frame[2] << 8)
    if declared != len(frame):
        return None
    return sum(frame[3 : len(frame) - 2]) & 0xFF


def validate_frame(frame: bytes) -> FrameValidation:
    length = len(frame)
    digest = sha256_bytes(frame)
    declared = (frame[1] | (frame[2] << 8)) if length >= 3 else None
    embedded_cs = frame[-2] if length >= 2 else None
    actual_cs = checksum(frame)

    header_ok = length >= 1 and frame[0] == FRAME_HEADER
    length_sane = IR_MIN_FRAME <= length <= IR_MAX_FRAME
    length_ok = length_sane and declared == length
    afn_ok = length >= 5 and frame[4] == AFN_EXT_LEARNED_FRAME
    tail_ok = length >= 1 and frame[-1] == FRAME_TAIL
    cs_ok = actual_cs is not None and embedded_cs == actual_cs
    full = header_ok and length_ok and afn_ok and cs_ok and tail_ok

    reason = "ok"
    if length < IR_MIN_FRAME:
        reason = "truncated_frame"
    elif length > IR_MAX_FRAME:
        reason = "frame_too_long"
    elif not header_ok:
        reason = "bad_header"
    elif not length_ok:
        reason = "bad_length"
    elif not afn_ok:
        reason = "bad_afn"
    elif not cs_ok:
        reason = "bad_checksum"
    elif not tail_ok:
        reason = "bad_tail"

    return FrameValidation(
        frame_length=length,
        frame_sha256=digest,
        header_valid=header_ok,
        length_field_valid=length_ok,
        afn22_valid=afn_ok,
        checksum_valid=cs_ok,
        tail_valid=tail_ok,
        full_frame_valid=full,
        declared_length=declared,
        checksum_expected=embedded_cs,
        checksum_actual=actual_cs,
        reason=reason,
    )


def validate_frame_or_raise(stage: str, frame: bytes) -> FrameValidation:
    validation = validate_frame(frame)
    if not validation.full_frame_valid:
        raise ExportProtocolError(
            "FRAME_VALIDATION_FAILED",
            stage,
            validation.reason,
            frameLength=validation.frame_length,
            frameSha256=validation.frame_sha256,
        )
    return validation


def strict_base64_decode(encoded: str) -> bytes:
    try:
        encoded.encode("ascii")
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise ExportProtocolError("STRICT_BASE64_DECODE_FAILED", "base64", exc.__class__.__name__) from exc


class ExportAssembler:
    """Assemble one correlated chunked 22H export under one absolute deadline."""

    def __init__(
        self,
        request_id: str,
        session_id: str,
        export_id: str,
        deadline_monotonic: float,
    ):
        self.request_id = _required_id(request_id, "requestId")
        self.session_id = _required_id(session_id, "sessionId")
        self.export_id = _required_id(export_id, "exportId")
        self.deadline_monotonic = float(deadline_monotonic)
        self.begin: Optional[ExportMetadata] = None
        self.chunks: Dict[int, str] = {}
        self.done: Optional[ExportMetadata] = None

    def remaining_seconds(self) -> float:
        return self.deadline_monotonic - time.monotonic()

    def check_deadline(self) -> None:
        if self.remaining_seconds() <= 0:
            raise ExportProtocolError("EXPORT_TIMEOUT", "deadline", "absolute_deadline_elapsed")

    def process_event(self, event: Dict) -> Optional[bytes]:
        self.check_deadline()
        name = event.get("event")
        if name == EXPORT_BEGIN_EVENT:
            self._process_begin(event)
            return None
        if name == EXPORT_CHUNK_EVENT:
            self._process_chunk(event)
            return None
        if name == EXPORT_DONE_EVENT:
            self._process_done(event)
            return self._decode_and_validate()
        if isinstance(name, str) and name.startswith("ir.learn.export"):
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "event", "unexpected_export_event", event=name)
        return None

    def _process_begin(self, event: Dict) -> None:
        if self.begin is not None:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "begin", "duplicate_begin")
        self.begin = _metadata_from_event(event, "begin", self.request_id, self.session_id, self.export_id)

    def _process_chunk(self, event: Dict) -> None:
        if self.begin is None:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "chunk_before_begin")
        _assert_ids(event, "chunk", self.request_id, self.session_id, self.export_id)
        index = _event_int(event, "index", "chunk")
        count = _event_int(event, "count", "chunk")
        data = event.get("data")
        if count != self.begin.chunk_count:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "chunk_count_mismatch")
        if index < 0 or index >= self.begin.chunk_count:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "chunk_index_out_of_range", index=index)
        if index in self.chunks:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "duplicate_chunk", index=index)
        if index != len(self.chunks):
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "chunk_out_of_order", index=index)
        if event.get("encoding") != "base64" or not isinstance(data, str):
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "invalid_chunk_encoding")
        try:
            data.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "chunk", "chunk_not_ascii", index=index) from exc
        if len(data) > MAX_CHUNK_CHARS:
            raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", "chunk", "chunk_chars_limit", length=len(data))
        if sum(len(v) for v in self.chunks.values()) + len(data) > self.begin.total_encoded_chars:
            raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", "chunk", "encoded_size_exceeds_begin")
        self.chunks[index] = data

    def _process_done(self, event: Dict) -> None:
        if self.begin is None:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "done", "done_before_begin")
        self.done = _metadata_from_event(event, "done", self.request_id, self.session_id, self.export_id)
        if self.done != self.begin:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "done", "begin_done_metadata_mismatch")
        if len(self.chunks) != self.begin.chunk_count:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "done", "missing_chunk")

    def _decode_and_validate(self) -> bytes:
        assert self.begin is not None
        encoded = "".join(self.chunks[i] for i in range(self.begin.chunk_count))
        if len(encoded) != self.begin.total_encoded_chars:
            raise ExportProtocolError(
                "PROTOCOL_CORRELATION_ERROR",
                "base64",
                "total_encoded_chars_mismatch",
                actual=len(encoded),
                expected=self.begin.total_encoded_chars,
            )
        raw = strict_base64_decode(encoded)
        if len(raw) != self.begin.frame_length:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "frame", "frame_length_mismatch")
        actual_sha = sha256_bytes(raw)
        if actual_sha != self.begin.frame_sha256:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "frame", "frame_sha256_mismatch")
        validate_frame_or_raise("assembler", raw)
        return raw


def _metadata_from_event(
    event: Dict,
    stage: str,
    request_id: str,
    session_id: str,
    export_id: str,
) -> ExportMetadata:
    _assert_ids(event, stage, request_id, session_id, export_id)
    encoding = _event_str(event, "encoding", stage)
    chunk_count = _event_int(event, "chunkCount", stage)
    frame_length = _event_int(event, "frameLength", stage)
    frame_sha256 = _event_str(event, "frameSha256", stage)
    total_encoded_chars = _event_int(event, "totalEncodedChars", stage)
    if encoding != "base64":
        raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", stage, "unsupported_encoding")
    if chunk_count <= 0:
        raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", stage, "chunk_count_zero")
    if chunk_count > MAX_CHUNK_COUNT:
        raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", stage, "chunk_count_limit", count=chunk_count)
    if frame_length <= 0:
        raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", stage, "frame_length_zero")
    if frame_length > MAX_FRAME_BYTES:
        raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", stage, "frame_length_limit", length=frame_length)
    if total_encoded_chars <= 0 or total_encoded_chars > MAX_BASE64_CHARS:
        raise ExportProtocolError("RESOURCE_LIMIT_EXCEEDED", stage, "total_encoded_chars_limit", chars=total_encoded_chars)
    if len(frame_sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in frame_sha256):
        raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", stage, "invalid_frame_sha256")
    return ExportMetadata(
        request_id=request_id,
        session_id=session_id,
        export_id=export_id,
        encoding=encoding,
        chunk_count=chunk_count,
        frame_length=frame_length,
        frame_sha256=frame_sha256.lower(),
        total_encoded_chars=total_encoded_chars,
    )


def _assert_ids(event: Dict, stage: str, request_id: str, session_id: str, export_id: str) -> None:
    expected = {
        "requestId": request_id,
        "sessionId": session_id,
        "exportId": export_id,
    }
    for key, value in expected.items():
        actual = event.get(key)
        if actual != value:
            raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", stage, f"{key}_mismatch_or_missing")


def _event_str(event: Dict, key: str, stage: str) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value:
        raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", stage, f"missing_{key}")
    return value


def _event_int(event: Dict, key: str, stage: str) -> int:
    value = event.get(key)
    if not isinstance(value, int):
        raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", stage, f"missing_{key}")
    return value


def _required_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExportProtocolError("PROTOCOL_CORRELATION_ERROR", "ids", f"missing_{name}")
    return value


def make_frame(data: Iterable[int], addr: int = 0x00, afn: int = AFN_EXT_LEARNED_FRAME) -> bytes:
    payload = bytes(int(x) & 0xFF for x in data)
    total = len(payload) + 7
    frame = bytearray()
    frame.append(FRAME_HEADER)
    frame.append(total & 0xFF)
    frame.append((total >> 8) & 0xFF)
    frame.append(addr & 0xFF)
    frame.append(afn & 0xFF)
    frame.extend(payload)
    frame.append(sum(frame[3:]) & 0xFF)
    frame.append(FRAME_TAIL)
    return bytes(frame)


def make_public_fake_frame(payload_len: int = 11) -> bytes:
    """Build artificial test data. It is not a real air-conditioner code."""
    return make_frame(((i * 17 + 3) & 0xFF for i in range(payload_len)))


def diff_summary(frames: List[bytes]) -> dict:
    if not frames:
        return {
            "sampleCount": 0,
            "allEqual": False,
            "recommendedCanonicalIndex": None,
            "pairwise": [],
        }

    first = frames[0]
    all_equal = all(f == first for f in frames)
    pairwise = []
    for idx, frame in enumerate(frames, start=1):
        diff_offsets = _diff_offsets(first, frame)
        pairwise.append(
            {
                "captureIndex": idx,
                "length": len(frame),
                "sha256": sha256_bytes(frame),
                "sameAsFirst": not diff_offsets and len(frame) == len(first),
                "differentByteCount": len(diff_offsets),
                "differentRegionCount": _region_count(diff_offsets),
                "firstDifferentOffset": diff_offsets[0] if diff_offsets else None,
                "lastDifferentOffset": diff_offsets[-1] if diff_offsets else None,
            }
        )

    return {
        "sampleCount": len(frames),
        "allEqual": all_equal,
        "recommendedCanonicalIndex": 1 if all_equal else None,
        "pairwise": pairwise,
    }


def _diff_offsets(a: bytes, b: bytes) -> List[int]:
    max_len = max(len(a), len(b))
    offsets: List[int] = []
    for i in range(max_len):
        av = a[i] if i < len(a) else None
        bv = b[i] if i < len(b) else None
        if av != bv:
            offsets.append(i)
    return offsets


def _region_count(offsets: List[int]) -> int:
    if not offsets:
        return 0
    regions = 1
    prev = offsets[0]
    for offset in offsets[1:]:
        if offset != prev + 1:
            regions += 1
        prev = offset
    return regions
