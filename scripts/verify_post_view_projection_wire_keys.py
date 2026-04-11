#!/usr/bin/env python3
"""Fail if post_view_projection.dart reintroduces bare string keys on card/block maps.

Run from repo root: python3 scripts/verify_post_view_projection_wire_keys.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "ui"
    / "content"
    / "post_view_projection.dart"
)

# After SSOT: card[...] / block[...] / next[...] must use Article*WireKeys, not string literals.
FORBIDDEN = re.compile(
    r"\b(card|block|next)\s*\[\s*['\"]([a-zA-Z0-9_]+)['\"]\s*\]"
)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    bad = FORBIDDEN.findall(text)
    if bad:
        print(
            "verify_post_view_projection_wire_keys: forbidden bare keys:\n  "
            + "\n  ".join(f"{a}[{b!r}]" for a, b in bad),
            file=sys.stderr,
        )
        return 1
    print("verify_post_view_projection_wire_keys: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
