"""只读预检 canonical terminal evidence，不签发或修复 authority。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core import paths
from content.execution.execution_terminal import (
    InvalidTerminalExecutionEvidenceError,
    load_terminal_execution_evidence,
)
from content.execution.identity import validate_execution_id


def terminal_evidence_precheck(
    execution_id: str,
    *,
    executions_root: Path | None = None,
) -> dict[str, Any]:
    """返回单一终态裁决；绝不创建 receipt 或改写 execution。"""
    normalized = validate_execution_id(execution_id)
    root = (executions_root or paths.DATA_EXECUTIONS_ROOT).resolve() / normalized
    if not root.is_dir():
        raise FileNotFoundError(f"execution root is missing: {root}")
    decision: str | None = None
    error_code: str | None = None
    issues: list[str] = []
    try:
        terminal = load_terminal_execution_evidence(root)
    except InvalidTerminalExecutionEvidenceError as exc:
        error_code = "DATA.EXECUTION.TERMINAL_EVIDENCE_INVALID"
        issues.append(str(exc))
    else:
        if terminal is None:
            error_code = "DATA.EXECUTION.TERMINAL_EVIDENCE_MISSING"
            issues.append("execution has no canonical terminal evidence")
        else:
            decision = terminal.decision
    return {
        "schema": "quwoquan_data.terminal_evidence_precheck",
        "executionId": normalized,
        "passed": not issues,
        "decision": decision,
        "errorCode": error_code,
        "issues": issues,
        "writable": False,
        "repairSupported": False,
    }


def _handle(args: argparse.Namespace) -> None:
    report = terminal_evidence_precheck(str(args.execution_id))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


def register_terminal_evidence_precheck_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "terminal-evidence-precheck",
        help="只读核验终态 authority；无安全 repair 时返回 typed blocker",
    )
    parser.add_argument("execution_id")
    parser.set_defaults(handler=_handle)


__all__ = [
    "register_terminal_evidence_precheck_parser",
    "terminal_evidence_precheck",
]
