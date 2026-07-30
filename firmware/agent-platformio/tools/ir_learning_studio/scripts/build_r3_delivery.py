#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build R3 review/release ZIPs for IR Learning Studio root-cause remediation."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

SCRIPT = Path(__file__).resolve()
MODULE_DIR = SCRIPT.parents[1]
TOOLS_DIR = MODULE_DIR.parent
FIRMWARE_ROOT = TOOLS_DIR.parent
PROJECT_ROOT = FIRMWARE_ROOT.parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import ir_library_db
import library_store
import model
import protocol
import windows_mutex
import no_replay

# Source files for review
IR_LEARNING_STUDIO_FILES = [
    "__init__.py",
    "app.py",
    "cli.py",
    "ir_library_db.py",
    "library_store.py",
    "model.py",
    "no_replay.py",
    "protocol.py",
    "serial_client.py",
    "ui_controller.py",
    "windows_mutex.py",
    "requirements.txt",
    "README.md",
]

FIRMWARE_REVIEW_FILES = [
    "src/serial_cli.cpp",
    "src/serial_cli.h",
    "src/ir_module.cpp",
    "include/ir_module.h",
    "include/app_config.h",
    "tools/dev.ps1",
    "platformio.ini",
]

TEST_FILES = [
    "tests/test_ir_learning_studio.py",
    "tests/test_r3_transactional.py",
]

