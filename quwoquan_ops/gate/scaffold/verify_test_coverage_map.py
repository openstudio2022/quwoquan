#!/usr/bin/env python3
"""Validate the derived spec_ref-to-test coverage map.

The map is rebuilt from physical test files on every run. No inventory or
recorded test path is accepted as an input truth source.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TEST_ROOTS = (
    ROOT / "quwoquan_app/test",
    ROOT / "quwoquan_data/tests",
    ROOT / "quwoquan_ops/tests",
    ROOT / "quwoquan_service/services",
    ROOT / "quwoquan_service/control-plane",
)
SPEC_REF = re.compile(
    r"spec_ref:\s*(specs/feature-tree/(?:[^\s#]+/)?spec\.md)#"
    r"((?:uat|dom|sit|gwt)-\d+)",
    re.IGNORECASE,
)
TEST_FILE = re.compile(
    r"(?:_test\.go|_test\.dart|_test\.py|__local_contract_test\.go|"
    r"__api_integration_test\.go)$"
)


def test_files() -> list[Path]:
    result: list[Path] = []
    for root in TEST_ROOTS:
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file() or not TEST_FILE.search(candidate.name):
                continue
            if any(part in {"vendor", ".dart_tool", "generated"} for part in candidate.parts):
                continue
            result.append(candidate)
    return sorted(set(result))


def main() -> int:
    failures: list[str] = []
    mapping: list[tuple[str, str]] = []
    for test in test_files():
        source = test.read_text(encoding="utf-8", errors="replace")
        for spec_path, case_id in SPEC_REF.findall(source):
            spec = ROOT / spec_path
            reference = f"{spec_path}#{case_id.lower()}"
            if not spec.is_file():
                failures.append(f"missing spec target: {reference} <- {test.relative_to(ROOT)}")
                continue
            spec_source = spec.read_text(encoding="utf-8", errors="replace").lower()
            anchor = f'<a id="{case_id.lower()}"></a>'
            if anchor not in spec_source:
                failures.append(f"missing case anchor: {reference} <- {test.relative_to(ROOT)}")
                continue
            mapping.append((reference, test.relative_to(ROOT).as_posix()))

    if not mapping:
        failures.append("no physical tests declare a stable spec_ref")
    if failures:
        for failure in failures:
            print(f"[verify-test-coverage-map] FAIL: {failure}")
        return 1
    counts = Counter(reference.split("#", 1)[1].split("-", 1)[0] for reference, _ in mapping)
    print(
        "[verify-test-coverage-map] OK: "
        f"bindings={len(mapping)}, tests={len(set(test for _, test in mapping))}, "
        f"layers={dict(sorted(counts.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
