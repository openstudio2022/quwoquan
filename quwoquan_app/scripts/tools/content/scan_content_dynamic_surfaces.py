#!/usr/bin/env python3
"""Scan content-domain surfaces for Map<String, dynamic> / dynamic markers.

Owner: content_service (manual analysis tool; not a gate).
Input: quwoquan_app/lib content-related presentation trees.
Output: stdout path:line:content report only.
Write behavior: none (no tracked inventory, no file writes).

Run from repo root:
  python3 quwoquan_app/scripts/tools/content/scan_content_dynamic_surfaces.py
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
APP = ROOT / "quwoquan_app" / "lib"

PATTERNS = [
    re.compile(r"Map<String,\s*dynamic>"),
    re.compile(r"\bdynamic\b"),
]

ROOTS = [
    APP / "ui" / "content",
    APP / "cloud" / "services" / "content",
    APP / "ui" / "discovery" / "widgets" / "works_immersive_viewer.dart",
    APP / "ui" / "discovery" / "widgets" / "home_multi_form_feed.dart",
    APP / "ui" / "circle" / "widgets" / "section_creations.dart",
    APP / "cloud" / "runtime" / "models" / "content_post_detail_payload.dart",
    APP / "core" / "models" / "media_viewer_extra.dart",
]


def iter_dart_files():
    for base in ROOTS:
        if base.is_file():
            if base.suffix == ".dart":
                yield base
            continue
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.dart")):
            if "/generated/" in str(path) or ".g.dart" in path.name:
                continue
            yield path


def main() -> int:
    hits = 0
    for path in iter_dart_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        for i, line in enumerate(lines, start=1):
            if any(p.search(line) for p in PATTERNS):
                if line.strip().startswith("//"):
                    continue
                print(f"{rel}:{i}:{line.strip()}")
                hits += 1
    print(f"# total_lines_matched: {hits}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
