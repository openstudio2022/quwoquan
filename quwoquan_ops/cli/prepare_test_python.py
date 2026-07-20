#!/usr/bin/env python3
"""Prepare the disposable external Python tool cache used by repository tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
DATA_SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS))

from core.python_environment import prepare_data_runtime_cache


def main() -> int:
    report = prepare_data_runtime_cache()
    if report.get("ready"):
        print(f"[prepare-test-python] ready: {report['python']}")
        return 0
    print("[prepare-test-python] FAIL: repository requirements could not prepare the test interpreter")
    for issue in report.get("missing") or ():
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
