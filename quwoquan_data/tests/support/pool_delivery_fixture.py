"""Pool delivery preserves reviewed truth across transport outages.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""
from __future__ import annotations

import json
from pathlib import Path

EXECUTION_ID = "20260811--travel-article-m100--china--scale-201"
_DIGEST = "sha256:" + "a" * 64
DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
