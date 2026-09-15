#!/usr/bin/env python3
"""Prepare distinct disposable Python caches for Data tests and Ops runtime."""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DATA_SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS))

from core.python_environment import prepare_data_runtime_cache
from quwoquan_ops.cli.commands.managed_python import prepare_ops_runtime_cache


def main() -> int:
    reports = {
        "data": prepare_data_runtime_cache(),
        "ops": prepare_ops_runtime_cache(),
    }
    failed = False
    for owner, report in reports.items():
        if report.get("ready"):
            print(f"[prepare-test-python] {owner} ready: {report['python']}")
            continue
        failed = True
        print(f"[prepare-test-python] {owner} FAIL: managed requirements unavailable")
        for issue in report.get("missing") or ():
            print(f"  - {issue}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
