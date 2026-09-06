# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from copy import deepcopy
from pathlib import Path

import yaml

from quwoquan_ops.gate.verify_ci_cd_evidence_contracts import (
    promotion_workflow_findings,
)

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"
POLICY = ROOT / "quwoquan_ops/policies/branch_policy.yaml"


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def _commands(job: dict[str, object]) -> str:
    return "\n".join(
        str(step.get("run") or "")
        for step in job.get("steps") or []
        if isinstance(step, dict)
    )


def _finding_details(text: str, workflow: dict[str, object]) -> list[str]:
    return [
        finding.detail
        for finding in promotion_workflow_findings(
            ".github/workflows/delivery-gate.yml", text, workflow
        )
    ]


def test_promotion_workflow_separates_pre_merge_gate_from_main_push_sealing() -> None:
    text, workflow = _workflow()
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))

    # 审批事件也重新评估同一 required context，避免"先绿后审批再手动重跑"的二次流程。
    assert workflow[True] == {
        "pull_request": {"branches": ["main"]},
        "pull_request_review": {"types": ["submitted", "dismissed"]},
        "push": {"branches": ["main"]},
    }
    assert list(workflow["jobs"]) == ["promotion_verify", "main_source_seal"]
    assert workflow["jobs"]["promotion_verify"]["name"] == "03. Delivery Gate"
    assert policy["required_promotion_checks"] == [
        {"name": "03. Delivery Gate", "workflow": ".github/workflows/delivery-gate.yml"}
    ]
    assert "workflow_dispatch" not in workflow[True]
    assert "github.sha" not in text
    # runner 上下文在 job 级 env 不可用；这正是曾让 workflow 文件校验失败的写法。
    for job in workflow["jobs"].values():
        assert not any("runner." in str(value) for value in (job.get("env") or {}).values())
    assert "create-github-app-token" not in text
    assert "${{ vars." not in text


