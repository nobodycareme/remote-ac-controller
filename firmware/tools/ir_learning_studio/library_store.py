#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Private IR library storage, validation, migration, and firmware include generation."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Tuple

import model
import protocol

CANONICAL_002_CODE_ID = "hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1"
CANONICAL_002_SHA256 = "e9ab43feca71acde248df5729d0cb0d228bdbcfb69f8513d43ea4b942cb6ac7e"
CANONICAL_002_LENGTH = 418


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    firmware_root: Path
    library_root: Path
    generated_dir: Path
    capture_002: Path
    evidence_root: Path
    read_only: bool = False
    read_only_reason: str = ""


@dataclass(frozen=True)
class CaptureRecord:
    capture_id: str
    capture_index: int
    raw_path: Path
    metadata_path: Path
    sha256: str
    length: int


def discover_paths() -> ProjectPaths:
    here = Path(__file__).resolve()
    firmware_root = here.parents[2]
    project_root = here.parents[4]
    valid_root = _is_valid_project_root(project_root)
    read_only = not valid_root
    return ProjectPaths(
        project_root=project_root,
        firmware_root=firmware_root,
        library_root=project_root / "Private" / "Firmware" / "IR" / "Library",
        generated_dir=firmware_root / "src" / "private_ir_codes" / "generated",
        capture_002=project_root / "Private" / "Firmware" / "IR" / "CAPTURE_002.bin",
        evidence_root=project_root / "Private" / "Evidence",
        read_only=read_only,
        read_only_reason="" if valid_root else "READ_ONLY_DEMO_INVALID_PROJECT_ROOT",
    )


def _is_valid_project_root(project_root: Path) -> bool:
    project_root = Path(project_root)
    forbidden = {"Deliverables", "PackageValidation"}
    if any(part in forbidden for part in project_root.parts):
        return False
    return (
        (project_root / "Firmware" / "Remote_AC_Controller").exists()
        and (project_root / "Firmware" / "Remote_AC_Controller" / "tools" / "dev.ps1").exists()
        and (project_root / "Private" / "Firmware" / "IR").exists()
    )


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def ensure_library(paths: Optional[ProjectPaths] = None) -> None:
    paths = paths or discover_paths()
    if paths.read_only:
        raise PermissionError(paths.read_only_reason or "READ_ONLY_DEMO")
    (paths.library_root / "states").mkdir(parents=True, exist_ok=True)
    manifest = paths.library_root / "library_manifest.json"
    if not manifest.exists():
        atomic_write_json(
            manifest,
            {
                "schemaVersion": 1,
                "libraryName": "Private AC IR Library",
                "createdAt": utc_now_iso(),
                "storagePolicy": "private-local-only",
                "rawFrameGitPolicy": "never-track-private-ir-frames",
            },
        )


