#!/usr/bin/env python3
"""Reject retired runtime identifiers without prose scans or path allowlists."""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
RUNTIME_ROOTS = (
    "quwoquan_app/lib",
    "quwoquan_app/android/app/src",
    "quwoquan_app/ios/Runner",
    "quwoquan_service/contracts/metadata",
    "quwoquan_service/runtime",
    "quwoquan_service/services",
    "quwoquan_data/control_plane",
    "quwoquan_data/scripts/core",
    "quwoquan_data/scripts/content",
    "quwoquan_data/scripts/governance",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
    "quwoquan_ops/portal/src",
)

SKIP_DIR_NAMES = {
    ".dart_tool",
    ".qwq_output",
    "__pycache__",
    "build",
    "node_modules",
    "test",
    "tests",
    "testdata",
    "vendor",
}

SOURCE_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".json",
    ".kt",
    ".mjs",
    ".py",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

# This gate targets executable compatibility identities, not natural-language
# history. Negative tests and governance scanners have their own contract gates.
RETIRED_IDENTIFIER = re.compile(
    r"\b(?:"
    r"(?i:legacy)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+(?:Legacy|_legacy)[A-Za-z0-9_]*|"
    r"compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+Compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*"
    r")\b"
)


def _is_runtime_source(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    return not (
        path.name.endswith("_test.go")
        or path.name.endswith("_test.dart")
        or path.name.startswith("test_")
    )


def _is_comment_only(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(("#", "//", "/*", "*", "<!--"))


def _self_test() -> None:
    rejected = (
        "final legacyAvailable = true;",
        'const wireKey = "legacyMedia";',
        "compatMode: enabled",
        "report_dir_legacy = output",
    )
    accepted = (
        "final availability = OneTapAvailability.available;",
        "compatibleRuntimeVersion: current",
        "final comparison = left == right;",
    )
    if not all(RETIRED_IDENTIFIER.search(value) for value in rejected):
        raise AssertionError("retired identifier detector missed a control fixture")
    if any(RETIRED_IDENTIFIER.search(value) for value in accepted):
        raise AssertionError("retired identifier detector rejected a current fixture")


def main() -> int:
    _self_test()
    findings: list[str] = []
    for relative_root in RUNTIME_ROOTS:
        source_root = ROOT / relative_root
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or not _is_runtime_source(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if _is_comment_only(line):
                    continue
                match = RETIRED_IDENTIFIER.search(line)
                if match:
                    rel = path.relative_to(ROOT).as_posix()
                    findings.append(f"{rel}:{line_number}:{match.group(0)}")

    if findings:
        print("verify_retired_terms_zero: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
