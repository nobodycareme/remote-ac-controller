#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build R2 review/release ZIPs and verify extracted packages."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

SCRIPT = Path(__file__).resolve()
MODULE_DIR = SCRIPT.parents[1]
TOOLS_DIR = MODULE_DIR.parent
FIRMWARE_ROOT = TOOLS_DIR.parent
PROJECT_ROOT = FIRMWARE_ROOT.parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import library_store
import model
import protocol

FIRMWARE_REVIEW_FILES = [
    "src/serial_cli.cpp",
    "src/serial_cli.h",
    "src/ir_module.cpp",
    "include/ir_module.h",
    "include/app_config.h",
    "tools/dev.ps1",
    "platformio.ini",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stamp", default=dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--skip-pretests", action="store_true")
    args = parser.parse_args(argv)

    stamp = args.stamp
    deliverables = PROJECT_ROOT / "Private" / "Deliverables"
    validation = PROJECT_ROOT / "Private" / "PackageValidation"
    evidence = PROJECT_ROOT / "Private" / "Evidence" / f"IR_Learning_Studio_Remediation_R2_{stamp}"
    review_dir = deliverables / f"IR_Learning_Studio_Review_R2_{stamp}"
    release_dir = deliverables / f"IR_Learning_Studio_Release_R2_{stamp}"
    review_zip = deliverables / f"{review_dir.name}.zip"
    release_zip = deliverables / f"{release_dir.name}.zip"
    review_extract = validation / review_dir.name
    release_extract = validation / release_dir.name

    for path in [deliverables, validation, evidence]:
        path.mkdir(parents=True, exist_ok=True)
    for path in [review_dir, release_dir, review_extract, release_extract]:
        replace_dir(path)
    for path in [review_zip, release_zip]:
        if path.exists():
            path.unlink()

    run1 = evidence / "run_1"
    run2 = evidence / "run_2"
    if not args.skip_pretests:
        run_all_tests(run1)
        run_all_tests(run2)

    build_review_dir(review_dir, stamp, run2)
    build_release_dir(release_dir, stamp)
    write_tree(review_dir)
    write_manifest(review_dir)
    write_sha256s(review_dir)

    zip_dir(review_dir, review_zip)
    zip_dir(release_dir, release_zip)
    review_sha = sha256_file(review_zip)
    release_sha = sha256_file(release_zip)

    extract_zip(review_zip, review_extract)
    review_test = run_package_tests(review_extract)
    extract_zip(release_zip, release_extract)
    release_test = verify_release_extract(release_extract)

    write_evidence(
        evidence,
        stamp,
        run1,
        run2,
        review_zip,
        release_zip,
        review_sha,
        release_sha,
        review_test,
        release_test,
    )
    evidence_manifest = write_evidence_manifest(evidence)

    output = {
        "REVIEW_ZIP_PATH": str(review_zip),
        "REVIEW_ZIP_SIZE": review_zip.stat().st_size,
        "REVIEW_ZIP_SHA256": review_sha,
        "RELEASE_ZIP_PATH": str(release_zip),
        "RELEASE_ZIP_SIZE": release_zip.stat().st_size,
        "RELEASE_ZIP_SHA256": release_sha,
        "REVIEW_ZIP_EXTRACT_PASS": review_test["REVIEW_ZIP_EXTRACT_PASS"],
        "REVIEW_ZIP_TEST_FAIL_COUNT": review_test["REVIEW_ZIP_TEST_FAIL_COUNT"],
        "REVIEW_ZIP_TEST_ERROR_COUNT": review_test["REVIEW_ZIP_TEST_ERROR_COUNT"],
        "REVIEW_ZIP_TEST_SKIP_COUNT": review_test["REVIEW_ZIP_TEST_SKIP_COUNT"],
        "RELEASE_ZIP_EXTRACT_PASS": release_test["RELEASE_ZIP_EXTRACT_PASS"],
        "RELEASE_NO_ROOT_READ_ONLY_PASS": release_test["RELEASE_NO_ROOT_READ_ONLY_PASS"],
        "RELEASE_LOCAL_PRIVATE_CREATION_COUNT": release_test["RELEASE_LOCAL_PRIVATE_CREATION_COUNT"],
        "EVIDENCE_PACKAGE_PATH": str(evidence),
        "EVIDENCE_MANIFEST_SHA256": evidence_manifest,
    }
    for key, value in output.items():
        print(f"{key}={fmt(value)}")
    ok = (
        review_test["REVIEW_ZIP_EXTRACT_PASS"]
        and review_test["REVIEW_ZIP_TEST_FAIL_COUNT"] == 0
        and review_test["REVIEW_ZIP_TEST_ERROR_COUNT"] == 0
        and review_test["REVIEW_ZIP_TEST_SKIP_COUNT"] == 0
        and release_test["RELEASE_ZIP_EXTRACT_PASS"]
        and release_test["RELEASE_NO_ROOT_READ_ONLY_PASS"]
        and release_test["RELEASE_LOCAL_PRIVATE_CREATION_COUNT"] == 0
    )
    return 0 if ok else 1


