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


def test_domain_governance_rejects_secret_or_deployment_payload_uploads() -> None:
    workflow = (ROOT / ".github/workflows/domain-governance.yml").read_text(
        encoding="utf-8"
    )
    marker = "uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    upload_steps = [
        "      - " + block
        for block in workflow.split("\n      - ")
        if marker in block
    ]

    assert len(upload_steps) == 2
    expected_paths = (
        ".qwq_output/env/repo/runs/domain/dns-failure-diagnostic.json",
        ".qwq_output/env/repo/runs/domain/${{ matrix.target }}-tls-failure-diagnostic.json",
    )
    for block, expected_path in zip(upload_steps, expected_paths, strict=True):
        assert "if: ${{ failure() && !cancelled() }}" in block
        assert "retention-days: 3" in block
        assert f"path: {expected_path}" in block
        assert "path: |" not in block
        for forbidden in (
            "${{ env.QWQ_TLS_BUNDLE_PATH }}",
            "tls-bundle.tar.age",
            "tls-evidence.json",
            "dns-*.json",
            "dns-plan.json",
            "dns-apply-receipt.json",
            "dns-live-evidence.json",
            "privkey.pem",
            "fullchain.pem",
            "QWQ_DEPLOY_WORK_ROOT",
            "QWQ_PUBLIC_TLS_BUNDLE_DIR",
        ):
            assert forbidden not in block

    assert workflow.count("quwoquan.domain-governance-failure-diagnostic") == 1
    assert workflow.count("quwoquan.domain-governance-tls-failure-diagnostic") == 1


def test_pr_workflows_use_lock_bound_shared_dependency_caches() -> None:
    recommendation = (
        ROOT / ".github/workflows/recommendation_api_integration.yml"
    ).read_text(encoding="utf-8")
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    assert "lookup-only: ${{ github.event_name == 'pull_request' }}" in recommendation
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" not in delivery
    assert "setup_flutter_sdk.py" not in delivery
    assert "subosito/flutter-action@" not in delivery
    assert "flutter test" not in delivery


def test_lifecycle_uses_github_hosted_linux_without_changing_trigger_filter() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert "runs-on: ubuntu-latest" in lifecycle
    assert "runs-on: [self-hosted, macOS, ARM64]" not in lifecycle
    assert "workflow_run:" not in lifecycle
    assert "github.event.workflow_run" not in lifecycle
    assert "schedule:" in lifecycle


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
