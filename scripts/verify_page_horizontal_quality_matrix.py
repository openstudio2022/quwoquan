#!/usr/bin/env python3
"""
v1：校验 page-horizontal-quality-matrix.md
- 表中 `lib/...` 路径在 quwoquan_app 下存在
- P1–P8 列仅允许 ✓、—、○（Unicode）

列扩展（P9…）时：同步增大下方 PILLAR_COUNT 与 label 元组。

用法（仓库根）:
  python3 scripts/verify_page_horizontal_quality_matrix.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / (
    "specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md"
)
APP = ROOT / "quwoquan_app"

PATH_RE = re.compile(r"`(lib/[^`]+\.dart)`")
PILLAR_OK = frozenset({"✓", "—", "○"})
PILLAR_COUNT = 8
P_LABELS = tuple(f"P{i}" for i in range(1, PILLAR_COUNT + 1))


def main() -> int:
    if not MATRIX.is_file():
        print(f"BLOCK: matrix missing: {MATRIX}", file=sys.stderr)
        return 2
    text = MATRIX.read_text(encoding="utf-8")
    errors: list[str] = []

    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        if "`lib/" not in line:
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", line):
            continue

        m = PATH_RE.search(line)
        if not m:
            continue
        rel = m.group(1)
        full = APP / rel
        if not full.is_file():
            errors.append(f"路径不存在: {rel}")

        cells = [c.strip() for c in line.split("|")[1:-1]]
        min_cells = 2 + PILLAR_COUNT + 1
        if len(cells) < min_cells:
            errors.append(f"{rel}: 列数不足（须含路径+类型+P1..P{PILLAR_COUNT}+备注）")
            continue
        for i, label in zip(range(2, 2 + PILLAR_COUNT), P_LABELS):
            val = cells[i].strip()
            if val not in PILLAR_OK:
                errors.append(f"{rel}: {label} 非法或为空 {val!r}（须为 ✓ / — / ○）")

    if errors:
        print("page-horizontal-quality-matrix 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("page-horizontal-quality-matrix: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
