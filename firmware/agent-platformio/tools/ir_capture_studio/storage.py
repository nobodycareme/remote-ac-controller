#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
storage.py — 采集数据落盘（第二节/二十/二十一/二十二节）

保存目录：<captures_root>/studio/<session_id>/
每个样本：capture_<NNN>.bin / .json / .txt / _serial.log
会话级：session.json + manifest.csv

不覆盖已有会话（自动加 _02/_03 安全后缀）。
不依赖 pyserial / GUI。
"""

import os
import json
import csv
import hashlib
import datetime

# 清单列（会话级 CSV，覆盖关键字段）
MANIFEST_FIELDS = [
    "sessionId", "captureId", "sampleNumber", "attemptNumber", "captureTime",
    "taskType", "customTaskName", "buttonPressed", "captureResult",
    "failureReason", "externalCodeLength", "AFN", "checksumExpected",
    "checksumActual", "checksumPass", "frameHeaderPass", "frameTailPass",
    "binLengthMatch", "uartTimeoutCount", "uartChecksumFailureCount",
    "uartOverflowCount", "uartResyncCount", "commandToPromptMs",
    "captureDurationMs", "binSha256", "replayed", "cloudTriggered",
]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def compute_sha256(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def session_dir_exists(base_dir, session_id):
    return os.path.isdir(os.path.join(base_dir, session_id))


def safe_session_dir(base_dir, session_id):
    """
    返回 (path, actual_session_id)。
    若 session_id 已存在，自动加 _02 / _03 ... 安全后缀，绝不覆盖。
    """
    ensure_dir(base_dir)
    candidate = session_id
    suffix = 1
    while session_dir_exists(base_dir, candidate):
        suffix += 1
        candidate = "%s_%02d" % (session_id, suffix)
    path = os.path.join(base_dir, candidate)
    os.makedirs(path, exist_ok=True)
    return path, candidate


def _write_file(path, data, mode="wb"):
    with open(path, mode) as f:
        f.write(data)


def build_txt(record, bin_hex):
    lines = []
    lines.append("IR LEARNING CAPTURE STUDIO — %s" % record.get("captureId", ""))
    lines.append("session_id      : %s" % record.get("sessionId", ""))
    lines.append("captured_at     : %s" % record.get("captureTime", ""))
    lines.append("schema_version  : %s" % record.get("schemaVersion", ""))
    lines.append("brand/ac/remote : %s / %s / %s" % (
        record.get("brand", ""), record.get("acModel", ""), record.get("remoteModel", "")))
    lines.append("task_type       : %s" % record.get("taskType", ""))
    lines.append("custom_task     : %s" % record.get("customTaskName", ""))
    lines.append("button_pressed  : %s" % record.get("buttonPressed", ""))
    sb = record.get("stateBefore", {})
    sa = record.get("stateAfter", {})
    lines.append("state_before    : power=%s mode=%s temp=%sC fan=%s sv=%s sh=%s qt=%s tb=%s sl=%s" % (
        sb.get("power"), sb.get("mode"), sb.get("temperatureC"), sb.get("fan"),
        sb.get("swingVertical"), sb.get("swingHorizontal"), sb.get("quiet"),
        sb.get("turbo"), sb.get("sleep")))
    lines.append("state_after     : power=%s mode=%s temp=%sC fan=%s sv=%s sh=%s qt=%s tb=%s sl=%s" % (
        sa.get("power"), sa.get("mode"), sa.get("temperatureC"), sa.get("fan"),
        sa.get("swingVertical"), sa.get("swingHorizontal"), sa.get("quiet"),
        sa.get("turbo"), sa.get("sleep")))
    lines.append("module          : %s @ %d baud" % (
        record.get("moduleModel"), record.get("moduleUartBaud")))
    lines.append("serial_port     : %s" % record.get("serialPort", ""))
    lines.append("learn_cmd       : %s" % record.get("learnCommand", ""))
    lines.append("learn_timeout_s : %s" % record.get("learnTimeoutSeconds"))
    lines.append("frame_len       : %s" % record.get("externalCodeLength"))
    lines.append("AFN             : %s" % record.get("AFN"))
    lines.append("checksum_exp    : %s" % record.get("checksumExpected"))
    lines.append("checksum_act    : %s" % record.get("checksumActual"))
    lines.append("checksum_pass   : %s" % record.get("checksumPass"))
    lines.append("header_pass     : %s" % record.get("frameHeaderPass"))
    lines.append("tail_pass       : %s" % record.get("frameTailPass"))
    lines.append("bin_len_match   : %s" % record.get("binLengthMatch"))
    lines.append("uart_timeout    : %s" % record.get("uartTimeoutCount"))
    lines.append("uart_cs_fail    : %s" % record.get("uartChecksumFailureCount"))
    lines.append("uart_overflow   : %s" % record.get("uartOverflowCount"))
    lines.append("uart_resync     : %s" % record.get("uartResyncCount"))
    lines.append("cmd_to_prompt_ms: %s" % record.get("commandToPromptMs"))
    lines.append("capture_dur_ms  : %s" % record.get("captureDurationMs"))
    lines.append("capture_result  : %s" % record.get("captureResult"))
    lines.append("failure_reason  : %s" % record.get("failureReason"))
    lines.append("ambiguous       : %s" % record.get("ambiguousResult"))
    lines.append("replayed        : %s" % record.get("replayed"))
    lines.append("cloud_triggered : %s" % record.get("cloudTriggered"))
    lines.append("bin_sha256      : %s" % record.get("binSha256"))
    lines.append("json_sha256     : %s" % record.get("jsonSha256"))
    lines.append("txt_sha256      : %s" % record.get("txtSha256"))
    lines.append("frame_hex       :")
    for i in range(0, len(bin_hex), 16):
        lines.append("  " + " ".join(bin_hex[i:i + 16]))
    if record.get("userNotes"):
        lines.append("notes           : %s" % record.get("userNotes"))
    return "\n".join(lines) + "\n"


def save_capture(session_dir, capture_id, bin_bytes, serial_log_lines, record):
    """
    保存一次成功样本。返回 dict{paths..., binSha256, jsonSha256, txtSha256, binLengthMatch}。
    bin_bytes: bytes；serial_log_lines: list[str]；record: 已含大部分字段的 dict。
    """
    ensure_dir(session_dir)
    bin_path = os.path.join(session_dir, capture_id + ".bin")
    json_path = os.path.join(session_dir, capture_id + ".json")
    txt_path = os.path.join(session_dir, capture_id + ".txt")
    log_path = os.path.join(session_dir, capture_id + "_serial.log")

    # BIN
    _write_file(bin_path, bin_bytes, "wb")
    bin_sha = compute_sha256(bin_bytes)
    bin_len_match = (os.path.getsize(bin_path) == len(bin_bytes))

    record["binSha256"] = bin_sha
    record["binLengthMatch"] = bin_len_match
    record["captureResult"] = "success"
    record["replayed"] = False
    record["cloudTriggered"] = False

    # JSON（先写一次取 sha，再写回 sha 字段）
    json_body = json.dumps(record, ensure_ascii=False, indent=2)
    _write_file(json_path, json_body.encode("utf-8"), "wb")
    json_sha = compute_sha256(json_body.encode("utf-8"))
    record["jsonSha256"] = json_sha
    # 二次写入带 sha 的版本
    json_body2 = json.dumps(record, ensure_ascii=False, indent=2)
    _write_file(json_path, json_body2.encode("utf-8"), "wb")

    # TXT
    bin_hex = " ".join("%02X" % b for b in bin_bytes)
    txt_body = build_txt(record, bin_hex)
    _write_file(txt_path, txt_body.encode("utf-8"), "wb")
    txt_sha = compute_sha256(txt_body.encode("utf-8"))
    record["txtSha256"] = txt_sha

    # serial.log
    _write_file(log_path, ("\n".join(serial_log_lines) + "\n").encode("utf-8"), "wb")

    # manifest
    append_manifest(session_dir, record)

    # 终写 JSON：确保所有 sha（含 txtSha256）已落入 record
    final_json = json.dumps(record, ensure_ascii=False, indent=2)
    _write_file(json_path, final_json.encode("utf-8"), "wb")
    json_sha = compute_sha256(final_json.encode("utf-8"))
    record["jsonSha256"] = json_sha

    return {
        "bin_path": bin_path, "json_path": json_path, "txt_path": txt_path,
        "log_path": log_path, "binSha256": bin_sha, "jsonSha256": json_sha,
        "txtSha256": txt_sha, "binLengthMatch": bin_len_match,
    }


def save_failed(session_dir, capture_id, record, serial_log_lines):
    """保存一次失败诊断：仅 JSON + serial.log，绝不生成伪成功 BIN。"""
    ensure_dir(session_dir)
    json_path = os.path.join(session_dir, capture_id + ".json")
    log_path = os.path.join(session_dir, capture_id + "_serial.log")

    record["captureResult"] = "failed"
    record["replayed"] = False
    record["cloudTriggered"] = False
    record["binSha256"] = None
    record["jsonSha256"] = None
    record["txtSha256"] = None

    json_body = json.dumps(record, ensure_ascii=False, indent=2)
    _write_file(json_path, json_body.encode("utf-8"), "wb")
    json_sha = compute_sha256(json_body.encode("utf-8"))
    record["jsonSha256"] = json_sha
    _write_file(json_path, json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"), "wb")

    _write_file(log_path, ("\n".join(serial_log_lines) + "\n").encode("utf-8"), "wb")
    append_manifest(session_dir, record)
    return {"json_path": json_path, "log_path": log_path, "jsonSha256": json_sha}


def _manifest_row(record):
    row = {}
    for k in MANIFEST_FIELDS:
        v = record.get(k, "")
        if isinstance(v, bool):
            v = "True" if v else "False"
        if v is None:
            v = ""
        row[k] = v
    return row


def append_manifest(session_dir, record):
    ensure_dir(session_dir)
    path = os.path.join(session_dir, "manifest.csv")
    exists = os.path.exists(path)
    row = _manifest_row(record)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def save_session_json(session_dir, session_record):
    ensure_dir(session_dir)
    path = os.path.join(session_dir, "session.json")
    body = json.dumps(session_record, ensure_ascii=False, indent=2)
    _write_file(path, body.encode("utf-8"), "wb")
    return path
