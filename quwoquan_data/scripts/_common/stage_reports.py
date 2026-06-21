"""Stage gate report / repair report 写盘辅助 + 对象优先路由（规格 §15.1）。

produce 命令的阶段报告挂到**内容对象目录**的过程阶段下（与 brief/draft 同处一棵对象树）：

- quality_analysis(+gate) → `2.quality/`
- compose_brief(+gate)    → `3.compose/`
- compose / review / media_check(+gate) / repair_report → `5.review/`

对象目录已按 ref 唯一，故文件名用 `{step}.json`（gate 为 `{step}_gate.json`）。
produce 命令的阶段报告仅读取已登记内容对象的对象树；其它命令继续写入各自命令工作区。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import (
    STAGE_COMPOSE,
    STAGE_QUALITY,
    STAGE_REVIEW,
    batch_results_dir,
)

# produce 阶段步骤（去 `_gate` 后缀的基名）→ 内容对象阶段目录。
_PRODUCE_STEP_STAGE: dict[str, str] = {
    "quality_analysis": STAGE_QUALITY,
    "compose_brief": STAGE_COMPOSE,
    "compose": STAGE_REVIEW,
    "review": STAGE_REVIEW,
    "media_check": STAGE_REVIEW,
    "repair_report": STAGE_REVIEW,
}


def _produce_object_report_path(
    task_id: str, batch_id: str, command: str, step: str, ref: str
) -> Path | None:
    """produce 命令 + 已登记内容对象 → 对象阶段目录下报告路径。"""
    if command != "produce":
        return None
    from _common import content_object  # 延迟导入避免循环依赖

    if not content_object.content_coords(task_id, batch_id, ref):
        return None
    base = step[:-5] if step.endswith("_gate") else step
    stage = _PRODUCE_STEP_STAGE.get(base)
    if stage is None:
        return None
    return content_object.content_object_stage_dir(task_id, batch_id, ref, stage) / f"{step}.json"


def stage_result_path(task_id: str, batch_id: str, command: str, step: str, ref: str) -> Path:
    """阶段报告写盘路径：produce 走对象阶段目录，其它命令走各自工作区。"""
    obj = _produce_object_report_path(task_id, batch_id, command, step, ref)
    if obj is not None:
        return obj
    if command == "produce":
        raise KeyError(f"produce stage report not registered for ref={ref!r} (task={task_id} batch={batch_id})")
    return batch_results_dir(task_id, batch_id, command, step) / f"{ref}.json"


def read_stage_envelope(
    task_id: str, batch_id: str, command: str, step: str, ref: str
) -> dict[str, Any] | None:
    """读单个阶段报告 envelope：produce 仅读对象树；其它命令读各自工作区。"""
    obj = _produce_object_report_path(task_id, batch_id, command, step, ref)
    if obj is not None and obj.is_file():
        return read_json(obj)
    if command == "produce":
        return None
    command_path = batch_results_dir(task_id, batch_id, command, step) / f"{ref}.json"
    return read_json(command_path) if command_path.is_file() else None


def iter_stage_envelopes(
    task_id: str, batch_id: str, command: str, step: str
) -> list[tuple[str, dict[str, Any]]]:
    """枚举某 (command, step) 全部 (ref, envelope)。"""
    if command == "produce":
        from _common import content_object  # 延迟导入避免循环依赖

        out: list[tuple[str, dict[str, Any]]] = []
        for ref in content_object.iter_content_refs(task_id, batch_id):
            env = read_stage_envelope(task_id, batch_id, command, step, ref)
            if env is not None:
                out.append((ref, env))
        return sorted(out)
    command_dir = batch_results_dir(task_id, batch_id, command, step)
    if not command_dir.is_dir():
        return []
    return sorted((f.stem, read_json(f)) for f in command_dir.glob("*.json"))


def write_stage_result(
    task_id: str,
    batch_id: str,
    command: str,
    step: str,
    ref: str,
    payload: dict[str, Any],
) -> Path:
    path = stage_result_path(task_id, batch_id, command, step, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    evidence_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
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
    if evidence_summary:
        payload["evidenceSummary"] = evidence_summary
    return payload


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
    evidence_summary: dict[str, Any] | None = None,
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
        evidence_summary=evidence_summary,
    )
    return write_stage_result(task_id, batch_id, command, "repair_report", ref, payload)


def clear_repair_report(*, task_id: str, batch_id: str, command: str, ref: str) -> Path | None:
    """Remove a stale repair report after the same object passes its gate."""
    path = stage_result_path(task_id, batch_id, command, "repair_report", ref)
    if path.is_file():
        path.unlink()
        return path
    return None
