"""ReliableTask lifecycle-accepted 吞吐按 canonical 配额而非全量判定。"""
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
from content.execution.controller import metrics as metrics_module  # noqa: E402
from content.execution.queue.reliabletask import fleet as reliabletask_fleet
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport  # noqa: E402
from content.execution.queue.reliabletask.transport import (  # noqa: E402
    ReliableTaskFleetTransport,
)
from core.control_types import QueueJobStage  # noqa: E402
from core.io import write_json  # noqa: E402


@pytest.fixture(autouse=True)
def _bind_attempt_report_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        metrics_module,
        "latest_attempt_report_path_from_root",
        lambda root, _stage: (
            root / "evidence/reliabletask/publish_fleet_report.json"
            if (root / "evidence/reliabletask/publish_fleet_report.json").is_file()
            else None
        ),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "attempt_evidence_dir",
        lambda _execution_id, attempt: (
            tmp_path
            / "evidence/reliabletask"
            / str(attempt["stage"])
            / str(attempt["jobSetDigest"])[7:]
        ),
    )


def _report(
    *,
    passed: bool = True,
    required_quota: int = 10,
    research_accepted: int = 0,
    commercial_accepted: int | None = None,
    execution_id: str = "20260720--travel-image-m100--china--scale-001",
    stage: str = "publish",
) -> dict[str, object]:
    total = 10
    commercial = commercial_accepted if commercial_accepted is not None else (
        total if passed else total - 1
    )
    accepted = research_accepted + commercial
    return {
        "schema": "quwoquan.reliabletask_fleet_report",
        "executionId": execution_id,
        "stage": stage,
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
        "researchAcceptedCount": research_accepted,
        "commercialAcceptedCount": commercial,
        "fleetControlPlaneThroughputPerHour": 600.0,
        "fleetAcceptedThroughputPerHour": float(accepted * 60),
        "endToEndAcceptedThroughputPerHour": float(accepted / 2),
        "acceptedContentThroughputStatus": (
            "MEASURED"
            if passed
            else "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
        ),
        "recoveryEligibleCount": 0,
        "automaticRecoveredCount": 0,
        "manualRecoveredCount": 0,
        "automaticRecoveryStatus": "NOT_EXERCISED",
        "automaticRecoveryRate": 0.0,
        "firstAttemptSuccessRate": 1.0,
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


def test_metrics_use_canonical_lifecycle_accepted_fleet_report(
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
        "reliabletask_canonical_accepted_end_to_end"
    )
    assert measured["objectsPerHour"] == 5.0
    assert measured["fleetAcceptedObjectsPerHour"] == 600.0
    assert measured["elapsedSeconds"] == 7200.0
    assert measured["fleetWallClockSeconds"] == 60.0
    assert measured["publishedObjectCount"] == 10
    assert measured["researchAcceptedCount"] == 0
    assert measured["commercialAcceptedCount"] == 10
    assert measured["objectTransactionResultCount"] == 10
    assert measured["reportRef"] == (
        "evidence/reliabletask/publish_fleet_report.json"
    )


def test_metrics_accept_research_only_canonical_fleet_report(tmp_path: Path) -> None:
    write_json(
        tmp_path / "evidence/reliabletask/publish_fleet_report.json",
        _report(research_accepted=10, commercial_accepted=0),
    )

    measured = _reliabletask_accepted_throughput(tmp_path)

    assert measured is not None
    assert measured["publishedObjectCount"] == 10
    assert measured["researchAcceptedCount"] == 10
    assert measured["commercialAcceptedCount"] == 0


def test_loader_preserves_historical_report_without_research_count(
    tmp_path: Path,
) -> None:
    report = _report()
    report.pop("researchAcceptedCount")
    write_json(
        tmp_path / "evidence/reliabletask/publish_fleet_report.json",
        report,
    )

    decoded = ReliableTaskFleetReport.from_document(report)
    measured = _reliabletask_accepted_throughput(tmp_path)

    assert decoded.research_accepted_count == 0
    assert decoded.commercial_accepted_count == 10
    assert measured is not None
    assert measured["publishedObjectCount"] == 10


@pytest.mark.parametrize(
    "updates",
    (
        {"researchAcceptedCount": 6, "commercialAcceptedCount": 5},
        {"succeeded": 5, "objectTransactionResultCount": 6},
        {"publishTaskCount": 5, "objectTransactionResultCount": 6},
    ),
)
def test_loader_rejects_impossible_publish_acceptance_counts(
    updates: dict[str, int],
) -> None:
    report = _report()
    report.update(updates)

    with pytest.raises(ValueError, match="publish acceptance counts are invalid"):
        ReliableTaskFleetReport.from_document(report)


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


def test_recovery_rate_is_derived_only_from_recovery_eligible_failures() -> None:
    report = _report()
    report.update(
        {
            "recoveryEligibleCount": 20,
            "automaticRecoveredCount": 19,
            "manualRecoveredCount": 1,
            "automaticRecoveryStatus": "MEASURED",
            "automaticRecoveryRate": 0.95,
        }
    )

    decoded = ReliableTaskFleetReport.from_document(report)

    assert decoded.recovery_eligible_count == 20
    assert decoded.automatic_recovered_count == 19
    assert decoded.manual_recovered_count == 1
    assert decoded.automatic_recovery_status == "MEASURED"
    assert decoded.automatic_recovery_rate == 0.95


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        (
            {
                "recoveryEligibleCount": 20,
                "automaticRecoveredCount": 19,
                "manualRecoveredCount": 1,
                "automaticRecoveryStatus": "MEASURED",
                "automaticRecoveryRate": 1.0,
            },
            "automatic recovery metric drift",
        ),
        (
            {
                "recoveryEligibleCount": 0,
                "automaticRecoveredCount": 0,
                "manualRecoveredCount": 0,
                "automaticRecoveryStatus": "MEASURED",
                "automaticRecoveryRate": 0.0,
            },
            "automatic recovery metric drift",
        ),
        (
            {
                "recoveryEligibleCount": 1,
                "automaticRecoveredCount": 1,
                "manualRecoveredCount": 1,
                "automaticRecoveryStatus": "MEASURED",
                "automaticRecoveryRate": 1.0,
            },
            "recovery counts are invalid",
        ),
    ),
)
def test_recovery_metric_drift_is_rejected(
    updates: dict[str, object],
    message: str,
) -> None:
    report = _report()
    report.update(updates)

    with pytest.raises(ValueError, match=message):
        ReliableTaskFleetReport.from_document(report)


