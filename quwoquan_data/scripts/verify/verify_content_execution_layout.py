#!/usr/bin/env python3
"""Verify the minimal hard-cut execution layout and target closure."""
from __future__ import annotations

import argparse
from pathlib import Path

from core.paths import DATA_EXECUTIONS_ROOT
from verify.stage_artifacts import verify_stage_artifacts
from verify.verify_task_init_contract import issues as task_init_contract_issues


def content_execution_layout_issues(*, execution_id: str | None = None) -> list[str]:
    if execution_id:
        roots = [DATA_EXECUTIONS_ROOT / execution_id]
    elif DATA_EXECUTIONS_ROOT.is_dir():
        roots = sorted(path for path in DATA_EXECUTIONS_ROOT.iterdir() if path.is_dir())
    else:
        roots = []
    issues: list[str] = []
    for root in roots:
        current = task_init_contract_issues(root.name)
        issues.extend(f"{root.name}: {issue}" for issue in current)
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-id")
    args = parser.parse_args(argv)
    issues = content_execution_layout_issues(execution_id=args.execution_id)
    if issues:
        print("[verify content-execution-layout] FAIL")
        for issue in issues: print(f"  - {issue}")
        return 1
    print("[verify content-execution-layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
