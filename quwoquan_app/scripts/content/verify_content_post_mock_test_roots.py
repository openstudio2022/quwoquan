#!/usr/bin/env python3
"""Sanity-check directories referenced by content post mock test layering (see mock.yaml description).

Run from repo root: python3 scripts/verify_content_post_mock_test_roots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"

REQUIRED_DIRS = [
    APP / "test" / "ui" / "content",
    APP / "test" / "cloud" / "content",
    APP / "test" / "ui" / "discovery",
    APP / "test" / "ui" / "content" / "entry" / "journeys",
]


def main() -> int:
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED_DIRS if not p.is_dir()]
    if missing:
        print(
            "verify_content_post_mock_test_roots: missing directories:\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        return 1
    print("verify_content_post_mock_test_roots: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
