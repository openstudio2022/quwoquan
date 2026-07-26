#!/usr/bin/env python3
"""Keep runtime requests in the disposable execution work package only."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from core.io import read_json
from core.paths import DATA_EXECUTIONS_ROOT, REPO_ROOT
from content.execution.recipe import RuntimeExecutionRequest
from content.execution.workspace import orphaned_transaction_workspaces


_STATIC_INPUT_ROOTS = (
    "quwoquan_data/control_plane",
    "quwoquan_data/verticals",
    "quwoquan_data/prompts",
    "quwoquan_data/templates",
    "quwoquan_data/schema",
)
_RUN_VALUE_PATTERNS = (
    re.compile(r"\.qwq_output/"),
    re.compile(r"\bexecutionId\s*[:=]\s*20\d{6}--"),
)
_REQUEST_REF = Path("0.plan/request.json")
_TARGET_SET_REF = Path("0.plan/target_set.json")


def _is_static_input(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    parts = relative.parts
    if len(parts) >= 3 and parts[0:2] == ("quwoquan_data", "verticals"):
        return path.name in {"providers.yaml", "content_policy.yaml", "license_policy.yaml"}
    return True


def _text_issues() -> list[str]:
    issues: list[str] = []
    for relative_root in _STATIC_INPUT_ROOTS:
        root = REPO_ROOT / relative_root
        if not root.is_dir():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if not _is_static_input(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in _RUN_VALUE_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}: static input contains frozen runtime value {pattern.pattern}"
                    )
                    break
    return issues


def _request_issues() -> list[str]:
    issues: list[str] = []
    if not DATA_EXECUTIONS_ROOT.is_dir():
        return issues
    for execution_root in sorted(path for path in DATA_EXECUTIONS_ROOT.iterdir() if path.is_dir()):
        request_path = execution_root / _REQUEST_REF
        target_set_path = execution_root / _TARGET_SET_REF
        if not request_path.is_file():
            issues.append(f"{request_path.relative_to(REPO_ROOT)}: execution request is missing")
            continue
        if not target_set_path.is_file():
            issues.append(f"{target_set_path.relative_to(REPO_ROOT)}: frozen target set is missing")
        try:
            RuntimeExecutionRequest.from_document(read_json(request_path))
        except (OSError, ValueError, SystemExit) as exc:
            issues.append(f"{request_path.relative_to(REPO_ROOT)}: invalid request: {exc}")
    return issues


def _transaction_workspace_issues() -> list[str]:
    return [
        f"{path.relative_to(REPO_ROOT)}: transaction evidence has no execution work package"
        for path in orphaned_transaction_workspaces()
    ]


def runtime_input_ownership_issues() -> list[str]:
    return [*_text_issues(), *_request_issues(), *_transaction_workspace_issues()]


def main() -> int:
    issues = runtime_input_ownership_issues()
    if issues:
        print("[verify_runtime_input_ownership] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_runtime_input_ownership] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
