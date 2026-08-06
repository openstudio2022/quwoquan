#!/usr/bin/env python3
"""
Block Material Scaffold as page root (return Scaffold() in scanned Dart files).

Aligned with runtime/runtime-client-foundation/ios-native-page-enforcement/spec.md.
and feature: runtime/runtime-client-foundation/ios-native-page-enforcement.

Scans canonical object ``presentation`` layers plus ``runtime/shell`` and
``design_system``. Retired ``lib/ui``/``lib/components`` roots are not positive
scan inputs.
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/ios-native-page-enforcement/spec.md#gwt-001
from __future__ import annotations


import sys
from pathlib import Path

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
# Material full-screen root scaffold is forbidden on every scanned page.
_PATTERN = re.compile(r"\breturn\s+Scaffold\s*\(")


def _collect_files() -> list[Path]:
    roots = sorted(APP_LIB.glob("service/*/*/*/presentation"))
    roots.extend((APP_LIB / "runtime/shell", APP_LIB / "design_system"))
    return sorted(
        {
            path
            for root in roots
            if root.is_dir()
            for path in root.rglob("*.dart")
        }
    )


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for path in _collect_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for m in _PATTERN.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            violations.append((rel, line_no, m.group(0).strip()))

    if violations:
        print("[ios_native_surface_gate] FAIL: Material root Scaffold detected.", file=sys.stderr)
        print(
            "  Use CupertinoPageScaffold or AppScaffold per "
            "specs/feature-tree/runtime/runtime-client-foundation/ios-native-page-enforcement/spec.md",
            file=sys.stderr,
        )
        for rel, line_no, frag in violations:
            print(f"  - {rel}:{line_no}: {frag}", file=sys.stderr)
        return 1

    print("[ios_native_surface_gate] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
