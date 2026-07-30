#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single production composition root for IR Learning Studio.

This is THE ONLY place where production dependencies are constructed.
All production entry points (app.py, cli.py, dev.ps1 Python code) MUST
obtain their runtime from this module. No other file should instantiate
library_store, SingleInstanceLock, or unrecorded PySerialTransport directly.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Production implementations (R3 architecture)
import ir_library_db
import library_service
import firmware_generator
import windows_mutex
import no_replay
import serial_client
import protocol


def _default_project_root() -> Path:
    """Resolve the repository root from this file's location.

    Layout: <repo>/firmware/tools/ir_learning_studio/composition_root.py
    Override with the IR_PROJECT_ROOT environment variable when running the
    tools from outside the repository tree.
    """
    override = os.environ.get("IR_PROJECT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


@dataclass
class ApplicationRuntime:
    """Complete runtime assembled by the composition root."""

    project_root: Path
    mode: str  # "production", "demo", "test"

    # Core infrastructure
    mutex: Optional[windows_mutex.WindowsNamedMutex] = None
    database: Optional[ir_library_db.IrLibraryDB] = None
    library_service: Optional[library_service.LibraryService] = None
    firmware_generator: Optional[firmware_generator.FirmwareGenerator] = None
    recorder: Optional[no_replay.NoReplayRecorder] = None

    # Serial
    serial_worker: Optional[serial_client.SerialIoWorker] = None

    # Paths
    db_path: Optional[Path] = None
    project_root_hash: str = ""

    # Flags
    write_enabled: bool = False
    learning_enabled: bool = False
    approval_enabled: bool = False
    generation_enabled: bool = False
    mock_mode: bool = False

    # Legacy compatibility flags (MUST be False in production)
    legacy_file_store_enabled: bool = False
    legacy_file_lock_enabled: bool = False

    def runtime_wiring(self) -> Dict[str, Any]:
        """Generate runtime_wiring.json diagnostics."""
        return {
            "projectRootHash": self.project_root_hash,
            "runtimeMode": self.mode,
            "mutexImplementation": type(self.mutex).__name__ if self.mutex else "None",
            "libraryImplementation": type(self.database).__name__ if self.database else "None",
            "libraryDatabasePathHash": (
                hashlib.sha256(str(self.db_path).encode()).hexdigest()[:16]
                if self.db_path else ""
            ),
            "recorderImplementation": type(self.recorder).__name__ if self.recorder else "None",
            "serialWorkerImplementation": (
                type(self.serial_worker).__name__ if self.serial_worker else "None"
            ),
            "protocolVersion": protocol.SUPPORTED_LEARNING_PROTOCOL_VERSION,
            "legacyFileStoreEnabled": self.legacy_file_store_enabled,
            "legacyFileLockEnabled": self.legacy_file_lock_enabled,
            "mockMode": self.mock_mode,
            "writeEnabled": self.write_enabled,
            "learningEnabled": self.learning_enabled,
            "approvalEnabled": self.approval_enabled,
            "generationEnabled": self.generation_enabled,
        }

    def close(self) -> None:
        """Clean shutdown."""
        if self.serial_worker is not None:
            try:
                self.serial_worker.post(serial_client.CMD_SHUTDOWN)
                self.serial_worker.join(timeout=5.0)
            except Exception:
                pass
        if self.database is not None:
            try:
                self.database.close()
            except Exception:
                pass
        if self.mutex is not None:
            try:
                self.mutex.release()
            except Exception:
                pass


def create_runtime(
    project_root: Path,
    mode: str = "production",
    serial_factory: Optional[Callable[[], serial_client.SerialTransport]] = None,
    allow_mock: bool = False,
) -> ApplicationRuntime:
    """Create the full application runtime.

    This is the SINGLE entry point for constructing all production dependencies.

    Args:
        project_root: Validated canonical repository root. Defaults to the
            path derived from this file's location, or IR_PROJECT_ROOT.
        mode: "production", "demo", or "test"
        serial_factory: Optional factory for serial transport (for testing)
        allow_mock: Allow mock transport (test/demo only)

    Returns:
        ApplicationRuntime with all dependencies wired.
    """
    project_root = Path(project_root).resolve()

    runtime = ApplicationRuntime(
        project_root=project_root,
        mode=mode,
        mock_mode=allow_mock,
    )

    # 1. Validate project root
    if not _is_valid_project_root(project_root):
        runtime.mode = "demo"
        runtime.write_enabled = False
        return runtime

    # 2. Compute project root hash
    runtime.project_root_hash = windows_mutex._compute_project_root_hash(project_root)

    # 3. Acquire Windows Named Mutex
    if os.name == "nt":
        mutex = windows_mutex.WindowsNamedMutex(project_root)
        if not mutex.acquire():
            # Second instance - read-only exit
            runtime.mutex = None
            runtime.write_enabled = False
            runtime.learning_enabled = False
            runtime.approval_enabled = False
            runtime.generation_enabled = False
            return runtime
        runtime.mutex = mutex
    else:
        runtime.mutex = None  # Non-Windows platforms

    # 4. Open SQLite database
    db_path = project_root / "Private" / "Firmware" / "IR" / "Library" / "ir_library.sqlite3"
    runtime.db_path = db_path
    database = ir_library_db.IrLibraryDB(
        db_path,
        project_root_hash=runtime.project_root_hash,
    )
    try:
        database.open()
        # Health checks
        health = database.quick_check()
        if not health["pass"]:
            runtime.write_enabled = False
            runtime.learning_enabled = False
            runtime.approval_enabled = False
            runtime.generation_enabled = False
            runtime.database = database
            return runtime

        # Verify project_root_hash matches
        meta_row = database._conn.execute(
            "SELECT value FROM library_meta WHERE key = 'project_root_hash'"
        ).fetchone()
        if meta_row and meta_row["value"] and meta_row["value"] != runtime.project_root_hash:
            runtime.write_enabled = False
            runtime.learning_enabled = False
            runtime.approval_enabled = False
            runtime.generation_enabled = False
            runtime.database = database
            return runtime

        runtime.write_enabled = True
        runtime.learning_enabled = True
        runtime.approval_enabled = True
        runtime.generation_enabled = True
        runtime.database = database
        runtime.library_service = library_service.LibraryService(database)
        runtime.firmware_generator = firmware_generator.FirmwareGenerator(database)
    except Exception:
        runtime.write_enabled = False
        runtime.learning_enabled = False
        runtime.approval_enabled = False
        runtime.generation_enabled = False
        if database:
            runtime.database = database
        return runtime

    # 5. Initialize NoReplay Recorder
    runtime.recorder = no_replay.get_recorder()

    # 6. Create SerialIoWorker (deferred until connect)
    # Only create in production mode with serial_factory
    if serial_factory is not None or allow_mock:
        runtime.serial_worker = serial_client.SerialIoWorker(
            transport_factory=serial_factory,
            allow_mock=allow_mock,
        )

    return runtime


def create_demo_runtime(project_root: Optional[Path] = None) -> ApplicationRuntime:
    """Create a read-only demo runtime (no serial, no write, no private)."""
    root = project_root or _default_project_root()
    return ApplicationRuntime(
        project_root=root,
        mode="demo",
        write_enabled=False,
        learning_enabled=False,
        approval_enabled=False,
        generation_enabled=False,
        legacy_file_store_enabled=False,
        legacy_file_lock_enabled=False,
    )


def _is_valid_project_root(project_root: Path) -> bool:
    """Verify the project root is a valid production root."""
    project_root = Path(project_root)
    forbidden = {"Deliverables", "PackageValidation"}
    if any(part in forbidden for part in project_root.parts):
        return False
    return (
        (project_root / "Firmware" / "Remote_AC_Controller").exists()
        and (project_root / "Firmware" / "Remote_AC_Controller" / "tools" / "dev.ps1").exists()
        and (project_root / "Private" / "Firmware" / "IR").exists()
    )