def test_pull_request_gate_only_qualifies_exact_current_dev_head() -> None:
    _, workflow = _workflow()
    job = workflow["jobs"]["promotion_verify"]
    commands = _commands(job)

    assert job["if"] == "${{ github.event_name == 'pull_request' || github.event_name == 'pull_request_review' }}"
    assert 'values["HEAD_REF"] != "dev1.0"' in commands
    assert 'values["BASE_REF"] != "main"' in commands
    assert 'os.environ["PR_HEAD_REPOSITORY"] != os.environ["REPOSITORY"]' in commands
    assert 'required_keys = {"qualification_bundle_ref", "promotion_ready_at"}' in commands
    assert job["permissions"] == {
        "contents": "read", "packages": "write", "checks": "write", "pull-requests": "read",
    }
    checkout = next(step for step in job["steps"] if "uses" in step)
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    ordered = (
        "refs/remotes/origin/dev1.0",
        "refs/remotes/origin/main",
        "promotion_hosted.py materialize-oci-bundle",
        "integration_qualification.py",
        "--signing-keyring quwoquan_ops/policies/evidence_signing_keyring.yaml",
        "--expected-qualification-signer-identity",
        "/reviews",
        "reviewThreads",
        "/rulesets",
        "verify_git_branch_policy.py",
        "--execution-profile promotion",
        "verify_ci_changed_boundary.py",
        "promotion_hosted.py hosted-authority",
        "promotion-admit",
        "promotion_evidence.py publish-oci",
        "promotion_evidence.py create-handoff",
        "/check-runs",
        'app.get("id") != 15368 or app.get("slug") != "github-actions"',
    )
    positions = [commands.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert '--transport-tag "base-${BASE_SHA}-head-${HEAD_SHA}"' in commands
    assert "actions/runs/${GITHUB_RUN_ID}/attempts/${GITHUB_RUN_ATTEMPT}" in commands
    assert "PR_INPUTS_JSON" in commands
    assert '"promotion_admission_ref"' not in commands
    # required 参数缺一即 argparse 失败，此处锁定 IQF 验签的完整接线；验签只靠仓内 keyring，无 secret。
    assert "secrets.QWQ_" not in commands and "SIGNING_KEY" not in commands
    for token in (
        "--expected-qualification-signer-identity",
        "--expected-alpha-signer-identity",
        "--expected-beta-signer-identity",
        "--expected-gamma-signer-identity",
        "--expected-tree-digest",
        "--expected-plan-digest",
    ):
        assert token in commands
    for forbidden in (
        "main-seal",
        "main-source-seal",
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
        "git merge-base --is-ancestor",
    ):
        assert forbidden not in commands


def test_main_push_consumes_exact_admission_before_issuing_seal_and_timing() -> None:
    _, workflow = _workflow()
    job = workflow["jobs"]["main_source_seal"]
    commands = _commands(job)

    assert job["if"] == "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    assert job["permissions"] == {
        "contents": "read", "packages": "write",
        "checks": "read", "pull-requests": "read",
    }
    checkout = next(step for step in job["steps"] if "uses" in step)
    assert checkout["with"]["ref"] == "${{ github.event.after }}"

    ordered = (
        'test "$(git rev-parse refs/remotes/origin/main)" = "$MAIN_SHA"',
        '/commits/${SOURCE_SHA}/check-runs',
        "promotion_evidence.py validate-hosted-handoff",
        "promotion_evidence.py materialize-oci",
        "git merge-base --is-ancestor",
        "promotion_evidence.py main-seal",
        "promotion_evidence.py publish-oci",
        "main-source-seal-readback.json",
        'cmp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    )
    positions = [commands.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert "oras resolve" not in commands
    assert '"promotion_admission_ref"' not in commands
    assert "$STORE/promotion-handoff" not in commands
    assert "HANDOFF_COUNT" in commands
    assert '--admission-oci-ref "$PROMOTION_ADMISSION_REF"' in commands
    assert "--hosted-handoff" in commands
    assert '--first-attempt-at "$PROMOTION_READY_AT"' in commands
    assert '--main-readback-at "$MAIN_READBACK_AT" --classification success' in commands
    readback = next(step for step in job["steps"] if step.get("id") == "readback")
    assert readback["env"]["TRUSTED_RECORDER_APP_SLUG"] == "github-actions"
    assert readback["env"]["TRUSTED_RECORDER_APP_ID"] == "15368"
    assert any(
        step.get("env", {}).get("PROMOTION_ADMISSION_REF")
        == "${{ steps.readback.outputs.promotion_admission_ref }}"
        for step in job["steps"]
    )
    assert job["outputs"] == {
        "source_sha": "${{ steps.readback.outputs.source_sha }}",
        "main_source_seal_ref": "${{ steps.seal.outputs.main_source_seal_ref }}",
        "main_source_seal_digest": "${{ steps.seal.outputs.main_source_seal_digest }}",
    }


def test_static_gate_rejects_missing_or_fabricated_post_merge_evidence() -> None:
    text, workflow = _workflow()
    assert _finding_details(text, workflow) == []

    missing_push = deepcopy(workflow)
    del missing_push[True]["push"]
    assert any("push" in detail for detail in _finding_details(text, missing_push))

    github_sha = text.replace("github.event.after", "github.sha", 1)
    assert any("github.sha" in detail for detail in _finding_details(github_sha, workflow))

    pr_body_exact_ref = deepcopy(workflow)
    input_step = next(
        step for step in pr_body_exact_ref["jobs"]["promotion_verify"]["steps"]
        if step.get("id") == "inputs"
    )
    input_step["run"] += '\nprint("promotion_admission_ref")'
    assert any("PR body" in detail for detail in _finding_details(text, pr_body_exact_ref))

    self_hosted_app = text + "\n# uses: actions/create-github-app-token@x\n"
    assert any("self-hosted App" in detail for detail in _finding_details(self_hosted_app, workflow))

    runner_in_job_env = deepcopy(workflow)
    runner_in_job_env["jobs"]["promotion_verify"]["env"]["EVIDENCE_ROOT"] = "${{ runner.temp }}/x"
    assert any("runner context" in detail for detail in _finding_details(text, runner_in_job_env))

    extra_backsync = deepcopy(workflow)
    extra_backsync["jobs"]["system_backsync"] = {"uses": "./.github/workflows/system-backsync.yml"}
    assert any("integration worktree fast-forward" in detail for detail in _finding_details(text, extra_backsync))

    fake_readback_workflow = deepcopy(workflow)
    seal_step = next(
        step
        for step in fake_readback_workflow["jobs"]["main_source_seal"]["steps"]
        if step.get("name") == "Issue, publish and read back MainSourceSeal"
    )
    seal_step["run"] = seal_step["run"].replace(
        "python3 quwoquan_ops/ci/promotion_evidence.py materialize-oci",
        'cp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json" #',
        1,
    )
    assert any("hosted MainSourceSeal readback" in detail for detail in _finding_details(text, fake_readback_workflow))

    mutable_lookup = deepcopy(workflow)
    mutable_lookup["jobs"]["main_source_seal"]["steps"][1]["run"] = "oras resolve repo:base-head"
    assert any("mutable" in detail for detail in _finding_details(text, mutable_lookup))

    local_store = deepcopy(workflow)
    local_store["jobs"]["main_source_seal"]["steps"][1]["run"] = "cat $STORE/promotion-handoff.json"
    assert any("local handoff" in detail for detail in _finding_details(text, local_store))

    premerge_seal = deepcopy(workflow)
    premerge_seal["jobs"]["promotion_verify"]["steps"].append(
        {"name": "invalid post merge", "run": "python3 promotion_evidence.py main-seal"}
    )
    assert any("pre-merge" in detail for detail in _finding_details(text, premerge_seal))

    foreign_identity = deepcopy(workflow)
    readback = next(step for step in foreign_identity["jobs"]["main_source_seal"]["steps"] if step.get("id") == "readback")
    readback["env"]["TRUSTED_RECORDER_APP_SLUG"] = "some-other-app"
    assert any("github-actions / 15368" in detail for detail in _finding_details(text, foreign_identity))

    early_digest = deepcopy(workflow)
    seal_step = next(
        step for step in early_digest["jobs"]["main_source_seal"]["steps"]
        if step.get("id") == "seal"
    )
    seal_step["run"] = seal_step["run"].replace(
        'cmp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        'true # hosted readback comparison removed',
    )
    assert any("post-readback" in detail for detail in _finding_details(text, early_digest))
