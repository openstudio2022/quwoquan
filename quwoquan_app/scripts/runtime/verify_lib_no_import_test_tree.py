#!/usr/bin/env python3
"""
阻断 quwoquan_app/lib 引用 test/ 树（防止「测试实现」混入发布编译单元）。

用法（仓库根）:
  python3 scripts/verify_lib_no_import_test_tree.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"

# package:quwoquan_app/.../test/... 或相对路径 ../test/
FORBIDDEN = re.compile(
    r"""import\s+['"](?:package:quwoquan_app/[^'"]*/test/[^'"]*|\.{1,2}/.*\btest/)['"]"""
)


def main() -> int:
    if not APP_LIB.is_dir():
        print(f"verify_lib_no_import_test_tree: skip (no {APP_LIB})", file=sys.stderr)
        return 0
    bad: list[str] = []
    for path in sorted(APP_LIB.rglob("*.dart")):
        if ".dart_tool" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"verify_lib_no_import_test_tree: ERROR {path}: {e}", file=sys.stderr)
            return 2
        for i, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                rel = path.relative_to(ROOT)
                bad.append(f"  {rel}:{i}: {line.strip()}")
    if bad:
        print(
            "verify_lib_no_import_test_tree: FAIL — lib must not import test/ tree:\n"
            + "\n".join(bad),
            file=sys.stderr,
        )
        return 1
    print("verify_lib_no_import_test_tree: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
