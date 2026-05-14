#!/usr/bin/env python3
"""
verify_dart_func_coverage.py

Checks that every dart_func declared in mock.yaml has a corresponding
function definition in the Dart test files.

Exemptions:
  - Scenarios with status: pending are skipped.

Usage:
  python3 scripts/verify_dart_func_coverage.py [--mock-yaml PATH] [--test-dir PATH]

Exit 0 on success, 1 on failure.
"""

import sys
import os
import re
import glob
import argparse

try:
    import yaml
except ImportError:
    # Attempt to use the bundled pyyaml from the system or fail with a helpful message.
    print("[gate] ERROR: PyYAML not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

SECTION_KEYS = ("widget_scenarios", "journey_scenarios")


def load_dart_funcs(test_dir: str) -> set[str]:
    """Scan all *_test.dart files under test_dir and return all top-level function names."""
    funcs: set[str] = set()
    pattern = os.path.join(test_dir, "**", "*_test.dart")
    for path in glob.glob(pattern, recursive=True):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        # Match: Future<void> funcName(...) or void funcName(...) at line start
        for m in re.finditer(r"^(?:Future<void>|void)\s+(\w+)\s*\(", text, re.MULTILINE):
            funcs.add(m.group(1))
    return funcs


def collect_declared_funcs(doc: dict) -> list[tuple[str, str]]:
    """
    Return list of (dart_func, scenario_name) for all non-pending scenarios.
    """
    result = []
    for section in SECTION_KEYS:
        for scenario in doc.get(section) or []:
            if not isinstance(scenario, dict):
                continue
            dart_func = scenario.get("dart_func", "")
            if not dart_func:
                continue
            if scenario.get("status", "") == "pending":
                continue
            name = scenario.get("name", dart_func)
            result.append((dart_func, name))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dart_func coverage from mock.yaml")
    parser.add_argument(
        "--mock-yaml",
        default="quwoquan_service/contracts/metadata/content/post/tests/mock.yaml",
        help="Path to mock.yaml (relative to repo root)",
    )
    parser.add_argument(
        "--test-dir",
        default="quwoquan_app/test",
        help="Root of Dart test directory (relative to repo root)",
    )
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    mock_yaml_path = os.path.join(repo_root, args.mock_yaml)
    test_dir = os.path.join(repo_root, args.test_dir)

    if not os.path.isfile(mock_yaml_path):
        print(f"[gate] SKIP: mock.yaml not found at {mock_yaml_path}")
        return 0

    with open(mock_yaml_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    declared = collect_declared_funcs(doc)
    if not declared:
        print("[gate] INFO: no dart_func declarations found in mock.yaml")
        return 0

    dart_funcs = load_dart_funcs(test_dir)

    missing = [(fn, name) for fn, name in declared if fn not in dart_funcs]

    if missing:
        print("[gate] FAIL: mock.yaml dart_func declarations without Dart test implementations:", file=sys.stderr)
        for fn, name in missing:
            print(f"  - {fn}  (scenario: {name})", file=sys.stderr)
        return 1

    print(f"[gate] OK: all {len(declared)} dart_func declarations covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