def test_failed_publish_fleet_report_remains_projectable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A valid failed receipt is business evidence, not environment unavailability."""
    report = _report(
        passed=False,
        execution_id="20260728--travel-video-supply--test-region-a--pilot-001",
    )
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
        lambda _execution_id, _stage, *, required_workers: {
            "campaignScale": "M1",
            "objectTimeoutMilliseconds": 1_000,
            "requiredWorkers": required_workers,
            "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
            "jobSetDigest": "sha256:" + "b" * 64,
            "actualTaskDigest": "sha256:" + "b" * 64,
            "jobs": [{} for _index in range(10)],
        },
    )
    monkeypatch.setattr(reliabletask_fleet, "execution_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_command",
        lambda _execution_id: (["fleet"], tmp_path),
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


def test_nonterminal_fleet_receipt_restarts_after_backend_interruption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    interrupted = _report(
        passed=False,
        required_quota=1,
        commercial_accepted=0,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
    interrupted.update(
        {
            "succeeded": 0,
            "stageCompletedCount": 0,
            "publishTaskCount": 0,
            "objectTransactionResultCount": 0,
            "finalizedObjectCount": 0,
            "taskOutcomes": [
                {
                    "jobId": f"job-{index}",
                    "status": "processing" if index == 0 else "ready",
                    "attempts": 1 if index == 0 else 0,
                }
                for index in range(10)
            ],
        }
    )
    resumed = _report(
        passed=True,
        required_quota=1,
        commercial_accepted=10,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
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
        lambda _execution_id, _stage, *, required_workers: {
            "campaignScale": "M1",
            "objectTimeoutMilliseconds": 1_000,
            "requiredWorkers": required_workers,
            "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
            "jobSetDigest": "sha256:" + "b" * 64,
            "actualTaskDigest": "sha256:" + "b" * 64,
            "jobs": [{} for _index in range(10)],
        },
    )
    monkeypatch.setattr(reliabletask_fleet, "execution_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_command",
        lambda _execution_id: (["fleet"], tmp_path),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_agent_python",
        lambda: Path("/usr/bin/python3"),
    )
    recovery_waits: list[str] = []
    monkeypatch.setattr(
        reliabletask_fleet,
        "_wait_for_fleet_transport",
        lambda transport, **_kwargs: recovery_waits.append(transport.target) or True,
    )
    invocations: list[int] = []

    def _run(command: list[str], **_kwargs: object) -> int:
        invocations.append(len(invocations) + 1)
        write_json(Path(command[-1]), interrupted if len(invocations) == 1 else resumed)
        return 1 if len(invocations) == 1 else 0

    monkeypatch.setattr(reliabletask_fleet, "_run_fleet_process", _run)

    decoded = reliabletask_fleet.run_reliabletask_fleet(
        "20260728--travel-homepage-supply--test-region-a--pilot-001",
        QueueJobStage.AUTHOR,
        workers=1,
        completion_grace_seconds=1,
    )

    assert invocations == [1, 2]
    assert recovery_waits == ["test"]
    assert decoded.passed is True
    archived = (
        tmp_path
        / ("evidence/reliabletask/author/" + "b" * 64)
        / "runtime-report-001.json"
    )
    assert archived.is_file()


def test_runtime_interruptions_do_not_exhaust_startup_failure_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    interrupted = _report(
        passed=False,
        required_quota=1,
        commercial_accepted=0,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
    interrupted.update(
        {
            "succeeded": 0,
            "stageCompletedCount": 0,
            "publishTaskCount": 0,
            "objectTransactionResultCount": 0,
            "finalizedObjectCount": 0,
            "taskOutcomes": [
                {
                    "jobId": f"job-{index}",
                    "status": "processing" if index == 0 else "ready",
                    "attempts": 0,
                }
                for index in range(10)
            ],
        }
    )
    resumed = _report(
        passed=True,
        required_quota=1,
        commercial_accepted=10,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
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
        lambda _execution_id, _stage, *, required_workers: {
            "campaignScale": "M1",
            "objectTimeoutMilliseconds": 1_000,
            "requiredWorkers": required_workers,
            "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
            "jobSetDigest": "sha256:" + "b" * 64,
            "actualTaskDigest": "sha256:" + "b" * 64,
            "jobs": [{} for _index in range(10)],
        },
    )
    monkeypatch.setattr(reliabletask_fleet, "execution_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_command",
        lambda _execution_id: (["fleet"], tmp_path),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_agent_python",
        lambda: Path("/usr/bin/python3"),
    )
    recovery_waits: list[str] = []
    monkeypatch.setattr(
        reliabletask_fleet,
        "_wait_for_fleet_transport",
        lambda transport, **_kwargs: recovery_waits.append(transport.target) or True,
    )
    invocations: list[int] = []

    def _run(command: list[str], **_kwargs: object) -> int:
        invocation = len(invocations) + 1
        invocations.append(invocation)
        if invocation <= 3:
            write_json(Path(command[-1]), interrupted)
            return 1
        if invocation == 4:
            return 1
        write_json(Path(command[-1]), resumed)
        return 0

    monkeypatch.setattr(reliabletask_fleet, "_run_fleet_process", _run)

    decoded = reliabletask_fleet.run_reliabletask_fleet(
        "20260728--travel-homepage-supply--test-region-a--pilot-001",
        QueueJobStage.AUTHOR,
        workers=1,
        completion_grace_seconds=1,
    )

    assert invocations == [1, 2, 3, 4, 5]
    assert recovery_waits == ["test", "test", "test", "test"]
    assert decoded.passed is True
    for attempt in range(1, 4):
        assert (
            tmp_path
            / ("evidence/reliabletask/author/" + "b" * 64)
            / f"runtime-report-{attempt:03d}.json"
        ).is_file()


def test_zero_exit_nonterminal_receipt_is_not_false_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    interrupted = _report(
        passed=False,
        required_quota=1,
        commercial_accepted=0,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
    interrupted["taskOutcomes"] = [
        {
            "jobId": f"job-{index}",
            "status": "processing" if index == 0 else "ready",
            "attempts": 0,
        }
        for index in range(10)
    ]
    resumed = _report(
        passed=True,
        required_quota=1,
        commercial_accepted=10,
        execution_id="20260728--travel-homepage-supply--test-region-a--pilot-001",
        stage="author",
    )
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
        lambda _execution_id, _stage, *, required_workers: {
            "campaignScale": "M1",
            "objectTimeoutMilliseconds": 1_000,
            "requiredWorkers": required_workers,
            "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
            "jobSetDigest": "sha256:" + "b" * 64,
            "actualTaskDigest": "sha256:" + "b" * 64,
            "jobs": [{} for _index in range(10)],
        },
    )
    monkeypatch.setattr(reliabletask_fleet, "execution_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_command",
        lambda _execution_id: (["fleet"], tmp_path),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "_fleet_agent_python",
        lambda: Path("/usr/bin/python3"),
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "_wait_for_fleet_transport",
        lambda _transport, **_kwargs: True,
    )
    invocations: list[int] = []

    def _run(command: list[str], **_kwargs: object) -> int:
        invocations.append(len(invocations) + 1)
        write_json(Path(command[-1]), interrupted if len(invocations) == 1 else resumed)
        return 0

    monkeypatch.setattr(reliabletask_fleet, "_run_fleet_process", _run)

    decoded = reliabletask_fleet.run_reliabletask_fleet(
        "20260728--travel-homepage-supply--test-region-a--pilot-001",
        QueueJobStage.AUTHOR,
        workers=1,
        completion_grace_seconds=1,
    )

    assert invocations == [1, 2]
    assert decoded.passed is True
