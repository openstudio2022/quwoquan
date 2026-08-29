"""Typed zero-qualified reason and its per-object basis ledger for one lane."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.schema import assert_valid

from content.execution.campaign.receipt_store import write_create_once_document
from content.execution.campaign.submission import campaign_root
from content.execution.closure.zero_qualified_reason import (
    ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET,
    ALL_OBJECTS_QUALITY_REJECTED,
    ZeroQualifiedReasonError,
    evidence_digest,
    non_resumable_reason_payload,
    parse_zero_qualified_reason,
    publish_admission_over_budget,
    resumable_reason_payload,
)
from content.execution.identity import validate_execution_id

ZERO_QUALIFIED_REASON_FIELD = "zeroQualifiedReason"


def basis_evidence_ref(carrier: str, phase: str) -> str:
    """basis 证据以 campaign 根为基准引用，与 lane 回执同目录同身份。"""
    return f"receipts/{carrier}-{phase}-zero-qualified-basis.json"


def _write_basis_evidence(
    *,
    root_execution_id: str,
    execution_id: str,
    carrier: str,
    phase: str,
    evaluated_object_count: int,
    object_exclusions: Sequence[Mapping[str, Any]],
    root: Path | None,
) -> tuple[str, str]:
    """持久化本 lane 观测到的逐对象排除台账，返回 (evidenceRef, evidenceDigest)。"""

    if evaluated_object_count < 1 or not object_exclusions:
        raise ZeroQualifiedReasonError(
            f"{carrier} {phase} lane 零合格终态缺逐对象排除台账："
            f"evaluatedObjectCount={evaluated_object_count} "
            f"objectExclusions={len(object_exclusions)}"
        )
    payload = {
        "schema": "quwoquan_data.zero_qualified_basis_evidence",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": validate_execution_id(execution_id),
        "carrier": carrier,
        "phase": phase,
        "evaluatedObjectCount": evaluated_object_count,
        "admittedObjectCount": 0,
        "objectExclusions": [
            {
                "objectRef": str(row["objectRef"]),
                "issues": [str(issue) for issue in row["issues"]],
            }
            for row in object_exclusions
        ],
    }
    assert_valid(
        payload,
        "execution",
        "zero_qualified_basis_evidence",
        label=f"zero_qualified_basis_evidence:{carrier}-{phase}",
    )
    reference = basis_evidence_ref(carrier, phase)
    path = write_create_once_document(
        campaign_root(root_execution_id, root=root) / reference,
        payload,
        collision_detail="zero-qualified basis evidence already differs",
    )
    return reference, evidence_digest(path)


def review_zero_qualified_reason(
    *,
    root_execution_id: str,
    execution_id: str,
    carrier: str,
    selected_count: int,
    discarded_count: int,
    discards: Sequence[Mapping[str, Any]],
    determined_at: str,
    root: Path | None,
) -> dict[str, Any]:
    """review 阶段的零合格只可能是「全部对象质量被拒」。

    候选集本身为空时 review 从未判定过任何对象，这个零不由 review 观测——它属于来源
    发现或 target set 冻结前的选择器准入。此处判否并点名缺的那处声明，而不是替观测者
    挑一个原因，也不退回不带原因的 `blocked`。
    """

    if selected_count < 1 or discarded_count != selected_count:
        raise ZeroQualifiedReasonError(
            f"{carrier} review lane 零合格，但 review 观测不到原因："
            f"selected={selected_count} discarded={discarded_count}。"
            "review 只能得出 ALL_OBJECTS_QUALITY_REJECTED；候选集为空时该原因由"
            "来源发现或 selector_admission 阶段的观测者写入 zeroQualifiedReason"
        )
    reference, digest = _write_basis_evidence(
        root_execution_id=root_execution_id,
        execution_id=execution_id,
        carrier=carrier,
        phase="review",
        evaluated_object_count=selected_count,
        object_exclusions=discards,
        root=root,
    )
    return non_resumable_reason_payload(
        code=ALL_OBJECTS_QUALITY_REJECTED,
        observed_stage="review",
        operator_action="repair_source",
        determined_at=determined_at,
        summary=(
            f"{carrier} lane 的 {selected_count} 个候选对象在 review 全部被拒，"
            "无对象进入 publish"
        ),
        evidence_ref=reference,
        evidence_digest=digest,
        label=f"campaign lane receipt:{carrier}-review",
    )


def publish_zero_qualified_reason(
    *,
    root_execution_id: str,
    execution_id: str,
    carrier: str,
    review_qualified_count: int,
    publish_discards: Sequence[Mapping[str, Any]],
    determined_at: str,
    root: Path | None,
) -> dict[str, Any]:
    """publish 阶段零 finalize 的原因按对象级排除码判定，两层只以引用衔接。

    全批都被单对象存储预算拦下时是 publish 准入观测到的超预算原因；其余排除码指向仍可
    重放的对象，因此是交付阶段的可续跑中断并逐对象给出续跑 refs。
    """

    if not publish_discards:
        raise ZeroQualifiedReasonError(
            f"{carrier} publish lane 零 finalize 但无对象级排除条目，"
            "无法判定批次级零合格原因"
        )
    if publish_admission_over_budget(publish_discards):
        reference, digest = _write_basis_evidence(
            root_execution_id=root_execution_id,
            execution_id=execution_id,
            carrier=carrier,
            phase="publish",
            evaluated_object_count=review_qualified_count,
            object_exclusions=publish_discards,
            root=root,
        )
        return non_resumable_reason_payload(
            code=ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET,
            observed_stage="publish_admission",
            operator_action="reduce_object_footprint",
            determined_at=determined_at,
            summary=(
                f"{carrier} lane 的 {review_qualified_count} 个评审合格对象在 publish "
                "准入全部因对象闭包超出单对象存储预算被拦下"
            ),
            evidence_ref=reference,
            evidence_digest=digest,
            label=f"campaign lane receipt:{carrier}-publish",
        )
    return resumable_reason_payload(
        determined_at=determined_at,
        resumable_refs=[str(row["objectRef"]) for row in publish_discards],
        label=f"campaign lane receipt:{carrier}-publish",
    )


def assert_lane_zero_qualified_reason(
    payload: Mapping[str, Any], *, label: str
) -> None:
    """零合格终态必须带闭集内的原因，非零合格终态不得带原因。

    未知取值在此判否，不映射为任何既有原因，也不退化成不带原因的 `blocked`。
    """

    reason = payload.get(ZERO_QUALIFIED_REASON_FIELD)
    blocked = str(payload.get("status") or "") == "blocked"
    if reason is None:
        if blocked:
            raise ZeroQualifiedReasonError(
                f"{label}: status=blocked 必须携带 zeroQualifiedReason，"
                "`blocked` 不是可以不带原因的汇总值"
            )
        return
    if not blocked:
        raise ZeroQualifiedReasonError(
            f"{label}: 只有零合格终态可携带 zeroQualifiedReason，"
            f"实得 status={payload.get('status')!r}"
        )
    parse_zero_qualified_reason(reason, label=label)
