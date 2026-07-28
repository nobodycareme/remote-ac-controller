#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified test runner for IR Learning Studio R4.

Auto-discovers all test_*.py modules, runs all suites,
generates unique test count and suite execution count.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
TESTS = HERE / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


# Auto-discover all test modules
def discover_test_modules():
    modules = []
    for f in sorted(TESTS.glob("test_*.py")):
        mod_name = f.stem
        try:
            mod = importlib.import_module(mod_name)
            modules.append((mod_name, mod))
        except Exception as e:
            print(f"SKIP_MODULE={mod_name} reason={e}")
    return modules


def discover_all_tests(modules):
    """Discover all test classes and methods from modules."""
    classes = {}
    unique_methods = set()
    for mod_name, mod in modules:
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                fq_class = f"{mod_name}.{name}"
                methods = []
                for m_name, method in inspect.getmembers(obj, inspect.isfunction):
                    if m_name.startswith("test_"):
                        fq_method = f"{fq_class}.{m_name}"
                        methods.append(m_name)
                        unique_methods.add(fq_method)

                        # Test quality check: empty test?
                        source = inspect.getsource(method)
                        lines = [l.strip() for l in source.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith('"""')]
                        body_lines = lines[1:] if lines else []
                        has_assert = any("assert" in l for l in body_lines)
                        has_raise = any("assertRaises" in l or "self.assert" in l for l in body_lines)
                        has_content = len(body_lines) > 1 and any(len(l) > 10 for l in body_lines)
                        if not has_assert and not has_raise and not has_content:
                            print(f"SHALLOW_TEST={fq_method}")

                classes[fq_class] = methods

    return classes, unique_methods


def summarize_result(result: unittest.TestResult, elapsed_s: float = 0.0) -> dict:
    failed = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    return {
        "testsRun": result.testsRun,
        "passed": result.testsRun - failed - errors - skipped,
        "failures": failed,
        "errors": errors,
        "skipped": skipped,
        "successful": result.wasSuccessful() and skipped == 0,
        "elapsedSeconds": round(elapsed_s, 3),
    }


def run_all() -> tuple[list, set]:
    modules = discover_test_modules()
    classes, unique_methods = discover_all_tests(modules)

    loader = unittest.TestLoader()
    all_suite = unittest.TestSuite()
    for mod_name, mod in modules:
        suite = loader.loadTestsFromModule(mod)
        all_suite.addTests(suite)

    runner = unittest.TextTestRunner(verbosity=1)
    start = time.monotonic()
    result = runner.run(all_suite)
    elapsed = time.monotonic() - start

    summary = summarize_result(result, elapsed)
    summary["uniqueTestMethodCount"] = len(unique_methods)
    summary["suiteExecutionCount"] = 1
    summary["testModuleCount"] = len(modules)

    return summary, unique_methods


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    summary, unique_methods = run_all()

    payload = {
        "schemaVersion": 2,
        "generatedAtEpoch": int(time.time()),
        "uniqueTestMethodCount": len(unique_methods),
        "totalSuiteExecutionCount": 1,
        "testModuleCount": summary["testModuleCount"],
        "summary": summary,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"UNIQUE_TEST_METHOD_COUNT={len(unique_methods)}")
    print(f"TOTAL_SUITE_EXECUTION_COUNT=1")

    return 0 if summary["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
