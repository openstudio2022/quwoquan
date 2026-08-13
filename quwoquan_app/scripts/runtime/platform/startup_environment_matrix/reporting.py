"""CaseResult 汇总、报告状态判定与报告写出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import SPEC_REFS


def _case(
    case_id: str,
    *,
    kind: str,
    status: str,
    required: bool,
    spec_refs: tuple[str, ...] = SPEC_REFS,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "caseId": case_id,
        "kind": kind,
        "required": required,
        "status": status,
        "specRefs": list(spec_refs),
        **fields,
    }


def _case_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    required_cases = [case for case in cases if case.get("required") is True]
    executed_statuses = {"component_ready", "passed", "failed"}
    return {
        "required": len(required_cases),
        "executed": sum(
            case.get("status") in executed_statuses for case in required_cases
        ),
        "skipped": sum(case.get("status") == "skipped" for case in required_cases),
        "failed": sum(case.get("status") == "failed" for case in required_cases),
    }


def _report_status(
    cases: list[dict[str, Any]],
    *,
    release_gate: bool,
) -> str:
    required_cases = [case for case in cases if case.get("required") is True]
    if any(case.get("status") == "failed" for case in required_cases):
        return "failed"
    if any(
        case.get("status") in {"gate_block", "missing", "skipped"}
        for case in required_cases
    ):
        return "gate_block"
    return "passed" if release_gate else "component_ready"


def _write_report(path_value: str, report: dict[str, Any]) -> None:
    if not path_value:
        return
    report_path = Path(path_value)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
