"""vertical source-registry CLI 契约测试。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from governance.coverage.handler import handle_source_registry  # noqa: E402


def test_verify_vertical_source_registry_passes_on_repository_state():
    handle_source_registry(argparse.Namespace())


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"vertical source registry verify tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
