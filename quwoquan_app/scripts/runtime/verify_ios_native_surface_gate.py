#!/usr/bin/env python3
"""
Block Material Scaffold as page root (return Scaffold() in scanned Dart files).

Aligned with runtime/runtime-client-foundation/ios-native-page-enforcement/spec.md.
and feature: runtime/runtime-client-foundation/ios-native-page-enforcement.

Scans:
  - quwoquan_app/lib/ui/**/pages/**/*.dart
  - quwoquan_app/lib/components/**/*_page.dart
  - quwoquan_app/lib/components/media/camera/camera_capture_page.dart
  - quwoquan_app/lib/app/shell/*.dart
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/ios-native-page-enforcement/spec.md#gwt-001
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
# Material full-screen root scaffold is forbidden on every scanned page.
_PATTERN = re.compile(r"\breturn\s+Scaffold\s*\(")


def _collect_files() -> list[Path]:
    files: list[Path] = []
    if APP_LIB.is_dir():
        files.extend(sorted(APP_LIB.glob("ui/**/pages/**/*.dart")))
        files.extend(sorted(APP_LIB.glob("components/**/*_page.dart")))
    cap = APP_LIB / "components/media/camera/camera_capture_page.dart"
    if cap.is_file() and cap not in files:
        files.append(cap)
    shell_dir = APP_LIB / "app" / "shell"
    if shell_dir.is_dir():
        for p in sorted(shell_dir.glob("*.dart")):
            if p not in files:
                files.append(p)
    return files


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
