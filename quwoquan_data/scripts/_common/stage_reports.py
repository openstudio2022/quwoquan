"""Stage gate report / repair report 写盘辅助。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.io import write_json
from _common.paths import batch_results_dir


def write_stage_result(
    task_id: str,
    batch_id: str,
    command: str,
    step: str,
    ref: str,
    payload: dict[str, Any],
) -> Path:
    out_dir = batch_results_dir(task_id, batch_id, command, step)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ref}.json"
    write_json(
        path,
        {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": step,
            "ref": ref,
            "payload": payload,
        },
    )
    return path


def build_gate_report(
    *,
    task_id: str,
    batch_id: str,
    command: str,
    step: str,
    ref: str,
    passed: bool,
    issues: list[str],
    evidence_summary: dict[str, Any] | None = None,
    next_step: str | None = None,
    fallback_stage: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "quwoquan_data.stage_gate_report",
        "taskId": task_id,
        "batchId": batch_id,
        "command": command,
        "step": step,
        "ref": ref,
        "status": "green" if passed else "red",
        "passed": passed,
        "issues": issues,
        "evidenceSummary": evidence_summary or {},
        "nextStep": next_step,
        "fallbackStage": fallback_stage,
    }


def write_gate_report(
    *,
    task_id: str,
    batch_id: str,
    command: str,
    step: str,
    ref: str,
    passed: bool,
    issues: list[str],
    evidence_summary: dict[str, Any] | None = None,
    next_step: str | None = None,
    fallback_stage: str | None = None,
) -> Path:
    payload = build_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command=command,
        step=step,
        ref=ref,
        passed=passed,
        issues=issues,
        evidence_summary=evidence_summary,
        next_step=next_step,
        fallback_stage=fallback_stage,
    )
    return write_stage_result(task_id, batch_id, command, f"{step}_gate", ref, payload)


def build_repair_report(
    *,
    task_id: str,
    batch_id: str,
    command: str,
    ref: str,
    failed_stage: str,
    failed_gate: str,
    issues: list[str],
    fallback_stage: str,
    rerun_chain: list[str],
) -> dict[str, Any]:
    return {
        "schemaVersion": "quwoquan_data.repair_report",
        "taskId": task_id,
        "batchId": batch_id,
        "command": command,
        "ref": ref,
        "failedStage": failed_stage,
        "failedGate": failed_gate,
        "issues": issues,
        "fallbackStage": fallback_stage,
        "rerunChain": rerun_chain,
    }


def write_repair_report(
    *,
    task_id: str,
    batch_id: str,
    command: str,
    ref: str,
    failed_stage: str,
    failed_gate: str,
    issues: list[str],
    fallback_stage: str,
    rerun_chain: list[str],
) -> Path:
    payload = build_repair_report(
        task_id=task_id,
        batch_id=batch_id,
        command=command,
        ref=ref,
        failed_stage=failed_stage,
        failed_gate=failed_gate,
        issues=issues,
        fallback_stage=fallback_stage,
        rerun_chain=rerun_chain,
    )
    return write_stage_result(task_id, batch_id, command, "repair_report", ref, payload)