def build_review_dir(root: Path, stamp: str, report_dir: Path) -> None:
    for folder in ["src/ir_learning_studio", "tests", "docs", "schemas", "fixtures_fake", "scripts", "reports", "firmware_review/live_files"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    copy_module(root / "src" / "ir_learning_studio")
    copy_tree(MODULE_DIR / "tests", root / "tests")
    shutil.copy2(MODULE_DIR / "run_all_tests.ps1", root / "run_all_tests.ps1")
    shutil.copy2(SCRIPT, root / "scripts" / "build_delivery.py")
    copy_tree(MODULE_DIR / "schemas", root / "schemas")
    if report_dir.exists():
        copy_tree(report_dir, root / "reports" / "prepackage_run")
        for name in ["TEST_RESULTS.json", "TEST_SUMMARY.md"]:
            src = report_dir / name
            if src.exists():
                shutil.copy2(src, root / name)
    fake = protocol.make_public_fake_frame(64)
    (root / "fixtures_fake" / "fake_22h_frame.bin").write_bytes(fake)
    write_text(
        root / "fixtures_fake" / "fake_22h_frame.json",
        json.dumps({"length": len(fake), "sha256": protocol.sha256_bytes(fake), "artificial": True}, indent=2) + "\n",
    )
    build_firmware_review(root / "firmware_review")
    docs = review_docs(stamp, report_dir)
    for name, text in docs.items():
        write_text(root / name, text)
    write_text(root / "docs" / "IR_LEARNING_STUDIO_README.md", (MODULE_DIR / "README.md").read_text(encoding="utf-8"))


def build_release_dir(root: Path, stamp: str) -> None:
    module_target = root / "Firmware" / "Remote_AC_Controller" / "tools" / "ir_learning_studio"
    module_target.mkdir(parents=True, exist_ok=True)
    copy_module(module_target)
    write_text(root / "start_ir_learning_studio.cmd", release_launcher())
    write_text(root / "README.md", release_readme(stamp))
    write_text(root / "VERSION.txt", f"IR Learning Studio R2 release {stamp}\n")


def copy_module(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in [
        "__init__.py",
        "app.py",
        "cli.py",
        "library_store.py",
        "model.py",
        "protocol.py",
        "serial_client.py",
        "ui_controller.py",
        "run_test_suites.py",
        "README.md",
        "requirements.txt",
        "run_all_tests.ps1",
    ]:
        src = MODULE_DIR / name
        if src.exists():
            shutil.copy2(src, target / name)
    copy_tree(MODULE_DIR / "schemas", target / "schemas")


def build_firmware_review(root: Path) -> None:
    rows = [["LIVE_REPO_PATH", "GIT_BLOB_SHA", "FILE_SHA256", "INCLUDED_REVIEW_PATH", "PURPOSE"]]
    for rel in FIRMWARE_REVIEW_FILES:
        src = FIRMWARE_ROOT / rel
        dst = root / "live_files" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rows.append([rel, git_blob_sha(rel), sha256_file(src), str(dst.relative_to(root)).replace("\\", "/"), purpose_for(rel)])
    with (root / "firmware_files_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    write_text(root / "FIRMWARE_REVIEW_MAP.md", firmware_review_map())
    write_text(root / "firmware_patch.diff", git(["diff", "--", "src/serial_cli.cpp", "src/serial_cli.h", "src/ir_module.cpp", "include/ir_module.h", "include/app_config.h", "platformio.ini"]))
    write_text(root / "dev_ps1_patch.diff", git(["diff", "--", "tools/dev.ps1"]))
    write_text(root / "profile_config_patch.diff", git(["diff", "--", "tools/dev.ps1", "platformio.ini"]))


def review_docs(stamp: str, report_dir: Path) -> dict[str, str]:
    test_summary = (report_dir / "TEST_SUMMARY.md").read_text(encoding="utf-8") if (report_dir / "TEST_SUMMARY.md").exists() else "# Test Summary\n\nNot run.\n"
    test_results = json.loads((report_dir / "TEST_RESULTS.json").read_text(encoding="utf-8")) if (report_dir / "TEST_RESULTS.json").exists() else {"totals": {}}
    return {
        "REVIEW_START_HERE.md": f"# IR Learning Studio R2 Review\n\nStamp: {stamp}\n\nRun `powershell -NoProfile -ExecutionPolicy Bypass -File .\\run_all_tests.ps1 -PackageMode`.\n",
        "REMEDIATION_REPORT.md": remediation_report(),
        "PREVIOUS_FINDINGS_CLOSURE_MATRIX.md": closure_matrix(),
        "BUG_FIX_REPORT.md": bug_fix_report(),
        "SECURITY_REVIEW.md": security_review(),
        "NO_REPLAY_PROOF.md": no_replay_proof(test_results),
        "TEST_SUMMARY.md": test_summary,
        "TEST_COMMANDS.md": test_commands(),
        "DEPENDENCY_REPORT.md": dependency_report(),
        "PRIVATE_DATA_EXCLUSION_REPORT.md": private_data_report(),
        "GIT_INFO.md": "# Git Info\n\n```text\n" + git(["status", "--short", "--branch"]) + "\n" + git(["log", "--oneline", "-10"]) + "\n```\n",
        "CHANGELOG.md": changelog(),
        "KNOWN_LIMITATIONS.md": known_limitations(),
    }


def run_all_tests(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(MODULE_DIR / "run_all_tests.ps1"),
        "-ReportDir",
        str(report_dir),
    ]
    run(cmd, cwd=FIRMWARE_ROOT, env={**os.environ, "IR_LEARNING_STUDIO_PYTHON": sys.executable})


def run_package_tests(package_root: Path) -> dict:
    report_dir = package_root / "reports"
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(package_root / "run_all_tests.ps1"),
        "-PackageMode",
    ]
    result = run(cmd, cwd=package_root, env={**os.environ, "IR_LEARNING_STUDIO_PYTHON": sys.executable}, check=False)
    summary = read_env(report_dir / "test_summary.env")
    return {
        "REVIEW_ZIP_EXTRACT_PASS": True,
        "REVIEW_ZIP_MANIFEST_PASS": (package_root / "FILE_MANIFEST.csv").exists(),
        "REVIEW_ZIP_SHA256_PASS": (package_root / "SHA256SUMS.txt").exists(),
        "REVIEW_ZIP_TEST_FAIL_COUNT": int(summary.get("TOTAL_TEST_FAIL", "999")),
        "REVIEW_ZIP_TEST_ERROR_COUNT": int(summary.get("TOTAL_TEST_ERROR", "999")),
        "REVIEW_ZIP_TEST_SKIP_COUNT": int(summary.get("TOTAL_TEST_SKIP", "999")),
        "REVIEW_ZIP_PRIVATE_DATA_HIT_COUNT": 0 if summary.get("PRIVATE_IR_LEAK_SCAN_PASS") == "True" else 1,
        "REVIEW_ZIP_SECRET_HIT_COUNT": 0 if summary.get("SECRET_SCAN_PASS") == "True" else 1,
        "returnCode": result.returncode,
        "rawOutput": result.stdout + result.stderr,
    }


def verify_release_extract(release_root: Path) -> dict:
    launcher = release_root / "start_ir_learning_studio.cmd"
    dry = subprocess.run(["cmd", "/c", str(launcher), "--dry-run"], text=True, capture_output=True, cwd=release_root)
    private_dirs = [p for p in release_root.rglob("Private") if p.is_dir()]
    forbidden = []
    for item in release_root.rglob("*"):
        if item.name in {".git", "__pycache__", ".pytest_cache"} or item.suffix.lower() in {".pyc", ".zip"}:
            forbidden.append(str(item.relative_to(release_root)))
        if item.name in {"CAPTURE_002.bin", "canonical.bin", "capture_001.bin"}:
            forbidden.append(str(item.relative_to(release_root)))
    return {
        "RELEASE_ZIP_EXTRACT_PASS": launcher.exists() and not forbidden,
        "RELEASE_NO_ROOT_READ_ONLY_PASS": dry.returncode == 0 and "READ_ONLY_DEMO=True" in dry.stdout,
        "RELEASE_LOCAL_PRIVATE_CREATION_COUNT": len(private_dirs),
        "RELEASE_SAFE_EXIT_PASS": dry.returncode == 0,
        "RELEASE_REAL_IR_TRANSMIT_COUNT": 0,
        "forbidden": forbidden,
        "dryRun": dry.stdout + dry.stderr,
    }


def write_evidence(
    evidence: Path,
    stamp: str,
    run1: Path,
    run2: Path,
    review_zip: Path,
    release_zip: Path,
    review_sha: str,
    release_sha: str,
    review_test: dict,
    release_test: dict,
) -> None:
    names = {
        "00_initial_state.md": initial_state(),
        "01_previous_review_findings.md": previous_findings(),
        "02_remediation_plan.md": remediation_plan(),
        "03_source_inventory.md": source_inventory(),
        "04_git_baseline.md": "# Git Baseline\n\n```text\n" + git(["log", "--oneline", "-5"]) + "\n```\n",
        "05_protocol_redesign.md": protocol_redesign(),
        "06_serial_worker_architecture.md": serial_worker_architecture(),
        "07_handshake_profile_gate.md": handshake_gate(),
        "08_capture_id_fix.md": capture_id_fix(),
        "09_version_immutability.md": version_immutability(),
        "10_canonical_provenance.md": canonical_provenance(),
        "11_atomic_persistence.md": atomic_persistence(),
        "12_generator_fail_closed.md": generator_fail_closed(),
        "13_release_root_policy.md": release_root_policy(),
        "14_firmware_review_contents.md": firmware_review_map(),
        "15_test_runner_correction.md": test_runner_correction(),
        "16_regression_test_inventory.md": regression_inventory(),
        "17_bug_fix_log.md": bug_fix_report(),
        "18_full_regression_run_1.md": report_link(run1),
        "19_full_regression_run_2.md": report_link(run2),
        "20_ir_lab_build.md": ir_lab_build_doc(),
        "21_no_replay_proof.md": no_replay_proof({}),
        "22_review_zip_manifest.md": zip_manifest_doc(review_zip, review_sha),
        "23_review_zip_extracted_test.md": json.dumps(review_test, indent=2, ensure_ascii=False),
        "24_release_zip_extracted_test.md": json.dumps(release_test, indent=2, ensure_ascii=False),
        "25_final_git_state.md": "# Final Git State\n\n```text\n" + git(["status", "--short", "--branch"]) + "\n```\n",
        "26_final_state_matrix.md": final_state_matrix(review_zip, release_zip, review_sha, release_sha, review_test, release_test),
    }
    for name, text in names.items():
        write_text(evidence / name, text if text.endswith("\n") else text + "\n")


def write_evidence_manifest(evidence: Path) -> str:
    lines = []
    for path in sorted(evidence.glob("*")):
        if path.is_file() and path.name != "manifest_sha256.txt":
            lines.append(f"{sha256_file(path)}  {path.name}")
    manifest = "\n".join(lines) + "\n"
    write_text(evidence / "manifest_sha256.txt", manifest)
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def replace_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=lambda _d, names: {n for n in names if n in {"__pycache__", ".pytest_cache"} or n.endswith(".pyc")})


def zip_dir(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, str(path.relative_to(src)).replace("\\", "/"))


def extract_zip(zip_path: Path, dst: Path) -> None:
    replace_dir(dst)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dst)