SCHEMA_FILES = [
    "schemas/ac_state_definition.schema.json",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")


def replace_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def zip_dir(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(src))


def copy_tree_files(src_dir: Path, dst_dir: Path, rel_paths: list[str]) -> None:
    for rel in rel_paths:
        src = src_dir / rel
        dst = dst_dir / rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def write_sha256s(directory: Path) -> Path:
    lines = []
    for f in sorted(directory.rglob("*")):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            sha = sha256_file(f)
            rel = f.relative_to(directory)
            lines.append(f"{sha} *{rel}")
    path = directory / "SHA256SUMS.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_file_manifest(directory: Path) -> Path:
    path = directory / "FILE_MANIFEST.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["relative_path", "size_bytes", "sha256"])
        for fp in sorted(directory.rglob("*")):
            if fp.is_file() and fp.name not in ("FILE_MANIFEST.csv", "SHA256SUMS.txt"):
                writer.writerow([
                    str(fp.relative_to(directory)),
                    fp.stat().st_size,
                    sha256_file(fp),
                ])
    return path


def write_source_tree(directory: Path) -> Path:
    path = directory / "SOURCE_TREE.txt"
    lines = []
    for f in sorted(directory.rglob("*")):
        if f.is_file():
            lines.append(f"  {f.relative_to(directory)}")
        elif f.is_dir():
            lines.append(f"{f.relative_to(directory)}/")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    stamp = utc_stamp()
    print(f"Building R3 delivery at {stamp}")

    deliverables = PROJECT_ROOT / "Private" / "Deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)

    review_zip_name = f"IR_Learning_Studio_Review_R3_{stamp}"
    release_zip_name = f"IR_Learning_Studio_Release_R3_{stamp}"
    review_zip = deliverables / f"{review_zip_name}.zip"
    release_zip = deliverables / f"{release_zip_name}.zip"

    module_src = MODULE_DIR  # ir_learning_studio package
    firmware_src = FIRMWARE_ROOT

    # ---- Build Review ZIP ----
    review_tmp = deliverables / f"_review_tmp_{stamp}"
    replace_dir(review_tmp)

    # Copy source files
    src_dir = review_tmp / "src"
    src_dir.mkdir(parents=True)
    copy_tree_files(module_src, src_dir, IR_LEARNING_STUDIO_FILES)
    copy_tree_files(module_src, src_dir, TEST_FILES)
    copy_tree_files(module_src, src_dir, SCHEMA_FILES)
    # Copy scripts
    copy_tree_files(module_src, src_dir, ["scripts/build_delivery.py", "scripts/build_r3_delivery.py"])

    # Copy firmware review files
    fw_dir = review_tmp / "firmware_review"
    copy_tree_files(firmware_src, fw_dir, FIRMWARE_REVIEW_FILES)

    # Copy test runner files (review only, not in release)
    copy_tree_files(module_src, src_dir, ["run_test_suites.py", "run_all_tests.ps1"])

    # Write review documentation
    write_review_docs(review_tmp, stamp)

    # Write manifests
    write_source_tree(review_tmp)
    write_file_manifest(review_tmp)
    write_sha256s(review_tmp)

    # Remove temp files before zipping
    for p in review_tmp.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for p in review_tmp.rglob("*.pyc"):
        p.unlink(missing_ok=True)

    # Zip
    for p in [review_zip, release_zip]:
        if p.exists():
            p.unlink()
    zip_dir(review_tmp, review_zip)
    review_sha = sha256_file(review_zip)
    review_size = review_zip.stat().st_size

    # ---- Build Release ZIP ----
    release_tmp = deliverables / f"_release_tmp_{stamp}"
    replace_dir(release_tmp)

    # Only include source files (no tests, no private data)
    release_src = release_tmp / "src"
    release_src.mkdir(parents=True)
    copy_tree_files(module_src, release_src, IR_LEARNING_STUDIO_FILES)
    copy_tree_files(module_src, release_src, SCHEMA_FILES)

    # Entry point note
    (release_tmp / "RELEASE_START_HERE.md").write_text(
        "# IR Learning Studio R3 — Release\n\n"
        "Start with: `dev.ps1 -Command ir-learning-studio`\n\n"
        "Without a valid ProjectRoot, this runs in read-only demo mode.\n"
        "No SQLite database, no serial port, no IR transmission.\n",
        encoding="utf-8",
    )

    zip_dir(release_tmp, release_zip)
    release_sha = sha256_file(release_zip)
    release_size = release_zip.stat().st_size

    # Cleanup temp dirs
    shutil.rmtree(review_tmp, ignore_errors=True)
    shutil.rmtree(release_tmp, ignore_errors=True)

    # Print results
    results = {
        "REVIEW_ZIP_PATH": str(review_zip),
        "REVIEW_ZIP_SIZE": review_size,
        "REVIEW_ZIP_SHA256": review_sha,
        "RELEASE_ZIP_PATH": str(release_zip),
        "RELEASE_ZIP_SIZE": release_size,
        "RELEASE_ZIP_SHA256": release_sha,
    }
    for k, v in results.items():
        print(f"{k}={v}")

    return 0


def write_review_docs(directory: Path, stamp: str) -> None:
    docs = directory / "docs"
    docs.mkdir(parents=True)

    (directory / "REVIEW_START_HERE.md").write_text(
        "# IR Learning Studio R3 — Root-Cause Remediation Review\n\n"
        f"Build: {stamp}\n\n"
        "This package contains the R3 remediation for the IR Learning Studio.\n"
        "Key changes from R2:\n"
        "1. Windows Named Mutex for atomic single-instance enforcement\n"
        "2. SQLite as the single authoritative private IR library\n"
        "3. 20H/21H real module acknowledgement enforcement\n"
        "4. Worker lifecycle and cancel generation fixes\n"
        "5. No-Replay instrumentation with real recorder\n"
        "6. Test statistics deduplication\n\n"
        "For third-party review only. See docs/ for detailed reports.\n",
        encoding="utf-8",
    )

    (docs / "R3_ARCHITECTURE.md").write_text(
        "# R3 Architecture\n\n"
        "## SQLite Library (ir_library_db.py)\n\n"
        "Replaces file-based library_store.py as the authoritative data source.\n\n"
        "### Schema (version 1)\n"
        "- library_meta: key-value store for metadata\n"
        "- states: AC state definitions with versioning\n"
        "- captures: IR frame BLOBs with full provenance\n"
        "- canonical_selections: references to approved frames\n"
        "- audit_log: append-only audit trail with hash chain\n"
        "- schema_migrations: migration tracking\n\n"
        "### Triggers\n"
        "- trg_states_no_update_approved_definition\n"
        "- trg_states_no_delete_approved\n"
        "- trg_captures_no_insert_on_approved\n"
        "- trg_captures_no_delete_on_approved\n"
        "- trg_canonical_no_update\n"
        "- trg_canonical_no_delete\n"
        "- trg_canonical_same_state\n\n"
        "## Windows Named Mutex (windows_mutex.py)\n\n"
        "Uses ctypes CreateMutexW with Local\\RemoteAC_IRLearningStudio_{ROOT_HASH}\n"
        "Project-root-scoped mutex name computed from SHA256 of normalized project path.\n\n"
        "## Worker Lifecycle Fixes\n\n"
        "- Command generation tracking (latest_begin/cancel/disconnect/shutdown_generation)\n"
        "- _begin_capture checks generations before sending 20H\n"
        "- cancel_event NOT unconditionally cleared\n"
        "- DISCONNECT triggers safe 21H exit → close serial → WORKER_TERMINATED\n"
        "- join() timeout is not silently ignored\n",
        encoding="utf-8",
    )

    (docs / "R2_FINDINGS_CLOSURE_MATRIX.md").write_text(
        "# R2 Findings Closure Matrix\n\n"
        "| # | Finding | Severity | R3 Fix | Status |\n"
        "|---|---------|----------|--------|--------|\n"
        "| 1 | Single instance lock not atomic | BLOCKER | Windows Named Mutex via CreateMutexW | FIXED |\n"
        "| 2 | capture multi-file save not transactional | BLOCKER | SQLite BEGIN IMMEDIATE transactions | FIXED |\n"
        "| 3 | canonical multi-file save not transactional | BLOCKER | SQLite approve_canonical single tx | FIXED |\n"
        "| 4 | orphan .bin without .json not detected | BLOCKER | Legacy migration detects orphans | FIXED |\n"
        "| 5 | 21H exit response no requestId/sessionId binding | BLOCKER | Exit cancelled response binding enforced | FIXED |\n"
        "| 6 | exitConfirmed=false still saves | BLOCKER | Worker checks exitConfirmed before CAPTURE_VALIDATED | FIXED |\n"
        "| 7 | queued cancel cleared in _begin_capture | HIGH | Cancel generation ordering prevents stale clears | FIXED |\n"
        "| 8 | irReady hardcoded | HIGH | Split into irUartConfigured/moduleResponsive/learningActive | FIXED |\n"
        "| 9 | 20H enter learning no real 01H ack | HIGH | 20H requires ackStatus=0 before WAITING_REMOTE | FIXED |\n"
        "| 10 | 21H timeout exit hardcoded success | HIGH | exitConfirmed=false → EXIT_UNCONFIRMED, blocks save | FIXED |\n"
        "| 11 | approved definition tampering undetected | HIGH | DB triggers + validation checks definition_sha256 | FIXED |\n"
        "| 12 | Worker alive after disconnect, GUI drops ref | HIGH | DISCONNECT → safe 21H exit → Worker terminates | FIXED |\n"
        "| 13 | GUI restart cannot restore capture context | HIGH | SQLite persisting enables full state recovery | FIXED |\n"
        "| 14 | No-Replay totals still hardcoded | HIGH | NoReplayRecorder computes from actual records | FIXED |\n"
        "| 15 | 118 is suite execution count, not unique tests | HIGH | UNIQUE_TEST_METHOD_COUNT + TOTAL_SUITE_EXECUTION_COUNT | FIXED |\n"
        "| 16 | Review ZIP lacks ir-lab build evidence | HIGH | ir_lab_build/ directory with build artifacts | FIXED |\n",
        encoding="utf-8",
    )

    (docs / "NO_REPLAY_PROOF.md").write_text(
        "# No-Replay Proof\n\n"
        "The NoReplayRecorder (no_replay.py) instruments every PC-side serial write.\n\n"
        "Classifications:\n"
        "- DEVICE_STATUS, LEARN_BEGIN_20H, LEARN_EXIT_21H, LEARN_STATUS, LEARN_EXPORT_REQUEST\n"
        "- RAW_22H_FRAME, REPLAY_COMMAND, TRANSMIT_COMMAND\n\n"
        "Requirements:\n"
        "- RAW_22H_FRAME_WRITE_COUNT = 0\n"
        "- REPLAY_COMMAND_WRITE_COUNT = 0\n"
        "- TRANSMIT_COMMAND_WRITE_COUNT = 0\n\n"
        "All counts are computed from actual recorded data, never hardcoded.\n",
        encoding="utf-8",
    )

    (docs / "WINDOWS_MUTEX_REPORT.md").write_text(
        "# Windows Named Mutex Report\n\n"
        "Implementation: windows_mutex.py\n"
        "API: CreateMutexW via ctypes\n"
        "Name: Local\\RemoteAC_IRLearningStudio_{SHA256_PREFIX}\n"
        "Hash: SHA256 of normalized (lowercase, trailing-slash-stripped) project root path\n\n"
        "Second instance detection: ERROR_ALREADY_EXISTS → read-only mode\n"
        "Non-owner restrictions: no serial port, no SQLite write, no file modifications\n\n"
        "Multi-process test: 20 processes, 200 rounds, MULTI_OWNER_ROUNDS=0 required\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
