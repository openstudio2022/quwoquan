# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/system-backsync.yml"
CORE = ROOT / "quwoquan_ops/ci/system_backsync.py"


def load_workflow() -> tuple[str, dict]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_permanent_managed_backsync_has_one_reusable_entry() -> None:
    _text, workflow = load_workflow()

    assert workflow["name"] == "08. Managed System Backsync"
    assert set(workflow[True]) == {"workflow_call"}
    called = workflow[True]["workflow_call"]
    assert set(called) == {"inputs"}
    assert set(called["inputs"]) == {
        "expected_dev_before",
        "source_sha",
        "main_source_seal_ref",
        "main_source_seal_digest",
    }
    assert all(
        descriptor["required"] is True and descriptor["type"] == "string"
        for descriptor in called["inputs"].values()
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "${{ github.repository }}-managed-system-backsync",
        "cancel-in-progress": False,
    }
    assert set(workflow["jobs"]) == {"backsync"}
    job = workflow["jobs"]["backsync"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 5
    assert job["environment"] == "system-backsync"
    assert job["permissions"] == {
        "actions": "read", "checks": "read", "contents": "read", "packages": "read",
    }
    assert job["env"] == {
        "QWQ_MANAGED_SYSTEM_BACKSYNC": "system-fast-forward-cas-v1",
        "QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": "${{ job.workflow_ref }}",
        "QWQ_PROMOTION_RECORDER_APP_SLUG": "${{ vars.QWQ_PROMOTION_RECORDER_APP_SLUG }}",
        "QWQ_PROMOTION_RECORDER_APP_ID": "${{ vars.QWQ_PROMOTION_RECORDER_APP_ID }}",
        "GITHUB_EVENT_BEFORE": "${{ github.event.before }}",
        "GITHUB_EVENT_AFTER": "${{ github.event.after }}",
    }


def test_workflow_consumes_exact_source_seal_before_nonforce_cas() -> None:
    text, _workflow = load_workflow()

    for token in (
        "MAIN_SOURCE_SEAL_REF",
        "MAIN_SOURCE_SEAL_DIGEST",
        "promotionAdmissionOciRef",
        "--main-source-seal-ref",
        "--main-source-seal-digest",
        "--promotion-admission-path",
        "--hosted-handoff-path",
        "--expected-dev-before",
        "--source-sha",
        "quwoquan_ops/ci/system_backsync.py",
        "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
        "persist-credentials: false",
        "SYSTEM_BACKSYNC_DEPLOY_KEY",
        "job.workflow_ref",
        "QWQ_PROMOTION_RECORDER_APP_SLUG",
        "QWQ_PROMOTION_RECORDER_APP_ID",
        "/commits/${SOURCE_SHA}/check-runs",
        "validate_hosted_promotion_handoff",
        "/actions/runs/${WORKFLOW_RUN_ID}",
        "check_run=check",
        "workflow_run=run",
        "GITHUB_EVENT_BEFORE",
        "GITHUB_EVENT_AFTER",
    ):
        assert token in text
    assert text.index("materialize-oci") < text.index(
        "quwoquan_ops/ci/system_backsync.py"
    )
    for forbidden in (
        "workflow_dispatch:",
        "workflow_run:",
        "push:",
        "schedule:",
        ":latest",
        "released_fact",
        "released-fact",
        "soak_fact",
        "soak-fact",
        "release-ledger",
        "PROD_SERVICE_SSH_KEY",
        "git merge",
        "git push --force ",
        "git push -f ",
        "/statuses?",
        "statusId",
        "statusNodeId",
        '"creator"',
        "QWQ_PROMOTION_RECORDER_LOGIN",
        "QWQ_PROMOTION_RECORDER_USER_ID",
    ):
        assert forbidden not in text


def test_workflow_delegates_check_run_validation_to_canonical_validator() -> None:
    text, _workflow = load_workflow()

    assert text.count("validate_hosted_promotion_handoff") == 2
    assert 'row.get("name") == "quwoquan/promotion-admission-handoff/v1"' in text
    assert 'expected_app_slug=sys.argv[8]' in text
    assert 'expected_app_id=int(sys.argv[9])' in text
    assert 'verified_at=seal["mainReadbackAt"]' in text
    for old_status_token in (
        "/statuses?", "statusId", "statusNodeId", '"creator"',
    ):
        assert old_status_token not in text


def test_gate_fails_closed_for_missing_or_raw_unmanaged_entry(tmp_path: Path) -> None:
    from quwoquan_ops.gate.verify_git_branch_policy import (
        system_backsync_workflow_issues,
    )

    missing = tmp_path / "system-backsync.yml"
    assert "workflow is missing" in system_backsync_workflow_issues(missing)[0]

    unmanaged = tmp_path / "raw.yml"
    unmanaged.write_text(
        "name: raw\npermissions: {contents: write}\non: {workflow_dispatch: {}}\njobs: {}\n",
        encoding="utf-8",
    )
    issues = system_backsync_workflow_issues(unmanaged)
    assert issues == [
        "managed system backsync workflow must expose only workflow_call"
    ]


def test_core_uses_nonforce_expected_before_cas_without_raw_fallback() -> None:
    text = CORE.read_text(encoding="utf-8")

    assert '"push", "--porcelain",' in text
    assert 'remote, "HEAD:refs/heads/dev1.0"' in text
    assert "--force-with-lease" not in text
    assert "--force-if-includes" not in text
    assert '"push", remote' not in text


def test_branch_gate_rejects_manual_runtime_and_accepts_canonical_caller() -> None:
    from quwoquan_ops.gate.verify_git_branch_policy import (
        _is_managed_system_backsync_environment,
    )

    repository = "owner/quwoquan"
    main = "a" * 40
    canonical = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": main,
        "GITHUB_ACTOR": "github-actions[bot]",
        "GITHUB_REPOSITORY": repository,
        "GITHUB_WORKFLOW_REF": (
            f"{repository}/.github/workflows/delivery-gate.yml@refs/heads/main"
        ),
        "QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": (
            f"{repository}/.github/workflows/system-backsync.yml@{main}"
        ),
        "QWQ_MANAGED_SYSTEM_BACKSYNC": "system-fast-forward-cas-v1",
    }
    assert _is_managed_system_backsync_environment(canonical) is True
    assert _is_managed_system_backsync_environment(
        {**canonical, "GITHUB_EVENT_NAME": "workflow_dispatch"}
    ) is False
