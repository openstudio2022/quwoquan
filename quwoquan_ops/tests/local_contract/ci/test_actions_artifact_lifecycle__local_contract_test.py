from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.manage_actions_artifacts import build_run_report, classify_artifact
from quwoquan_ops.gate.verify_github_artifact_lifecycle import verify


NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _artifact(
    *,
    artifact_id: int = 1,
    name: str = "device-matrix-report",
    created_at: str = "2026-05-01T00:00:00Z",
    expired: bool = False,
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
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


def test_automatic_docker_build_record_is_immediately_invalid_even_on_failure() -> None:
    decision = classify_artifact(
        _artifact(name="record.dockerbuild", created_at="2026-07-27T00:00:00Z"),
        {"conclusion": "failure"},
        now=NOW,
        failed_retention_days=3,
        success_retention_days=1,
    )

    assert decision is not None
    assert decision.reason == "invalid-automatic-build-record"


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


def test_repository_artifact_policy_rejects_implicit_go_cache() -> None:
    assert verify() == []


def test_pr_workflows_use_lock_bound_shared_dependency_caches() -> None:
    recommendation = (
        ROOT / ".github/workflows/recommendation_api_integration.yml"
    ).read_text(encoding="utf-8")
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    assert "lookup-only: ${{ github.event_name == 'pull_request' }}" in recommendation
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in delivery
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in delivery
    assert "subosito/flutter-action@" not in delivery
    assert "quwoquan_app/.flutter-version" in delivery


def test_lifecycle_only_spends_a_runner_for_failures_or_service_build_record_audit() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert "github.event.workflow_run.name == '02. Service Pipeline'" in lifecycle
    assert "github.event.workflow_run.conclusion != 'success'" in lifecycle


def test_lifecycle_reclaims_isolated_cache_when_pull_request_closes() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:\n    types: [closed]" in lifecycle
    assert "Reclaim closed pull-request caches" in lifecycle
    assert "refs/pull/${{ github.event.pull_request.number }}/merge" in lifecycle
    assert "actions/caches/${cache_id}" in lifecycle
