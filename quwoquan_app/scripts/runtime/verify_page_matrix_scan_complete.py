#!/usr/bin/env python3
"""
确保「全页面扫描基线」与 page-horizontal-quality-matrix.md 双向一致，防止漏登记；
并确保矩阵中每一行路径均在 metadata_driven_ui_gap_inventory.yaml 中登记（P2 治理）。

扫描规则（须与矩阵文档「扫描基线」一致）：
- quwoquan_app/lib/ui/**/pages/*_page.dart
- quwoquan_app/lib/ui/welcome/pages/welcome_screen.dart
- quwoquan_app/lib/components/**/*_page.dart
- quwoquan_app/lib/app/shell/*.dart

排除（仅占位 export，不占矩阵行）：
- lib/ui/chat/pages/chat_display_fallbacks.dart

用法（仓库根）:
  python3 scripts/verify_page_matrix_scan_complete.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

from page_disk_scan_paths import EXCLUDE_REL, matrix_disk_scan_paths

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / (
    "specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md"
)
INV = ROOT / "specs/gates/metadata_driven_ui_gap_inventory.yaml"
APP = ROOT / "quwoquan_app"


def matrix_paths() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    found = set(re.findall(r"`(lib/[^`]+\.dart)`", text))
    return {p for p in found if "*" not in p and p not in EXCLUDE_REL}


def disk_scan_paths() -> set[str]:
    return set(matrix_disk_scan_paths(ROOT))


def inventory_ui_paths() -> set[str]:
    if yaml is None or not INV.is_file():
        return set()
    data = yaml.safe_load(INV.read_text(encoding="utf-8"))
    out: set[str] = set()
    for dom in data.get("domains", []):
        for page in dom.get("ui_pages", []):
            rel = page.get("path")
            if not isinstance(rel, str):
                continue
            if rel.startswith("quwoquan_app/"):
                rel = rel[len("quwoquan_app/") :]
            out.add(rel)
    return out


def main() -> int:
    if not MATRIX.is_file():
        print(f"BLOCK: matrix missing: {MATRIX}", file=sys.stderr)
        return 2
    m = matrix_paths()
    d = disk_scan_paths()
    only_matrix = sorted(m - d)
    only_disk = sorted(d - m)
    if only_matrix or only_disk:
        print("page_matrix_scan_complete: FAIL", file=sys.stderr)
        if only_disk:
            print("  磁盘有但矩阵未登记（须补矩阵 + 缺口清单等）:", file=sys.stderr)
            for x in only_disk:
                print(f"    + {x}", file=sys.stderr)
        if only_matrix:
            print("  矩阵有但磁盘无（路径过期或已删）:", file=sys.stderr)
            for x in only_matrix:
                print(f"    - {x}", file=sys.stderr)
        return 1

    if yaml is None:
        print("page_matrix_scan_complete: BLOCK: PyYAML required for inventory check", file=sys.stderr)
        return 2
    if not INV.is_file():
        print(f"page_matrix_scan_complete: BLOCK: missing {INV}", file=sys.stderr)
        return 2
    inv = inventory_ui_paths()
    not_in_inv = sorted(m - inv)
    if not_in_inv:
        print(
            "page_matrix_scan_complete: FAIL（矩阵路径未在 metadata_driven_ui_gap_inventory 登记）",
            file=sys.stderr,
        )
        for x in not_in_inv:
            print(f"    ! {x}", file=sys.stderr)
        return 1

    print(f"page_matrix_scan_complete: OK ({len(m)} paths, inventory aligned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
