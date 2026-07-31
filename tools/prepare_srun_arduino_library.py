#!/usr/bin/env python3
"""Generate an Arduino-layout srun-c library from the single authoritative source.

WHY THIS EXISTS
---------------
The repository keeps exactly ONE copy of the srun-c sources, in the PlatformIO
layout that upstream/PlatformIO expects:

    firmware/agent-platformio/lib/srun-c/
        include/   srun.h, compat.h
        src/       srun.c, md.c, *.cpp adapters

``arduino-cli`` / the Arduino IDE do not understand the ``include/`` + ``src/``
split: a library must expose every header and translation unit under a single
``src/`` directory (or a flat root). Naively copying the PlatformIO directory
into ``<sketchbook>/libraries`` therefore does NOT work -- ``#include <srun.h>``
fails to resolve.

Rather than committing a second, divergent copy of the sources (which would be
two authorities for one protocol implementation), this script *derives* an
Arduino-compatible library on demand, deterministically, into a temporary
directory that is never committed.

GUARANTEES
----------
* Single source of truth  - reads only ``firmware/agent-platformio/lib/srun-c``.
* No algorithm changes    - files are copied byte-for-byte; nothing is rewritten.
* Deterministic           - identical input always yields an identical manifest
                            (stable ordering, fixed metadata, no timestamps).
* Fail closed             - an unknown file in the source tree, or a missing
                            expected file, aborts with a non-zero exit code
                            instead of silently producing a partial library.
* Licence preserved       - LICENSE and a THIRD_PARTY_NOTICE always ship.
* Never writes into the repository working tree.

USAGE
-----
    python tools/prepare_srun_arduino_library.py --output <dir>
    python tools/prepare_srun_arduino_library.py --output <dir> --verify-deterministic

``--output`` must be outside the repository (a scratch/CI temp directory, or the
Arduino sketchbook's ``libraries/`` folder when you want to build locally).

This script never touches credentials, never compiles, never flashes hardware
and never performs any network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

# --- The authoritative source tree, relative to the repository root ----------
SRUN_SOURCE_RELPATH = Path("firmware/agent-platformio/lib/srun-c")

# --- Exact expected inventory of the authoritative tree ----------------------
# Any deviation (missing entry, or a file present here that is not listed) is a
# hard error: an unreviewed source file must never be silently vendored into a
# generated library, and a silently dropped file would break the build in a way
# that is hard to diagnose.
EXPECTED_INCLUDE_HEADERS = ("compat.h", "srun.h")
EXPECTED_SRC_FILES = (
    "arduinojson.cpp",
    "esp8266_http_adapter_secure.cpp",
    "esp8266_mock_adapter.cpp",
    "md.c",
    "srun.c",
)
EXPECTED_METADATA_FILES = ("LICENSE", "README_UPSTREAM.md", "library.json")

# --- Generated library.properties (Arduino library specification 1.5) --------
# Kept constant so repeated runs are byte-identical. The version mirrors
# library.json; upstream provenance lives in README_UPSTREAM.md / NOTICE.
LIBRARY_PROPERTIES = """\
name=srun-c
version=1.1.0
author=45gfg9
maintainer=remote-ac-controller
sentence=srun campus network authentication client for ESP8266.
paragraph=GENERATED - do not edit. Produced by tools/prepare_srun_arduino_library.py from the single authoritative copy at firmware/agent-platformio/lib/srun-c. Edit the repository copy and re-run the script.
category=Communication
url=https://github.com/45gfg9/srun-c
architectures=esp8266
includes=srun.h
depends=ArduinoJson
"""

THIRD_PARTY_NOTICE = """\
THIRD PARTY NOTICE - srun-c
===========================

This directory is a GENERATED, Arduino-layout copy of the vendored srun-c
sources. It is produced by tools/prepare_srun_arduino_library.py and is not
part of the git-tracked repository content.

Upstream project : srun-c
Upstream URL     : https://github.com/45gfg9/srun-c
Upstream author  : 45gfg9
Upstream licence : WTFPL (see LICENSE in this directory)
Pinned commit    : 1881da8fa98e52041fb92f38888b3d5eb4789f7a

Project modifications (documented in README_UPSTREAM.md):
  - ESP8266 HTTPS adapter uses TLS certificate pinning instead of
    setInsecure(); credentials are never transmitted over an unverified
    connection.
  - An ArduinoJson-based JSON layer replaces cJSON for the embedded target.
  - A mock adapter is provided for host-side and offline builds.

The srun authentication algorithm itself (challenge handling, parameter
ordering, encoding and checksum) is byte-identical to upstream.

