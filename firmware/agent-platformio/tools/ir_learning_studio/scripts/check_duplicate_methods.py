#!/usr/bin/env python3
"""AST-based duplicate class method checker for IR Learning Studio.

Scans all Python files and reports any class with duplicate method names.
"""

import ast
import sys
from pathlib import Path


def check_file(filepath: Path) -> list[str]:
    """Check a single Python file for duplicate class methods. Returns issues."""
    issues = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"PARSE_ERROR: {filepath}: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_names = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = item.name
                    if name in method_names:
                        prev_line = method_names[name]
                        issues.append(
                            f"DUPLICATE_METHOD: {filepath}: class={node.name} "
                            f"method={name} defined at line {prev_line} and line {item.lineno}"
                        )
                    else:
                        method_names[name] = item.lineno
    return issues


def main():
    project_root = Path(__file__).resolve().parents[1]  # ir_learning_studio dir
    all_issues = []

    for py_file in sorted(project_root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        if "legacy_library_migration" in str(py_file):
            continue  # Legacy module, allowed to have duplicates with new code
        issues = check_file(py_file)
        all_issues.extend(issues)

    if all_issues:
        for issue in all_issues:
            print(issue)
        print(f"DUPLICATE_CLASS_METHOD_COUNT={len(all_issues)}")
        return 1
    else:
        print("DUPLICATE_CLASS_METHOD_COUNT=0")
        return 0


if __name__ == "__main__":
    sys.exit(main())
