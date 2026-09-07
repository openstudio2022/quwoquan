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
RULESETS = "/rulesets?per_page=100"
EXPECTED_CALLS = {"", RULESETS, "/rulesets/1", "/rulesets/2"}


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
        "target": "branch",
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
        "": {"default_branch": "main"},
        RULESETS: [{"id": 1}, {"id": 2}],
        # dev1.0：合入执行者是 integration fast-forward push，不得有 pull_request 规则。
        "/rulesets/1": _ruleset(1, "dev1.0", integration_checks, with_pull_request=False),
        # main：属 03. Delivery Gate 的读回范围，这里只用来证明本脚本不会误选它。
        "/rulesets/2": _ruleset(2, "main", promotion_checks, with_pull_request=True),
    }


def _dev_required_checks(value: dict) -> list:
    ruleset = value["/rulesets/1"]
    return ruleset["rules"][_rule_index(ruleset, "required_status_checks")]["parameters"]["required_status_checks"]


def _add_ruleset(value: dict, ruleset: dict) -> None:
    value[RULESETS].append({"id": ruleset["id"]})
    value[f"/rulesets/{ruleset['id']}"] = ruleset


def _verify(responses: dict[str, object], *, expected_calls: set[str] = EXPECTED_CALLS, **kwargs) -> dict:
    with patch(
        API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path]),
    ) as api:
        receipt = verify_hosted_integration_ruleset(repository=REPOSITORY, token="token", **kwargs)
    # 只读 repository 元数据与 rulesets，不触碰 Actions / Environment / runner 等与 lane gate 无关的端点。
    assert {call.args[1] for call in api.call_args_list} == expected_calls
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


def test_admin_readback_requires_observable_bypass_actors() -> None:
    # admin 侧读回负责证明 bypass 为空：字段不可见即阻断，可见为空才通过。
    responses = _responses()
    assert _verify(responses, require_bypass_observable=True)["ruleset"]["bypassActorsObservable"] is True
    responses["/rulesets/1"].pop("bypass_actors")
    with pytest.raises(HostedIntegrationRulesetError, match="bypass_actors is not observable"):
        _verify(responses, require_bypass_observable=True)


def test_non_active_or_non_branch_rulesets_do_not_count_as_applicable() -> None:
    # 管理员留下的 disabled/evaluate 副本或 tag ruleset 不构成「第二条适用 ruleset」。
    responses = _responses()
    disabled = _ruleset(3, "dev1.0", ["04. Lane Gate"], with_pull_request=True)
    disabled["enforcement"] = "disabled"
    _add_ruleset(responses, disabled)
    tag_ruleset = _ruleset(4, "dev1.0", ["04. Lane Gate"], with_pull_request=True)
    tag_ruleset["target"] = "tag"
    _add_ruleset(responses, tag_ruleset)
    receipt = _verify(responses, expected_calls=EXPECTED_CALLS | {"/rulesets/3", "/rulesets/4"})
    assert receipt["ruleset"]["id"] == 1


def test_exclude_pattern_removes_wildcard_ruleset_from_dev_applicability() -> None:
    responses = _responses()
    wildcard = _ruleset(3, "other", ["04. Lane Gate"], with_pull_request=True)
    wildcard["conditions"] = {"ref_name": {"include": ["refs/heads/*"], "exclude": ["refs/heads/dev1.0"]}}
    _add_ruleset(responses, wildcard)
    assert _verify(responses, expected_calls=EXPECTED_CALLS | {"/rulesets/3"})["ruleset"]["id"] == 1


@pytest.mark.parametrize(
    ("label", "include"),
    [
        ("tilde-all", ["~ALL"]),
        ("fnmatch", ["refs/heads/dev*"]),
        ("default-branch", ["~DEFAULT_BRANCH"]),
    ],
)
def test_second_ruleset_matching_dev_by_github_pattern_semantics_is_not_missed(label: str, include: list[str]) -> None:
    # 第二条以 ~ALL / fnmatch / ~DEFAULT_BRANCH 命中 dev1.0 并带 pull_request 规则的 ruleset
    # 会封死 integration fast-forward 通道；字面 include 比对会漏掉它。
    responses = _responses()
    if label == "default-branch":
        responses[""] = {"default_branch": "dev1.0"}
    shadow = _ruleset(3, "shadow", ["04. Lane Gate"], with_pull_request=True)
    shadow["conditions"] = {"ref_name": {"include": include, "exclude": []}}
    _add_ruleset(responses, shadow)
    with pytest.raises(HostedIntegrationRulesetError, match="exactly one applicable active branch ruleset \\(found 2\\)"):
        _verify(responses, expected_calls=EXPECTED_CALLS | {"/rulesets/3"})


