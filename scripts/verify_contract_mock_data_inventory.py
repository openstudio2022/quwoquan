#!/usr/bin/env python3
"""阻止测试侧新增对端侧 mock data 类的直接依赖。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "specs" / "gates" / "contract_mock_data_baseline.json"
INVENTORY = ROOT / "specs" / "gates" / "contract_mock_data_inventory.md"
TEST_ROOT = ROOT / "quwoquan_app" / "test"


def main() -> int:
    if not INVENTORY.is_file():
        print(f"BLOCK: inventory missing: {INVENTORY}", file=sys.stderr)
        return 1
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    tokens = data.get("tokens", {})
    failures: list[str] = []
    for token, limits in tokens.items():
        occurrences = 0
        files: set[str] = set()
        for path in TEST_ROOT.rglob("*.dart"):
            text = path.read_text(encoding="utf-8")
            count = text.count(token)
            if count:
                occurrences += count
                files.add(path.relative_to(ROOT).as_posix())
        max_occurrences = int(limits.get("maxOccurrences", 0))
        max_files = int(limits.get("maxFiles", 0))
        if occurrences > max_occurrences or len(files) > max_files:
            failures.append(
                f"{token}: occurrences={occurrences}/{max_occurrences}, "
                f"files={len(files)}/{max_files}"
            )
    if failures:
        print("contract_mock_data_inventory 校验失败:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("请将新增测试数据迁入 contracts/metadata/**/test_fixtures。", file=sys.stderr)
        return 1
    print("contract_mock_data_inventory: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
