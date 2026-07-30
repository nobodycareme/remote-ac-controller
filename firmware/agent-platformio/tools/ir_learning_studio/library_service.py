#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Library service wrapping SQLite authority database.

This is the ONLY production interface for IR library operations.
No other module should call ir_library_db.IrLibraryDB methods directly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ir_library_db
import model
import protocol


class LibraryService:
    """Service layer over IrLibraryDB. Handles business logic and validation."""

    def __init__(self, database: ir_library_db.IrLibraryDB):
        self._db = database

    # ---- State management ----

    def create_draft(self, definition: Dict[str, Any]) -> str:
        """Create a new draft state. Returns state_id."""
        definition = model.normalize_for_display(definition)
        definition["status"] = "draft"
        errors = model.validate_for_capture(definition)
        if errors:
            raise ValueError("; ".join(errors))
        return self._db.create_state(definition)

    def update_draft(self, state_id: str, definition: Dict[str, Any]) -> None:
        """Update an existing draft. Rejects approved states via DB trigger."""
        state = self._db.get_state(state_id)
        if state is None:
            raise ValueError(f"state not found: {state_id}")
        if state["status"] == "approved":
            raise PermissionError("approved state is immutable; fork a new version")

        definition = model.normalize_for_display(definition)
        def_json = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        def_sha = hashlib.sha256(def_json.encode()).hexdigest()

        # Direct update (trigger will reject if approved)
        self._db._conn.execute(
            "UPDATE states SET definition_json = ?, definition_sha256 = ?, display_name = ?, updated_at = ? WHERE state_id = ?",
            (def_json, def_sha, definition.get("displayName", ""), ir_library_db._utc_now(), state_id),
        )
        self._db._conn.commit()

    def get_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_state(state_id)

    def get_state_by_code_id(self, code_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_state_by_code_id(code_id)

    def list_states(self) -> List[Dict[str, Any]]:
        return self._db.list_states()

    # ---- Capture management ----

    def add_capture(self, state_id: str, frame: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Add a capture to a state. Transactional."""
        if metadata.get("learnExitConfirmed") is not True:
            raise ValueError("capture requires confirmed exit (learnExitConfirmed=True)")
        return self._db.add_capture(state_id, frame, metadata)

    def get_captures(self, state_id: str) -> List[Dict[str, Any]]:
        return self._db.get_captures(state_id)

    def get_capture_blob(self, capture_id: str) -> Optional[bytes]:
        return self._db.get_capture_blob(capture_id)

    def compare_captures(self, state_id: str) -> Dict[str, Any]:
        """Compare all captures for a state."""
        captures = self.get_captures(state_id)
        frames = []
        for cap in captures:
            blob = self.get_capture_blob(cap["capture_id"])
            if blob:
                frames.append(blob)
        return protocol.diff_summary(frames)

    # ---- Canonical approval ----

    def approve_canonical(self, state_id: str, capture_id: str, approved_by: str = "") -> Dict[str, Any]:
        return self._db.approve_canonical(state_id, capture_id, approved_by)

    def get_canonical(self, state_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_canonical(state_id)

    # ---- Versioning ----

    def fork_approved_state(self, state_id: str) -> str:
        return self._db.fork_approved_state(state_id)

    # ---- Validation ----

    def validate_library(self) -> Dict[str, Any]:
        health = self._db.integrity_check()
        if not health["pass"]:
            return {"LIBRARY_VALIDATION_PASS": False, "issues": ["integrity_check_failed"]}
        return self._db.validate_library()

    def export_snapshot(self, output_dir: Path) -> Dict[str, Any]:
        return self._db.export_snapshot(output_dir)

    def generate_firmware_include(self, output_path: Path) -> Dict[str, Any]:
        return self._db.generate_firmware_include(output_path)

    def migrate_legacy(self, library_root: Path, capture_002_path: Path) -> Dict[str, Any]:
        return self._db.migrate_legacy_library(library_root, capture_002_path)

    # ---- Audit ----

    def verify_audit_chain(self) -> Dict[str, Any]:
        """Verify the audit log chain integrity."""
        rows = self._db._conn.execute(
            "SELECT * FROM audit_log ORDER BY audit_id"
        ).fetchall()
        result = {"AUDIT_CHAIN_PASS": True, "AUDIT_ENTRY_COUNT": len(rows), "issues": []}

        prev_hash = ""
        for i, row in enumerate(rows):
            r = dict(row)
            # Recompute entry hash
            entry_data = (
                f"{r['event_type']}|{r['state_id'] or ''}|{r['capture_id'] or ''}|"
                f"{r['occurred_at']}|{r['actor']}|{r['details_json']}|{prev_hash}"
            )
            computed = hashlib.sha256(entry_data.encode()).hexdigest()

            if r["entry_hash"] != computed:
                result["AUDIT_CHAIN_PASS"] = False
                result["issues"].append(f"audit_id={r['audit_id']}: entry_hash mismatch")
            if r["previous_hash"] != prev_hash:
                result["AUDIT_CHAIN_PASS"] = False
                result["issues"].append(f"audit_id={r['audit_id']}: previous_hash mismatch")
            prev_hash = r["entry_hash"]

        return result

    def close(self) -> None:
        self._db.close()
