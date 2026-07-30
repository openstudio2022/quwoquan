"""ReliableTask 商业吞吐必须覆盖旧的批次文件时间估算，并按配额而非全量判定。"""
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
from content.execution import reliabletask_fleet  # noqa: E402
from content.execution.reliabletask_fleet import (  # noqa: E402
    ReliableTaskFleetTransport,
)
from core.control_types import QueueJobStage  # noqa: E402
from core.io import write_json  # noqa: E402


def _report(
    *,
    passed: bool = True,
    required_quota: int = 10,
    commercial_accepted: int | None = None,
) -> dict[str, object]:
    total = 10
    accepted = commercial_accepted if commercial_accepted is not None else (
        total if passed else total - 1
    )
    return {
        "schema": "quwoquan.reliabletask_fleet_report",
        "passed": passed,
        "backend": "mongodb+redis",
        "total": total,
        "succeeded": total,
        "stageCompletedCount": 0,
        "publishTaskCount": total,
        "objectTransactionResultCount": total,
        "commercialAcceptedCount": accepted,
        "fleetControlPlaneThroughputPerHour": 600.0,
        "fleetAcceptedThroughputPerHour": float(accepted * 60),
        "endToEndAcceptedThroughputPerHour": float(accepted / 2),
        "acceptedContentThroughputStatus": (
            "MEASURED"
            if passed
            else "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
        ),
        "automaticRecoveryRate": 1.0,
        "finalizedWithinStageBudgetRate": 1.0,
        "duplicatePublishCount": 0,
        "missingObjectCount": 0,
        "requiredQuota": required_quota,
        "finalizedObjectCount": accepted,
        "idempotencyKey": "executionId+entity+carrier+sourceRevision+stage",
        "taskOutcomes": [
            {"jobId": f"job-{index}", "status": "succeeded", "attempts": 1}
            for index in range(total)
        ],
        "executionCreatedAt": "2026-07-20T03:00:00Z",
        "fleetStartedAt": "2026-07-20T04:59:00Z",
        "canonicalFinalizedAt": "2026-07-20T05:00:00Z",
        "fleetWallClockMilliseconds": 60_000,
        "endToEndWallClockMilliseconds": 7_200_000,
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
    assert measured["measurementMode"] == (
        "reliabletask_commercial_accepted_end_to_end"
    )
    assert measured["objectsPerHour"] == 5.0
    assert measured["fleetAcceptedObjectsPerHour"] == 600.0
    assert measured["elapsedSeconds"] == 7200.0
    assert measured["fleetWallClockSeconds"] == 60.0
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
        match="未达准出配额",
    ):
        _reliabletask_accepted_throughput(tmp_path)


def test_metrics_accept_quota_without_full_batch_success(tmp_path: Path) -> None:
    """达配额即通过：8/10 达标、配额 7 时仍是合法的 MEASURED 吞吐。"""
    write_json(
        tmp_path / "evidence/reliabletask/publish_fleet_report.json",
        _report(required_quota=7, commercial_accepted=8),
    )

    measured = _reliabletask_accepted_throughput(tmp_path)

    assert measured is not None
    assert measured["publishedObjectCount"] == 8
    assert measured["requiredQuota"] == 7
    assert measured["finalizedObjectCount"] == 8
    assert measured["objectsPerHour"] == 4.0
    assert measured["fleetAcceptedObjectsPerHour"] == 480.0


def test_metrics_reject_accepted_below_quota(tmp_path: Path) -> None:
    """未达配额必须报清楚“已达标 / 配额”。"""
    write_json(
        tmp_path / "evidence/reliabletask/publish_fleet_report.json",
        _report(required_quota=9, commercial_accepted=5),
    )

    with pytest.raises(ValueError, match="已达标 5 / 配额 9"):
        _reliabletask_accepted_throughput(tmp_path)


def test_failed_publish_fleet_report_remains_projectable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A valid failed receipt is business evidence, not environment unavailability."""
    report = _report(passed=False)
    report["taskOutcomes"] = [
        {
            "jobId": f"job-{index}",
            "status": "dead" if index == 0 else "succeeded",
            "attempts": 3 if index == 0 else 1,
            **(
                {"failureCode": "RELIABLETASK.WORKER.handler_failed"}
                if index == 0
                else {}
            ),
        }
        for index in range(10)
    ]
    monkeypatch.setattr(
        reliabletask_fleet,
        "resolve_reliabletask_fleet_transport",
        lambda: ReliableTaskFleetTransport(
            target="test",
            mongo_uri="mongodb://127.0.0.1:27017/quwoquan",
            redis_addr="127.0.0.1:6379",
        ),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "build_fleet_request",
        lambda _execution_id, _stage: {
            "objectTimeoutMilliseconds": 1_000,
            "jobs": [{} for _index in range(10)],
        },
    )
    monkeypatch.setattr(reliabletask_fleet, "execution_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_command",
        lambda: (["fleet"], tmp_path),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_agent_python",
        lambda: Path("/usr/bin/python3"),
    )

    def _run(command: list[str], **_kwargs: object) -> int:
        write_json(Path(command[-1]), report)
        return 1

    monkeypatch.setattr(reliabletask_fleet, "_run_fleet_process", _run)

    decoded = reliabletask_fleet.run_reliabletask_fleet(
        "20260728--travel-video-supply--test-region-a--pilot-001",
        QueueJobStage.PUBLISH,
        workers=2,
        completion_grace_seconds=1,
    )

    assert decoded.passed is False
    assert decoded.accepted_content_throughput_status == (
        "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
    )
    assert decoded.outcomes[0].failure_code == "RELIABLETASK.WORKER.handler_failed"
