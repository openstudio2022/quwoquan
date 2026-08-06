#!/usr/bin/env python3
"""Gate: forbid `dynamic` formal parameters in content presentation layers.

Platform / JSON decode boundaries may still use `Object?` or `Map<String, dynamic>`.

Run from repo root:
  python3 quwoquan_app/scripts/content_service/content/verify_ui_content_no_dynamic_parameters.py
"""
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
CONTENT_DOMAIN = ROOT / "quwoquan_app" / "lib" / "content"

# Parameter-like: (dynamic x  or , dynamic x  or <dynamic> x — last is rare)
_PARAM_DYNAMIC = re.compile(
    r"(?:\(|,)\s*dynamic\s+\w+|\bvoid\s+\w+\s*\(\s*dynamic\s+\w+"
)


def main() -> int:
    bad: list[str] = []
    presentation_roots = sorted(CONTENT_DOMAIN.glob("*/*/presentation"))
    for path in sorted(
        candidate
        for presentation in presentation_roots
        for candidate in presentation.rglob("*.dart")
    ):
        if "/generated/" in str(path) or path.name.endswith(".g.dart"):
            continue
        rel = path.relative_to(ROOT)
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
