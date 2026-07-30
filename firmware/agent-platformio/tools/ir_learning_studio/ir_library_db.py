#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transactional SQLite authoritative private IR library.

This replaces the file-based library_store.py storage model.
SQLite is the single source of truth. File exports are read-only snapshots
that can be fully reconstructed from the database.

Schema version: 1
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import model
import protocol

# ---- Constants ----

SCHEMA_VERSION = 1
DB_FILENAME = "ir_library.sqlite3"

CANONICAL_002_CODE_ID = "hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1"
CANONICAL_002_SHA256 = "e9ab43feca71acde248df5729d0cb0d228bdbcfb69f8513d43ea4b942cb6ac7e"
CANONICAL_002_LENGTH = 418

VALID_STATUSES = ("draft", "captured", "approved", "retired")

# ---- Schema DDL ----

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS library_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS states (
    state_id                  TEXT PRIMARY KEY,
    code_id                   TEXT NOT NULL UNIQUE,
    logical_key               TEXT NOT NULL,
    version                   INTEGER NOT NULL,
    display_name              TEXT NOT NULL,
    definition_json           TEXT NOT NULL,
    definition_sha256         TEXT NOT NULL,
    status                    TEXT NOT NULL,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    approved_at               TEXT,
    forked_from_state_id      TEXT,
    physical_validation_json  TEXT,
    row_version               INTEGER NOT NULL DEFAULT 1,
    CHECK (status IN ('draft','captured','approved','retired')),
    CHECK (version >= 1),
    UNIQUE (logical_key, version),
    FOREIGN KEY (forked_from_state_id) REFERENCES states(state_id)
);

CREATE TABLE IF NOT EXISTS captures (
    capture_id        TEXT PRIMARY KEY,
    state_id          TEXT NOT NULL,
    capture_index     INTEGER NOT NULL,
    frame_blob        BLOB NOT NULL,
    frame_length      INTEGER NOT NULL,
    frame_sha256      TEXT NOT NULL,
    captured_at       TEXT NOT NULL,
    device_mac        TEXT NOT NULL,
    firmware_commit   TEXT NOT NULL,
    firmware_profile  TEXT NOT NULL,
    module_model      TEXT NOT NULL,
    uart_baud         INTEGER NOT NULL,
    request_id        TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    export_id         TEXT NOT NULL,
    validation_json   TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (state_id) REFERENCES states(state_id),
    UNIQUE (state_id, capture_index),
    CHECK (frame_length > 0),
    CHECK (uart_baud = 19200)
);

CREATE TABLE IF NOT EXISTS canonical_selections (
    state_id          TEXT PRIMARY KEY,
    capture_id        TEXT NOT NULL UNIQUE,
    capture_sha256    TEXT NOT NULL,
    definition_sha256 TEXT NOT NULL,
    approved_at       TEXT NOT NULL,
    approved_by       TEXT NOT NULL,
    approval_note     TEXT,
    FOREIGN KEY (state_id)   REFERENCES states(state_id),
    FOREIGN KEY (capture_id) REFERENCES captures(capture_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    state_id      TEXT,
    capture_id    TEXT,
    occurred_at   TEXT NOT NULL,
    actor         TEXT NOT NULL,
    details_json  TEXT NOT NULL,
    previous_hash TEXT,
    entry_hash    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT NOT NULL,
    migration_sha256 TEXT NOT NULL
);

-- === Trigger: prevent approved state mutation ===

CREATE TRIGGER IF NOT EXISTS trg_states_no_update_approved_definition
BEFORE UPDATE ON states
WHEN OLD.status = 'approved'
  AND (NEW.definition_json != OLD.definition_json
    OR NEW.definition_sha256 != OLD.definition_sha256
    OR NEW.code_id != OLD.code_id
    OR NEW.version != OLD.version)
BEGIN
    SELECT RAISE(ABORT, 'APPROVED_STATE_IMMUTABLE: cannot modify definition of approved state');
END;

CREATE TRIGGER IF NOT EXISTS trg_states_no_delete_approved
BEFORE DELETE ON states
WHEN OLD.status = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'APPROVED_STATE_IMMUTABLE: cannot delete approved state');
END;

CREATE TRIGGER IF NOT EXISTS trg_captures_no_insert_on_approved
BEFORE INSERT ON captures
WHEN (SELECT status FROM states WHERE state_id = NEW.state_id) = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'APPROVED_STATE_IMMUTABLE: cannot add capture to approved state');
END;

CREATE TRIGGER IF NOT EXISTS trg_captures_no_delete_on_approved
BEFORE DELETE ON captures
WHEN (SELECT status FROM states WHERE state_id = OLD.state_id) = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'APPROVED_STATE_IMMUTABLE: cannot delete capture from approved state');
END;

CREATE TRIGGER IF NOT EXISTS trg_canonical_no_update
BEFORE UPDATE ON canonical_selections
BEGIN
    SELECT RAISE(ABORT, 'CANONICAL_IMMUTABLE: cannot modify canonical selection');
END;

CREATE TRIGGER IF NOT EXISTS trg_canonical_no_delete
BEFORE DELETE ON canonical_selections
BEGIN
    SELECT RAISE(ABORT, 'CANONICAL_IMMUTABLE: cannot delete canonical selection');
END;

CREATE TRIGGER IF NOT EXISTS trg_canonical_same_state
BEFORE INSERT ON canonical_selections
WHEN (SELECT state_id FROM captures WHERE capture_id = NEW.capture_id) != NEW.state_id
BEGIN
    SELECT RAISE(ABORT, 'CANONICAL_CROSS_STATE: canonical must reference capture from same state');