@pytest.mark.parametrize(
    ("label", "mutate", "detail"),
    [
        # 当前 hosted 现状（governance job 只读视角，ruleset 20969668 配置前）：只有
        # deletion/non_fast_forward/creation，没有 required_status_checks；bypass 字段不可见。
        ("hosted-state-before-2026-09-07-readonly-view", lambda value: (
            value["/rulesets/1"].update(
                rules=[{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "creation"}],
            ),
            value["/rulesets/1"].pop("bypass_actors"),
        ), "must contain one 'required_status_checks' rule"),
        # 同一 ruleset 的 admin 视角：DeployKey/always bypass 可见且非空，必须阻断。
        ("hosted-state-before-2026-09-07-admin-view", lambda value: value["/rulesets/1"].update(
            bypass_actors=[{"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}],
        ), "must have no bypass actors"),
        ("missing-lane-gate", lambda value: _dev_required_checks(value).clear(), "required checks must be exactly"),
        ("promotion-check-instead-of-lane-gate", lambda value: _dev_required_checks(value)[0].update(context="03. Delivery Gate"), "required checks must be exactly"),
        ("unbound-check-producer", lambda value: _dev_required_checks(value)[0].pop("integration_id"), "required checks must be exactly"),
        ("bypass-actor", lambda value: value["/rulesets/1"].update(bypass_actors=[{"actor_id": 1, "actor_type": "DeployKey"}]), "must have no bypass actors"),
        ("pull-request-rule", lambda value: value["/rulesets/1"]["rules"].insert(2, _pull_request_rule()), "must not require pull requests"),
        ("non-strict", lambda value: value["/rulesets/1"]["rules"][_rule_index(value["/rulesets/1"], "required_status_checks")]["parameters"].update(strict_required_status_checks_policy=False), "required-check protection is incomplete"),
        ("enforce-on-create-off", lambda value: value["/rulesets/1"]["rules"][_rule_index(value["/rulesets/1"], "required_status_checks")]["parameters"].update(do_not_enforce_on_create=True), "required-check protection is incomplete"),
        ("missing-non-fast-forward", lambda value: value["/rulesets/1"]["rules"].pop(_rule_index(value["/rulesets/1"], "non_fast_forward")), "must contain one 'non_fast_forward' rule"),
        ("inactive", lambda value: value["/rulesets/1"].update(enforcement="evaluate"), "exactly one applicable active branch ruleset (found 0)"),
        ("two-dev-rulesets", lambda value: value["/rulesets/2"]["conditions"]["ref_name"]["include"].append("refs/heads/dev1.0"), "exactly one applicable active branch ruleset (found 2)"),
        ("no-dev-ruleset", lambda value: value["/rulesets/1"]["conditions"]["ref_name"]["include"].__setitem__(0, "refs/heads/other"), "exactly one applicable active branch ruleset (found 0)"),
    ],
)
def test_integration_ruleset_fails_closed_with_specific_detail(label: str, mutate, detail: str) -> None:
    responses = _responses()
    mutate(responses)
    with pytest.raises(HostedIntegrationRulesetError, match="OPS.BRANCH.AUTHORITY_UNAVAILABLE") as error:
        _verify(responses)
    message = str(error.value)
    assert detail in message, message
    assert "recovery=configure the dev1.0 branch ruleset" in message


def test_requires_authenticated_token() -> None:
    with pytest.raises(HostedIntegrationRulesetError, match="terminal=blocked"):
        verify_hosted_integration_ruleset(repository=REPOSITORY, token="")


def test_cli_writes_receipt_prints_observability_and_blocks_with_exit_2(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    output = tmp_path / "receipt.json"
    responses = _responses()
    responses["/rulesets/1"].pop("bypass_actors")
    with patch(API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path])):
        assert main(["--repository", REPOSITORY, "--output", str(output)]) == 0
    assert '"schema": "hosted-integration-ruleset-receipt"' in output.read_text(encoding="utf-8")
    assert "bypassActorsObservable=False" in capsys.readouterr().out

    blocked = tmp_path / "blocked.json"
    with patch(API, side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path])):
        assert main(["--repository", REPOSITORY, "--output", str(blocked), "--require-bypass-observable"]) == 2
    assert not blocked.exists()
    assert "bypass_actors is not observable" in capsys.readouterr().err