The enclosing project, Remote AC Controller, is licensed under the Apache
License 2.0; see LICENSE and NOTICE at the repository root.
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    print(f"SRUN_ADAPTER_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def audit_source(source: Path) -> tuple[list[Path], list[Path]]:
    """Validate the authoritative tree and return (headers, sources)."""
    if not source.is_dir():
        fail(f"authoritative srun-c source not found: {source}")

    include_dir = source / "include"
    src_dir = source / "src"
    for directory in (include_dir, src_dir):
        if not directory.is_dir():
            fail(f"missing expected directory: {directory}")

    def audit(directory: Path, expected: tuple[str, ...]) -> list[Path]:
        actual = sorted(p.name for p in directory.iterdir() if p.is_file())
        unexpected = sorted(set(actual) - set(expected))
        missing = sorted(set(expected) - set(actual))
        if unexpected:
            fail(
                f"unknown source file(s) in {directory.name}/: {', '.join(unexpected)} "
                "- review the file, then add it to the expected inventory in this script"
            )
        if missing:
            fail(f"missing source file(s) in {directory.name}/: {', '.join(missing)}")
        return [directory / name for name in expected]

    headers = audit(include_dir, EXPECTED_INCLUDE_HEADERS)
    sources = audit(src_dir, EXPECTED_SRC_FILES)

    for name in EXPECTED_METADATA_FILES:
        if not (source / name).is_file():
            fail(f"missing metadata file: {source / name}")

    return headers, sources


def generate(source: Path, output_root: Path) -> dict:
    headers, sources = audit_source(source)

    library_dir = output_root / "srun-c"
    if library_dir.exists():
        shutil.rmtree(library_dir)
    src_out = library_dir / "src"
    src_out.mkdir(parents=True)

    # Headers from include/ and translation units from src/ are flattened into a
    # single src/ directory. Relative #include "..." between them keeps working
    # because they end up as siblings, exactly as under the PlatformIO layout
    # where src/ files include headers resolved from include/.
    emitted: list[Path] = []
    for path in headers + sources:
        target = src_out / path.name
        if target.exists():
            fail(f"filename collision while flattening: {path.name}")
        shutil.copyfile(path, target)
        emitted.append(target)

    shutil.copyfile(source / "LICENSE", library_dir / "LICENSE")
    shutil.copyfile(source / "README_UPSTREAM.md", library_dir / "README_UPSTREAM.md")
    (library_dir / "library.properties").write_text(LIBRARY_PROPERTIES, encoding="utf-8", newline="\n")
    (library_dir / "THIRD_PARTY_NOTICE").write_text(THIRD_PARTY_NOTICE, encoding="utf-8", newline="\n")

    manifest_files = sorted(
        (p for p in library_dir.rglob("*") if p.is_file() and p.name != "MANIFEST.json"),
        key=lambda p: p.relative_to(library_dir).as_posix(),
    )
    manifest = {
        "generator": "tools/prepare_srun_arduino_library.py",
        "authoritative_source": SRUN_SOURCE_RELPATH.as_posix(),
        "upstream": "https://github.com/45gfg9/srun-c",
        "upstream_commit": "1881da8fa98e52041fb92f38888b3d5eb4789f7a",
        "license": "WTFPL",
        "input_file_count": len(headers) + len(sources) + len(EXPECTED_METADATA_FILES),
        "output_file_count": len(manifest_files),
        "files": [
            {
                "path": p.relative_to(library_dir).as_posix(),
                "size": p.stat().st_size,
                "sha256": sha256_file(p),
            }
            for p in manifest_files
        ],
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    (library_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--output",
        required=True,
        help="destination directory (a 'srun-c' subdirectory is created inside). Must be outside the repository.",
    )
    parser.add_argument(
        "--verify-deterministic",
        action="store_true",
        help="generate a second copy into a scratch directory and assert the manifests match",
    )
    args = parser.parse_args()

    root = repo_root()
    source = root / SRUN_SOURCE_RELPATH
    output_root = Path(args.output).resolve()

    try:
        output_root.relative_to(root)
    except ValueError:
        pass
    else:
        fail(
            f"refusing to write inside the repository ({output_root}); "
            "the generated library must never be committed"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = generate(source, output_root)

    print(f"SRUN_CANONICAL_SOURCE_PATH={SRUN_SOURCE_RELPATH.as_posix()}")
    print(f"SRUN_ADAPTER_INPUT_FILE_COUNT={manifest['input_file_count']}")
    print(f"SRUN_ADAPTER_OUTPUT_FILE_COUNT={manifest['output_file_count']}")
    print(f"SRUN_ADAPTER_MANIFEST_SHA256={manifest['manifest_sha256']}")
    print(f"SRUN_ADAPTER_OUTPUT_PATH={(output_root / 'srun-c')}")
    print("SRUN_ADAPTER_MANIFEST_PASS=True")

    if args.verify_deterministic:
        with tempfile.TemporaryDirectory(prefix="srun-adapter-verify-") as scratch:
            second = generate(source, Path(scratch))
        if second["manifest_sha256"] != manifest["manifest_sha256"]:
            fail("second generation produced a different manifest (non-deterministic)")
        print("SRUN_ADAPTER_DETERMINISTIC_PASS=True")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