END;
"""


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _new_uuid4() -> str:
    import uuid
    return uuid.uuid4().hex


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256(text.encode("utf-8"))


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


class IrLibraryDB:
    """Transactional SQLite authoritative private IR library."""

    def __init__(self, db_path: Path, project_root_hash: str = "", app_version: str = ""):
        self.db_path = Path(db_path)
        self.project_root_hash = project_root_hash
        self.app_version = app_version
        self._conn: Optional[sqlite3.Connection] = None
        self._write_enabled = True

    # ---- Connection management ----

    def open(self, read_only: bool = False) -> None:
        """Open the database connection with required PRAGMAs."""
        if self._conn is not None:
            return

        # Ensure parent directory exists for write connections
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        uri = f"file:{self.db_path}?mode=ro" if read_only else str(self.db_path)
        self._conn = sqlite3.connect(uri if read_only else str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        if not read_only:
            self._apply_pragmas()
            self._init_schema()
            self._ensure_meta()

    def _apply_pragmas(self) -> None:
        pragmas = [
            ("PRAGMA foreign_keys = ON;", "foreign_keys"),
            ("PRAGMA journal_mode = DELETE;", "journal_mode"),
            ("PRAGMA synchronous = EXTRA;", "synchronous"),
            ("PRAGMA busy_timeout = 5000;", "busy_timeout"),
            ("PRAGMA trusted_schema = OFF;", "trusted_schema"),
        ]
        for sql, name in pragmas:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError as exc:
                raise RuntimeError(f"PRAGMA {name} not supported: {exc}")

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA_DDL)
        self._conn.commit()

    def _ensure_meta(self) -> None:
        """Ensure library_meta has required entries."""
        meta_defaults = {
            "schema_version": str(SCHEMA_VERSION),
            "project_root_hash": self.project_root_hash,
            "application_version": self.app_version,
        }
        for key, value in meta_defaults.items():
            existing = self._conn.execute(
                "SELECT value FROM library_meta WHERE key = ?", (key,)
            ).fetchone()
            if existing is None:
                now = _utc_now()
                if key == "schema_version":
                    self._conn.execute(
                        "INSERT INTO library_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                    self._conn.execute(
                        "INSERT INTO library_meta (key, value) VALUES (?, ?)",
                        ("created_at", now),
                    )
                    self._conn.execute(
                        "INSERT INTO library_meta (key, value) VALUES (?, ?)",
                        ("last_migrated_at", now),
                    )
                else:
                    self._conn.execute(
                        "INSERT INTO library_meta (key, value) VALUES (?, ?)",
                        (key, value),
                    )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ---- Health checks ----

    def quick_check(self) -> Dict[str, Any]:
        """PRAGMA quick_check + foreign_key_check."""
        result = {"quick_check": "not_run", "foreign_key_check": "not_run", "pass": False}
        try:
            row = self._conn.execute("PRAGMA quick_check;").fetchone()
            result["quick_check"] = row[0] if row else "no_result"
        except Exception as exc:
            result["quick_check"] = f"error: {exc}"

        try:
            fk_rows = self._conn.execute("PRAGMA foreign_key_check;").fetchall()
            result["foreign_key_check"] = "ok" if not fk_rows else f"violations: {len(fk_rows)}"
        except Exception as exc:
            result["foreign_key_check"] = f"error: {exc}"

        result["pass"] = result["quick_check"] == "ok" and result["foreign_key_check"] == "ok"
        return result

    def integrity_check(self) -> Dict[str, Any]:
        """Full PRAGMA integrity_check + foreign_key_check."""
        result = {"integrity_check": "not_run", "foreign_key_check": "not_run", "pass": False}
        try:
            row = self._conn.execute("PRAGMA integrity_check;").fetchone()
            result["integrity_check"] = row[0] if row else "no_result"
        except Exception as exc:
            result["integrity_check"] = f"error: {exc}"

        try:
            fk_rows = self._conn.execute("PRAGMA foreign_key_check;").fetchall()
            result["foreign_key_check"] = "ok" if not fk_rows else f"violations: {len(fk_rows)}"
        except Exception as exc:
            result["foreign_key_check"] = f"error: {exc}"

        result["pass"] = result["integrity_check"] == "ok" and result["foreign_key_check"] == "ok"
        return result

    # ---- State operations ----

    def create_state(self, definition: Dict[str, Any]) -> str:
        """Create a new draft state. Returns state_id."""
        definition = model.normalize_for_display(definition)
        errors = model.validate_definition(definition, for_approval=False, strict=True)
        if errors:
            raise ValueError("; ".join(errors))

        code_id = definition["codeId"]
        state_id = f"state-{_new_uuid4()}"
        logical_key = _extract_logical_key(code_id)
        version = _extract_version(code_id)
        def_json = _json_dumps(definition)
        def_sha = _sha256_text(def_json)
        now = _utc_now()

        with self._conn:
            self._conn.execute(
                """INSERT INTO states (state_id, code_id, logical_key, version,
                   display_name, definition_json, definition_sha256, status,
                   created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,'draft',?,?)""",
                (state_id, code_id, logical_key, version,
                 definition.get("displayName", ""), def_json, def_sha,
                 now, now),
            )
            self._add_audit("STATE_CREATED", state_id=state_id, details={"codeId": code_id})

        return state_id

    def get_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        """Get a state by ID."""
        row = self._conn.execute(
            "SELECT * FROM states WHERE state_id = ?", (state_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_state_by_code_id(self, code_id: str) -> Optional[Dict[str, Any]]:
        """Get a state by code_id."""
        row = self._conn.execute(
            "SELECT * FROM states WHERE code_id = ?", (code_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_states(self) -> List[Dict[str, Any]]:
        """List all states with capture counts."""
        rows = self._conn.execute("""
            SELECT s.*, COUNT(c.capture_id) as capture_count
            FROM states s
            LEFT JOIN captures c ON s.state_id = c.state_id
            GROUP BY s.state_id
            ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

    # ---- Capture operations (transactional) ----

    def add_capture(
        self,
        state_id: str,
        frame: bytes,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Add a capture in a single atomic transaction.

        Transaction boundary:
        1. Read state, verify not approved
        2. Validate definition
        3. Validate 22H frame
        4. Compute next capture_index
        5. INSERT capture with BLOB and metadata
        6. Update state status to captured
        7. Write audit log
        8. Re-read and verify
        9. COMMIT
        Any failure → ROLLBACK.
        """
        validation = protocol.validate_frame_or_raise("ir_library_db", frame)
        now = _utc_now()

        with self._conn as conn:
            state = conn.execute(
                "SELECT * FROM states WHERE state_id = ?", (state_id,)
            ).fetchone()
            if state is None:
                raise ValueError(f"state not found: {state_id}")
            if state["status"] == "approved":
                raise PermissionError("approved state cannot append capture; fork a new version")

            definition = json.loads(state["definition_json"])
            errors = model.validate_for_capture(definition)
            if errors:
                raise ValueError("; ".join(errors))

            # Compute next capture_index
            max_idx_row = conn.execute(
                "SELECT MAX(capture_index) FROM captures WHERE state_id = ?",
                (state_id,),
            ).fetchone()
            capture_index = (max_idx_row[0] or 0) + 1
            capture_id = f"capture_{capture_index:03d}"

            # Check for existing capture_index conflict
            existing = conn.execute(
                "SELECT capture_id FROM captures WHERE state_id = ? AND capture_index = ?",
                (state_id, capture_index),
            ).fetchone()
            if existing:
                raise FileExistsError(f"capture_index conflict: {capture_index}")

            capture_row_id = f"cap-{_new_uuid4()}"
            sha = _sha256(frame)
            val_json = _json_dumps(validation.as_metadata())

            conn.execute(
                """INSERT INTO captures
                   (capture_id, state_id, capture_index, frame_blob, frame_length,
                    frame_sha256, captured_at, device_mac, firmware_commit,
                    firmware_profile, module_model, uart_baud, request_id,
                    session_id, export_id, validation_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    capture_row_id, state_id, capture_index,
                    frame, len(frame), sha,
                    metadata.get("capturedAt") or now,
                    metadata.get("deviceMac", ""),
                    metadata.get("firmwareCommit", ""),
                    metadata.get("firmwareProfile", ""),
                    metadata.get("irModuleModel", "ZJ-IR-V2"),
                    metadata.get("irUartBaud", 19200),
                    metadata.get("requestId", ""),
                    metadata.get("learnSessionId", ""),
                    metadata.get("exportId", ""),
                    val_json,
                    now,
                ),
            )

            # Update state status if draft
            if state["status"] == "draft":
                conn.execute(
                    "UPDATE states SET status = 'captured', updated_at = ? WHERE state_id = ?",
                    (now, state_id),
                )

            self._add_audit_tx(
                conn, "CAPTURE_ADDED", state_id=state_id,
                capture_id=capture_row_id,
                details={"captureIndex": capture_index, "frameSha256": sha},
            )

            # Verify blob was written correctly
            verify = conn.execute(
                "SELECT frame_blob, frame_sha256 FROM captures WHERE capture_id = ?",
                (capture_row_id,),
            ).fetchone()
            if verify is None:
                raise IOError("capture verification failed: row not found after insert")
            if _sha256(bytes(verify["frame_blob"])) != sha:
                raise IOError("capture blob verification failed")

        return {
            "capture_id": capture_row_id,
            "capture_index": capture_index,
            "capture_display_id": capture_id,
            "frame_sha256": sha,
            "frame_length": len(frame),
        }

    def get_captures(self, state_id: str) -> List[Dict[str, Any]]:
        """Get all captures for a state (without BLOB data)."""
        rows = self._conn.execute(
            """SELECT capture_id, state_id, capture_index, frame_length,
                      frame_sha256, captured_at, device_mac, firmware_commit,
                      firmware_profile, module_model, uart_baud, request_id,
                      session_id, export_id, validation_json, created_at
               FROM captures WHERE state_id = ?
               ORDER BY capture_index""",
            (state_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_capture_blob(self, capture_row_id: str) -> Optional[bytes]:
        """Get the raw frame BLOB for a capture."""
        row = self._conn.execute(
            "SELECT frame_blob FROM captures WHERE capture_id = ?",
            (capture_row_id,),
        ).fetchone()
        return bytes(row[0]) if row else None

    # ---- Canonical operations (transactional) ----

    def approve_canonical(
        self,
        state_id: str,
        capture_row_id: str,
        approved_by: str = "",
        approval_note: str = "",
    ) -> Dict[str, Any]:
        """Approve a capture as canonical in a single atomic transaction.

        Transaction boundary:
        1. Read state, verify status=captured
        2. Validate definition
        3. Read specified capture
        4. Re-validate frame blob
        5. Confirm capture belongs to state
        6. INSERT canonical_selection
        7. UPDATE state.status=approved
        8. Write audit log
        9. COMMIT
        """
        now = _utc_now()

        with self._conn as conn:
            state = conn.execute(
                "SELECT * FROM states WHERE state_id = ?", (state_id,)
            ).fetchone()
            if state is None:
                raise ValueError(f"state not found: {state_id}")
            if state["status"] == "approved":
                raise PermissionError("already approved; fork a new version")
            if state["status"] != "captured":
                raise ValueError(f"state must be in 'captured' status, got '{state['status']}'")

            definition = json.loads(state["definition_json"])
            errors = model.validate_for_approval(definition)
            if errors:
                raise ValueError("; ".join(errors))

            capture = conn.execute(
                "SELECT * FROM captures WHERE capture_id = ?", (capture_row_id,)
            ).fetchone()
            if capture is None:
                raise FileNotFoundError(f"capture not found: {capture_row_id}")
            if capture["state_id"] != state_id:
                raise ValueError("canonical source capture does not belong to this state")

            # Re-validate blob
            frame_bytes = bytes(capture["frame_blob"])
            validation = protocol.validate_frame_or_raise("canonical_approval", frame_bytes)
            capture_sha = _sha256(frame_bytes)
            def_sha = _sha256_text(state["definition_json"])

            # Verify existing canonical_selections for this state
            existing = conn.execute(
                "SELECT capture_id FROM canonical_selections WHERE state_id = ?",
                (state_id,),
            ).fetchone()
            if existing:
                raise PermissionError("canonical selection already exists for this state")

            # INSERT canonical_selection
            conn.execute(
                """INSERT INTO canonical_selections
                   (state_id, capture_id, capture_sha256, definition_sha256,
                    approved_at, approved_by, approval_note)
                   VALUES (?,?,?,?,?,?,?)""",
                (state_id, capture_row_id, capture_sha, def_sha,
                 now, approved_by or "local_user", approval_note),
            )

            # Update state to approved
            conn.execute(
                "UPDATE states SET status = 'approved', approved_at = ?, updated_at = ? WHERE state_id = ?",
                (now, now, state_id),
            )

            self._add_audit_tx(
                conn, "CANONICAL_APPROVED", state_id=state_id,
                capture_id=capture_row_id,
                details={
                    "captureSha256": capture_sha,
                    "definitionSha256": def_sha,
                    "approvedBy": approved_by or "local_user",
                },
            )

        return {
            "state_id": state_id,
            "capture_id": capture_row_id,
            "capture_sha256": capture_sha,
            "definition_sha256": def_sha,
            "approved_at": now,
            "approved_by": approved_by or "local_user",
        }

    def get_canonical(self, state_id: str) -> Optional[Dict[str, Any]]:
        """Get canonical selection and its capture blob for a state."""
        row = self._conn.execute(
            """SELECT cs.*, c.frame_blob, c.frame_length, c.frame_sha256
               FROM canonical_selections cs
               JOIN captures c ON cs.capture_id = c.capture_id
               WHERE cs.state_id = ?""",
            (state_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        # Convert BLOB to bytes for JSON serialization safety
        result["frame_blob"] = bytes(result["frame_blob"])
        return result

    # ---- Fork operations (transactional) ----

    def fork_approved_state(self, source_state_id: str) -> str:
        """Fork an approved state to a new version (draft).

        Transaction boundary:
        1. Read approved source state
        2. Compute next version
        3. Create new codeId
        4. INSERT new draft
        5. Write audit
        6. COMMIT
        """
        now = _utc_now()

        with self._conn as conn:
            source = conn.execute(
                "SELECT * FROM states WHERE state_id = ?", (source_state_id,)
            ).fetchone()
            if source is None:
                raise ValueError(f"source state not found: {source_state_id}")
            if source["status"] != "approved":
                raise ValueError("only approved states can be forked")

            # Compute next version
            old_code_id = source["code_id"]
            base, old_ver = _parse_code_id_version(old_code_id)
            new_ver = old_ver + 1
            new_code_id = f"{base}_v{new_ver}"

            # Check for existing
            existing = conn.execute(
                "SELECT state_id FROM states WHERE code_id = ?", (new_code_id,)
            ).fetchone()
            if existing:
                raise FileExistsError(f"target version exists: {new_code_id}")

            # Build new definition (copy from source, strip approved fields)
            src_def = json.loads(source["definition_json"])
            new_def = model.normalize_for_display(src_def)
            new_def["codeId"] = new_code_id
            new_def["status"] = "draft"
            new_def.pop("canonical", None)
            new_def.pop("physicalValidation", None)
            new_def.pop("unknownApprovalConfirmed", None)

            def_json = _json_dumps(new_def)
            def_sha = _sha256_text(def_json)
            new_state_id = f"state-{_new_uuid4()}"

            conn.execute(
                """INSERT INTO states
                   (state_id, code_id, logical_key, version, display_name,
                    definition_json, definition_sha256, status,
                    created_at, updated_at, forked_from_state_id)
                   VALUES (?,?,?,?,?,?,?,'draft',?,?,?)""",
                (new_state_id, new_code_id, base, new_ver,
                 new_def.get("displayName", ""), def_json, def_sha,
                 now, now, source_state_id),
            )

            self._add_audit_tx(
                conn, "STATE_FORKED", state_id=new_state_id,
                details={
                    "forkedFrom": source_state_id,
                    "oldCodeId": old_code_id,
                    "newCodeId": new_code_id,
                    "newVersion": new_ver,
                },
            )

        return new_state_id

    # ---- Validation ----

    def validate_library(self) -> Dict[str, Any]:
        """Full library validation against SQLite authority."""
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
            "ORPHAN_CAPTURE_COUNT": 0,
            "APPROVED_DEFINITION_TAMPER_COUNT": 0,
            "CANONICAL_DEFINITION_SHA_MISMATCH_COUNT": 0,
            "LIBRARY_VALIDATION_PASS": False,
            "CANONICAL_PROVENANCE_PASS": False,
            "issues": [],
        }

        health = self.integrity_check()
        if not health["pass"]:
            report["issues"].append(f"SQLite integrity check failed: {health}")
            return report

        # Check all states
        states = self._conn.execute("SELECT * FROM states ORDER BY created_at").fetchall()
        code_ids_seen = set()
        for state in states:
            s = dict(state)
            report["TOTAL_STATE_COUNT"] += 1
            status = s["status"]

            if status == "approved":
                report["APPROVED_STATE_COUNT"] += 1
            elif status == "captured":
                report["CAPTURED_STATE_COUNT"] += 1
            else:
                report["DRAFT_STATE_COUNT"] += 1

            # Check duplicate code_id
            if s["code_id"] in code_ids_seen:
                report["DUPLICATE_CODE_ID_COUNT"] += 1
                report["issues"].append(f"duplicate codeId: {s['code_id']}")
            code_ids_seen.add(s["code_id"])

            # Validate definition
            try:
                definition = json.loads(s["definition_json"])
                actual_sha = _sha256_text(s["definition_json"])
                if actual_sha != s["definition_sha256"]:
                    report["HASH_MISMATCH_COUNT"] += 1
                    report["issues"].append(f"definition_sha256 mismatch for {s['code_id']}")

                errors = model.validate_definition(
                    definition, for_approval=(status == "approved"), strict=True
                )
                if errors:
                    report["INVALID_CAPTURE_COUNT"] += 1
                    report["issues"].extend([f"{s['code_id']}: {e}" for e in errors])
            except Exception as exc:
                report["INVALID_CAPTURE_COUNT"] += 1
                report["issues"].append(f"{s['code_id']}: invalid definition: {exc}")

            # Validate captures
            captures = self._conn.execute(
                "SELECT * FROM captures WHERE state_id = ? ORDER BY capture_index",
                (s["state_id"],),
            ).fetchall()
            for cap in captures:
                c = dict(cap)
                report["TOTAL_CAPTURE_COUNT"] += 1

                # Validate frame
                frame_bytes = bytes(c["frame_blob"])
                actual_frame_sha = _sha256(frame_bytes)
                if actual_frame_sha != c["frame_sha256"]:
                    report["HASH_MISMATCH_COUNT"] += 1
                    report["issues"].append(
                        f"{s['code_id']} capture_{c['capture_index']:03d}: frame_sha256 mismatch"
                    )
                validation = protocol.validate_frame(frame_bytes)
                if not validation.full_frame_valid:
                    report["FRAME_VALIDATION_FAIL_COUNT"] += 1
                    report["issues"].append(
                        f"{s['code_id']} capture_{c['capture_index']:03d}: frame validation failed"
                    )

            # Validate canonical
            if status == "approved":
                canonical = self._conn.execute(
                    """SELECT cs.*, c.frame_sha256 as cap_sha
                       FROM canonical_selections cs
                       JOIN captures c ON cs.capture_id = c.capture_id
                       WHERE cs.state_id = ?""",
                    (s["state_id"],),
                ).fetchone()
                if canonical is None:
                    report["MISSING_FILE_COUNT"] += 1
                    report["issues"].append(f"{s['code_id']}: missing canonical for approved state")
                else:
                    can = dict(canonical)
                    # Check definition_sha256 consistency
                    if can["definition_sha256"] != s["definition_sha256"]:
                        report["CANONICAL_DEFINITION_SHA_MISMATCH_COUNT"] += 1
                        report["issues"].append(
                            f"{s['code_id']}: canonical definition_sha256 differs from state"
                        )
                    if can["capture_sha256"] != can["cap_sha"]:
                        report["HASH_MISMATCH_COUNT"] += 1
                        report["issues"].append(
                            f"{s['code_id']}: canonical capture_sha256 differs from actual capture"
                        )

        fail_keys = [
            "INVALID_CAPTURE_COUNT",
            "DUPLICATE_CODE_ID_COUNT",
            "MISSING_FILE_COUNT",
            "HASH_MISMATCH_COUNT",
            "FRAME_VALIDATION_FAIL_COUNT",
            "ORPHAN_CAPTURE_COUNT",
            "APPROVED_DEFINITION_TAMPER_COUNT",
            "CANONICAL_DEFINITION_SHA_MISMATCH_COUNT",
        ]
        report["LIBRARY_VALIDATION_PASS"] = all(report[k] == 0 for k in fail_keys)
        report["CANONICAL_PROVENANCE_PASS"] = report["LIBRARY_VALIDATION_PASS"]
        return report

    # ---- Migration from legacy file-based library ----

    def migrate_legacy_library(
        self,
        library_root: Path,
        capture_002_path: Path,
    ) -> Dict[str, Any]:
        """Read-only migration from legacy file-based library to SQLite.

        Does NOT modify or delete legacy files.
        """
        result = {
            "LEGACY_LIBRARY_MIGRATION_PASS": False,
            "STATES_MIGRATED": 0,
            "CAPTURES_MIGRATED": 0,
            "ORPHAN_BIN_DETECTED": 0,
            "ORPHAN_JSON_DETECTED": 0,
            "CANONICAL_SOURCE_INCONSISTENT": 0,
            "MIGRATION_BLOCKED": 0,
            "CAPTURE_002_MIGRATION_PASS": False,
            "CAPTURE_002_ORIGINAL_UNCHANGED": False,
            "issues": [],
        }

        # Migrate CAPTURE_002 first
        try:
            capture_002_result = self._migrate_capture_002(capture_002_path)
            result.update(capture_002_result)
            if capture_002_result.get("CAPTURE_002_MIGRATION_PASS"):
                result["STATES_MIGRATED"] += 1
                result["CAPTURES_MIGRATED"] += 1
        except Exception as exc:
            result["issues"].append(f"CAPTURE_002 migration failed: {exc}")
            result["MIGRATION_BLOCKED"] += 1

        # Scan for legacy state directories
        states_dir = library_root / "states"
        if states_dir.exists():
            for state_dir in sorted(states_dir.iterdir()):
                if not state_dir.is_dir():
                    continue
                try:
                    state_result = self._migrate_legacy_state(state_dir)
                    if state_result.get("migrated"):
                        result["STATES_MIGRATED"] += 1
                        result["CAPTURES_MIGRATED"] += state_result.get("captures_migrated", 0)
                    result["ORPHAN_BIN_DETECTED"] += state_result.get("orphan_bin", 0)
                    result["ORPHAN_JSON_DETECTED"] += state_result.get("orphan_json", 0)
                except Exception as exc:
                    result["issues"].append(f"state migration failed for {state_dir.name}: {exc}")
                    result["MIGRATION_BLOCKED"] += 1

        # Check orphan bin/json files at root level
        for orphan in sorted((library_root / "states").glob("*.bin") if states_dir.exists() else []):
            result["ORPHAN_BIN_DETECTED"] += 1
            result["issues"].append(f"orphan .bin at states root: {orphan.name}")

        for orphan in sorted((library_root / "states").glob("*.json") if states_dir.exists() else []):
            result["ORPHAN_JSON_DETECTED"] += 1
            result["issues"].append(f"orphan .json at states root: {orphan.name}")

        # Verify CAPTURE_002 unchanged
        if capture_002_path.exists():
            actual_sha = _sha256(capture_002_path.read_bytes())
            result["CAPTURE_002_ORIGINAL_UNCHANGED"] = (
                actual_sha == CANONICAL_002_SHA256
                and len(capture_002_path.read_bytes()) == CANONICAL_002_LENGTH
            )

        result["LEGACY_LIBRARY_MIGRATION_PASS"] = (
            result["MIGRATION_BLOCKED"] == 0
            and result["CAPTURE_002_MIGRATION_PASS"]
            and result["CAPTURE_002_ORIGINAL_UNCHANGED"]
        )

        return result

    def _migrate_capture_002(self, capture_002_path: Path) -> Dict[str, Any]:
        """Migrate CAPTURE_002.bin as an approved state."""
        if not capture_002_path.exists():
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "CAPTURE_002.bin not found"}

        data = capture_002_path.read_bytes()
        validation = protocol.validate_frame(data)
        if len(data) != CANONICAL_002_LENGTH or validation.frame_sha256 != CANONICAL_002_SHA256:
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "CAPTURE_002 identity mismatch"}
        if not validation.full_frame_valid:
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "CAPTURE_002 frame validation failed"}

        # Check if already migrated (idempotent)
        existing = self._conn.execute(
            "SELECT state_id FROM states WHERE code_id = ?",
            (CANONICAL_002_CODE_ID,),
        ).fetchone()
        if existing:
            return {"CAPTURE_002_MIGRATION_PASS": True, "already_migrated": True}

        definition = model.default_definition()
        definition.update({
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
        })
        definition["state"].update({
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
        })

        def_json = _json_dumps(definition)
        def_sha = _sha256_text(def_json)
        now = _utc_now()
        state_id = f"state-{_new_uuid4()}"
        capture_id = f"cap-{_new_uuid4()}"

        with self._conn as conn:
            # Create approved state directly
            conn.execute(
                """INSERT INTO states
                   (state_id, code_id, logical_key, version, display_name,
                    definition_json, definition_sha256, status,
                    created_at, updated_at, approved_at)
                   VALUES (?,?,?,?,?,?,?,'approved',?,?,?)""",
                (state_id, CANONICAL_002_CODE_ID,
                 _extract_logical_key(CANONICAL_002_CODE_ID),
                 _extract_version(CANONICAL_002_CODE_ID),
                 definition.get("displayName", ""),
                 def_json, def_sha, now, now, now),
            )

            # Create capture_001
            conn.execute(
                """INSERT INTO captures
                   (capture_id, state_id, capture_index, frame_blob, frame_length,
                    frame_sha256, captured_at, device_mac, firmware_commit,
                    firmware_profile, module_model, uart_baud, request_id,
                    session_id, export_id, validation_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'ZJ-IR-V2',19200,?,?,?,?,?)""",
                (capture_id, state_id, 1, data, len(data),
                 validation.frame_sha256, "2026-07-22T00:00:00+08:00",
                 "", "", "ir-lab",
                 "migration-req", "existing_capture_002_migration",
                 "migration-exp", _json_dumps(validation.as_metadata()), now),
            )

            # Create canonical_selection
            conn.execute(
                """INSERT INTO canonical_selections
                   (state_id, capture_id, capture_sha256, definition_sha256,
                    approved_at, approved_by, approval_note)
                   VALUES (?,?,?,?,?,?,?)""",
                (state_id, capture_id, validation.frame_sha256, def_sha,
                 now, "user-confirmed-physical-validation",
                 "Migrated from CAPTURE_002.bin with 3x physical validation"),
            )

            # Audit logs
            self._add_audit_tx(conn, "STATE_CREATED", state_id=state_id,
                             details={"codeId": CANONICAL_002_CODE_ID, "via": "migration"})
            self._add_audit_tx(conn, "CAPTURE_ADDED", state_id=state_id, capture_id=capture_id,
                             details={"captureIndex": 1, "frameSha256": validation.frame_sha256, "via": "migration"})
            self._add_audit_tx(conn, "CANONICAL_APPROVED", state_id=state_id, capture_id=capture_id,
                             details={"via": "migration", "physicalValidation": True})

        # Verify migration
        verify = self._conn.execute(
            "SELECT frame_blob FROM captures WHERE capture_id = ?", (capture_id,)
        ).fetchone()
        if verify is None:
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "verification failed: capture not found"}
        if bytes(verify[0]) != data:
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "verification failed: blob mismatch"}
        if _sha256(bytes(verify[0])) != CANONICAL_002_SHA256:
            return {"CAPTURE_002_MIGRATION_PASS": False, "issue": "verification failed: sha256 mismatch"}

        return {
            "CAPTURE_002_MIGRATION_PASS": True,
            "state_id": state_id,
            "capture_id": capture_id,
            "CAPTURE_002_ORIGINAL_UNCHANGED": True,
        }

    def _migrate_legacy_state(self, state_dir: Path) -> Dict[str, Any]:
        """Migrate one legacy state directory. Read-only."""
        result = {
            "migrated": False,
            "captures_migrated": 0,
            "orphan_bin": 0,
            "orphan_json": 0,
        }

        definition_path = state_dir / "definition.json"
        if not definition_path.exists():
            result["orphan_json"] += 1  # no definition at all
            # Check for orphan .bin files
            for p in state_dir.glob("*.bin"):
                result["orphan_bin"] += 1
            return result

        try:
            definition = json.loads(definition_path.read_text(encoding="utf-8"))
        except Exception:
            return result

        code_id = definition.get("codeId", state_dir.name)
        status = definition.get("status", "draft")
        existing = self._conn.execute(
            "SELECT state_id FROM states WHERE code_id = ?", (code_id,)
        ).fetchone()
        if existing:
            return result  # already migrated

        # Check definition validity
        errors = model.validate_definition(definition, for_approval=(status == "approved"))
        if errors:
            return result  # skip invalid

        # Migrate the state
        now = _utc_now()
        state_id = f"state-{_new_uuid4()}"
        def_json = _json_dumps(definition)
        def_sha = _sha256_text(def_json)

        with self._conn as conn:
            conn.execute(
                """INSERT INTO states
                   (state_id, code_id, logical_key, version, display_name,
                    definition_json, definition_sha256, status,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (state_id, code_id,
                 _extract_logical_key(code_id),
                 _extract_version(code_id),
                 definition.get("displayName", ""),
                 def_json, def_sha, status, now, now),
            )

            # Migrate captures
            captures_dir = state_dir / "captures"
            if captures_dir.exists():
                for cap_bin in sorted(captures_dir.glob("capture_*.bin")):
                    try:
                        cap_idx = int(cap_bin.stem.split("_")[1])
                    except Exception:
                        continue
                    cap_json_path = captures_dir / f"{cap_bin.stem}.json"
                    frame_data = cap_bin.read_bytes()
                    sha = _sha256(frame_data)
                    validation = protocol.validate_frame(frame_data)

                    cap_id = f"cap-{_new_uuid4()}"
                    val_json = _json_dumps(validation.as_metadata())
                    meta = {}
                    if cap_json_path.exists():
                        try:
                            meta = json.loads(cap_json_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass

                    conn.execute(
                        """INSERT INTO captures
                           (capture_id, state_id, capture_index, frame_blob, frame_length,
                            frame_sha256, captured_at, device_mac, firmware_commit,
                            firmware_profile, module_model, uart_baud, request_id,
                            session_id, export_id, validation_json, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (cap_id, state_id, cap_idx, frame_data, len(frame_data),
                         sha, meta.get("capturedAt", now),
                         meta.get("deviceMac", ""),
                         meta.get("firmwareCommit", ""),
                         meta.get("firmwareProfile", ""),
                         meta.get("irModuleModel", "ZJ-IR-V2"),
                         meta.get("irUartBaud", 19200),
                         meta.get("learnSessionId", ""),
                         meta.get("learnSessionId", ""),
                         meta.get("exportId", ""),
                         val_json, now),
                    )
                    result["captures_migrated"] += 1

                    if not cap_json_path.exists():
                        result["orphan_json"] += 1

                # Check for json without corresponding bin
                for cap_json in sorted(captures_dir.glob("capture_*.json")):
                    bin_path = captures_dir / f"{cap_json.stem}.bin"
                    if not bin_path.exists():
                        result["orphan_json"] += 1

            # Migrate canonical
            approved_dir = state_dir / "approved"
            if status == "approved" and approved_dir.exists():
                canonical_json = approved_dir / "canonical.json"
                canonical_bin = approved_dir / "canonical.bin"
                if canonical_json.exists() and canonical_bin.exists():
                    try:
                        can_meta = json.loads(canonical_json.read_text(encoding="utf-8"))
                        src_capture_id = can_meta.get("sourceCaptureId", "")
                        src_idx = int(src_capture_id.split("_")[1]) if "_" in src_capture_id else 1
                        # Find the migrated capture
                        src_cap = conn.execute(
                            "SELECT capture_id, frame_sha256 FROM captures WHERE state_id = ? AND capture_index = ?",
                            (state_id, src_idx),
                        ).fetchone()
                        if src_cap:
                            conn.execute(
                                """INSERT INTO canonical_selections
                                   (state_id, capture_id, capture_sha256, definition_sha256,
                                    approved_at, approved_by, approval_note)
                                   VALUES (?,?,?,?,?,?,?)""",
                                (state_id, src_cap["capture_id"], src_cap["frame_sha256"],
                                 def_sha, can_meta.get("approvedAt", now),
                                 can_meta.get("approvedBy", "migration"),
                                 "Migrated from legacy file-based library"),
                            )
                    except Exception:
                        pass

            self._add_audit_tx(conn, "STATE_CREATED", state_id=state_id,
                             details={"codeId": code_id, "via": "legacy_migration"})

            result["migrated"] = True

        return result

    # ---- Audit helpers (must be called within a transaction) ----

    def _add_audit(
        self, event_type: str, state_id: Optional[str] = None,
        capture_id: Optional[str] = None, details: Optional[Dict] = None,
    ) -> None:
        self._add_audit_tx(self._conn, event_type, state_id, capture_id, details)

    @staticmethod
    def _add_audit_tx(
        conn: sqlite3.Connection, event_type: str,
        state_id: Optional[str] = None,
        capture_id: Optional[str] = None,
        details: Optional[Dict] = None,
    ) -> None:
        """Add audit log entry within an existing transaction."""
        import getpass
        now = _utc_now()
        details_json = _json_dumps(details or {})
        actor = getpass.getuser() or "local_user"

        # Get previous hash for chain integrity
        prev = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1"
        ).fetchone()
        prev_hash = prev["entry_hash"] if prev else ""

        entry_data = f"{event_type}|{state_id or ''}|{capture_id or ''}|{now}|{actor}|{details_json}|{prev_hash}"
        entry_hash = _sha256_text(entry_data)

        conn.execute(
            """INSERT INTO audit_log
               (event_type, state_id, capture_id, occurred_at, actor,
                details_json, previous_hash, entry_hash)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event_type, state_id, capture_id, now, actor,
             details_json, prev_hash, entry_hash),
        )

    # ---- Export (snapshot from DB) ----

    def export_snapshot(self, output_dir: Path) -> Dict[str, Any]:
        """Export a file-system snapshot from the SQLite library.

        This is a read-only, fully-reconstructable export. The snapshot
        is NOT authoritative — SQLite remains the source of truth.
        """
        health = self.integrity_check()
        if not health["pass"]:
            raise RuntimeError("database integrity check failed; cannot export")

        result = {
            "EXPORT_SNAPSHOT_PASS": False,
            "STATES_EXPORTED": 0,
            "CAPTURES_EXPORTED": 0,
            "CANONICALS_EXPORTED": 0,
            "output_dir": str(output_dir),
        }

        staging = Path(tempfile.mkdtemp(prefix="ir_snapshot_", dir=output_dir.parent))
        try:
            (staging / "states").mkdir(parents=True, exist_ok=True)

            manifest = {
                "schemaVersion": 1,
                "exportedAt": _utc_now(),
                "source": "sqlite_authoritative_export",
                "states": [],
            }

            states = self._conn.execute("SELECT * FROM states ORDER BY code_id").fetchall()
            for state in states:
                s = dict(state)
                code_id = s["code_id"]
                state_dir = staging / "states" / code_id
                state_dir.mkdir(parents=True, exist_ok=True)

                # Write definition
                definition = json.loads(s["definition_json"])
                (state_dir / "definition.json").write_text(
                    _json_dumps(definition) + "\n", encoding="utf-8"
                )

                # Write captures
                captures_dir = state_dir / "captures"
                captures_dir.mkdir(exist_ok=True)
                captures = self._conn.execute(
                    "SELECT * FROM captures WHERE state_id = ? ORDER BY capture_index",
                    (s["state_id"],),
                ).fetchall()

                state_info = {
                    "codeId": code_id,
                    "status": s["status"],
                    "captures": [],
                }

                for cap in captures:
                    c = dict(cap)
                    cap_idx = c["capture_index"]
                    cap_display = f"capture_{cap_idx:03d}"

                    # Write .bin
                    (captures_dir / f"{cap_display}.bin").write_bytes(bytes(c["frame_blob"]))

                    # Write .json metadata
                    meta = {
                        "schemaVersion": 1,
                        "captureId": cap_display,
                        "codeId": code_id,
                        "captureIndex": cap_idx,
                        "capturedAt": c["captured_at"],
                        "deviceMac": c["device_mac"],
                        "firmwareCommit": c["firmware_commit"],
                        "firmwareProfile": c["firmware_profile"],
                        "irModuleModel": c["module_model"],
                        "irUartBaud": c["uart_baud"],
                        "learnSessionId": c["session_id"],
                        "frameLength": c["frame_length"],
                        "frameSha256": c["frame_sha256"],
                        "rawFile": f"captures/{cap_display}.bin",
                        "validation": json.loads(c["validation_json"]),
                    }
                    (captures_dir / f"{cap_display}.json").write_text(
                        _json_dumps(meta) + "\n", encoding="utf-8"
                    )

                    state_info["captures"].append(cap_display)
                    result["CAPTURES_EXPORTED"] += 1

                # Write canonical
                if s["status"] == "approved":
                    canonical = self._conn.execute(
                        """SELECT cs.*, c.frame_blob, c.frame_sha256, c.frame_length
                           FROM canonical_selections cs
                           JOIN captures c ON cs.capture_id = c.capture_id
                           WHERE cs.state_id = ?""",
                        (s["state_id"],),
                    ).fetchone()
                    if canonical:
                        can = dict(canonical)
                        approved_dir = state_dir / "approved"
                        approved_dir.mkdir(exist_ok=True)

                        (approved_dir / "canonical.bin").write_bytes(bytes(can["frame_blob"]))
                        can_meta = {
                            "schemaVersion": 1,
                            "codeId": code_id,
                            "approvedAt": can["approved_at"],
                            "approvedBy": can["approved_by"],
                            "sourceCaptureId": f"capture_{'001':0>3}",
                            "definitionSha256": can["definition_sha256"],
                            "frameLength": can["frame_length"],
                            "frameSha256": can["frame_sha256"],
                            "canonicalSha256": can["capture_sha256"],
                        }
                        (approved_dir / "canonical.json").write_text(
                            _json_dumps(can_meta) + "\n", encoding="utf-8"
                        )
                        result["CANONICALS_EXPORTED"] += 1

                manifest["states"].append(state_info)
                result["STATES_EXPORTED"] += 1

            # Write manifest
            (staging / "library_manifest.json").write_text(
                _json_dumps(manifest) + "\n", encoding="utf-8"
            )

            # Atomic rename
            if output_dir.exists():
                import shutil
                shutil.rmtree(output_dir)
            staging.rename(output_dir)

            result["EXPORT_SNAPSHOT_PASS"] = True
        except Exception:
            import shutil
            try:
                shutil.rmtree(staging)
            except Exception:
                pass
            raise

        return result

    # ---- Generate firmware include ----

    def generate_firmware_include(self, output_path: Path) -> Dict[str, Any]:
        """Generate firmware include from approved canonical frames."""
        validation = self.validate_library()
        if not validation["LIBRARY_VALIDATION_PASS"]:
            return {
                "APPROVED_CODE_COUNT": 0,
                "IR_LIBRARY_GENERATE_PASS": False,
                "issues": validation.get("issues", []),
            }

        approved_states = self._conn.execute(
            "SELECT * FROM states WHERE status = 'approved' ORDER BY code_id"
        ).fetchall()

        entries: List[Tuple[Dict, bytes, str]] = []
        for state in approved_states:
            s = dict(state)
            canonical = self._conn.execute(
                """SELECT cs.*, c.frame_blob, c.frame_sha256
                   FROM canonical_selections cs
                   JOIN captures c ON cs.capture_id = c.capture_id
                   WHERE cs.state_id = ?""",
                (s["state_id"],),
            ).fetchone()
            if canonical is None:
                continue
            can = dict(canonical)
            frame = bytes(can["frame_blob"])
            validation_f = protocol.validate_frame(frame)
            if not validation_f.full_frame_valid:
                continue
            entries.append((json.loads(s["definition_json"]), frame, can["frame_sha256"]))

        total_raw = sum(len(f) for _, f, _ in entries)
        largest = max((len(f) for _, f, _ in entries), default=0)

        lines = [
            "// AUTO-GENERATED from SQLite authoritative IR library.",
            "// Gitignored. Do not commit raw private IR frames.",
            "#define PRIVATE_IR_LIBRARY_GENERATED 1",
            "",
        ]
        for idx, (definition, frame, sha) in enumerate(entries):
            symbol = f"kPrivateIrFrame{idx:03d}"
            lines.append(f"static const uint8_t {symbol}[] PROGMEM = {{")
            for off in range(0, len(frame), 12):
                chunk = ", ".join(f"0x{b:02X}" for b in frame[off:off + 12])
                lines.append(f"  {chunk},")
            lines.append("};")
            lines.append("")

        lines.append("static const PrivateIrCode kPrivateIrCodes[] = {")
        for idx, (definition, frame, sha) in enumerate(entries):
            display = str(definition.get("displayName", "")).replace("\\", "\\\\").replace('"', '\\"')
            lines.append("  {")
            lines.append(f'    "{definition["codeId"]}",')
            lines.append(f"    kPrivateIrFrame{idx:03d},")
            lines.append(f"    {len(frame)},")
            lines.append(f'    "{sha}",')
            lines.append(f'    "{display}",')
            lines.append("  },")
        lines.append("};")
        lines.append(
            "static const uint8_t kPrivateIrCodeCount = "
            "static_cast<uint8_t>(sizeof(kPrivateIrCodes) / sizeof(kPrivateIrCodes[0]));"
        )
        lines.append("")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        old_hash = _sha256(output_path.read_bytes()) if output_path.exists() else ""
        content = "\n".join(lines)
        output_path.write_text(content, encoding="utf-8")
        new_hash = _sha256(output_path.read_bytes())

        return {
            "APPROVED_CODE_COUNT": len(entries),
            "TOTAL_RAW_BYTES": total_raw,
            "TOTAL_GENERATED_BYTES": len(content.encode("utf-8")),
            "LARGEST_FRAME_LENGTH": largest,
            "IR_LIBRARY_GENERATE_PASS": True,
            "GENERATED_OUTPUT_CHANGED": old_hash != new_hash,
            "GENERATED_INCLUDE": str(output_path),
        }


# ---- Helpers ----

def _extract_logical_key(code_id: str) -> str:
    """Extract logical key from code_id (everything before _vN)."""
    import re
    m = re.search(r"^(.*)_v[0-9]+$", code_id)
    return m.group(1) if m else code_id


def _extract_version(code_id: str) -> int:
    """Extract version number from code_id."""
    import re
    m = re.search(r"_v([0-9]+)$", code_id)
    return int(m.group(1)) if m else 1


def _parse_code_id_version(code_id: str) -> Tuple[str, int]:
    import re
    m = re.search(r"^(.*)_v([0-9]+)$", code_id)
    if m:
        return m.group(1), int(m.group(2))
    return code_id, 1


def discover_paths() -> Tuple[Path, Path]:
    """Discover project root and library DB path."""
    here = Path(__file__).resolve()
    project_root = here.parents[4]
    db_path = project_root / "Private" / "Firmware" / "IR" / "Library" / DB_FILENAME
    return project_root, db_path
