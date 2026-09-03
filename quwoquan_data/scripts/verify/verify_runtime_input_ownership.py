#!/usr/bin/env python3
"""Verify runtime requests exist only in initialized work packages."""
from __future__ import annotations

from pathlib import Path

from core.io import read_json
from core.paths import DATA_EXECUTIONS_ROOT, REPO_ROOT
from core.schema import assert_valid


def runtime_input_ownership_issues() -> list[str]:
    issues: list[str] = []
    if not DATA_EXECUTIONS_ROOT.is_dir():
        return issues
    for root in sorted(path for path in DATA_EXECUTIONS_ROOT.iterdir() if path.is_dir()):
        for rel, schema in (("0.plan/request.json", "task_init_request"), ("0.plan/target_set.json", "target_set")):
            path = root / rel
            try:
                value = read_json(path)
                assert_valid(value, "execution", schema, label=str(path))
            except Exception as exc:  # noqa: BLE001
                issues.append(f"{path}: {exc}")
    return issues


def main() -> int:
    issues = runtime_input_ownership_issues()
    if issues:
        print("[verify runtime-input-ownership] FAIL")
        for issue in issues: print(f"  - {issue}")
        return 1
    print("[verify runtime-input-ownership] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
