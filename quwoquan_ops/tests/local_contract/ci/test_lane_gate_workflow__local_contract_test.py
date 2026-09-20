"""旧 Lane PR workflow 退役为只读手动保护读回；accept 本地检查保持完整。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/lane-gate.yml"


def test_dev_readback_is_manual_read_only_and_not_a_lane_required_check():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    assert set(workflow.get(True) or workflow.get("on")) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert list(workflow["jobs"]) == ["readback"]
    job = workflow["jobs"]["readback"]
    assert job["timeout-minutes"] == 5
    assert "environment" not in job and "secrets" not in job
    assert job["steps"][0]["with"]["persist-credentials"] is False
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "verify_hosted_integration_ruleset.py" in runs
    assert "Hosted Alpha enforcement is not implemented" in runs
    for retired in ("pytest", "verify_incremental_code_health", "verify_code_health_delivery", "verify-feature-tree",
                    "delivery_gate_data_shard", "git push", "stackctl"):
        assert retired not in runs
    assert workflow["name"] != "04. Lane Gate"


def test_local_accept_checks_remain_independent_of_hosted_readback():
    contract = yaml.safe_load((ROOT / "quwoquan_ops/policies/local_readiness_contract.yaml").read_text())["lane_gate"]
    assert contract["required_groups"] == ["governance", "impact_boundary", "code_health_full", "ops_local_contract"]
    assert len(contract["governance_scripts"]) == 6
    assert contract["python_governance_scopes"] == ["app", "service", "ops", "data"]
    assert contract["feature_tree_command"] == ["make", "verify-feature-tree"]
    assert contract["ops_shards"] == 4
    assert contract["legacy_fast_receipt"] == "rejected"
    assert contract["hosted_alpha_enforcement"] == "open_track_not_blocking_local_dev"
    from quwoquan_ops.ci.local_readiness_planner import build_impact_plan, bind_source_health_plan
    plan = bind_source_health_plan(build_impact_plan(["quwoquan_ops/cli/integration_run.py"], level="fast"),
                                  mode="push", base="a" * 40, head="b" * 40)
    assert not any("verify_hosted_integration_ruleset.py" in argument for check in plan["checks"] for argument in check["command"])
    # 四片仍由 generator 产出供 hosted 消费，但不进入 source-admitted 冻结闭集（见 REQ-002 与
    # test_lane_gate_acceptance 的闭集断言）。
    from quwoquan_ops.ci.local_readiness_planner import _lane_gate_checks
    generated = _lane_gate_checks(base="a" * 40, head="b" * 40, paths=["quwoquan_ops/cli/integration_run.py"])
    assert len([check for check in generated if check["id"].startswith("lane_gate:ops-local-contract:")]) == 4
    assert not any(check["id"].startswith("lane_gate:ops-local-contract:") for check in plan["checks"])


def test_branch_policy_retires_only_dev_hosted_required_checks():
    policy = yaml.safe_load((ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text())
    assert policy["required_integration_checks"] == []
    assert policy["required_promotion_checks"] == [{"name": "03. Delivery Gate", "workflow": ".github/workflows/delivery-gate.yml"}]
    assert policy["allowed_pull_request_edges"] == [{"head": "dev1.0", "base": "main"}]
