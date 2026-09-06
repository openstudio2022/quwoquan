"""lane/* -> dev1.0 的 hosted required check：04. Lane Gate 的结构合同。

spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-005
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/lane-gate.yml"
CHECKOUT = "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"
REQUIRED_CHECK_NAME = "04. Lane Gate"


def _load() -> tuple[str, dict]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_lane_gate_is_the_only_lane_pull_request_trigger_and_never_pushes() -> None:
    _, workflow = _load()
    triggers = workflow.get(True) or workflow.get("on")
    assert set(triggers) == {"pull_request"}
    assert triggers["pull_request"] == {"branches": ["dev1.0"]}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is True
    assert "pull_request.number" in workflow["concurrency"]["group"]
    for name, job in workflow["jobs"].items():
        assert job["runs-on"] == "ubuntu-latest", name
        assert job["timeout-minutes"] <= 25, name
        assert "secrets" not in job, name
        assert "environment" not in job, name


def test_lane_gate_jobs_and_summary_form_a_closed_fail_closed_dag() -> None:
    text, workflow = _load()
    jobs = workflow["jobs"]
    assert list(jobs) == [
        "governance", "impact_and_code_health", "ops_local_contract", "lane_gate_summary",
    ]
    summary = jobs["lane_gate_summary"]
    assert summary["name"] == REQUIRED_CHECK_NAME
    assert summary["if"] == "${{ always() }}"
    assert set(summary["needs"]) == {"governance", "impact_and_code_health", "ops_local_contract"}
    run = summary["steps"][0]["run"]
    for job_name in ("governance", "impact_and_code_health", "ops_local_contract"):
        assert f'expect_success "{job_name}"' in run
    assert 'expect_success_or_skipped' not in run
    assert "exit 1" in run


def test_lane_gate_checks_out_exact_pr_head_without_credentials() -> None:
    _, workflow = _load()
    for name, job in workflow["jobs"].items():
        if name == "lane_gate_summary":
            continue
        checkout = job["steps"][0]
        assert checkout["uses"] == CHECKOUT, name
        assert checkout["with"] == {
            "fetch-depth": 0,
            "ref": "${{ github.event.pull_request.head.sha }}",
            "persist-credentials": False,
        }, name


def test_lane_gate_runs_every_repo_wide_static_gate_and_feature_tree() -> None:
    _, workflow = _load()
    runs = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["governance"]["steps"]
    )
    for gate in (
        "quwoquan_ops/gate/verify_git_branch_policy.py",
        "quwoquan_ops/gate/verify_github_supply_chain.py",
        "quwoquan_ops/gate/verify_github_artifact_lifecycle.py",
        "quwoquan_ops/gate/verify_workflow_cli_arguments.py",
        "quwoquan_ops/gate/verify_entrypoint_script_paths.py",
        "quwoquan_ops/ci/verify_quality_policy.py",
        "quwoquan_ops/gate/verify_python_script_governance.py",
        "make verify-feature-tree",
    ):
        assert gate in runs, gate
    assert "--mode check" in runs
    assert 'test -z "$(git status --porcelain --untracked-files=all)"' in runs


def test_lane_gate_binds_code_health_to_the_exact_impact_plan() -> None:
    text, workflow = _load()
    steps = {
        step.get("id") or step.get("name") or step.get("uses"): step
        for step in workflow["jobs"]["impact_and_code_health"]["steps"]
    }
    detect = steps["detect"]["run"]
    assert "--execution-profile pr" in detect
    assert "--source-tree-digest" in detect
    assert "--validate-impact-plan" in detect
    assert "quwoquan_ops/ci/verify_ci_changed_boundary.py" in detect
    for flag in ("--expected-source-sha", "--expected-tree-digest", "--expected-plan-digest"):
        assert detect.count(flag) == 2, flag
    code_health = steps["Verify exact clean-candidate Code Health Delta"]
    assert code_health["env"]["EXPECTED_PATH_DIGEST"] == "${{ steps.detect.outputs.path_digest }}"
    assert code_health["env"]["EXPECTED_PLAN_DIGEST"] == "${{ steps.detect.outputs.plan_digest }}"
    assert "git diff --quiet && git diff --cached --quiet" in code_health["run"]
    assert "quwoquan_ops/ci/verify_code_health_delivery.py" in code_health["run"]
    assert '--summary-markdown "$RUNNER_TEMP/code-health-summary.md"' in code_health["run"]
    # Reviewer 在 PR 上直接看到 blocker/recovery/债务 delta；GATE_BLOCK 使上一步失败后本步仍执行。
    render = steps["Render Code Health summary for reviewers"]
    assert render["if"] == "${{ !cancelled() }}"
    assert 'cat "$RUNNER_TEMP/code-health-summary.md" >> "$GITHUB_STEP_SUMMARY"' in render["run"]
    upload = steps["Upload failed Code Health Delta diagnostic"]
    assert upload["if"] == "${{ failure() && !cancelled() }}"
    assert upload["with"]["retention-days"] == 3
    assert "actions/download-artifact@" not in text


def test_lane_gate_shards_ops_local_contract_through_the_canonical_selector() -> None:
    _, workflow = _load()
    job = workflow["jobs"]["ops_local_contract"]
    assert job["strategy"] == {"fail-fast": False, "matrix": {"shard_index": [0, 1, 2, 3]}}
    run = job["steps"][-1]["run"]
    assert "quwoquan_ops/gate/delivery_gate_data_shard.py" in run
    assert "--scope ops --lane-gate --total-shards 4 --shard-index" in run
    assert 'test "${#test_files[@]}" -gt 0' in run
    assert "-p no:cacheprovider" in run


def test_lane_gate_required_check_name_matches_branch_policy_declaration() -> None:
    policy = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(encoding="utf-8")
    )
    declared = policy["required_integration_checks"]
    assert declared == [
        {"name": REQUIRED_CHECK_NAME, "workflow": ".github/workflows/lane-gate.yml"},
    ]
    assert json.dumps(declared[0]["name"]) == json.dumps(
        _load()[1]["jobs"]["lane_gate_summary"]["name"]
    )
