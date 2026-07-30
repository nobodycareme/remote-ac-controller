#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Firmware include generator backed by SQLite authority library."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import ir_library_db


class FirmwareGenerator:
    """Generate firmware include files from SQLite-authored IR library."""

    def __init__(self, database: ir_library_db.IrLibraryDB):
        self._db = database
        self._last_result: Dict[str, Any] = {}

    def validate_and_check(self) -> Dict[str, Any]:
        """Run full pre-generation validation."""
        health = self._db.integrity_check()
        if not health["pass"]:
            return {"GENERATE_ENABLED": False, "reason": "integrity_check_failed", "health": health}

        validation = self._db.validate_library()
        if not validation.get("LIBRARY_VALIDATION_PASS"):
            return {"GENERATE_ENABLED": False, "reason": "library_validation_failed", "validation": validation}

        return {"GENERATE_ENABLED": True, "validation": validation}

    def generate(self, output_path: Path) -> Dict[str, Any]:
        """Generate firmware include file. Returns result dict."""
        self._last_result = self._db.generate_firmware_include(output_path)
        return self._last_result

    @property
    def last_result(self) -> Dict[str, Any]:
        return self._last_result
