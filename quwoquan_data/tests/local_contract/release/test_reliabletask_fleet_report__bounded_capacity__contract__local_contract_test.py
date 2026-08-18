"""GWT-011：fleet 运行回执必须顶层携带并发峰值、wave 数与绝对批次截止。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-011.t1`、`GWT-011.t2`、`GWT-011.t5`
与 L2 `design.md` 的 `DEC-002`、`DEC-004`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011
from __future__ import annotations

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

from core.schema import assert_valid, load_schema  # noqa: E402

CAPACITY_RECEIPT_FIELDS = (
    "fleetPeakConcurrentWorkers",
    "fleetWaveCount",
    "fleetBatchDeadlineEpochSeconds",
)


def _report() -> dict[str, Any]:
    total = 3
    return {
        "schema": "quwoquan.reliabletask_fleet_report",
        "executionId": "20260816--travel-article-g1--china-sichuan--pilot-011",
        "stage": "publish",
        "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
        "jobSetDigest": "sha256:" + "b" * 64,
        "actualTaskDigest": "sha256:" + "b" * 64,
        "passed": True,
        "backend": "mongodb+redis",
        "total": total,
        "succeeded": total,
        "stageCompletedCount": 0,
        "publishTaskCount": total,
        "objectTransactionResultCount": total,
        "researchAcceptedCount": total,
        "commercialAcceptedCount": 0,
        "fleetControlPlaneThroughputPerHour": 1.0,
        "fleetAcceptedThroughputPerHour": 1.0,
        "endToEndAcceptedThroughputPerHour": 1.0,
        "acceptedContentThroughputStatus": "MEASURED",
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
        "finalizedObjectCount": total,
        "idempotencyKey": "executionId+entity+carrier+sourceRevision+stage",
        "fleetPeakConcurrentWorkers": 2,
        "fleetWaveCount": 2,
        "fleetBatchDeadlineEpochSeconds": 1_786_000_000,
        "taskOutcomes": [
            {"jobId": f"job-{index}", "status": "succeeded", "attempts": 1}
            for index in range(total)
        ],
        "executionCreatedAt": "2026-08-16T00:00:00Z",
        "fleetStartedAt": "2026-08-16T00:00:00Z",
        "canonicalFinalizedAt": "2026-08-16T00:10:00Z",
        "fleetWallClockMilliseconds": 600_000,
        "endToEndWallClockMilliseconds": 600_000,
        "completedAt": "2026-08-16T00:10:00Z",
    }


def _validate(report: dict[str, Any]) -> None:
    assert_valid(report, "release", "reliabletask_fleet_report")


def test_receipt_with_all_three_capacity_observations_is_valid() -> None:
    _validate(_report())


@pytest.mark.parametrize("field", CAPACITY_RECEIPT_FIELDS)
def test_receipt_without_any_capacity_observation_fails_validation(
    field: str,
) -> None:
    """GWT-011.t1：缺任一项校验失败且回执不成立。"""
    report = _report()
    del report[field]

    with pytest.raises(ValueError, match=field):
        _validate(report)


@pytest.mark.parametrize("field", CAPACITY_RECEIPT_FIELDS)
def test_capacity_observations_are_top_level_required(field: str) -> None:
    """DEC-002：三值落顶层必填位，不进 taskOutcomes 也不进诊断子对象。"""
    schema = load_schema("release", "reliabletask_fleet_report")

    assert field in schema["required"]
    assert field in schema["properties"]
    assert field not in schema["properties"]["taskOutcomes"]["items"]["properties"]


@pytest.mark.parametrize("field", CAPACITY_RECEIPT_FIELDS)
def test_capacity_observations_declare_no_default(field: str) -> None:
    """缺席不得由契约默认值补齐，否则「缺任一项即不成立」失效。"""
    declaration = load_schema("release", "reliabletask_fleet_report")["properties"][
        field
    ]

    assert "default" not in declaration
    assert "const" not in declaration


def test_receipt_does_not_restate_the_frozen_concurrency_cap() -> None:
    """DEC-004：冻结上限只在 execution spec，回执只携带实测峰值。"""
    schema = load_schema("release", "reliabletask_fleet_report")

    assert "fleetMaxConcurrentWorkers" not in schema["properties"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("fleetPeakConcurrentWorkers", -1),
        ("fleetWaveCount", 0),
        ("fleetBatchDeadlineEpochSeconds", 0),
        ("fleetBatchDeadlineEpochSeconds", -1),
    ),
)
def test_capacity_observations_reject_impossible_values(
    field: str,
    value: int,
) -> None:
    """wave 数至少一轮；批次截止是绝对纪元秒，剩余时间归零不是合法截止。"""
    report = _report()
    report[field] = value

    with pytest.raises(ValueError, match=field):
        _validate(report)


@pytest.mark.parametrize("field", CAPACITY_RECEIPT_FIELDS)
def test_capacity_observations_reject_non_integer(field: str) -> None:
    report = _report()
    report[field] = 2.5

    with pytest.raises(ValueError, match=field):
        _validate(report)
