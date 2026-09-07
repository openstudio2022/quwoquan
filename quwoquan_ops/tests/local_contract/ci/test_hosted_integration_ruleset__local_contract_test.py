# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-005
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""dev1.0 ruleset 读回合同：04. Lane Gate 只在 hosted 真把它设为 required 时才算 fail-closed。"""
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from quwoquan_ops.ci.verify_hosted_integration_ruleset import (
    GITHUB_ACTIONS_APP_ID,
    HostedIntegrationRulesetError,
    main,
    verify_hosted_integration_ruleset,
)
from quwoquan_ops.gate.verify_git_branch_policy import load_policy

REPOSITORY = "example/quwoquan"
API = "quwoquan_ops.ci.verify_hosted_integration_ruleset._api_get"


def _pull_request_rule() -> dict:
    return {"type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": True,
        "required_review_thread_resolution": True,
        "require_extra_approval_for_unattributed_changes": True,
        "require_last_push_approval": False,
        "allowed_merge_methods": ["merge"],
    }}


def _ruleset(rule_id: int, branch: str, checks: list[str], *, with_pull_request: bool) -> dict:
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"}]
    if with_pull_request:
        rules.append(_pull_request_rule())
    rules.append({"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": True,
        "do_not_enforce_on_create": False,
        "required_status_checks": [
            {"context": check, "integration_id": GITHUB_ACTIONS_APP_ID}
            for check in checks
        ],
    }})
    return {
        "id": rule_id,
        "name": f"protect {branch}",
        "enforcement": "active",
        "bypass_actors": [],
        "updated_at": "2026-09-05T00:00:00Z",
        "conditions": {"ref_name": {"exclude": [], "include": [f"refs/heads/{branch}"]}},
        "rules": rules,
    }


def _rule_index(ruleset: dict, rule_type: str) -> int:
    return next(
        index for index, rule in enumerate(ruleset["rules"]) if rule["type"] == rule_type
    )


def _responses() -> dict[str, object]:
    policy = load_policy()
    integration_checks = [item.name for item in policy.required_integration_checks]
    promotion_checks = [item.name for item in policy.required_promotion_checks]
    return {
        "/rulesets": [{"id": 1}, {"id": 2}],
        # dev1.0：合入执行者是 integration fast-forward push，不得有 pull_request 规则。
        "/rulesets/1": _ruleset(1, "dev1.0", integration_checks, with_pull_request=False),
        # main：属 03. Delivery Gate 的读回范围，这里只用来证明本脚本不会误选它。
        "/rulesets/2": _ruleset(2, "main", promotion_checks, with_pull_request=True),
    }


def _dev_required_checks(value: dict) -> list:
    ruleset = value["/rulesets/1"]
    return ruleset["rules"][_rule_index(ruleset, "required_status_checks")]["parameters"]["required_status_checks"]


def _verify(responses: dict[str, object]) -> dict:
    with patch(
        API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path]),
    ) as api:
        receipt = verify_hosted_integration_ruleset(repository=REPOSITORY, token="token")
    # 只读 rulesets，不触碰 Actions / Environment / runner 等与 lane gate 无关的端点。
    assert {call.args[1] for call in api.call_args_list} == {"/rulesets", "/rulesets/1", "/rulesets/2"}
    return receipt


def test_lane_gate_is_proven_to_be_the_hosted_required_check() -> None:
    receipt = _verify(_responses())
    assert receipt["schema"] == "hosted-integration-ruleset-receipt"
    assert receipt["branch"] == "dev1.0"
    assert receipt["requiredIntegrationChecksEnforced"] is True
    assert [item["name"] for item in receipt["ruleset"]["requiredChecks"]] == ["04. Lane Gate"]
    assert receipt["ruleset"]["mergeExecutor"] == "integration_fast_forward_push"
    assert receipt["ruleset"]["bypassActorsObservable"] is True
    assert receipt["evidenceDigest"].startswith("sha256:")


@pytest.mark.parametrize("shape", ["absent", "null"])
def test_read_only_token_cannot_observe_bypass_actors_and_receipt_says_so(shape: str) -> None:
    # GitHub 只向对 ruleset 有 write 权限的调用者返回 bypass_actors；governance job 的只读
    # github.token 看到的是字段缺席或 null。不可见不等于已证明为空，收据必须如实标记。
    responses = _responses()
    if shape == "absent":
        responses["/rulesets/1"].pop("bypass_actors")
    else:
        responses["/rulesets/1"]["bypass_actors"] = None
    receipt = _verify(responses)
    assert receipt["requiredIntegrationChecksEnforced"] is True
    assert receipt["ruleset"]["bypassActorsObservable"] is False


@pytest.mark.parametrize(
    ("label", "mutate", "recovery"),
    [
        # 当前 hosted 现状（governance job 只读视角）：只有 deletion/non_fast_forward/creation，
        # 没有 required_status_checks；admin 视角另有一条 DeployKey bypass，但只读 token 看不到。
        ("current-hosted-state", lambda value: (
            value["/rulesets/1"].update(
                rules=[{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "creation"}],
            ),
            value["/rulesets/1"].pop("bypass_actors"),
        ), "configure the dev1.0 branch ruleset"),
        # admin 视角的同一 ruleset：bypass 可见且非空时也必须阻断。
        ("current-hosted-state-admin-view", lambda value: value["/rulesets/1"].update(
            bypass_actors=[{"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}],
        ), "no bypass actors"),
        ("missing-lane-gate", lambda value: _dev_required_checks(value).clear(), "configure the dev1.0 branch ruleset"),
        ("promotion-check-instead-of-lane-gate", lambda value: _dev_required_checks(value)[0].update(context="03. Delivery Gate"), "configure the dev1.0 branch ruleset"),
        ("unbound-check-producer", lambda value: _dev_required_checks(value)[0].pop("integration_id"), "configure the dev1.0 branch ruleset"),
        ("bypass-actor", lambda value: value["/rulesets/1"].update(bypass_actors=[{"actor_id": 1, "actor_type": "DeployKey"}]), "no bypass actors"),
        ("pull-request-rule", lambda value: value["/rulesets/1"]["rules"].insert(2, _pull_request_rule()), "no pull_request rule"),
        ("non-strict", lambda value: value["/rulesets/1"]["rules"][_rule_index(value["/rulesets/1"], "required_status_checks")]["parameters"].update(strict_required_status_checks_policy=False), "strict"),
        ("inactive", lambda value: value["/rulesets/1"].update(enforcement="evaluate"), "configure the dev1.0 branch ruleset"),
        ("two-dev-rulesets", lambda value: value["/rulesets/2"]["conditions"]["ref_name"]["include"].append("refs/heads/dev1.0"), "exactly one active ruleset"),
        ("no-dev-ruleset", lambda value: value["/rulesets/1"]["conditions"]["ref_name"]["include"].__setitem__(0, "refs/heads/other"), "exactly one active ruleset"),
    ],
)
def test_integration_ruleset_fails_closed_with_ruleset_recovery(label: str, mutate, recovery: str) -> None:
    responses = _responses()
    mutate(responses)
    with pytest.raises(HostedIntegrationRulesetError, match="OPS.BRANCH.AUTHORITY_UNAVAILABLE") as error:
        _verify(responses)
    assert recovery in str(error.value)


def test_requires_authenticated_token() -> None:
    with pytest.raises(HostedIntegrationRulesetError, match="terminal=blocked"):
        verify_hosted_integration_ruleset(repository=REPOSITORY, token="")


def test_cli_writes_receipt_and_blocks_on_drift(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    output = tmp_path / "receipt.json"
    github_output = tmp_path / "github_output"
    responses = _responses()
    with patch(API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path])):
        assert main([
            "--repository", REPOSITORY, "--output", str(output), "--github-output", str(github_output),
        ]) == 0
    assert '"schema": "hosted-integration-ruleset-receipt"' in output.read_text(encoding="utf-8")
    assert "decision=pass" in github_output.read_text(encoding="utf-8")

    _dev_required_checks(responses).clear()
    blocked = tmp_path / "blocked.json"
    with patch(API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path])):
        assert main(["--repository", REPOSITORY, "--output", str(blocked)]) == 2
    assert not blocked.exists()
