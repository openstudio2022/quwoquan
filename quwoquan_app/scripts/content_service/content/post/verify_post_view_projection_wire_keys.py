#!/usr/bin/env python3
"""Fail if post_view_projection.dart reintroduces bare string keys on card/block maps.

Run from repo root:
  python3 quwoquan_app/scripts/content_service/content/post/verify_post_view_projection_wire_keys.py
"""
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

from _common.paths import REPO_ROOT

import re

ROOT = REPO_ROOT
TARGET = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "service"
    / "content_service"
    / "content"
    / "post"
    / "adapters"
    / "post_view_projection.dart"
)

# After SSOT: card[...] / block[...] / next[...] must use Article*WireKeys, not string literals.
FORBIDDEN = re.compile(
    r"\b(card|block|next)\s*\[\s*['\"]([a-zA-Z0-9_]+)['\"]\s*\]"
)


def main() -> int:
    if not TARGET.exists():
        print(
            f"verify_post_view_projection_wire_keys: target missing: "
            f"{TARGET.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1
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
