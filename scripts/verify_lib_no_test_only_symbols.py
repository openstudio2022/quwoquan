#!/usr/bin/env python3
"""Fail if lib/** introduces un-allowlisted test-only factory names (policy §4.1 P0b)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOWLIST = ROOT / "specs" / "gates" / "lib_test_only_symbols_allowlist.yaml"

# Top-level or static members whose names signal test-only entrypoints in release compile unit.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bstatic\s+[^;{]*\bcreateForTest\s*\("), "createForTest"),
    (re.compile(r"^\s*AssistantRuntime\s+createTestAssistantRuntime\s*\(", re.M), "createTestAssistantRuntime"),
]


def _load_allowed() -> dict[str, set[str]]:
    import yaml  # type: ignore

    raw = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    out: dict[str, set[str]] = {}
    for row in raw.get("allowed", []) or []:
        p = str(row.get("path", "")).strip().replace("\\", "/")
        sym = str(row.get("symbol", "")).strip()
        if p and sym:
            out.setdefault(p, set()).add(sym)
    return out


def main() -> int:
    try:
        allowed = _load_allowed()
    except Exception as e:  # noqa: BLE001
        print(f"lib_test_only_symbols: FAIL load allowlist: {e}", file=sys.stderr)
        return 1

    violations: list[str] = []
    for path in sorted(APP_LIB.rglob("*.dart")):
        rel = path.relative_to(APP_LIB).as_posix()
        text = path.read_text(encoding="utf-8")
        for rx, sym in PATTERNS:
            if not rx.search(text):
                continue
            per_file = allowed.get(rel, set())
            if sym not in per_file:
                violations.append(f"{rel}: un-allowlisted {sym}")

    if violations:
        print("lib_test_only_symbols: FAIL", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(f"  allowlist: {ALLOWLIST}", file=sys.stderr)
        return 1

    print("lib_test_only_symbols: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
