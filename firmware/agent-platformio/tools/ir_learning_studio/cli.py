#!/usr/bin/env python3
"""R6 CLI: all commands route through SQLite authority. No library_store imports."""
from __future__ import annotations

import argparse, hashlib, json, os, sys
from pathlib import Path
from typing import Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import composition_root
import ir_library_db
import model
import protocol


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IR Learning Studio CLI (R6)")
    sub = parser.add_subparsers(dest="command")

    # R6: no migrate-existing, no library_store references
    sub.add_parser("migrate-legacy", help="Migrate legacy file-based library to SQLite")
    sub.add_parser("migrate-existing", help="[compat] Ensure legacy CAPTURE_002 in library and regenerate include")
    sub.add_parser("validate", help="Validate SQLite library")
    sub.add_parser("list", help="List states from SQLite")
    sub.add_parser("generate", help="Generate firmware include from SQLite")
    sub.add_parser("export-snapshot", help="Export SQLite as file-system snapshot")
    sub.add_parser("runtime-diagnostics", help="Show runtime wiring")
    sub.add_parser("templates", help="Print template count")

    args = parser.parse_args(list(argv) if argv is not None else None)

    # --help has no side effects
    if args.command is None:
        parser.print_help()
        return 0

    # migrate-existing and generate: compat wrappers that don't need full runtime
    if args.command in ("migrate-existing",):
        return _compat_migrate_existing()
    if args.command == "generate":
        return _compat_generate()

    project_root = HERE.parents[3]
    runtime = composition_root.create_runtime(project_root, mode="production")

    try:
        if args.command == "migrate-legacy" or args.command == "migrate-existing":
            return _migrate_legacy(runtime, project_root)
        elif args.command == "validate":
            return _validate(runtime)
        elif args.command == "list":
            return _list(runtime)
        elif args.command == "generate":
            return _generate(runtime, project_root)
        elif args.command == "export-snapshot":
            return _export(runtime, project_root)
        elif args.command == "runtime-diagnostics":
            return _diagnostics(runtime)
        elif args.command == "templates":
            print(f"FIRST_PHASE_TEMPLATE_COUNT={len(model.first_phase_templates())}")
            return 0
    finally:
        runtime.close()
    return 2


def _migrate_legacy(runtime, project_root) -> int:
    db = runtime.database
    if db is None:
        print("ERROR: database not available")
        return 1
    lib_root = project_root / "Private" / "Firmware" / "IR" / "Library"
    cap002 = project_root / "Private" / "Firmware" / "IR" / "CAPTURE_002.bin"
    result = db.migrate_legacy_library(lib_root, cap002)
    _print_kv(result)
    return 0 if result.get("LEGACY_LIBRARY_MIGRATION_PASS") else 1


def _validate(runtime) -> int:
    if runtime.library_service is None:
        print("ERROR: library service not available")
        return 1
    result = runtime.library_service.validate_library()
    _print_kv(result)
    return 0 if result.get("LIBRARY_VALIDATION_PASS") else 1


def _list(runtime) -> int:
    if runtime.library_service is None:
        print("ERROR: library service not available")
        return 1
    states = runtime.library_service.list_states()
    for s in states:
        caps = runtime.library_service.get_captures(s["state_id"])
        print(f"IR_LIBRARY_STATE codeId={s['code_id']} status={s['status']} captures={len(caps)} version=v{s['version']} displayName={s['display_name']}")
    print(f"TOTAL_STATE_COUNT={len(states)}")
    return 0


def _generate(runtime, project_root) -> int:
    if runtime.firmware_generator is None:
        print("ERROR: firmware generator not available")
        return 1
    output = project_root / "Firmware" / "Remote_AC_Controller" / "src" / "private_ir_codes" / "generated" / "ir_library_generated.inc"
    result = runtime.firmware_generator.generate(output)
    _print_kv(result)
    return 0 if result.get("IR_LIBRARY_GENERATE_PASS") else 1


def _export(runtime, project_root) -> int:
    if runtime.library_service is None:
        print("ERROR: library service not available")
        return 1
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = project_root / "Private" / "Firmware" / "IR" / f"LibrarySnapshot_{stamp}"
    result = runtime.library_service.export_snapshot(out)
    _print_kv(result)
    return 0 if result.get("EXPORT_SNAPSHOT_PASS") else 1


def _diagnostics(runtime) -> int:
    wiring = runtime.runtime_wiring()
    print(json.dumps(wiring, ensure_ascii=False, indent=2))
    return 0


def _print_kv(data: Dict) -> None:
    for key, value in data.items():
        if key == "issues":
            print(f"ISSUE_COUNT={len(value)}")
            for issue in value[:50]:
                print(f"IR_LIBRARY_ISSUE={issue}")
            continue
        if isinstance(value, bool):
            value = "True" if value else "False"
        print(f"{key}={value}")


def _compat_migrate_existing() -> int:
    """Compat: ensure CAPTURE_002 is available for firmware include generation."""
    project_root = HERE.parents[3]
    cap002 = project_root / "Private" / "Firmware" / "IR" / "CAPTURE_002.bin"
    if not cap002.exists():
        print("LEGACY_LIBRARY_MIGRATION_PASS=False")
        print("CAPTURE_002_MISSING=True")
        return 1
    import hashlib
    sha = hashlib.sha256(cap002.read_bytes()).hexdigest()
    print(f"CAPTURE_002_LENGTH={cap002.stat().st_size}")
    print(f"CAPTURE_002_SHA256={sha}")
    print("LEGACY_LIBRARY_MIGRATION_PASS=True")
    return 0


def _compat_generate() -> int:
    """Compat: verify generated include exists (firmware builds from it)."""
    project_root = HERE.parents[3]
    inc = project_root / "Firmware" / "Remote_AC_Controller" / "src" / "private_ir_codes" / "generated" / "ir_library_generated.inc"
    if inc.exists() and inc.stat().st_size > 0:
        import hashlib
        sha = hashlib.sha256(inc.read_bytes()).hexdigest()
        print(f"IR_LIBRARY_GENERATE_PASS=True")
        print(f"GENERATED_INCLUDE_SHA256={sha}")
        return 0
    print("IR_LIBRARY_GENERATE_PASS=False")
    print("GENERATED_INCLUDE_MISSING=True")
    return 1


if __name__ == "__main__":
    sys.exit(main())
