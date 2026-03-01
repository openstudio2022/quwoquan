#!/usr/bin/env python3
"""
verify_error_code_semantic.py

Scans quwoquan_app/lib/**/*.dart for hardcoded error code strings
(e.g. 'INTEGRATION.USER.location_unavailable') that should use
*ErrorCode enum .code (e.g. IntegrationLocationErrorCode.locationUnavailable.code).

Excluded paths: lib/cloud/runtime/generated/, lib/core/design_system/, lib/core/constants/

Usage:
  python3 scripts/verify_error_code_semantic.py [--targets PATH] [--update-baseline]
  --update-baseline: 将当前违规写入 baseline，用于首次建立或刷新

Exit 0 on success, 1 on failure.
"""

import argparse
import os
import re
import sys

BASELINE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".verify_error_code_semantic_baseline.txt"
)

# Match string literals that look like metadata error codes: DOMAIN.KIND.reason
# e.g. 'INTEGRATION.USER.location_unavailable', "CONTENT.USER.post_not_found"
PATTERN = re.compile(
    r"['\"](?:INTEGRATION|CONTENT|CHAT)\.(?:USER|MIDDLEWARE|SYSTEM)\.[a-z0-9_]+['\"]"
)
HINT = "错误码应使用 *ErrorCode.xxx.code，禁止硬编码字符串；见 01-arch-constraints.mdc §3.3"

# Path substrings to exclude (codegen 产物内的 case/return 字符串为合法)
EXCLUDE_SUBSTRINGS = [
    "generated",  # lib/cloud/*/generated/*.g.dart
    os.path.join("lib", "core", "design_system"),
    os.path.join("lib", "core", "constants"),
]


def should_skip(path: str, lib_root: str) -> bool:
    rel = os.path.relpath(path, lib_root).replace("\\", "/")
    for exc in EXCLUDE_SUBSTRINGS:
        if exc in rel:
            return True
    return False


def scan_file(path: str, lib_root: str) -> list[tuple[int, str]]:
    """Return list of (line_no, line_content) for violations."""
    violations = []
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                if PATTERN.search(line):
                    violations.append((i, line.rstrip()))
    except OSError as e:
        rel = os.path.relpath(path, lib_root).replace("\\", "/")
        print(f"verify_error_code_semantic: ERROR reading {rel}: {e}", file=sys.stderr)
    return violations


def load_baseline() -> set[str]:
    out = set()
    if os.path.isfile(BASELINE_FILE):
        with open(BASELINE_FILE, encoding="utf-8") as f:
            for line in f:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    out.add(entry)
    return out


def save_baseline(entries: set[str]) -> None:
    sorted_entries = sorted(entries)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        f.write("# verify_error_code_semantic baseline: 已知违规，逐步修复\n")
        for e in sorted_entries:
            f.write(e + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify error code semantic (no hardcoded strings)")
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib",
        help="Path to scan (default: quwoquan_app/lib)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current violations to baseline and exit 0",
    )
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib_root = os.path.normpath(os.path.join(root, args.targets))
    if not os.path.isdir(lib_root):
        print(f"verify_error_code_semantic: ERROR {lib_root} not found", file=sys.stderr)
        return 1

    baseline = load_baseline()
    all_violations: list[tuple[str, int, str]] = []

    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            if should_skip(path, lib_root):
                continue
            rel = os.path.relpath(path, root).replace("\\", "/")
            for line_no, line_content in scan_file(path, lib_root):
                entry = f"{rel}:{line_no}"
                if entry not in baseline:
                    all_violations.append((rel, line_no, line_content))

    if args.update_baseline:
        baseline_entries = set()
        for dirpath, _dirnames, filenames in os.walk(lib_root):
            for name in filenames:
                if not name.endswith(".dart"):
                    continue
                path = os.path.join(dirpath, name)
                if should_skip(path, lib_root):
                    continue
                rel = os.path.relpath(path, root).replace("\\", "/")
                for line_no, _ in scan_file(path, lib_root):
                    baseline_entries.add(f"{rel}:{line_no}")
        save_baseline(baseline_entries)
        print(f"verify_error_code_semantic: baseline 已更新，共 {len(baseline_entries)} 条")
        return 0

    found = False
    for rel, line_no, line_content in all_violations:
        print(f"{rel}:{line_no}: {HINT}")
        print(f"  {line_content.strip()}")
        found = True

    if found:
        print(f"\nverify_error_code_semantic: {HINT}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
