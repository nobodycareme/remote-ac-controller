#!/usr/bin/env python3
# build_zip.py
# Create a ZIP archive using FORWARD-SLASH entry names so it extracts without
# warnings on both Windows and Linux (Section 8 requirement).
#
# Usage:
#   python build_zip.py <stage_dir> <output_zip>
import os
import sys
import zipfile


def main():
    if len(sys.argv) < 3:
        print("usage: build_zip.py <stage> <output.zip>", file=sys.stderr)
        return 2
    stage = sys.argv[1]
    out = sys.argv[2]
    if os.path.exists(out):
        os.remove(out)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(stage):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, stage).replace("\\", "/")
                z.write(full, rel)
                count += 1
    print("ZIP_ENTRIES=%d" % count, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
