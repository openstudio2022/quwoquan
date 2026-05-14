#!/usr/bin/env python3
"""Scan content-domain surfaces for Map<String, dynamic> / dynamic markers (inventory aid).

Run from repo root: python3 scripts/scan_content_dynamic_surfaces.py
Prints path:line:content for manual merge into
specs/gates/content_domain_dynamic_map_inventory.yaml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app" / "lib"

PATTERNS = [
    re.compile(r"Map<String,\s*dynamic>"),
    re.compile(r"\bdynamic\b"),
]

ROOTS = [
    APP / "ui" / "content",
    APP / "cloud" / "services" / "content",
    APP / "ui" / "discovery" / "widgets" / "works_immersive_viewer.dart",
    APP / "ui" / "discovery" / "widgets" / "moment_social_feed.dart",
    APP / "ui" / "circle" / "widgets" / "section_creations.dart",
    APP / "cloud" / "runtime" / "models" / "content_post_detail_payload.dart",
    APP / "core" / "models" / "media_viewer_extra.dart",
    APP / "core" / "services" / "app_content_repository.dart",
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
