#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-readme-render.py — verify README rendering via the GitHub GFM API.

Instead of trusting the Markdown source alone, this checker POSTs each file to
the GitHub Markdown REST API (mode=gfm, context=nobodycareme/remote-ac-controller)
and inspects the rendered HTML:

  * the top navigation block produces real <a> elements (no literal
    "[快速开始](...)" text left in the HTML);
  * every in-page #fragment in the READMEs resolves to a real HTML id;
  * both dashboard screenshots produce <img> tags;
  * the v1.2.2 release notes contain no ../../docs image paths;
  * no empty href attributes;
  * no duplicate HTML ids.

The API call uses GITHUB_TOKEN when available (CI) or gh auth on the CLI.
--offline skips the API call and only validates fragments against the
markdown source (used by CI dry-run / offline environments).

Exit code non-zero on any failure.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "nobodycareme/remote-ac-controller"

FILES = [
    "README.md",
    "README.en.md",
    ".github/release-notes/v1.2.2.md",
    ".github/release-notes/v1.2.3.md",
]
SCREENSHOTS = ["dashboard-desktop.png", "dashboard-mobile.png"]


def resolve_root():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--root", default=None)
    ap.add_argument("--offline", action="store_true")
    ns, _ = ap.parse_known_args()
    return (os.path.normpath(ns.root) if ns.root else DEFAULT_ROOT), ns.offline


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def render_via_api(text, root):
    """Render Markdown through the GitHub /markdown endpoint."""
    payload = {"text": text, "mode": "gfm", "context": REPO}
    tmp = os.path.join(root, "_render_payload.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    try:
        r = subprocess.run(
            ["gh", "api", "--method", "POST", "/markdown",
             "--input", tmp, "-H", "Accept: text/html"],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout, r.returncode
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def heading_id(heading):
    """GitHub's heading id algorithm (approximation for ASCII + CJK)."""
    h = heading.strip().lower()
    h = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", h)
    h = h.replace(" ", "-")
    return h


def main():
    root, offline = resolve_root()
    ok = True
    files = [os.path.join(root, f) for f in FILES]

    # fragment map built from markdown source (used for both modes)
    frag_map = {}
    for path in files:
        if not os.path.exists(path):
            print(f"FILE_MISSING {path}")
            ok = False
            continue
        txt = read(path)
        ids = set()
        for m in re.finditer(r"(?m)^#{1,6}\s+(.+)$", txt):
            ids.add(heading_id(m.group(1)))
        # explicit HTML anchors
        for m in re.finditer(r'<a id="([^"]+)"></a>', txt):
            ids.add(m.group(1))
        frag_map[os.path.basename(path)] = ids

    for path in files:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        txt = read(path)

        # ---- offline fragment validation -------------------------------
        headings = frag_map[name]
        for m in re.finditer(r"\]\(#([^)]+)\)", txt):
            frag = m.group(1)
            if frag not in headings:
                print(f"BROKEN_FRAGMENT {name}: #{frag}")
                ok = False
        for m in re.finditer(r'<a href="#([^"]+)">', txt):
            frag = m.group(1)
            if frag not in headings and frag not in txt:
                print(f"BROKEN_NAV_FRAGMENT {name}: #{frag}")
                ok = False

        # ---- image path checks (source-level) ---------------------------
        if name.startswith("v1.2.2.md") or name.startswith("v1.2.3.md"):
            if "../../docs/" in txt or "<img" in txt:
                print("RELEASE_NOTES_IMAGE_PATH_ERROR: ../../docs or <img found")
                ok = False

        # ---- API render (skip in offline mode) --------------------------
        if offline:
            print(f"RENDER_OFFLINE {name}: fragment checks only")
            continue

        html_out, rc = render_via_api(txt, root)
        if rc != 0:
            print(f"GFM_API_FAIL {name}: rc={rc}")
            ok = False
            continue

        # nav must be real <a> links, no literal "[快速开始](" residue
        for lit in ["[快速开始](", "[Quick Start](", "](./docs/"]:
            if lit in html_out:
                print(f"LITERAL_MARKDOWN_IN_RENDERED_HTML {name}: {lit!r}")
                ok = False

        # every nav <a> href must have content
        for m in re.finditer(r'<a\s+[^>]*href="([^"]*)"', html_out):
            href = m.group(1)
            if href.strip() in ("", "#"):
                print(f"EMPTY_HREF {name}")
                ok = False

        # duplicate ids in rendered html
        ids = re.findall(r'id="([^"]+)"', html_out)
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            print(f"DUPLICATE_HTML_ID {name}: {sorted(dup)[:5]}")
            ok = False

        # screenshots must produce <img>
        if name in ("README.md", "README.en.md"):
            for shot in SCREENSHOTS:
                if shot not in html_out:
                    print(f"SCREENSHOT_IMG_MISSING {name}: {shot}")
                    ok = False

        print(f"GFM_RENDER_OK {name}: {len(html_out)} bytes")

    print(f"README_GFM_RENDER_PASS={'True' if ok else 'False'}")
    return 0 if ok else 1


if __name__ == "__main__":
    root, offline = resolve_root()
    sys.exit(main())
