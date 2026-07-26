"""ReliableTask 商业吞吐必须覆盖旧的批次文件时间估算。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.execution.controller.metrics import (  # noqa: E402
    _reliabletask_accepted_throughput,
)
from core.io import write_json  # noqa: E402


def _report(*, passed: bool = True) -> dict[str, object]:
    total = 10
    return {
        "schema": "quwoquan.reliabletask_fleet_report",
        "passed": passed,
        "backend": "mongodb+redis",
        "total": total,
        "succeeded": total,
        "stageCompletedCount": 0,
        "publishTaskCount": total,
        "objectTransactionResultCount": total,
        "commercialAcceptedCount": total if passed else total - 1,
        "controlPlaneTaskThroughputPerHour": 500.0,
        "acceptedContentThroughputPerHour": 480.0 if passed else 432.0,
        "acceptedContentThroughputStatus": (
            "MEASURED"
            if passed
            else "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
        ),
        "automaticRecoveryRate": 1.0,
        "finalizedWithinStageBudgetRate": 1.0,
        "duplicatePublishCount": 0,
        "missingObjectCount": 0,
        "idempotencyKey": "executionId+entity+carrier+sourceRevision+stage",
        "taskOutcomes": [
            {"jobId": f"job-{index}", "status": "succeeded", "attempts": 1}
            for index in range(total)
        ],
        "completedAt": "2026-07-20T05:00:00Z",
    }


def test_metrics_use_only_commercially_accepted_fleet_report(
    tmp_path: Path,
) -> None:
    report_path = (
        tmp_path
        / "evidence/reliabletask/publish_fleet_report.json"
    )
    write_json(report_path, _report())

    measured = _reliabletask_accepted_throughput(tmp_path)

    assert measured is not None
    assert measured["measurementMode"] == "reliabletask_commercial_accepted"
    assert measured["objectsPerHour"] == 480.0
    assert measured["publishedObjectCount"] == 10
    assert measured["reportRef"] == (
        "evidence/reliabletask/publish_fleet_report.json"
    )


def test_metrics_reject_incomplete_commercial_fleet_report(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "evidence/reliabletask/publish_fleet_report.json",
        _report(passed=False),
    )

    with pytest.raises(
        ValueError,
        match="未形成 commercial accepted throughput",
    ):
        _reliabletask_accepted_throughput(tmp_path)
