"""控制器侧的断点续跑准入与进度投影适配层。

两条能力都只消费磁盘上已有的证据：终态 review 收口收据决定哪些对象绝不可重入，
冻结 manifest 的 provider/model/runtime 绑定决定这次到底还能不能算「同一个
execution 的继续」。这里不产生第二份台账，也不改任何既有证据。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.io import read_json, write_json
from core.paths import execution_root

from content.execution.controller.progress import (
    ExecutionProgress,
    project_execution_progress,
)
from content.execution.planning.resume_admission import (
    ResumeAdmission,
    admit_in_place_resume,
)

_FINALIZATION_RECEIPT = "5.review/finalization_report.json"
_PASSED_STATUSES = frozenset(
    {"passed", "approved", "done", "accepted", "success", "succeeded"}
)


def _receipt_is_terminal(receipt: object) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    if receipt.get("passed") is True:
        return True
    status = str(receipt.get("status") or receipt.get("decision") or "").casefold()
    return status in _PASSED_STATUSES


def finished_object_refs(execution_id: str) -> tuple[str, ...]:
    """有终态 review 收口收据的对象引用；这是 resume 唯一不得重入的证据。"""
    root = execution_root(execution_id)
    refs: set[str] = set()
    for path in sorted(root.rglob(_FINALIZATION_RECEIPT)):
        if not _receipt_is_terminal(read_json(path)):
            continue
        refs.add(path.parent.parent.relative_to(root).as_posix())
    return tuple(sorted(refs))


def frozen_object_refs(execution_id: str) -> tuple[str, ...]:
    """本次执行冻结的对象目录集合，homepage 与 post 载体同源枚举。"""
    root = execution_root(execution_id)
    refs: set[str] = set()
    for anchor in ("entities", "posts"):
        base = root / anchor
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("3.compose")):
            if path.is_dir():
                refs.add(path.parent.relative_to(root).as_posix())
    refs.update(finished_object_refs(execution_id))
    return tuple(sorted(refs))


def _identity_drift(execution_id: str) -> dict[str, bool]:
    """只报告真实不一致；冻结 manifest 缺席不是漂移，也不能当成漂移处理。"""
    from content.execution.model_contract import (
        semantic_execution_binding_for_execution,
    )
    from content.execution.workspace import execution_manifest_path

    if not execution_manifest_path(execution_id).is_file():
        return {}
    try:
        semantic_execution_binding_for_execution(execution_id)
    except ValueError as exc:
        message = str(exc)
        return {
            "runtimeProfile": "runtime profile identity drift" in message,
            "semanticBinding": (
                "semantic runtime identity drift" in message
                or "semantic model binding drift" in message
            ),
        }
    return {}


def _superseded_by(execution_id: str) -> str:
    from content.execution.execution_supersession import (
        load_execution_supersession_receipt,
    )

    receipt = load_execution_supersession_receipt(execution_root(execution_id))
    if receipt is None:
        return ""
    return str(receipt[0].get("supersededBy") or receipt[0].get("successor") or "")


def admit_execution_resume(execution_id: str) -> ResumeAdmission:
    """判定本次调用可以原地续跑的对象范围，或给出禁止续跑的阻断原因。"""
    refs = frozen_object_refs(execution_id)
    admission = admit_in_place_resume(
        execution_id=execution_id,
        object_refs=refs,
        finished_refs=finished_object_refs(execution_id),
        identity_drift=_identity_drift(execution_id),
        superseded_by=_superseded_by(execution_id) or None,
    )
    write_json(
        execution_root(execution_id) / "_shared" / "resume_admission.json",
        admission.report(),
    )
    return admission


def record_stage_progress(
    execution_id: str,
    *,
    approved_quota: int,
    completed_stages: tuple[str, ...],
    total_stages: int,
    current_stage: str | None,
    started_at: object,
    failed_count: int,
) -> ExecutionProgress:
    """把一轮 stage 收口后的进度投影落盘并打印一行运维可读进度。"""
    progress = project_execution_progress(
        execution_id=execution_id,
        approved_quota=approved_quota,
        produced_count=len(finished_object_refs(execution_id)),
        failed_count=failed_count,
        completed_stages=completed_stages,
        total_stages=total_stages,
        current_stage=current_stage,
        started_at=started_at,
    )
    write_json(
        execution_root(execution_id) / "_shared" / "progress.json",
        progress.to_document(),
    )
    print(f"[task execute] ▸ {progress.render()}", flush=True)
    return progress


def progress_document(execution_id: str) -> dict[str, Any]:
    path = execution_root(execution_id) / "_shared" / "progress.json"
    document = read_json(path) if path.is_file() else {}
    return dict(document) if isinstance(document, Mapping) else {}


__all__ = [
    "admit_execution_resume",
    "finished_object_refs",
    "frozen_object_refs",
    "progress_document",
    "record_stage_progress",
]
