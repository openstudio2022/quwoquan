"""GWT-011：三层生产消费者读到同一个零合格原因取值，未知值 fail closed。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-011.t3`、`GWT-011.t4`
与 L2 `design.md` 的 `DEC-005`、`DEC-013`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t4
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.execution.campaign.plan_lane_status import (  # noqa: E402
    apply_receipt_fields,
)
from content.execution.campaign.receipt import load_lane_receipt  # noqa: E402
from content.execution.queue.reliabletask.report import (  # noqa: E402
    ReliableTaskFleetReport,
)
from core.io import write_json  # noqa: E402

ROOT_ID = "20260728--travel-article-workload-article-1--china--scale-001"
BASIS_REF = "receipts/article-review-zero-qualified-basis.json"

QUALITY_REJECTED_REASON: dict[str, Any] = {
    "code": "ALL_OBJECTS_QUALITY_REJECTED",
    "observedStage": "review",
    "determinedAt": "2026-08-16T00:10:00Z",
    "operatorAction": "repair_source",
    "nonResumableBasis": {
        "summary": "article lane 的 2 个候选对象在 review 全部被拒",
        "evidenceRef": BASIS_REF,
        "evidenceDigest": "sha256:" + "c" * 64,
    },
}
OVER_BUDGET_REASON: dict[str, Any] = {
    "code": "ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET",
    "observedStage": "publish_admission",
    "determinedAt": "2026-08-16T00:20:00Z",
    "operatorAction": "reduce_object_footprint",
    "nonResumableBasis": {
        "summary": "article lane 的 2 个评审合格对象在 publish 准入全部超预算",
        "evidenceRef": "receipts/article-publish-zero-qualified-basis.json",
        "evidenceDigest": "sha256:" + "d" * 64,
    },
}


def _lane_receipt(
    *,
    status: str = "blocked",
    reason: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": ROOT_ID,
        "executionId": ROOT_ID,
        "carrier": "article",
        "phase": "review",
        "status": status,
        "approvedQuota": 2,
        "qualifiedCount": 0 if status == "blocked" else 2,
        "finalizedCount": 0,
        "selectedCount": 2,
        "discardedCount": 2,
        "shortfallCount": 2 if status == "blocked" else 0,
        "discards": [
            {"objectRef": "posts/article/a", "issues": ["quality"]},
            {"objectRef": "posts/article/b", "issues": ["quality"]},
        ],
    }
    if reason is not None:
        payload["zeroQualifiedReason"] = copy.deepcopy(reason)
    return payload


def _write_lane_receipt(root: Path, payload: dict[str, Any]) -> None:
    write_json(
        root / ROOT_ID / "receipts" / "article-review.json",
        payload,
    )


def test_blocked_lane_receipt_carries_the_typed_reason(tmp_path: Path) -> None:
    """GWT-011.t3：零合格 lane 回执带唯一 typed 原因，读侧原值返回。"""
    _write_lane_receipt(tmp_path, _lane_receipt(reason=QUALITY_REJECTED_REASON))

    loaded = load_lane_receipt(ROOT_ID, "article", "review", root=tmp_path)

    assert loaded["zeroQualifiedReason"] == QUALITY_REJECTED_REASON


def test_blocked_lane_receipt_without_a_reason_fails_closed(tmp_path: Path) -> None:
    """DEC-005：`blocked` 不再是没有原因的汇总值。"""
    _write_lane_receipt(tmp_path, _lane_receipt(reason=None))

    with pytest.raises(ValueError) as failure:
        load_lane_receipt(ROOT_ID, "article", "review", root=tmp_path)
    assert "zeroQualifiedReason" in str(failure.value)


def test_non_zero_qualified_receipt_must_not_carry_a_reason(tmp_path: Path) -> None:
    """存在合格对象时批次按合格对象数进入 partial，不带零合格原因。"""
    _write_lane_receipt(
        tmp_path,
        _lane_receipt(status="qualified", reason=QUALITY_REJECTED_REASON),
    )

    with pytest.raises(ValueError):
        load_lane_receipt(ROOT_ID, "article", "review", root=tmp_path)


@pytest.mark.parametrize(
    "mutation",
    (
        {"code": "BLOCKED"},
        {"code": "ALL_OBJECTS_QUALITY_REJECTED_V2"},
        {"observedStage": "publish_admission"},
        {"operatorAction": "reduce_object_footprint"},
    ),
)
def test_lane_receipt_reason_outside_the_closed_set_fails_closed(
    tmp_path: Path,
    mutation: dict[str, str],
) -> None:
    """未知取值在读侧判否，不映射为既有原因也不退回 generic blocked。"""
    reason = {**copy.deepcopy(QUALITY_REJECTED_REASON), **mutation}
    _write_lane_receipt(tmp_path, _lane_receipt(reason=reason))

    with pytest.raises(ValueError):
        load_lane_receipt(ROOT_ID, "article", "review", root=tmp_path)


def test_campaign_report_projects_the_same_reason_value() -> None:
    """DEC-005：campaign 只投影不写，取值与 lane 回执逐字段相同。"""
    lanes: dict[str, dict[str, Any]] = {"article": {}}

    apply_receipt_fields(
        lanes,
        "article",
        _lane_receipt(reason=QUALITY_REJECTED_REASON),
        phase="review",
    )

    assert lanes["article"]["status"] == "blocked"
    assert lanes["article"]["zeroQualifiedReason"] == QUALITY_REJECTED_REASON


def test_campaign_report_drops_the_reason_when_the_lane_is_not_blocked() -> None:
    """后一阶段不再是零合格终态时，上一阶段的原因不得留在报告行里。"""
    lanes: dict[str, dict[str, Any]] = {
        "article": {"zeroQualifiedReason": copy.deepcopy(QUALITY_REJECTED_REASON)}
    }

    apply_receipt_fields(
        lanes,
        "article",
        _lane_receipt(status="qualified"),
        phase="review",
    )

    assert "zeroQualifiedReason" not in lanes["article"]


def _fleet_report(
    *,
    reason: dict[str, Any] | None,
    commercial_accepted: int = 0,
    passed: bool = False,
) -> dict[str, Any]:
    total = 2
    document: dict[str, Any] = {
        "schema": "quwoquan.reliabletask_fleet_report",
        "executionId": ROOT_ID,
        "stage": "publish",
        "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
        "jobSetDigest": "sha256:" + "b" * 64,
        "actualTaskDigest": "sha256:" + "b" * 64,
        "passed": passed,
        "backend": "mongodb+redis",
        "total": total,
        "succeeded": total,
        "stageCompletedCount": 0,
        "publishTaskCount": total,
        "objectTransactionResultCount": total,
        "researchAcceptedCount": 0,
        "commercialAcceptedCount": commercial_accepted,
        "fleetControlPlaneThroughputPerHour": 600.0,
        "fleetAcceptedThroughputPerHour": 0.0,
        "endToEndAcceptedThroughputPerHour": 0.0,
        "acceptedContentThroughputStatus": (
            "MEASURED" if passed else "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
        ),
        "fleetPeakConcurrentWorkers": 2,
        "fleetWaveCount": 1,
        "fleetBatchDeadlineEpochSeconds": 1_784_696_400,
        "recoveryEligibleCount": 0,
        "automaticRecoveredCount": 0,
        "manualRecoveredCount": 0,
        "automaticRecoveryStatus": "NOT_EXERCISED",
        "automaticRecoveryRate": 0.0,
        "firstAttemptSuccessRate": 1.0,
        "finalizedWithinStageBudgetRate": 1.0,
        "duplicatePublishCount": 0,
        "missingObjectCount": 0,
        "requiredQuota": total,
        "finalizedObjectCount": commercial_accepted,
        "idempotencyKey": "executionId+entity+carrier+sourceRevision+stage",
        "taskOutcomes": [
            {"jobId": f"job-{index}", "status": "succeeded", "attempts": 1}
            for index in range(total)
        ],
        "executionCreatedAt": "2026-08-16T03:00:00Z",
        "fleetStartedAt": "2026-08-16T04:59:00Z",
        "canonicalFinalizedAt": "2026-08-16T05:00:00Z",
        "fleetWallClockMilliseconds": 60_000,
        "endToEndWallClockMilliseconds": 7_200_000,
        "completedAt": "2026-08-16T05:00:00Z",
    }
    if reason is not None:
        document["zeroQualifiedReason"] = copy.deepcopy(reason)
    return document


def test_fleet_report_decodes_the_same_reason_value() -> None:
    """DEC-005：在交付阶段终结的 lane 直接绑定 fleet 回执中的同一取值。"""
    decoded = ReliableTaskFleetReport.from_document(
        _fleet_report(reason=OVER_BUDGET_REASON)
    )

    assert decoded.zero_qualified_reason is not None
    assert decoded.zero_qualified_reason.code == OVER_BUDGET_REASON["code"]
    assert decoded.zero_qualified_reason.observed_stage == "publish_admission"
    assert decoded.zero_qualified_reason.operator_action == "reduce_object_footprint"
    assert decoded.zero_qualified_reason.resumable is False


def test_fleet_report_reason_outside_the_closed_set_fails_closed() -> None:
    document = _fleet_report(reason={**OVER_BUDGET_REASON, "code": "BLOCKED"})

    with pytest.raises(ValueError) as failure:
        ReliableTaskFleetReport.from_document(document)
    assert "zeroQualifiedReason" in str(failure.value)


def test_fleet_report_with_accepted_objects_must_not_carry_a_reason() -> None:
    """存在任一合格对象时批次进入 partial，不带零合格原因。"""
    document = _fleet_report(reason=OVER_BUDGET_REASON, commercial_accepted=2)

    with pytest.raises(ValueError):
        ReliableTaskFleetReport.from_document(document)


def test_fleet_report_absent_reason_stays_absent() -> None:
    """字段缺席表示本批次不是零合格终态，不塌陷成零值原因。"""
    decoded = ReliableTaskFleetReport.from_document(
        _fleet_report(reason=None, commercial_accepted=2, passed=True)
    )

    assert decoded.zero_qualified_reason is None
