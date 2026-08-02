#!/usr/bin/env python3
"""Reject executable setInsecure() calls in firmware source files."""
import argparse
import os
import re
import sys
import tempfile


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_EXTENSIONS = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp")
CALL_RE = re.compile(r"(?:\.|->)\s*setInsecure\s*\(")


def strip_comments_and_literals(source):
    pattern = re.compile(
        r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        re.DOTALL,
    )
    return pattern.sub(lambda match: "\n" * match.group(0).count("\n"), source)


def find_calls(root):
    hits = []
    firmware = os.path.join(root, "firmware")
    for base, directories, files in os.walk(firmware):
        directories[:] = [name for name in directories if name not in (".build", ".pio", "node_modules")]
        for name in files:
            if not name.endswith(SOURCE_EXTENSIONS):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                cleaned = strip_comments_and_literals(handle.read())
            for match in CALL_RE.finditer(cleaned):
                line = cleaned.count("\n", 0, match.start()) + 1
                hits.append((os.path.relpath(path, root).replace("\\", "/"), line))
    return hits


def report(root):
    hits = find_calls(root)
    for path, line in hits:
        print(f"SET_INSECURE_CALL {path}:{line}")
    print(f"MQTT_TLS_SET_INSECURE_CALL_COUNT={len(hits)}")
    print(f"MQTT_TLS_SET_INSECURE_COUNT={len(hits)}")
    print(f"NO_INSECURE_TLS_PASS={'True' if not hits else 'False'}")
    return 0 if not hits else 1


def self_test(root):
    positive = report(root) == 0
    with tempfile.TemporaryDirectory(prefix="no-insecure-tls-") as tmp:
        target = os.path.join(tmp, "firmware", "probe.cpp")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("void probe(Client& client) { client.setInsecure(); }\n")
        negative = bool(find_calls(tmp))
    print(f"NO_INSECURE_TLS_POSITIVE_TEST_PASS={positive}")
    print(f"NO_INSECURE_TLS_NEGATIVE_TEST_PASS={negative}")
    print(f"NO_INSECURE_TLS_SELF_TEST_PASS={positive and negative}")
    return 0 if positive and negative else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    return self_test(root) if args.self_test else report(root)


if __name__ == "__main__":
    sys.exit(main())
