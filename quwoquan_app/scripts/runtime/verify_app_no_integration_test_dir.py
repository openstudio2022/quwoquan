#!/usr/bin/env python3
"""确保端侧环境测试不再使用 integration_test/ 并行目录。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTEGRATION_DIR = ROOT / "quwoquan_app" / "integration_test"
INVENTORY = ROOT / "specs" / "gates" / "environment_test_layout_inventory.md"


def main() -> int:
    if not INVENTORY.is_file():
        print(f"BLOCK: inventory missing: {INVENTORY}", file=sys.stderr)
        return 1
    dart_files = []
    if INTEGRATION_DIR.exists():
        dart_files = sorted(INTEGRATION_DIR.rglob("*.dart"))
    if dart_files:
        print("BLOCK: quwoquan_app/integration_test 不再允许 Dart 测试入口:", file=sys.stderr)
        for path in dart_files:
            print(f"  - {path.relative_to(ROOT)}", file=sys.stderr)
        print("请迁移到 quwoquan_app/test/common|alpha|beta|gamma|patrol。", file=sys.stderr)
        return 1
    print("app_no_integration_test_dir: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