def safe_state_dir(paths: ProjectPaths, code_id: str) -> Path:
    ok, msg = model.validate_code_id(code_id)
    if not ok:
        raise ValueError(msg)
    states = (paths.library_root / "states").resolve()
    target = (states / code_id).resolve()
    if states not in target.parents and target != states:
        raise ValueError("path traversal rejected")
    return target


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if hashlib.sha256(tmp.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise IOError("atomic write verification failed")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, data: Dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def save_definition(definition: Dict, paths: Optional[ProjectPaths] = None) -> Path:
    paths = paths or discover_paths()
    ensure_library(paths)
    definition = model.normalize_for_display(definition)
    errors = model.validate_for_approval(definition) if definition.get("status") == "approved" else model.validate_definition(definition)
    if errors:
        raise ValueError("; ".join(errors))
    state_dir = safe_state_dir(paths, definition["codeId"])
    definition_path = state_dir / "definition.json"
    if definition_path.exists():
        existing = _read_json(definition_path)
        if existing.get("status") == "approved" and existing != definition:
            raise PermissionError("approved definition is immutable; fork a new version")
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(definition_path, definition)
    notes = state_dir / "notes.md"
    if not notes.exists():
        atomic_write_text(notes, f"# {definition['displayName']}\n\n")
    return state_dir / "definition.json"


def add_capture(
    code_id: str,
    frame: bytes,
    metadata: Dict,
    paths: Optional[ProjectPaths] = None,
) -> CaptureRecord:
    paths = paths or discover_paths()
    ensure_library(paths)
    state_dir = safe_state_dir(paths, code_id)
    definition_path = state_dir / "definition.json"
    if not definition_path.exists():
        raise FileNotFoundError(f"definition missing for {code_id}")
    definition = _read_json(definition_path)
    if definition.get("status") == "approved":
        raise PermissionError("approved state cannot append capture; fork a new version")
    errors = model.validate_for_capture(definition)
    if errors:
        raise ValueError("; ".join(errors))
    validation = protocol.validate_frame_or_raise("library_store", frame)
    captures_dir = state_dir / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    capture_index = _next_capture_index(captures_dir)
    capture_id = f"capture_{capture_index:03d}"
    bin_path = captures_dir / f"{capture_id}.bin"
    json_path = captures_dir / f"{capture_id}.json"
    if bin_path.exists() or json_path.exists():
        raise FileExistsError(f"capture already exists: {capture_id}")
    record = {
        "schemaVersion": 1,
        "captureId": capture_id,
        "codeId": code_id,
        "captureIndex": capture_index,
        "capturedAt": metadata.get("capturedAt") or utc_now_iso(),
        "deviceMac": metadata.get("deviceMac", ""),
        "firmwareCommit": metadata.get("firmwareCommit", ""),
        "firmwareProfile": metadata.get("firmwareProfile", ""),
        "serialPort": metadata.get("serialPort", ""),
        "usbVid": metadata.get("usbVid", "1A86"),
        "usbPid": metadata.get("usbPid", "55D4"),
        "irModuleModel": metadata.get("irModuleModel", "ZJ-IR-V2"),
        "irUartBaud": metadata.get("irUartBaud", 19200),
        "learnSessionId": metadata.get("learnSessionId", ""),
        "learnStartAt": metadata.get("learnStartAt", ""),
        "learnCompletedAt": metadata.get("learnCompletedAt", metadata.get("capturedAt") or utc_now_iso()),
        "learnExitConfirmed": bool(metadata.get("learnExitConfirmed", False)),
        "rawFile": f"captures/{capture_id}.bin",
        **validation.as_metadata(),
    }
    atomic_write_bytes(bin_path, frame)
    if protocol.sha256_bytes(bin_path.read_bytes()) != validation.frame_sha256:
        raise IOError("capture hash verification failed after atomic write")
    atomic_write_json(json_path, record)
    _refresh_validation(state_dir)
    _update_definition_status_after_capture(definition_path)
    return CaptureRecord(
        capture_id=capture_id,
        capture_index=capture_index,
        raw_path=bin_path,
        metadata_path=json_path,
        sha256=validation.frame_sha256,
        length=validation.frame_length,
    )


def approve_canonical(
    code_id: str,
    source_capture_id: str,
    approved_by: str,
    notes: str = "",
    paths: Optional[ProjectPaths] = None,
) -> Path:
    paths = paths or discover_paths()
    ensure_library(paths)
    state_dir = safe_state_dir(paths, code_id)
    definition = _read_json(state_dir / "definition.json")
    if definition.get("status") == "approved":
        raise PermissionError("approved canonical is immutable; fork a new version")
    errors = model.validate_for_approval(definition)
    if errors:
        raise ValueError("; ".join(errors))
    capture_id = str(source_capture_id)
    if not re_match(r"^capture_[0-9]{3}$", capture_id):
        raise ValueError("source_capture_id must be capture_NNN")
    capture_index = int(capture_id.split("_")[1])
    capture_bin = state_dir / "captures" / f"{capture_id}.bin"
    capture_json = state_dir / "captures" / f"{capture_id}.json"
    if not capture_bin.exists() or not capture_json.exists():
        raise FileNotFoundError(f"canonical source does not exist: {capture_id}")
    source_bytes = capture_bin.read_bytes()
    validation = protocol.validate_frame_or_raise("canonical_source", source_bytes)
    source_sha = protocol.sha256_bytes(source_bytes)
    definition_sha = protocol.sha256_bytes(
        json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    approved_dir = state_dir / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    canonical_bin = approved_dir / "canonical.bin"
    canonical_json = approved_dir / "canonical.json"
    atomic_write_bytes(canonical_bin, source_bytes)
    written = canonical_bin.read_bytes()
    if written != source_bytes:
        raise IOError("canonical byte proof failed")
    canonical_sha = protocol.sha256_bytes(written)
    if canonical_sha != source_sha:
        raise IOError("canonical hash proof failed")
    canonical_meta = {
        "schemaVersion": 1,
        "codeId": code_id,
        "approvedAt": utc_now_iso(),
        "approvedBy": approved_by or "local_user",
        "sourceCaptureId": capture_id,
        "sourceCaptureIndex": capture_index,
        "sourceCaptureSha256": source_sha,
        "canonicalSha256": canonical_sha,
        "definitionSha256": definition_sha,
        "frameLength": validation.frame_length,
        "frameSha256": validation.frame_sha256,
        "validation": validation.as_metadata(),
        "userNotes": notes,
    }
    atomic_write_json(canonical_json, canonical_meta)
    definition["status"] = "approved"
    definition["canonical"] = {
        "sourceCaptureId": capture_id,
        "sourceCaptureSha256": source_sha,
        "canonicalSha256": canonical_sha,
        "definitionSha256": definition_sha,
        "frameLength": validation.frame_length,
        "frameSha256": validation.frame_sha256,
        "approvedAt": canonical_meta["approvedAt"],
        "approvedBy": canonical_meta["approvedBy"],
    }
    atomic_write_json(state_dir / "definition.json", definition)
    _refresh_validation(state_dir)
    return canonical_json


def migrate_existing_capture_002(paths: Optional[ProjectPaths] = None) -> Dict:
    paths = paths or discover_paths()
    ensure_library(paths)
    if not paths.capture_002.exists():
        raise FileNotFoundError(paths.capture_002)
    data = paths.capture_002.read_bytes()
    validation = protocol.validate_frame(data)
    if len(data) != CANONICAL_002_LENGTH or validation.frame_sha256 != CANONICAL_002_SHA256:
        raise ValueError("existing CAPTURE_002 identity mismatch")
    if not validation.full_frame_valid:
        raise ValueError("existing CAPTURE_002 frame validation failed")

    definition = model.default_definition()
    definition.update(
        {
            "codeId": CANONICAL_002_CODE_ID,
            "displayName": "海信制冷24℃ 静音 上下扫风开启 左右扫风开启",
            "brand": "Hisense",
            "deviceModel": "",
            "remoteModel": "",
            "remoteDisplayText": "unknown",
            "triggerButton": "unknown",
            "notes": "由已完成 3 次真实物理验证的 CAPTURE_002.bin 只读迁移登记。",
            "status": "approved",
            "physicalValidation": {
                "testCount": 3,
                "successCount": 3,
                "passed": True,
                "validatedByUser": True,
            },
            "unknownApprovalConfirmed": True,
        }
    )
    definition["state"].update(
        {
            "power": "on",
            "mode": "cool",
            "targetTemperatureC": "24",
            "fanSpeed": "silent",
            "quietMode": "on",
            "swingVertical": "on",
            "swingHorizontal": "on",
            "turboMode": "off",
            "sleepMode": "off",
            "ecoMode": "off",
            "auxHeat": "N/A",
            "displayLight": "N/A",
            "timer": "off",
        }
    )
    state_dir = safe_state_dir(paths, CANONICAL_002_CODE_ID)
    captures_dir = state_dir / "captures"
    approved_dir = state_dir / "approved"
    captures_dir.mkdir(parents=True, exist_ok=True)
    approved_dir.mkdir(parents=True, exist_ok=True)

    atomic_write_json(state_dir / "definition.json", definition)
    capture_bin = captures_dir / "capture_001.bin"
    capture_json = captures_dir / "capture_001.json"
    canonical_bin = approved_dir / "canonical.bin"
    canonical_json = approved_dir / "canonical.json"
    _write_private_binary_if_missing_or_same(capture_bin, data, CANONICAL_002_SHA256)
    _write_private_binary_if_missing_or_same(canonical_bin, data, CANONICAL_002_SHA256)
    capture_record = {
        "schemaVersion": 1,
        "captureId": "capture_001",
        "codeId": CANONICAL_002_CODE_ID,
        "captureIndex": 1,
        "capturedAt": "2026-07-22T00:00:00+08:00",
        "deviceMac": "",
        "firmwareCommit": "",
        "firmwareProfile": "ir-lab",
        "serialPort": "",
        "usbVid": "1A86",
        "usbPid": "55D4",
        "irModuleModel": "ZJ-IR-V2",
        "irUartBaud": 19200,
        "learnSessionId": "existing_capture_002_migration",
        "learnStartAt": "",
        "learnCompletedAt": "",
        "learnExitConfirmed": True,
        "rawFile": "captures/capture_001.bin",
        "legacySource": str(paths.capture_002),
        "physicalValidation": definition["physicalValidation"],
        **validation.as_metadata(),
    }
    atomic_write_json(capture_json, capture_record)
    atomic_write_json(
        canonical_json,
        {
            "schemaVersion": 1,
            "codeId": CANONICAL_002_CODE_ID,
            "approvedAt": utc_now_iso(),
            "approvedBy": "user-confirmed-physical-validation",
            "sourceCaptureId": "capture_001",
            "sourceCaptureIndex": 1,
            "sourceCaptureSha256": validation.frame_sha256,
            "canonicalSha256": validation.frame_sha256,
            "definitionSha256": protocol.sha256_bytes(
                json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
            "frameLength": validation.frame_length,
            "frameSha256": validation.frame_sha256,
            "validation": validation.as_metadata(),
            "legacySource": str(paths.capture_002),
            "physicalValidation": definition["physicalValidation"],
        },
    )
    definition["canonical"] = {
        "sourceCaptureId": "capture_001",
        "sourceCaptureSha256": validation.frame_sha256,
        "canonicalSha256": validation.frame_sha256,
        "definitionSha256": protocol.sha256_bytes(
            json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "frameLength": validation.frame_length,
        "frameSha256": validation.frame_sha256,
        "approvedAt": utc_now_iso(),
        "approvedBy": "user-confirmed-physical-validation",
    }
    atomic_write_json(state_dir / "definition.json", definition)
    _refresh_validation(state_dir)
    return {
        "EXISTING_CAPTURE_002_MIGRATION_PASS": True,
        "EXISTING_CAPTURE_002_SHA_UNCHANGED": protocol.sha256_bytes(paths.capture_002.read_bytes()) == CANONICAL_002_SHA256,
        "EXISTING_CAPTURE_002_LENGTH": len(data),
        "stateDir": str(state_dir),
    }


def fork_approved_state(source_code_id: str, paths: Optional[ProjectPaths] = None) -> Dict:
    paths = paths or discover_paths()
    ensure_library(paths)
    source_dir = safe_state_dir(paths, source_code_id)
    definition_path = source_dir / "definition.json"
    if not definition_path.exists():
        raise FileNotFoundError(f"definition missing for {source_code_id}")
    definition = _read_json(definition_path)
    if definition.get("status") != "approved":
        raise ValueError("only approved states require version fork")
    base = re_match(r"^(.*)_v([0-9]+)$", source_code_id)
    if not base:
        raise ValueError("source codeId must end in _vN")
    prefix = base.group(1)
    highest = int(base.group(2))
    states_root = paths.library_root / "states"
    for item in states_root.glob(prefix + "_v*"):
        m = re_match(r"_v([0-9]+)$", item.name)
        if m:
            highest = max(highest, int(m.group(1)))
    new_code_id = f"{prefix}_v{highest + 1}"
    new_definition = model.normalize_for_display(definition)
    new_definition["codeId"] = new_code_id
    new_definition["status"] = "draft"
    new_definition.pop("canonical", None)
    new_definition.pop("physicalValidation", None)
    new_definition.pop("unknownApprovalConfirmed", None)
    target = safe_state_dir(paths, new_code_id)
    if target.exists():
        raise FileExistsError(f"target version already exists: {new_code_id}")
    target.mkdir(parents=True)
    atomic_write_json(target / "definition.json", new_definition)
    atomic_write_text(target / "notes.md", f"# Forked from {source_code_id}\n\n")
    return new_definition


def validate_library(paths: Optional[ProjectPaths] = None, git_tracked_private_override: Optional[int] = None) -> Dict:
    paths = paths or discover_paths()
    report = {
        "TOTAL_STATE_COUNT": 0,
        "DRAFT_STATE_COUNT": 0,
        "CAPTURED_STATE_COUNT": 0,
        "APPROVED_STATE_COUNT": 0,
        "TOTAL_CAPTURE_COUNT": 0,
        "INVALID_CAPTURE_COUNT": 0,
        "DUPLICATE_CODE_ID_COUNT": 0,
        "MISSING_FILE_COUNT": 0,
        "HASH_MISMATCH_COUNT": 0,
        "FRAME_VALIDATION_FAIL_COUNT": 0,
        "GIT_TRACKED_PRIVATE_FILE_COUNT": 0,
        "ORPHAN_FILE_COUNT": 0,
        "DUPLICATE_SAMPLE_COUNT": 0,
        "LIBRARY_VALIDATION_PASS": False,
        "CANONICAL_PROVENANCE_PASS": False,
        "issues": [],
    }
    if paths.read_only:
        report["LIBRARY_VALIDATION_PASS"] = True
        report["CANONICAL_PROVENANCE_PASS"] = True
        report["READ_ONLY_DEMO"] = True
        return report
    ensure_library(paths)
    code_ids = set()
    state_dirs = sorted((paths.library_root / "states").glob("*"))
    hashes_seen: Dict[str, str] = {}
    for state_dir in state_dirs:
        if not state_dir.is_dir():
            continue
        report["TOTAL_STATE_COUNT"] += 1
        definition_path = state_dir / "definition.json"
        if not definition_path.exists():
            report["MISSING_FILE_COUNT"] += 1
            report["issues"].append(f"{state_dir.name}: missing definition.json")
            continue
        try:
            definition = _read_json(definition_path)
        except Exception as exc:
            report["INVALID_CAPTURE_COUNT"] += 1
            report["issues"].append(f"{state_dir.name}: invalid definition json: {exc}")
            continue
        code_id = definition.get("codeId", state_dir.name)
        if code_id in code_ids:
            report["DUPLICATE_CODE_ID_COUNT"] += 1
            report["issues"].append(f"{code_id}: duplicate codeId")
        code_ids.add(code_id)
        if state_dir.name != code_id:
            report["issues"].append(f"{code_id}: directory name does not match codeId")
        errors = model.validate_definition(definition, for_approval=definition.get("status") == "approved")
        if errors:
            report["INVALID_CAPTURE_COUNT"] += 1
            report["issues"].extend([f"{code_id}: {e}" for e in errors])
        status = definition.get("status")
        if status == "approved":
            report["APPROVED_STATE_COUNT"] += 1
        elif status == "captured":
            report["CAPTURED_STATE_COUNT"] += 1
        else:
            report["DRAFT_STATE_COUNT"] += 1

        captures = sorted((state_dir / "captures").glob("capture_*.json"))
        for meta_path in captures:
            report["TOTAL_CAPTURE_COUNT"] += 1
            try:
                meta = _read_json(meta_path)
            except Exception as exc:
                report["INVALID_CAPTURE_COUNT"] += 1
                report["issues"].append(f"{code_id}: invalid capture metadata {meta_path.name}: {exc}")
                continue
            raw_file = _safe_relative_path(state_dir, meta.get("rawFile", ""))
            if raw_file is None or not raw_file.exists():
                report["MISSING_FILE_COUNT"] += 1
                report["issues"].append(f"{code_id}: missing raw file for {meta_path.name}")
                continue
            raw = raw_file.read_bytes()
            actual_sha = protocol.sha256_bytes(raw)
            expected_sha = meta.get("frameSha256")
            if actual_sha != expected_sha:
                report["HASH_MISMATCH_COUNT"] += 1
                report["issues"].append(f"{code_id}: hash mismatch for {raw_file.name}")
            validation = protocol.validate_frame(raw)
            if not validation.full_frame_valid:
                report["FRAME_VALIDATION_FAIL_COUNT"] += 1
                report["issues"].append(f"{code_id}: frame invalid for {raw_file.name}: {validation.reason}")
            if actual_sha in hashes_seen and hashes_seen[actual_sha] != f"{code_id}/{raw_file.name}":
                report["DUPLICATE_SAMPLE_COUNT"] += 1
            hashes_seen[actual_sha] = f"{code_id}/{raw_file.name}"

        if status == "approved":
            canonical_json = state_dir / "approved" / "canonical.json"
            canonical_bin = state_dir / "approved" / "canonical.bin"
            if not canonical_json.exists() or not canonical_bin.exists():
                report["MISSING_FILE_COUNT"] += 1
                report["issues"].append(f"{code_id}: missing canonical files")
            else:
                canonical = _read_json(canonical_json)
                src = canonical.get("sourceCaptureId")
                source_bin = state_dir / "captures" / f"{src}.bin"
                if not src or not source_bin.exists():
                    report["MISSING_FILE_COUNT"] += 1
                    report["issues"].append(f"{code_id}: canonical source missing")
                    source_bytes = None
                else:
                    source_bytes = source_bin.read_bytes()
                validation = protocol.validate_frame(canonical_bin.read_bytes())
                if not validation.full_frame_valid:
                    report["FRAME_VALIDATION_FAIL_COUNT"] += 1
                    report["issues"].append(f"{code_id}: canonical frame invalid: {validation.reason}")
                canonical_sha = validation.frame_sha256
                if canonical_sha != canonical.get("frameSha256"):
                    report["HASH_MISMATCH_COUNT"] += 1
                    report["issues"].append(f"{code_id}: canonical hash mismatch")
                if source_bytes is not None:
                    source_sha = protocol.sha256_bytes(source_bytes)
                    canonical_bytes = canonical_bin.read_bytes()
                    if canonical_bytes != source_bytes:
                        report["HASH_MISMATCH_COUNT"] += 1
                        report["issues"].append(f"{code_id}: canonical bytes differ from source capture")
                    if canonical.get("sourceCaptureSha256") != source_sha:
                        report["HASH_MISMATCH_COUNT"] += 1
                        report["issues"].append(f"{code_id}: sourceCaptureSha256 mismatch")
                    if canonical.get("canonicalSha256") != canonical_sha:
                        report["HASH_MISMATCH_COUNT"] += 1
                        report["issues"].append(f"{code_id}: canonicalSha256 mismatch")

        report["ORPHAN_FILE_COUNT"] += _count_orphans(state_dir)

    report["GIT_TRACKED_PRIVATE_FILE_COUNT"] = (
        git_tracked_private_override
        if git_tracked_private_override is not None
        else _git_tracked_private_count(paths)
    )
    fail_keys = [
        "INVALID_CAPTURE_COUNT",
        "DUPLICATE_CODE_ID_COUNT",
        "MISSING_FILE_COUNT",
        "HASH_MISMATCH_COUNT",
        "FRAME_VALIDATION_FAIL_COUNT",
        "GIT_TRACKED_PRIVATE_FILE_COUNT",
        "ORPHAN_FILE_COUNT",
    ]
    report["LIBRARY_VALIDATION_PASS"] = all(report[k] == 0 for k in fail_keys)
    report["CANONICAL_PROVENANCE_PASS"] = report["LIBRARY_VALIDATION_PASS"]
    return report


def list_states(paths: Optional[ProjectPaths] = None) -> List[Dict]:
    paths = paths or discover_paths()
    if paths.read_only:
        return []
    ensure_library(paths)
    states: List[Dict] = []
    for definition_path in sorted((paths.library_root / "states").glob("*/definition.json")):
        definition = _read_json(definition_path)
        state_dir = definition_path.parent
        captures = list((state_dir / "captures").glob("capture_*.bin"))
        validation_path = state_dir / "validation.json"
        validation_ok = False
        if validation_path.exists():
            validation_ok = bool(_read_json(validation_path).get("allCapturesValid", False))
        states.append(
            {
                "codeId": definition.get("codeId", state_dir.name),
                "displayName": definition.get("displayName", ""),
                "status": definition.get("status", "draft"),
                "captureCount": len(captures),
                "version": _version_from_code_id(definition.get("codeId", "")),
                "validation": "pass" if validation_ok else "check",
            }
        )
    return states


def generate_firmware_include(paths: Optional[ProjectPaths] = None) -> Dict:
    paths = paths or discover_paths()
    report = validate_library(paths)
    output = paths.generated_dir / "ir_library_generated.inc"
    if not report["LIBRARY_VALIDATION_PASS"]:
        return {
            "APPROVED_CODE_COUNT": 0,
            "TOTAL_RAW_BYTES": 0,
            "TOTAL_GENERATED_BYTES": 0,
            "ESTIMATED_FLASH_USAGE": 0,
            "LARGEST_FRAME_LENGTH": 0,
            "IR_LIBRARY_GENERATE_PASS": False,
            "IR_LIBRARY_GENERATE_AUTO_BUILD": False,
            "IR_LIBRARY_GENERATE_AUTO_FLASH": False,
            "IR_LIBRARY_GENERATE_AUTO_TRANSMIT": False,
            "GENERATED_OUTPUT_CHANGED": False,
            "GENERATED_INCLUDE": str(output),
            "issues": report.get("issues", []),
        }
    approved_entries = []
    for state in list_states(paths):
        if state["status"] != "approved":
            continue
        state_dir = safe_state_dir(paths, state["codeId"])
        definition = _read_json(state_dir / "definition.json")
        canonical_bin = state_dir / "approved" / "canonical.bin"
        canonical_json = state_dir / "approved" / "canonical.json"
        if not canonical_bin.exists() or not canonical_json.exists():
            continue
        raw = canonical_bin.read_bytes()
        validation = protocol.validate_frame(raw)
        if not validation.full_frame_valid:
            continue
        approved_entries.append((definition, raw, validation))

    total_raw = sum(len(raw) for _, raw, _ in approved_entries)
    largest = max((len(raw) for _, raw, _ in approved_entries), default=0)
    lines: List[str] = [
        "// AUTO-GENERATED by tools/ir_learning_studio/cli.py.",
        "// Gitignored. Do not commit raw private IR frames.",
        "#define PRIVATE_IR_LIBRARY_GENERATED 1",
        "",
    ]
    for idx, (definition, raw, validation) in enumerate(approved_entries):
        symbol = f"kPrivateIrFrame{idx:03d}"
        lines.append(f"static const uint8_t {symbol}[] PROGMEM = {{")
        for off in range(0, len(raw), 12):
            chunk = ", ".join(f"0x{b:02X}" for b in raw[off : off + 12])
            lines.append(f"  {chunk},")
        lines.append("};")
        lines.append("")
    lines.append("static const PrivateIrCode kPrivateIrCodes[] = {")
    for idx, (definition, raw, validation) in enumerate(approved_entries):
        display = _cpp_string(definition.get("displayName", ""))
        lines.append("  {")
        lines.append(f'    "{definition["codeId"]}",')
        lines.append(f"    kPrivateIrFrame{idx:03d},")
        lines.append(f"    {len(raw)},")
        lines.append(f'    "{validation.frame_sha256}",')
        lines.append(f'    "{display}",')
        lines.append("  },")
    lines.append("};")
    lines.append(
        "static const uint8_t kPrivateIrCodeCount = "
        "static_cast<uint8_t>(sizeof(kPrivateIrCodes) / sizeof(kPrivateIrCodes[0]));"
    )
    lines.append("")
    paths.generated_dir.mkdir(parents=True, exist_ok=True)
    old_hash = protocol.sha256_bytes(output.read_bytes()) if output.exists() else ""
    atomic_write_text(output, "\n".join(lines))
    new_hash = protocol.sha256_bytes(output.read_bytes())
    generated_size = len("\n".join(lines).encode("utf-8"))
    result = {
        "APPROVED_CODE_COUNT": len(approved_entries),
        "TOTAL_RAW_BYTES": total_raw,
        "TOTAL_GENERATED_BYTES": generated_size,
        "ESTIMATED_FLASH_USAGE": total_raw,
        "LARGEST_FRAME_LENGTH": largest,
        "IR_LIBRARY_GENERATE_PASS": report["LIBRARY_VALIDATION_PASS"],
        "IR_LIBRARY_GENERATE_AUTO_BUILD": False,
        "IR_LIBRARY_GENERATE_AUTO_FLASH": False,
        "IR_LIBRARY_GENERATE_AUTO_TRANSMIT": False,
        "GENERATED_OUTPUT_CHANGED": old_hash != new_hash,
        "GENERATED_INCLUDE": str(output),
    }
    return result


def _next_capture_index(captures_dir: Path) -> int:
    existing = []
    for path in captures_dir.glob("capture_*.bin"):
        try:
            existing.append(int(path.stem.split("_")[1]))
        except Exception:
            pass
    return (max(existing) + 1) if existing else 1


def _read_json(path: Path) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _update_definition_status_after_capture(definition_path: Path) -> None:
    definition = _read_json(definition_path)
    if definition.get("status") == "draft":
        definition["status"] = "captured"
        atomic_write_json(definition_path, definition)


def _refresh_validation(state_dir: Path) -> None:
    frames = [p.read_bytes() for p in sorted((state_dir / "captures").glob("capture_*.bin"))]
    validations = [protocol.validate_frame(f).as_metadata() for f in frames]
    summary = protocol.diff_summary(frames)
    atomic_write_json(
        state_dir / "validation.json",
        {
            "schemaVersion": 1,
            "generatedAt": utc_now_iso(),
            "captureCount": len(frames),
            "allCapturesValid": all(v["fullFrameValid"] for v in validations),
            "sampleComparison": summary,
            "captures": validations,
        },
    )


def _safe_relative_path(base: Path, rel: str) -> Optional[Path]:
    if not rel or os.path.isabs(rel) or ":" in rel:
        return None
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if target == base_resolved or base_resolved in target.parents:
        return target
    return None


def _count_orphans(state_dir: Path) -> int:
    allowed = {
        "definition.json",
        "validation.json",
        "notes.md",
        "captures",
        "approved",
    }
    count = 0
    for item in state_dir.iterdir():
        if item.name not in allowed:
            count += 1
    return count


def _git_tracked_private_count(paths: ProjectPaths) -> int:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(paths.firmware_root), "ls-files"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return 0
    tracked = [line for line in out.splitlines() if "Private/Firmware/IR" in line.replace("\\", "/")]
    return len(tracked)


def _version_from_code_id(code_id: str) -> str:
    m = re_match(r"_v([0-9]+)$", code_id)
    return f"v{m.group(1)}" if m else ""


def re_match(pattern: str, text: str):
    import re

    return re.search(pattern, text or "")


def _cpp_string(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _write_private_binary_if_missing_or_same(path: Path, data: bytes, expected_sha: str) -> None:
    if path.exists():
        if protocol.sha256_bytes(path.read_bytes()) != expected_sha:
            raise ValueError(f"refusing to overwrite different private frame: {path}")
        return
    atomic_write_bytes(path, data)
