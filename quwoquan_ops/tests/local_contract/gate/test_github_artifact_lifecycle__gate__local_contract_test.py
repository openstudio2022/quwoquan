from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.manage_actions_artifacts import build_run_report, classify_artifact
from quwoquan_ops.gate.verify_github_artifact_lifecycle import verify


NOW = datetime(2026, 7, 27, tzinfo=UTC)


UPLOAD_ARTIFACT_ACTION = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
WEEKLY_REPORT_UPLOAD = f"""      - name: Upload successful weekly report
        if: success()
        uses: {UPLOAD_ARTIFACT_ACTION}
        with:
          name: code-health-weekly-report-${{{{ github.run_id }}}}-${{{{ github.run_attempt }}}}
          path: ${{{{ env.QWQ_OUTPUT_ROOT }}}}/env/repo/runs/code-health/weekly/**/report.json
          if-no-files-found: error
          compression-level: 0
          retention-days: 14
"""


def _weekly_workflow(upload: str = WEEKLY_REPORT_UPLOAD, *, suffix: str = "") -> str:
    return f"""# Report-only observation.
name: Weekly Code Health
permissions:
  contents: read
  actions: read
jobs:
  report:
    name: Weekly Code Health — Report Only
    runs-on: ubuntu-latest
    steps:
{upload}{suffix}"""


def _verify_workflows(
    tmp_path: Path,
    monkeypatch: object,
    *,
    weekly: str = WEEKLY_REPORT_UPLOAD,
    ordinary: str | None = None,
    weekly_suffix: str = "",
) -> list[str]:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "code-health-weekly.yml").write_text(
        _weekly_workflow(weekly, suffix=weekly_suffix), encoding="utf-8"
    )
    if ordinary is not None:
        (workflows / "ordinary.yml").write_text(ordinary, encoding="utf-8")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.ROOT", tmp_path
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.WORKFLOWS", workflows
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quwoquan_ops.gate.verify_github_artifact_lifecycle.WEEKLY_REPORT_WORKFLOW",
        workflows / "code-health-weekly.yml",
    )
    return verify()


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


def test_immutable_reference_index_protects_referenced_artifact() -> None:
    class FakeApi:
        repository = "openstudio2022/quwoquan"
        def list_artifacts(self): return [_artifact(artifact_id=77)]
        def workflow_runs(self, _ids): return {42: {"conclusion": "success"}}
    from quwoquan_ops.ci.manage_actions_artifacts import build_report
    report, decisions = build_report(
        FakeApi(), now=NOW, failed_retention_days=3, success_retention_days=1,
        referenced_artifact_ids=frozenset({77}),
    )
    assert decisions == []
    assert report["inventory"]["protectedByImmutableReference"] == [77]


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


def test_success_upload_in_ordinary_workflow_remains_forbidden(
    tmp_path: Path, monkeypatch: object
) -> None:
    ordinary = f"""name: Ordinary
jobs:
  check:
    steps:
{WEEKLY_REPORT_UPLOAD}"""

    issues = _verify_workflows(tmp_path, monkeypatch, ordinary=ordinary)

    assert any(
        "ordinary.yml" in issue and "failure diagnostics only" in issue
        for issue in issues
    )


@pytest.mark.parametrize(
    ("current", "drifted"),
    (
        ("retention-days: 14", "retention-days: 15"),
        (
            "env/repo/runs/code-health/weekly/**/report.json",
            "env/repo/runs/code-health/weekly/**",
        ),
        ("if-no-files-found: error", "if-no-files-found: ignore"),
        ("name: code-health-weekly-report-", "name: code-health-report-"),
    ),
    ids=("retention", "broad-path", "missing-file-policy", "artifact-name"),
)
def test_weekly_success_report_contract_rejects_any_bounded_identity_drift(
    tmp_path: Path, monkeypatch: object, current: str, drifted: str
) -> None:
    issues = _verify_workflows(
        tmp_path, monkeypatch, weekly=WEEKLY_REPORT_UPLOAD.replace(current, drifted)
    )

    assert any("failure diagnostics only" in issue for issue in issues)
    assert any("exactly one bounded successful weekly report" in issue for issue in issues)


@pytest.mark.parametrize(
    "unsafe_step",
    (
        "      - uses: actions/download-artifact@" + "a" * 40 + "\n",
        "      - run: python3 governance.py --create-open\n",
        "      - run: python3 governance.py --promotion\n",
        "      - run: python3 governance.py --mutation\n",
    ),
    ids=("download", "automatic-open", "promotion", "mutation"),
)
def test_weekly_success_report_contract_requires_report_only_workflow(
    tmp_path: Path, monkeypatch: object, unsafe_step: str
) -> None:
    issues = _verify_workflows(tmp_path, monkeypatch, weekly_suffix=unsafe_step)

    assert any("failure diagnostics only" in issue for issue in issues)
    assert any("exactly one bounded successful weekly report" in issue for issue in issues)


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


def test_lifecycle_uses_github_hosted_linux_without_changing_trigger_filter() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert "runs-on: ubuntu-latest" in lifecycle
    assert "runs-on: [self-hosted, macOS, ARM64, quwoquan-release-authority]" not in lifecycle
    assert "workflow_run:" not in lifecycle
    assert "schedule:" in lifecycle
    assert "workflow_dispatch:" in lifecycle


def test_lifecycle_schedule_is_report_only() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    assert lifecycle.count("args+=(--apply)") == 1
    assert 'github.event_name }}" != "workflow_dispatch"' not in lifecycle
    assert (
        'github.event_name }}" == "workflow_dispatch" '
        '&& "${{ inputs.apply }}" == "true"'
    ) in lifecycle


def test_lifecycle_manual_apply_defaults_false_and_requires_explicit_true() -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    dispatch = lifecycle.split("  workflow_dispatch:\n", 1)[1].split(
        "  pull_request:\n", 1
    )[0]

    assert "default: false" in dispatch
    assert "default: true" not in dispatch
    assert (
        'if [[ "${{ github.event_name }}" == "workflow_dispatch" '
        '&& "${{ inputs.apply }}" == "true" ]]; then'
    ) in lifecycle


def test_gate_rejects_self_hosted_macos_arm64_lifecycle_runner(
    tmp_path: Path, monkeypatch: object
) -> None:
    lifecycle = (ROOT / ".github/workflows/artifact-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    forbidden_workflow = tmp_path / "artifact-lifecycle.yml"
    forbidden_workflow.write_text(
        lifecycle.replace(
            "runs-on: ubuntu-latest", "runs-on: [self-hosted, macOS, ARM64, quwoquan-release-authority]"
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
