#!/usr/bin/env python3
"""Verify canonical test roots do not contain fake or placeholder evidence."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from test_directory_inventory_lib import LEGACY_ALLOWLIST_PATH, ROOT, build_inventory, go_suite_names, iter_canonical_files


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
)
DART_TEST_RE = re.compile(r"\b(?:test(?:Widgets)?|patrolTest)\s*\(")
PYTHON_TEST_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(", re.MULTILINE)


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: no fake canonical tests detected")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def load_legacy_allowlist(failures: Failures) -> tuple[set[str], set[str], set[str]]:
    if not LEGACY_ALLOWLIST_PATH.exists():
        failures.add(f"missing legacy allowlist file: {LEGACY_ALLOWLIST_PATH.relative_to(ROOT)}")
        return set(), set(), set()
    data = yaml.safe_load(LEGACY_ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}
    if data.get("version") != 1:
        failures.add("legacy allowlist version must be 1")
    current_paths = {
        str(value).strip()
        for value in (data.get("grandfathered_current_paths") or [])
        if str(value).strip()
    }
    bench_only_allowed = {
        str(value).strip()
        for value in (data.get("bench_only_allowed_sources") or [])
        if str(value).strip()
    }
    skip_grandfathered = {
        str(value).strip()
        for value in (data.get("skip_grandfathered_sources") or [])
        if str(value).strip()
    }
    return current_paths, bench_only_allowed, skip_grandfathered


def verify_canonical_files(failures: Failures) -> None:
    for _, path, _ in iter_canonical_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                failures.add(f"{path.relative_to(ROOT)} contains placeholder pattern {pattern.pattern!r}")
        if path.suffix == ".go" and "exec.Command(" not in text and "testing.T" not in text:
            failures.add(f"{path.relative_to(ROOT)} go canonical test lacks bridge or test body")
        if path.suffix == ".py" and "importlib.util.spec_from_file_location" not in text and "def test_" not in text:
            failures.add(f"{path.relative_to(ROOT)} python canonical test lacks bridge or real test body")


def verify_legacy_sources(
    failures: Failures,
    grandfathered_current_paths: set[str],
    bench_only_allowed: set[str],
    skip_grandfathered: set[str],
) -> None:
    seen: set[str] = set()
    for area_data in (build_inventory().get("areas") or {}).values():
        if not isinstance(area_data, dict):
            continue
        for entry in area_data.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            current_path = str(entry.get("current_path") or "").strip()
            if not current_path or current_path in seen:
                continue
            seen.add(current_path)
            if current_path not in grandfathered_current_paths:
                failures.add(f"{current_path} missing from legacy allowlist")
                continue
            path = ROOT / current_path
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern.search(text):
                    failures.add(f"{current_path} contains placeholder pattern {pattern.pattern!r}")
            for pattern in SKIP_PATTERNS:
                if pattern.search(text) and current_path not in skip_grandfathered:
                    failures.add(f"{current_path} contains skip pattern {pattern.pattern!r} without explicit grandfathering")
            if path.suffix == ".go":
                tests, benches = go_suite_names(path)
                if benches and not tests and current_path not in bench_only_allowed:
                    failures.add(f"{current_path} is benchmark-only but not registered as explicit exception")
                if not tests and not benches:
                    failures.add(f"{current_path} go legacy source lacks Test*/Benchmark* bodies")
            elif path.suffix == ".py":
                if not PYTHON_TEST_RE.search(text):
                    failures.add(f"{current_path} python legacy source lacks def test_* body")
            elif path.suffix == ".dart":
                if "Source legacy file:" in text:
                    failures.add(f"{current_path} legacy dart source must not be wrapper-generated bridge")
                if not DART_TEST_RE.search(text):
                    failures.add(f"{current_path} dart legacy source lacks test/testWidgets body")


def verify_test_artifacts(failures: Failures) -> None:
    test_artifacts = ROOT / "artifacts" / "tests"
    if not test_artifacts.exists():
        return
    for path in test_artifacts.rglob("report.json"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '"exit_code"' not in text or '"case_results"' not in text:
            failures.add(f"{path.relative_to(ROOT)} report.json missing exit_code or case_results")


def main() -> int:
    failures = Failures()
    grandfathered_current_paths, bench_only_allowed, skip_grandfathered = load_legacy_allowlist(failures)
    verify_canonical_files(failures)
    verify_legacy_sources(failures, grandfathered_current_paths, bench_only_allowed, skip_grandfathered)
    verify_test_artifacts(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
