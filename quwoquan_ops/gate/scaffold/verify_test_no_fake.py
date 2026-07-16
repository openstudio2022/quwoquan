#!/usr/bin/env python3
"""Verify canonical test roots do not contain fake or placeholder evidence."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from test_directory_inventory_lib import (
    ROOT,
    contains_generated_bridge_marker,
    go_has_test_entrypoint,
    iter_canonical_files,
)


PLACEHOLDER_PATTERNS = (
    re.compile(r"\bassert\s*\(\s*true\s*\)"),
    re.compile(r"\bexpect\s*\(\s*true\s*,\s*isTrue\s*\)"),
    re.compile(r"\bTODO_FAKE_TEST\b"),
)
SKIP_PATTERNS = (
    re.compile(r"\bpytest\.skip\s*\("),
    re.compile(r"@pytest\.mark\.skip\b"),
    re.compile(r"@unittest\.skip\b"),
    re.compile(r"\b(?:t|b)\.Skip(?:f)?\s*\("),
    re.compile(r"\bskip\s*:\s*true\b"),
    re.compile(r"\bos\.Exit\s*\(\s*0\s*\)"),
)
FAKE_INTEGRATION_DEPENDENCY_PATTERNS = (
    re.compile(
        r"\b(?:New)?(?:InMemory|Memory|Noop|Mock|Stub|Fake)[A-Za-z0-9_]*\s*\("
    ),
    re.compile(
        r"\b[A-Za-z0-9_]*(?:Mock|Stub|Fake)[A-Za-z0-9_]*\s*\{"
    ),
    re.compile(r"\bminiredis(?:\.|/v[0-9]+)"),
    re.compile(r'\bMode\s*:\s*"memory"'),
)
FAKE_INTEGRATION_FILENAME_RE = re.compile(
    r"(?:^|[_-])(?:fake|mock|stub|memory|test[_-]?double)(?:[_\-.]|$)",
    re.IGNORECASE,
)
DART_TEST_RE = re.compile(r"\b(?:test(?:Widgets)?|patrolTest)\s*\(")
PYTHON_TEST_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(", re.MULTILINE)


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items:
            self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: no fake canonical tests detected")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def verify_canonical_files(failures: Failures) -> None:
    for _, path, _ in iter_canonical_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if contains_generated_bridge_marker(path):
            failures.add(f"{path.relative_to(ROOT)} contains generated bridge marker")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                failures.add(f"{path.relative_to(ROOT)} contains placeholder pattern {pattern.pattern!r}")
        for pattern in SKIP_PATTERNS:
            if pattern.search(text):
                failures.add(f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}")
        if "api_integration" in path.parts:
            for pattern in FAKE_INTEGRATION_DEPENDENCY_PATTERNS:
                if pattern.search(text):
                    failures.add(
                        f"{path.relative_to(ROOT)} uses fake integration dependency "
                        f"{pattern.pattern!r}"
                    )
        if path.suffix == ".go" and not go_has_test_entrypoint(path):
            failures.add(f"{path.relative_to(ROOT)} go canonical test lacks Test*/Benchmark*/TestMain entrypoint")
        if path.suffix == ".py" and "importlib.util.spec_from_file_location" not in text and "def test_" not in text:
            failures.add(f"{path.relative_to(ROOT)} python canonical test lacks real test body")
        if path.suffix == ".dart" and not DART_TEST_RE.search(text):
            failures.add(f"{path.relative_to(ROOT)} dart canonical test lacks test/testWidgets/patrolTest body")


def verify_test_artifacts(failures: Failures) -> None:
    test_artifacts = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "tests"
    if not test_artifacts.exists():
        return
    for path in test_artifacts.rglob("report.json"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '"exit_code"' not in text or '"case_results"' not in text:
            failures.add(f"{path.relative_to(ROOT)} report.json missing exit_code or case_results")


def verify_all_test_sources(failures: Failures) -> None:
    excluded_dirs = {
        ".git",
        ".dart_tool",
        ".qwq_output",
        ".qwq_sandbox",
        ".qwq_test_venv",
        ".worktrees",
        ".venv",
        "build",
        "node_modules",
        "site-packages",
        "vendor",
    }
    for current_root, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(
            dirname for dirname in dirnames if dirname not in excluded_dirs
        )
        current = Path(current_root)
        for name in sorted(filenames):
            path = current / name
            is_canonical_test_source = (
                name.endswith(("_test.go", "_test.py", "_test.dart", "_test.ts"))
                or (name.startswith("test_") and name.endswith(".py"))
            )
            is_api_integration_source = (
                "api_integration" in path.parts
                and path.suffix in {".go", ".py", ".dart", ".ts"}
            )
            if is_api_integration_source:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if FAKE_INTEGRATION_FILENAME_RE.search(path.name):
                    failures.add(
                        f"{path.relative_to(ROOT)} uses fake integration source filename"
                    )
                for pattern in FAKE_INTEGRATION_DEPENDENCY_PATTERNS:
                    if pattern.search(text):
                        failures.add(
                            f"{path.relative_to(ROOT)} uses fake integration dependency "
                            f"{pattern.pattern!r}"
                        )
                for pattern in SKIP_PATTERNS:
                    if pattern.search(text):
                        failures.add(
                            f"{path.relative_to(ROOT)} contains skip pattern "
                            f"{pattern.pattern!r}"
                        )
            if not is_canonical_test_source:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SKIP_PATTERNS:
                if pattern.search(text):
                    failures.add(
                        f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}"
                    )


def main() -> int:
    failures = Failures()
    verify_canonical_files(failures)
    verify_all_test_sources(failures)
    verify_test_artifacts(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
