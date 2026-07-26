from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.manage_actions_artifacts import build_run_report, classify_artifact


NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _artifact(*, artifact_id: int = 1, created_at: str = "2026-05-01T00:00:00Z", expired: bool = False) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": "device-matrix-report",
        "size_in_bytes": 1024,
        "created_at": created_at,
        "expires_at": "2026-08-01T00:00:00Z",
        "expired": expired,
        "workflow_run": {"id": 42},
    }


def test_cancelled_run_artifact_is_immediately_invalid() -> None:
    decision = classify_artifact(
        _artifact(created_at="2026-07-27T00:00:00Z"),
        {"conclusion": "cancelled"},
        now=NOW,
        failed_retention_days=7,
        success_retention_days=14,
    )

    assert decision is not None
    assert decision.reason == "invalid-run-cancelled"


def test_old_failed_diagnostic_expires_but_success_is_immediately_invalid() -> None:
    failed = classify_artifact(
        _artifact(artifact_id=2),
        {"conclusion": "failure"},
        now=NOW,
        failed_retention_days=7,
        success_retention_days=14,
    )
    success = classify_artifact(
        _artifact(artifact_id=3),
        {"conclusion": "success"},
        now=NOW,
        failed_retention_days=7,
        success_retention_days=14,
    )

    assert failed is not None
    assert failed.reason == "failure-diagnostic-retention-expired"
    assert success is not None
    assert success.reason == "invalid-success-artifact"


def test_recent_successful_artifact_is_not_preserved() -> None:
    decision = classify_artifact(
        _artifact(created_at="2026-07-20T00:00:00Z"),
        {"conclusion": "success"},
        now=NOW,
        failed_retention_days=7,
        success_retention_days=14,
    )

    assert decision is not None
    assert decision.reason == "invalid-success-artifact"


def test_completed_run_cleanup_queries_only_its_exact_artifacts() -> None:
    class FakeApi:
        repository = "openstudio2022/quwoquan"

        def workflow_run(self, run_id: int) -> dict[str, object] | None:
            assert run_id == 42
            return {"conclusion": "cancelled"}

        def list_run_artifacts(self, run_id: int) -> list[dict[str, object]]:
            assert run_id == 42
            return [_artifact(artifact_id=9, created_at="2026-07-27T00:00:00Z")]

    report, decisions = build_run_report(
        FakeApi(),  # type: ignore[arg-type]
        run_id=42,
        now=NOW,
        failed_retention_days=3,
        success_retention_days=1,
    )

    assert report["scope"] == {"workflowRunId": 42}
    assert [item.reason for item in decisions] == ["invalid-run-cancelled"]
