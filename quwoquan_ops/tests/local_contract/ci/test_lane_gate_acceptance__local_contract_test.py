"""Lane Gate 左移只扩充 canonical push readiness；不伪造 runtime 准出。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
"""
from __future__ import annotations

from unittest import mock

import pytest

from quwoquan_ops.ci import local_readiness_planner as planner
from quwoquan_ops.gate.delivery_gate_data_shard import sharded_test_files

BASE, HEAD = "a" * 40, "b" * 40


def _plan():
    return planner.build_impact_plan(["quwoquan_ops/cli/integration_run.py"], level="fast")


def test_push_includes_all_hosted_governance_and_four_exact_ops_shards():
    plan = planner.bind_source_health_plan(_plan(), mode="push", base=BASE, head=HEAD)
    checks = {check["id"]: check for check in plan["checks"]}
    for name in ("verify_git_branch_policy", "verify_github_supply_chain", "verify_github_artifact_lifecycle",
                 "verify_workflow_cli_arguments", "verify_entrypoint_script_paths", "verify_quality_policy"):
        assert "lane_gate:" + name in checks
    for scope in ("app", "service", "ops", "data"):
        assert "static:python_script_governance_" + scope in checks
    assert "lane_gate:feature-tree" in checks
    for shard in range(4):
        check = checks[f"lane_gate:ops-local-contract:{shard}"]
        assert check["command"][4:] == sharded_test_files(planner.ROOT, 4, shard, "ops", lane_gate=True)
        assert check["timeout_seconds"] == 900
    health = [check for check in checks.values() if "code-health" in check["resources"]]
    assert len(health) == 1 and "full" in health[0]["command"]
    assert BASE in health[0]["command"] and HEAD in health[0]["command"]
    assert not any(item["work"].startswith("quwoquan_ops/tests/local_contract") for item in plan["deferred"])
    commands = [tuple(check["command"]) for check in checks.values()]
    assert len(commands) == len(set(commands))
    covered = {path for shard in range(4) for path in checks[f"lane_gate:ops-local-contract:{shard}"]["command"][4:]}
    assert not any(check["id"] == "focused:python" and covered.intersection(check["command"][4:])
                   for check in checks.values())


def test_old_fast_receipt_check_identity_cannot_equal_push_lane_gate():
    plan = _plan()
    staged = planner.bind_source_health_plan(plan, mode="staged", base=BASE, head=HEAD)
    pushed = planner.bind_source_health_plan(plan, mode="push", base=BASE, head=HEAD)
    assert not any(check["id"].startswith("lane_gate:") for check in staged["checks"])
    assert planner._canonical_digest(staged["checks"]) != planner._canonical_digest(pushed["checks"])
    drift = planner.bind_source_health_plan(plan, mode="push", base=BASE, head="c" * 40)
    assert planner._canonical_digest(drift["checks"]) != planner._canonical_digest(pushed["checks"])


def test_ops_selector_empty_fails_closed():
    with mock.patch("quwoquan_ops.gate.delivery_gate_data_shard.sharded_test_files", return_value=[]):
        with pytest.raises(ValueError, match="empty"):
            planner.bind_source_health_plan(_plan(), mode="push", base=BASE, head=HEAD)


def test_ops_selection_is_bound_into_complete_commands():
    plan = _plan()
    original = planner.bind_source_health_plan(plan, mode="push", base=BASE, head=HEAD)
    def changed(root, count, shard, scope, lane_gate):
        return [*sharded_test_files(root, count, shard, scope, lane_gate=lane_gate), "quwoquan_ops/tests/local_contract/ci/test_new__local_contract_test.py"]
    with mock.patch("quwoquan_ops.gate.delivery_gate_data_shard.sharded_test_files", side_effect=changed):
        drift = planner.bind_source_health_plan(plan, mode="push", base=BASE, head=HEAD)
    assert planner._canonical_digest(original["checks"]) != planner._canonical_digest(drift["checks"])


@pytest.mark.parametrize("failure", [None, "lane_gate:ops-local-contract:3"])
def test_existing_runner_executes_required_once_then_reuses_exact_cache(tmp_path, monkeypatch, failure):
    from quwoquan_ops.tests.local_contract.ci import test_local_readiness__execution__local_contract_test as support
    from lib.local_readiness import core
    repo = tmp_path / "repo"
    repo.mkdir()
    support._init(repo)
    base = core._head_sha(repo)
    (repo / "source.txt").write_text("candidate\n")
    head = support._commit_all(repo, "candidate")
    updates = core.parse_push_updates(f"refs/heads/dev1.0 {head} refs/heads/dev1.0 {base}\n")
    state = tmp_path / "state"
    calls = []
    def execute(check, log_path, **kwargs):
        # 编排测试隔离外部 gate；不是四片和 runtime 实际执行证据。
        calls.append(check["id"])
        failed = check["id"] == failure
        return {"id": check["id"], "status": "FAIL" if failed else "PASS", "exit_code": 1 if failed else 0}
    monkeypatch.setattr(core, "_run_check", execute)
    plan = core.plan_readiness(paths=["source.txt"], level="fast", mode="push", repo_root=repo, push_updates=updates, state_root=state)
    receipt = core.run_readiness(plan, repo_root=repo, push_updates=updates, state_root=state)
    assert calls == [check["id"] for check in plan["checks"]]
    assert len(calls) == len(set(calls))
    assert receipt["status"] == ("FAIL" if failure else "PASS")
    if not failure:
        second = core.run_readiness(plan, repo_root=repo, push_updates=updates, state_root=state)
        assert second["cache_hit"] is True
        assert calls == [check["id"] for check in plan["checks"]]
    legacy = {**plan, "checks": [check for check in plan["checks"] if not check["id"].startswith("lane_gate:")]}
    with pytest.raises(core.LocalReadinessError, match="canonical planner"):
        core.run_readiness(legacy, repo_root=repo, push_updates=updates, state_root=state)


def test_exact_impact_boundary_rejects_incomplete_range_before_scan():
    with mock.patch("quwoquan_ops.ci.detect_ci_impacted_scopes.git_changed_files", return_value=["Makefile", "README.md"]):
        with pytest.raises(ValueError, match="exact candidate range"):
            planner.validate_lane_impact(base=BASE, head=HEAD, paths=["Makefile"])