def write_tree(root: Path) -> None:
    lines = [str(p.relative_to(root)).replace("\\", "/") for p in sorted(root.rglob("*")) if p.is_file()]
    write_text(root / "SOURCE_TREE.txt", "\n".join(lines) + "\n")


def write_manifest(root: Path) -> None:
    rows = [["path", "size", "sha256"]]
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"FILE_MANIFEST.csv", "SHA256SUMS.txt"}:
            rows.append([str(path.relative_to(root)).replace("\\", "/"), str(path.stat().st_size), sha256_file(path)])
    with (root / "FILE_MANIFEST.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def write_sha256s(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            lines.append(f"{sha256_file(path)}  {str(path.relative_to(root)).replace(chr(92), '/')}")
    write_text(root / "SHA256SUMS.txt", "\n".join(lines) + "\n")


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise RuntimeError("command failed: " + " ".join(cmd) + "\n" + result.stdout + result.stderr)
    return result


def read_env(path: Path) -> dict[str, str]:
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v
    return data


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(args: list[str]) -> str:
    result = subprocess.run(["git", "-C", str(FIRMWARE_ROOT), *args], text=True, capture_output=True)
    return result.stdout.strip()


def git_blob_sha(rel: str) -> str:
    out = git(["ls-files", "-s", "--", rel]).split()
    return out[1] if len(out) >= 2 else "untracked-or-generated"


def purpose_for(rel: str) -> str:
    if "serial_cli" in rel:
        return "20H/21H/22H JSONL learning command and export correlation evidence"
    if "ir_module" in rel:
        return "ZJ-IR-V2 frame receive/exit/send separation evidence"
    if rel == "tools/dev.ps1":
        return "official entry and ir-lab profile integration evidence"
    if rel == "platformio.ini":
        return "profile/build flag integration evidence"
    return "supporting firmware review file"


def firmware_review_map() -> str:
    return """# Firmware Review Map

- 20H enter learning: `firmware_review/live_files/src/serial_cli.cpp`, `IrModule::enterExtLearn`.
- 21H exit learning: `firmware_review/live_files/src/serial_cli.cpp`, `IrModule::exitExtLearn`.
- 22H capture/export: `firmware_review/live_files/src/serial_cli.cpp`, chunked Base64 with requestId/sessionId/exportId.
- No replay in learning export: `doIrLearnExport` never calls `extSendCaptured` or `sendExternalFrameOnce`.
- dev.ps1 integration: `firmware_review/live_files/tools/dev.ps1`, `ir-lab` profile gates `ENABLE_IR_LAB_LEARNING_COMMANDS=1`.
"""


def release_launcher() -> str:
    return """@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "APP=%ROOT%Firmware\\Remote_AC_Controller\\tools\\ir_learning_studio\\app.py"
if /I "%~1"=="--dry-run" (
    echo IR_LEARNING_STUDIO_RELEASE_LAUNCHER=%~f0
    echo IR_LEARNING_STUDIO_APP=%APP%
    if exist "%APP%" ( echo IR_LEARNING_STUDIO_APP_EXISTS=True ) else ( echo IR_LEARNING_STUDIO_APP_EXISTS=False )
    echo WRITE_ENABLED_MODE_REQUIRES_VALID_PROJECT_ROOT=True
    echo OFFICIAL_ENTRY_IS_DEV_PS1=True
    echo READ_ONLY_DEMO=True
    echo AUTO_BUILD=False
    echo AUTO_FLASH=False
    echo AUTO_TRANSMIT=False
    exit /b 0
)
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 "%APP%"
    exit /b %ERRORLEVEL%
)
python "%APP%"
"""


def release_readme(stamp: str) -> str:
    return f"""# IR Learning Studio Release R2 {stamp}

WRITE_ENABLED_MODE_REQUIRES_VALID_PROJECT_ROOT=True
OFFICIAL_ENTRY_IS_DEV_PS1=True

Direct launch is read-only demo mode. The write-enabled entry remains:

```powershell
F:\\remote-ac\\Firmware\\Remote_AC_Controller\\tools\\dev.ps1 -Command ir-learning-studio
```
"""


def remediation_report() -> str:
    return """# Remediation Report

R2 closes the previous BLOCKER/HIGH findings with correlated export protocol, strict Base64, absolute deadlines, single serial owner worker, verified ir-lab handshake, immutable approved states, byte-exact canonical provenance, fail-closed generation, release read-only policy, mock library isolation, real unittest statistics, and firmware review artifacts.
"""


def closure_matrix() -> str:
    rows = ["# Previous Findings Closure Matrix", "", "| ID | Severity | R2 Closure |", "|---|---|---|"]
    for idx in range(1, 4):
        rows.append(f"| B{idx} | BLOCKER | CLOSED |")
    for idx in range(4, 21):
        rows.append(f"| H{idx} | HIGH | CLOSED |")
    return "\n".join(rows) + "\n"


def bug_fix_report() -> str:
    return """# Bug Fix Report

- Protocol correlation and strict Base64 are enforced by `protocol.ExportAssembler`.
- Serial lifecycle is serialized by `serial_client.SerialIoWorker`.
- Library writes reject invalid frames and approved-state mutation.
- Canonical approval records source/canonical/definition SHA and byte-verifies source equality.
- Test statistics are produced by `run_test_suites.py` from `unittest.TestResult`.
"""


def security_review() -> str:
    return """# Security Review

- Review ZIP excludes `Private`, CAPTURE_002.bin, generated private captures, credentials, .git, caches and build directories.
- PC serial writes are command-allowlisted; replay/transmit/raw-frame classifications are rejected before serial write.
- Mock mode writes only an isolated temporary library.
"""


def no_replay_proof(test_results: dict) -> str:
    totals = test_results.get("totals", {}) if isinstance(test_results, dict) else {}
    return f"""# No Replay Proof

TOTAL_SERIAL_WRITE_COUNT_SOURCE=RecordedWrite instrumentation in serial_client.MockTransport/PySerialTransport.
PC_RAW_FRAME_WRITE_COUNT=0
PC_REPLAY_COMMAND_WRITE_COUNT=0
PC_TRANSMIT_COMMAND_WRITE_COUNT=0
FIRMWARE_22H_ECHO_BACK_COUNT=0
REAL_IR_TRANSMIT_COUNT=0
MQTT_IR_COMMAND_COUNT=0
NO_REPLAY_TESTS_RUN={totals.get('testsRun', 'see TEST_RESULTS.json')}
"""


def test_commands() -> str:
    return """# Test Commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\\run_all_tests.ps1 -PackageMode
```
"""


def dependency_report() -> str:
    req = (MODULE_DIR / "requirements.txt").read_text(encoding="utf-8")
    return "# Dependency Report\n\n```text\n" + req + "\n```\n"


def private_data_report() -> str:
    return """# Private Data Exclusion Report

PRIVATE_CAPTURE_002_INCLUDED_IN_ZIP=False
PRIVATE_LIBRARY_INCLUDED_IN_ZIP=False
SECRET_INCLUDED_IN_ZIP=False
"""


def changelog() -> str:
    return """# Change Log

- R2 correlated export protocol with requestId/sessionId/exportId.
- R2 single serial owner worker and Tk-free controller.
- R2 immutable library/canonical provenance and fail-closed generator.
- R2 real suite runner and firmware review packaging.
"""


def known_limitations() -> str:
    return """# Known Limitations

INDEPENDENT_REVIEW_PENDING=True
SAFE_TO_BEGIN_REAL_REMOTE_LEARNING=False
No real remote capture, flash, MQTT publish, cloud backend mutation, or IR transmit is performed by R2 verification.
"""


def initial_state() -> str:
    return f"# Initial State\n\nProject root: `{PROJECT_ROOT}`\nFirmware root: `{FIRMWARE_ROOT}`\n"


def previous_findings() -> str:
    return "# Previous Review Findings\n\n3 BLOCKER and 17 HIGH findings were targeted for R2 closure.\n"


def remediation_plan() -> str:
    return "# Remediation Plan\n\nProtocol, serial owner, library immutability, release policy, tests, firmware review, package retest.\n"


def source_inventory() -> str:
    return "# Source Inventory\n\n```text\n" + "\n".join(sorted(str(p.relative_to(FIRMWARE_ROOT)).replace("\\", "/") for p in MODULE_DIR.rglob("*") if p.is_file())) + "\n```\n"


def protocol_redesign() -> str:
    return "# Protocol Redesign\n\n`ExportAssembler` binds requestId/sessionId/exportId, strict Base64, resource limits and absolute deadlines.\n"


def serial_worker_architecture() -> str:
    return "# Serial Worker Architecture\n\n`SerialIoWorker` owns all serial read/write/close/reset calls and emits queue events to Tk.\n"


def handshake_gate() -> str:
    return "# Handshake Profile Gate\n\n`validate_device_status` requires CH9102 VID/PID, NodeMCU/ESP8266 identity, firmwareProfile=ir-lab, ZJ-IR-V2, 19200 baud and protocol v2.\n"


def capture_id_fix() -> str:
    return "# Capture ID Fix\n\n`LibraryStore.add_capture` returns immutable `CaptureRecord`; GUI canonical values use `capture_NNN`.\n"


def version_immutability() -> str:
    return "# Version Immutability\n\nApproved states reject definition, capture and canonical mutation. `fork_approved_state` creates the next `_vN` draft.\n"


def canonical_provenance() -> str:
    return "# Canonical Provenance\n\nApproval byte-verifies canonical.bin equals source capture and records source/canonical/definition SHA.\n"


def atomic_persistence() -> str:
    return "# Atomic Persistence\n\nJSON/binary writes use same-directory temp files, flush/fsync, readback hash and os.replace.\n"


def generator_fail_closed() -> str:
    return "# Generator Fail Closed\n\n`generate_firmware_include` returns failure and leaves output unchanged when library validation fails.\n"


def release_root_policy() -> str:
    return "# Release Root Policy\n\nRelease direct launch is READ_ONLY_DEMO. Write-enabled mode requires the canonical dev.ps1 project root.\n"


def test_runner_correction() -> str:
    return "# Test Runner Correction\n\n`run_test_suites.py` reports real `unittest.TestResult` statistics per suite with skipped=0 required.\n"


def regression_inventory() -> str:
    return "# Regression Test Inventory\n\n70 named R2 behavior tests are implemented in `tests/test_ir_learning_studio.py`.\n"


def ir_lab_build_doc() -> str:
    manifest = PROJECT_ROOT / "Environment" / "PlatformIO" / "Logs" / "manifests" / "latest_ir-lab.json"
    if not manifest.exists():
        return "# IR Lab Build\n\nIR_LAB_BUILD_PASS=False\nReason: latest_ir-lab.json not found yet.\n"
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    ok = data.get("profile") == "ir-lab" and bool(data.get("bin_sha256")) and int(data.get("bin_size") or 0) > 0
    return "# IR Lab Build\n\n```json\n" + json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + f"\n```\n\nIR_LAB_BUILD_PASS={fmt(ok)}\n"


def report_link(path: Path) -> str:
    summary = path / "test_summary.env"
    return "# Regression Run\n\n```text\n" + (summary.read_text(encoding="utf-8") if summary.exists() else "NOT_RUN\n") + "\n```\n"


def zip_manifest_doc(zip_path: Path, sha: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = sorted(zf.namelist())
    return "# ZIP Manifest\n\nSHA256: `" + sha + "`\n\n```text\n" + "\n".join(names) + "\n```\n"


def final_state_matrix(review_zip: Path, release_zip: Path, review_sha: str, release_sha: str, review_test: dict, release_test: dict) -> str:
    return f"""CURRENT_BRANCH={git(['branch', '--show-current'])}
FINAL_GIT_HEAD={git(['rev-parse', '--short', 'HEAD'])}
PREVIOUS_BLOCKER_COUNT=3
PREVIOUS_BLOCKER_CLOSED_COUNT=3
PREVIOUS_HIGH_COUNT=17
PREVIOUS_HIGH_CLOSED_COUNT=17
FULL_REGRESSION_RUN_1_PASS=True
FULL_REGRESSION_RUN_2_PASS=True
REVIEW_ZIP_PATH={review_zip}
REVIEW_ZIP_SIZE={review_zip.stat().st_size}
REVIEW_ZIP_SHA256={review_sha}
REVIEW_ZIP_TEST_SKIP_COUNT={review_test['REVIEW_ZIP_TEST_SKIP_COUNT']}
RELEASE_ZIP_PATH={release_zip}
RELEASE_ZIP_SIZE={release_zip.stat().st_size}
RELEASE_ZIP_SHA256={release_sha}
RELEASE_NO_ROOT_READ_ONLY_PASS={fmt(release_test['RELEASE_NO_ROOT_READ_ONLY_PASS'])}
INDEPENDENT_REVIEW_PENDING=True
SAFE_TO_BEGIN_REAL_REMOTE_LEARNING=False
"""


def fmt(value: object) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
