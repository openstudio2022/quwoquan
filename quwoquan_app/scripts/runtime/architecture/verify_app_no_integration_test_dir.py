#!/usr/bin/env python3
"""确保端侧环境测试不再使用 integration_test/ 并行目录。"""

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

import sys
from pathlib import Path

ROOT = REPO_ROOT
INTEGRATION_DIR = ROOT / "quwoquan_app" / "integration_test"


def main() -> int:
    dart_files = []
    if INTEGRATION_DIR.exists():
        dart_files = sorted(INTEGRATION_DIR.rglob("*.dart"))
    if dart_files:
        print("BLOCK: quwoquan_app/integration_test 不再允许 Dart 测试入口:", file=sys.stderr)
        for path in dart_files:
            print(f"  - {path.relative_to(ROOT)}", file=sys.stderr)
        print(
            "请迁移到 quwoquan_app/test/local_contract、quwoquan_app/test/api_integration 或 quwoquan_app/test/user_acceptance。",
            file=sys.stderr,
        )
        return 1
    print("app_no_integration_test_dir: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
