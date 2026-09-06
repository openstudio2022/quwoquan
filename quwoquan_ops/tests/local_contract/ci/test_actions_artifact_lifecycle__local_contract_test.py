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


def test_gate_covers_mapping_list_inline_and_multiline_artifact_uses(
    tmp_path: Path, monkeypatch: object
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    digest = "a" * 40
    workflows.joinpath("forms.yml").write_text(
        f"""name: Fixture\njobs:
  mapping:
    steps:
      - name: Mapping upload
        if: ${{{{ failure() && !cancelled() }}}}
        uses: actions/upload-artifact@{digest}
        with:
          name: mapping
          path: mapping.log
          retention-days: 3
      - uses: actions/upload-artifact@{digest}
        if: ${{{{ failure() && !cancelled() }}}}
        with: {{name: inline, path: inline.log, retention-days: 3}}
      - name: Invalid list upload
        uses: actions/upload-artifact@{digest}
        with:
          name: invalid
          path: invalid.log
      - name: Forbidden download
        uses: actions/download-artifact@{digest}
        with:
          name: exchange
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.ROOT", tmp_path
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.WORKFLOWS", workflows
    )

    issues = verify()

    assert sum(
        "artifact uploads require explicit retention-days" in issue
        for issue in issues
    ) == 1
    assert sum(
        "Actions artifacts are failure diagnostics only" in issue for issue in issues
    ) == 1
    assert any(
        "Actions Artifact job exchange is forbidden" in issue for issue in issues
    )


def test_promotion_gate_has_no_dependency_cache_or_toolchain_bootstrap() -> None:
    recommendation = (
        ROOT / ".github/workflows/recommendation_api_integration.yml"
    ).read_text(encoding="utf-8")
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "lookup-only: ${{ github.event_name == 'pull_request' }}" in recommendation
    for token in ("actions/cache@", "cache-dependency-path:", "setup_flutter_sdk.py", ".flutter-version", "setup-node", "setup-go"):
        assert token not in delivery


def test_lifecycle_is_periodic_or_pr_close_without_workflow_run_fanout() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in lifecycle
    assert "runs-on: [self-hosted, macOS, ARM64]" not in lifecycle
    assert "workflow_run:" not in lifecycle
    assert "schedule:" in lifecycle
    assert "pull_request:" in lifecycle and "closed" in lifecycle


def test_gate_rejects_self_hosted_macos_arm64_lifecycle_runner(
    tmp_path: Path, monkeypatch: object
) -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    forbidden_workflow = tmp_path / "artifact-lifecycle.yml"
    forbidden_workflow.write_text(
        lifecycle.replace(
            "runs-on: ubuntu-latest", "runs-on: [self-hosted, macOS, ARM64]"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.LIFECYCLE_WORKFLOW",
        forbidden_workflow,
    )

    assert (
        "artifact lifecycle workflow must not use a self-hosted macOS ARM64 runner"
        in verify()
    )


def test_lifecycle_reclaims_isolated_cache_when_pull_request_closes() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:\n    types: [closed]" in lifecycle
    assert "Reclaim closed pull-request caches" in lifecycle
    assert "refs/pull/${{ github.event.pull_request.number }}/merge" in lifecycle
    assert "actions/caches/${cache_id}" in lifecycle
