#!/usr/bin/env python3
"""Root flat-file ratchet for scripts/ and tests/.

禁止 quwoquan_data/scripts/ 与 quwoquan_data/tests/ 根层级再次出现业务平铺文件。
允许 scripts/ 根仅保留 cli.py；允许 tests/ 根仅保留 conftest.py。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.paths import DATA_ROOT as _DATA_ROOT  # noqa: E402

ALLOWED_SCRIPT_ROOT_FILES = {"cli.py"}
ALLOWED_TEST_ROOT_FILES = {"conftest.py"}


def verify_no_flat_roots() -> list[str]:
    issues: list[str] = []
    scripts_root = _DATA_ROOT / "scripts"
    tests_root = _DATA_ROOT / "tests"
    if scripts_root.is_dir():
        for path in sorted(scripts_root.glob("*.py")):
            if path.name not in ALLOWED_SCRIPT_ROOT_FILES:
                issues.append(f"scripts root flat file: {path.relative_to(_DATA_ROOT)}")
    if tests_root.is_dir():
        for path in sorted(tests_root.glob("*.py")):
            if path.name not in ALLOWED_TEST_ROOT_FILES:
                issues.append(f"tests root flat file: {path.relative_to(_DATA_ROOT)}")
    return issues


def main() -> None:
    issues = verify_no_flat_roots()
    if issues:
        print("[verify-flat-roots] FAILED: root-level flat files remain", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify-flat-roots] PASSED")


if __name__ == "__main__":
    main()
