#!/usr/bin/env python3
"""Gate: discourage `dynamic` as a formal parameter type under lib/ui/content.

Platform / JSON decode boundaries may still use `Object?` or `Map<String, dynamic>`.
Excludes: entry/services/ios_video_editing_service.dart (MethodChannel payloads).

Run from repo root: python3 scripts/verify_ui_content_no_dynamic_parameters.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT_UI = ROOT / "quwoquan_app" / "lib" / "ui" / "content"

# Parameter-like: (dynamic x  or , dynamic x  or <dynamic> x — last is rare)
_PARAM_DYNAMIC = re.compile(
    r"(?:\(|,)\s*dynamic\s+\w+|\bvoid\s+\w+\s*\(\s*dynamic\s+\w+"
)

_EXCLUDE_SUBPATH = "entry/services/ios_video_editing_service.dart"


def main() -> int:
    bad: list[str] = []
    for path in sorted(CONTENT_UI.rglob("*.dart")):
        if "/generated/" in str(path) or path.name.endswith(".g.dart"):
            continue
        rel = path.relative_to(ROOT)
        if str(rel).endswith(_EXCLUDE_SUBPATH):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if _PARAM_DYNAMIC.search(line):
                bad.append(f"{rel}:{i}:{stripped}")

    if bad:
        print("verify_ui_content_no_dynamic_parameters: FAIL", file=sys.stderr)
        for row in bad:
            print(row, file=sys.stderr)
        return 1
    print("verify_ui_content_no_dynamic_parameters: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
