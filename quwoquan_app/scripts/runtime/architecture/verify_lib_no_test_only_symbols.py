#!/usr/bin/env python3
"""Fail if production lib/** contains test-only factory names."""

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
APP_LIB = ROOT / "quwoquan_app" / "lib"
# Top-level or static members whose names signal test-only entrypoints in release compile unit.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bstatic\s+[^;{]*\bcreateForTest\s*\("), "createForTest"),
    (re.compile(r"^\s*AssistantRuntime\s+createTestAssistantRuntime\s*\(", re.M), "createTestAssistantRuntime"),
    (re.compile(r"\bContractFixtureRuntimeLoader\b"), "ContractFixtureRuntimeLoader"),
    (re.compile(r"\bPrefabUserResolver\b"), "PrefabUserResolver"),
    (re.compile(r"\bPrefabUserMetadata\b"), "PrefabUserMetadata"),
    (re.compile(r"\bkMockCurrent(?:Owner|Persona)Id\b"), "mock session identity"),
    (
        re.compile(r"\bhydrateFromNativeRuntimePackageForTest\b"),
        "hydrateFromNativeRuntimePackageForTest",
    ),
    (
        re.compile(r"\b_forceNativeRuntimePackageForTest\b"),
        "_forceNativeRuntimePackageForTest",
    ),
]
RETIRED_FIXTURE_PATHS = (
    "cloud/runtime/contract_fixture_runtime_loader.dart",
    "cloud/runtime/prefab_user_resolver.dart",
    "cloud/user/generated/prefab_user_metadata.g.dart",
    "core/auth/mock_session_identity.dart",
)


def collect_violations(app_lib: Path = APP_LIB) -> list[str]:
    violations: list[str] = []
    for rel in RETIRED_FIXTURE_PATHS:
        if (app_lib / rel).exists():
            violations.append(f"{rel}: retired production fixture helper exists")
    for path in sorted(app_lib.rglob("*.dart")):
        rel = path.relative_to(app_lib).as_posix()
        text = path.read_text(encoding="utf-8")
        for rx, sym in PATTERNS:
            if rx.search(text):
                violations.append(f"{rel}: forbidden test-only symbol {sym}")
    return violations


def main() -> int:
    violations = collect_violations()

    if violations:
        print("lib_test_only_symbols: FAIL", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("lib_test_only_symbols: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
