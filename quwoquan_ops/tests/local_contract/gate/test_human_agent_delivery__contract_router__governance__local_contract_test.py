"""Human-Agent Delivery contract/router local contract.

Clause bindings stay next to the test that actually asserts each outcome.
"""
from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/human_agent_delivery.py"
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import lib.human_agent_delivery.contract as contract_module
import lib.human_agent_delivery.states as states_module
from lib.human_agent_delivery import (
    ContractError,
    advance_campaign,
    balanced_permutations,
    commercial_option_is_legal,
    legal_option_ids,
    load_contract,
    production_concurrency_policy,
    project_authorization_grant,
    project_role_card,
    project_role_interaction,
    route,
    stable_option_order,
    transition_inconclusive_outcome,
    validate_contract,
)

FIELDS = (
    "option_id", "neutral_label", "user_outcome", "business_outcome", "cost",
    "time_to_effect", "risk", "reversibility", "scope_change", "unknowns", "next_step",
)


def option(option_id: str) -> dict[str, object]:
    values: dict[str, object] = {field: f"{option_id}-{field}" for field in FIELDS}
    values["option_id"] = option_id
    values["unknowns"] = [f"{option_id}-unknown"]
    return values


def card_payload(*, decision_kind: str = "product_scope") -> dict[str, object]:
    return {
        "card_type": "choice",
        "decision_kind": decision_kind,
        "current_role": "product_owner",
        "question": "请选择当前职责内的业务方向",
        "known_facts": ["已知事实"],
        "unknowns": ["允许不知道"],
        "hard_constraints": ["不可豁免约束"],
        "options": [option("a"), option("b")],
        "consequences": {"will": "记录选择", "will_not": "不会自动生产发布"},
        "seed": "decision-unit-1",
    }


def decision_record(decision_kind: str) -> dict[str, object]:
    return {
        "decision_id": "decision-1",
        "decision_unit_id": "unit-1",
        "decision_kind": decision_kind,
        "selected_option_id": "go",
        "accountable_role": "product_owner",
        "actor_id": "actor-1",
        "actor_authenticated": True,
        "authority_source": "authority-provider-placeholder",
        "recorded_at": "2026-08-29T00:00:00Z",
        "expires_at": "2026-08-30T00:00:00Z",
        "scope": {"candidate": "sha256:abc"},
        "append_only": True,
        "consumed": False,
    }


def cli_projection(harness: str, payload: dict[str, object], command: str = "project-card") -> bytes:
    completed = subprocess.run(
        [sys.executable, "-B", str(CLI), command, "--harness", harness],
        cwd=ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.encode("utf-8")


def test_contract_is_versioned_closed_and_projection_only() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t9
    contract = load_contract()
    validate_contract(contract)
    assert len(contract["closed_sets"]["delivery_stage"]) == 15
    assert len(contract["namespaces"]["human_authority_role"]["values"]) == 11
    assert contract["namespaces"]["review_role"]["may_decide_or_authorize"] is False
    assert contract["schemas"]["authorization_grant"]["projection_only_until_authority_provider"] is True
    assert contract["schemas"]["authorization_grant"]["executable"] is False
    drift = deepcopy(contract)
    drift["schemas"]["authorization_grant"]["projection_only_until_authority_provider"] = False
    with pytest.raises(ContractError):
        validate_contract(drift)
    version_drift = deepcopy(contract)
    version_drift["schema_version"] += 1
    with pytest.raises(ContractError):
        validate_contract(version_drift)


def test_wrong_role_and_review_role_cannot_decide() -> None:
    wrong = route("product_definition", "product_scope", current_role="release_owner")
    review = route("product_definition", "product_scope", current_role="product")
    assert wrong["code"] == "HAD.WRONG_HUMAN_ROLE"
    assert review["code"] == "HAD.REVIEW_ROLE_FORBIDDEN"
    assert "grant" not in json.dumps(review).lower()


def test_hard_gate_removes_option_and_majority_cannot_restore_it() -> None:
    options = [{"option_id": "go"}, {"option_id": "limited_go"}, {"option_id": "hold"}]
    failed_gate = {"gate_id": "security", "option_ids": ["go", "limited_go"], "passed": False, "evidence_fresh": True}
    assert legal_option_ids(options, [failed_gate], majority_option_ids=["go", "go"]) == ("hold",)
    blocked = route(
        "commercial_readiness", "commercial_readiness", current_role="product_owner",
        hard_gates=[failed_gate],
    )
    assert blocked["code"] == "HAD.HARD_GATE_FAILED"


def test_independent_principal_requires_distinct_authenticated_actor() -> None:
    same_actor = {
        "domain_solution_architecture_owner": "actor-1",
        "security_privacy_legal_compliance_owner": "actor-1",
        "quality_owner": "actor-2",
        "environment_reliability_owner": "actor-3",
    }
    blocked = route(
        "solution_risk_design", "solution_risk",
        current_role="domain_solution_architecture_owner",
        risk_categories=["safety"], role_actor_ids=same_actor,
    )
    assert blocked["code"] == "HAD.SOD_FAILED"


def test_absence_timeout_identity_scope_and_stale_evidence_fail_closed() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t9
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t11
    cases = (
        ({"role_present": False}, "HAD.ROLE_ABSENT"),
        ({"timed_out": True}, "HAD.ROLE_TIMEOUT"),
        ({"actor_authenticated": False}, "HAD.IDENTITY_UNKNOWN"),
        ({"scope_valid": False}, "HAD.SCOPE_INVALID"),
        ({"evidence_fresh": False}, "HAD.EVIDENCE_EXPIRED"),
    )
    for kwargs, code in cases:
        result = route(
            "product_definition", "product_scope", current_role="product_owner", **kwargs
        )
        assert result["result"] == "typed_blocker"
        assert result["code"] == code
        assert result["terminal"] in {"pause", "hold", "escalate", "abort"}


def test_role_records_remain_separate_and_review_pass_is_only_evidence() -> None:
    contract = load_contract()
    assert contract["sod_policies"]["role-record-only"]["separate_role_records_required"] is True
    assert contract["namespaces"]["review_role"]["may_supply_evidence_only"] is True
    assert project_authorization_grant(decision_record("commercial_readiness")) is None


def test_options_are_symmetric_stable_and_order_does_not_change_eligibility() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t3
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t4
    options = [option("a"), option("b"), option("c")]
    gates = [{"gate_id": "g", "option_ids": ["b"], "passed": False, "evidence_fresh": True}]
    assert legal_option_ids(options, gates) == legal_option_ids(list(reversed(options)), gates)
    assert stable_option_order(options, "seed") == stable_option_order(options, "seed")
    permutations = balanced_permutations(options, "seed")
    assert len(permutations) == 3
    for position in range(3):
        assert {row[position]["option_id"] for row in permutations} == {"a", "b", "c"}
    card = project_role_card(**card_payload())
    assert card["selected_option_id"] is None
    assert all(tuple(projected) == FIELDS for projected in card["options"])


@pytest.mark.parametrize("decision_kind", [
    "product_scope", "experience_direction", "commercial_readiness", "outcome_acceptance",
])
def test_preference_decisions_reject_agent_recommendation(decision_kind: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t5
    payload = card_payload(decision_kind=decision_kind)
    payload["agent_recommendation"] = {"option_id": "a", "reason": "agent preference"}
    result = project_role_card(**payload)
    assert result["code"] == "HAD.RECOMMENDATION_FORBIDDEN"


def test_engineering_recommendation_requires_independent_inputs_sealed() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t6
    payload = card_payload(decision_kind="solution_risk")
    payload["agent_recommendation"] = {"option_id": "a", "reason": "客观支配关系"}
    payload["independent_inputs_sealed"] = False
    blocked = project_role_card(**payload)
    assert blocked["code"] == "HAD.RECOMMENDATION_FORBIDDEN"

    payload["independent_inputs_sealed"] = True
    projected = project_role_card(**payload)
    assert projected["agent_recommendation"] == payload["agent_recommendation"]


def test_all_card_types_expose_evidence_transfer_and_pause_recovery() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t7
    for card_type in ("choice", "authorization", "exception", "post_check"):
        payload = card_payload()
        payload["card_type"] = card_type
        card = project_role_card(**payload)
        assert card["actions"] == [
            "request_evidence", "transfer_to_correct_role", "pause_or_stop"
        ]
        assert card["unknowns"] == ["允许不知道"]


def test_card_types_preserve_authorization_exception_and_post_check_boundaries() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t8
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t9
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t10
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t11
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t12
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t13
    authorization = card_payload(decision_kind="delivery_authorization")
    authorization["card_type"] = "authorization"
    authorization["consequences"] = {
        "automatic_execution_boundary": "仅执行当前冻结范围",
        "excluded_actions": ["外部发布"],
        "budget": "不新增外部成本",
        "reconfirmation_required_for": ["外部动作", "范围或版本变化"],
        "revocation_consequence": "立即暂停且保留当前状态",
    }
    authorization_card = project_role_card(**authorization)
    assert authorization_card["consequences"] == authorization["consequences"]
    assert authorization_card["selected_option_id"] is None

    exception = card_payload(decision_kind="implementation_exception")
    exception["card_type"] = "exception"
    exception["consequences"] = {
        "safe_action": "保持暂停并保留当前状态",
        "safest_default": "不扩大授权范围",
        "timeout_consequence": "维持暂停，不产生隐式批准",
    }
    exception_card = project_role_card(**exception)
    assert exception_card["consequences"] == exception["consequences"]
    assert "不产生隐式批准" in exception_card["consequences"]["timeout_consequence"]
    assert exception_card["selected_option_id"] is None

    post_check = card_payload(decision_kind="quality_uat_acceptance")
    post_check["card_type"] = "post_check"
    post_check["current_role"] = "quality_owner"
    post_check["question"] = "是否接受质量责任域内的当前结果"
    post_check["consequences"] = {
        "accepts": "仅接受质量责任域结果",
        "does_not_accept": ["产品价值", "发布授权", "运行可靠性"],
    }
    post_check_card = project_role_card(**post_check)
    assert post_check_card["current_role"] == "quality_owner"
    assert post_check_card["consequences"]["accepts"] == "仅接受质量责任域结果"
    assert post_check_card["consequences"]["does_not_accept"] == [
        "产品价值", "发布授权", "运行可靠性",
    ]
    assert post_check_card["selected_option_id"] is None


def test_commercial_go_does_not_derive_production_grant_and_limited_go_cannot_bypass_gate() -> None:
    assert project_authorization_grant(decision_record("commercial_readiness")) is None
    hard_gate = {"gate_id": "slo", "option_ids": ["go", "limited_go"], "passed": False, "evidence_fresh": True}
    assert not commercial_option_is_legal(
        "limited_go", hard_gates=[hard_gate], limited_scope_reversible=True,
        policy_allows_limited_scope=True,
    )
    projection = project_authorization_grant(decision_record("production_campaign_approval"))
    assert projection is not None
    assert projection["projection_only_until_authority_provider"] is True
    assert projection["authenticated_authority"] is False
    assert projection["executable"] is False


def test_campaign_uses_one_approval_and_stage_technical_gates() -> None:
    approval = {"decision_id": "campaign-1"}
    next_step = advance_campaign(approval, current_stage="canary", technical_gate_passed=True)
    assert next_step == {"status": "executing", "approval_id": "campaign-1", "next_stage": "5"}
    paused = advance_campaign(approval, current_stage="5", technical_gate_passed=False)
    assert paused["status"] == "paused"
    changed = advance_campaign(
        approval, current_stage="5", technical_gate_passed=True, constraints_changed=True
    )
    assert changed["code"] == "HAD.CAMPAIGN_REAPPROVAL_REQUIRED"


@pytest.mark.parametrize(
    ("admission", "expected"),
    [
        (
            {"status": "admitted", "write_concurrency": 2},
            {"s4_admission": "admitted", "write_concurrency": 2},
        ),
        (
            {"status": "not_admitted", "write_concurrency": 1},
            {"s4_admission": "not_admitted", "write_concurrency": 1},
        ),
    ],
)
def test_s4_projection_follows_dynamic_objective_admission(
    admission: dict[str, object],
    expected: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-003.t4
    monkeypatch.setattr(states_module, "inspect_admission", lambda: admission)
    assert production_concurrency_policy() == expected


def test_channel_release_and_outcome_do_not_impersonate_each_other() -> None:
    assert route("channel_distribution", "channel_publication")["role"] == "operations_support_market_channel_owner"
    assert route("outcome_observation_acceptance", "outcome_acceptance")["role"] == "product_owner"
    assert project_authorization_grant(decision_record("outcome_acceptance")) is None


def test_outcome_extension_requires_prefrozen_policy_and_is_bounded() -> None:
    no_policy = transition_inconclusive_outcome(extension_policy=None, extensions_used=0)
    assert no_policy["observation_state"] == "clarify"
    policy = {
        "max_extensions": 1, "budget": "b", "sample": "s", "window": "w",
        "exit_conditions": ["enough data"],
    }
    extended = transition_inconclusive_outcome(extension_policy=policy, extensions_used=0)
    assert extended["transition"] == ["observing", "paused", "observing"]
    assert extended["extensions_used"] == 1
    exhausted = transition_inconclusive_outcome(extension_policy=policy, extensions_used=1)
    assert exhausted["observation_state"] == "escalated"


def test_cursor_and_codex_use_identical_json_projection() -> None:
    payload = card_payload()
    assert cli_projection("cursor", payload) == cli_projection("codex", payload)
    contract = load_contract()
    assert contract["harness_projection"]["canonical_cli"] == "quwoquan_ops/cli/human_agent_delivery.py"

INTERACTION_BASE_FIELDS = {
    "event_type", "delivery_stage", "audience_role", "what_happened",
    "user_or_business_impact", "decision_owner", "legal_actions",
    "safe_actions_taken", "next_acceptance", "next_acceptance_role", "audit_details",
}


def interaction_payload(event_type: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": event_type,
        "delivery_stage": "agent_led_implementation",
        "audience_role": "engineering_delivery_owner",
        "what_happened": "已完成当前授权范围内的工作。",
        "user_or_business_impact": "本地能力已更新，外部行为保持不变。",
        "decision_owner": None,
        "legal_actions": ["continue_authorized_work", "pause"],
        "safe_actions_taken": ["preserve_current_state", "keep_external_effects_disabled"],
        "next_acceptance": "由工程交付负责人检查当前范围与结果。",
        "next_acceptance_role": "engineering_delivery_owner",
        "audit_details": {"digest": "sha256:abc", "internal_command": "pytest"},
    }
    if event_type == "decision_request":
        payload["decision_owner"] = "engineering_delivery_owner"
        payload["legal_actions"] = ["choose_legal_option", "request_evidence", "pause"]
    if event_type == "exception_escalation":
        payload["decision_owner"] = "engineering_delivery_owner"
        payload["cannot_continue_reason"] = "授权范围发生变化，继续会越过当前决定。"
        payload["safest_default"] = "保持暂停并保留当前状态。"
    if event_type == "completion_report":
        payload["decision_owner"] = "engineering_delivery_owner"
        payload["proof"] = ["当前增量的本地契约测试通过。"]
        payload["limits"] = ["仅证明本地范围，不代表生产、渠道或业务结果。"]
    return payload


@pytest.mark.parametrize("event_type,extra_fields", [
    ("progress_update", set()),
    ("decision_request", set()),
    ("exception_escalation", {"cannot_continue_reason", "safest_default"}),
    ("completion_report", {"proof", "limits"}),
])
def test_role_interaction_four_event_envelopes_have_required_fields(
    event_type: str, extra_fields: set[str],
) -> None:
    payload = interaction_payload(event_type)
    result = project_role_interaction(payload, harness="cursor")
    assert result == payload
    assert set(result) == INTERACTION_BASE_FIELDS | extra_fields
    assert result["decision_owner"] is None or result["decision_owner"] == "engineering_delivery_owner"


def test_exception_and_completion_event_specific_fields_are_required() -> None:
    exception = interaction_payload("exception_escalation")
    exception.pop("safest_default")
    assert project_role_interaction(exception, harness="cursor")["code"] == "HAD.INTERACTION_FIELD_INVALID"
    completion = interaction_payload("completion_report")
    completion.pop("limits")
    assert project_role_interaction(completion, harness="cursor")["code"] == "HAD.INTERACTION_FIELD_INVALID"


@pytest.mark.parametrize("term", [
    "digest", "CAS", "GATE_BLOCK", "typed blocker", "fingerprint", "owner manifest",
    "receipt", "readback", "exact-byte", "SHA256:abc", "/Users/name/private/file",
    "pytest -q", "Cursor",
])
def test_internal_terms_are_only_allowed_inside_audit_details(term: str) -> None:
    leaked = interaction_payload("progress_update")
    leaked["what_happened"] = f"内部细节 {term} 已变化。"
    blocked = project_role_interaction(leaked, harness="cursor")
    assert blocked["code"] == "HAD.INTERACTION_TERM_LEAK", (term, blocked)
    audit_only = interaction_payload("progress_update")
    audit_only["audit_details"] = {"machine_detail": term}
    assert project_role_interaction(audit_only, harness="cursor") == audit_only


def test_project_interaction_cursor_codex_bytes_match_and_unknown_harness_fails() -> None:
    payload = interaction_payload("completion_report")
    assert cli_projection("cursor", payload, "project-interaction") == cli_projection(
        "codex", payload, "project-interaction"
    )
    completed = subprocess.run(
        [sys.executable, "-B", str(CLI), "project-interaction", "--harness", "other"],
        cwd=ROOT, input=json.dumps(payload, ensure_ascii=False), text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["code"] == "HAD.UNKNOWN_HARNESS"


def test_completion_report_cannot_accept_another_role_domain() -> None:
    payload = interaction_payload("completion_report")
    payload["decision_owner"] = "product_owner"
    blocked = project_role_interaction(payload, harness="cursor")
    assert blocked["code"] == "HAD.INTERACTION_ROLE_OVERRUN"
    payload = interaction_payload("completion_report")
    payload["next_acceptance_role"] = "release_owner"
    blocked = project_role_interaction(payload, harness="cursor")
    assert blocked["code"] == "HAD.INTERACTION_ROLE_OVERRUN"


def _temporary_workflow_contract() -> dict[str, object]:
    contract = load_contract()
    workflow = contract["workflow_interaction_binding"]
    sample_binding = deepcopy(next(iter(workflow["bindings"].values())))
    workflow["bindings"] = {"dynamic-skill": sample_binding}
    return contract


def _temporary_contract_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    contract_path = repo_root / "quwoquan_ops/policies/human_agent_delivery_contract.yaml"
    contract_path.parent.mkdir(parents=True)
    monkeypatch.setattr(contract_module, "CONTRACT_PATH", contract_path)
    return repo_root


def _write_workflow_skill(skill_root: Path, text: str | None = None) -> Path:
    skill_dir = skill_root / "dynamic-skill"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        text
        or """---
name: dynamic-skill
description: Dynamically discovered workflow.
metadata:
  kind: workflow
---

# Dynamic workflow
""",
        encoding="utf-8",
    )
    return skill_path


def _assert_skill_discovery_fails_before_binding_closure(
    contract: dict[str, object],
    match: str,
    *,
    code: str | None = None,
    causal_category: str | None = None,
) -> ContractError:
    with pytest.raises(ContractError, match=match) as failure:
        validate_contract(contract)
    assert "动态覆盖" not in str(failure.value)
    if code is not None:
        assert failure.value.code == code
    if causal_category is not None:
        assert failure.value.causal_category == causal_category
    return failure.value


@pytest.mark.parametrize("symlink_level", ["agents", "skills", "child", "skill-file"])
def test_workflow_skill_discovery_rejects_symlink_boundaries(
    symlink_level: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    agents_root = repo_root / ".agents"
    external_root = tmp_path / "external"
    if symlink_level == "agents":
        _write_workflow_skill(external_root / "skills")
        agents_root.symlink_to(external_root, target_is_directory=True)
        expected = r"\.agents.*不得为 symlink"
    elif symlink_level == "skills":
        agents_root.mkdir(parents=True)
        _write_workflow_skill(external_root)
        (agents_root / "skills").symlink_to(external_root, target_is_directory=True)
        expected = r"\.agents/skills.*不得为 symlink"
    elif symlink_level == "child":
        skills_root = agents_root / "skills"
        skills_root.mkdir(parents=True)
        _write_workflow_skill(external_root)
        (skills_root / "dynamic-skill").symlink_to(
            external_root / "dynamic-skill", target_is_directory=True,
        )
        expected = r"dynamic-skill.*不得为 symlink"
    else:
        skill_dir = agents_root / "skills/dynamic-skill"
        skill_dir.mkdir(parents=True)
        external_skill = external_root / "SKILL.md"
        external_skill.parent.mkdir(parents=True)
        external_skill.write_text("untrusted", encoding="utf-8")
        (skill_dir / "SKILL.md").symlink_to(external_skill)
        expected = r"SKILL\.md.*不得为 symlink"
    _assert_skill_discovery_fails_before_binding_closure(
        contract,
        expected,
        code="HAD.SKILL_DISCOVERY_SYMLINK_FORBIDDEN",
        causal_category="symlink",
    )


def test_workflow_skill_discovery_rejects_noncanonical_skill_root() -> None:
    contract = load_contract()
    contract["workflow_interaction_binding"]["skill_root"] = ".agents/skills/../skills"
    _assert_skill_discovery_fails_before_binding_closure(contract, "必须精确为")


def test_workflow_skill_discovery_rejects_non_directory_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    skills_root = repo_root / ".agents/skills"
    skills_root.mkdir(parents=True)
    (skills_root / "dynamic-skill").write_text("not a directory", encoding="utf-8")
    _assert_skill_discovery_fails_before_binding_closure(
        contract,
        r"dynamic-skill.*non-symlink directory",
        code="HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
        causal_category="path_type",
    )


def test_workflow_skill_discovery_rejects_direct_child_without_skill_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    (repo_root / ".agents/skills/dynamic-skill").mkdir(parents=True)
    _assert_skill_discovery_fails_before_binding_closure(
        contract,
        r"SKILL\.md.*regular non-symlink file",
        code="HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
        causal_category="path_type",
    )


@pytest.mark.parametrize(
    ("raised", "code", "causal_category"),
    [
        (
            PermissionError(errno.EACCES, "denied"),
            "HAD.SKILL_DISCOVERY_PERMISSION_DENIED",
            "permission",
        ),
        (
            OSError(errno.EIO, "io failure"),
            "HAD.SKILL_DISCOVERY_IO_FAILED",
            "io",
        ),
    ],
)
def test_workflow_skill_discovery_preserves_permission_and_io_categories(
    raised: OSError,
    code: str,
    causal_category: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    _write_workflow_skill(repo_root / ".agents/skills")

    def fail_listdir(_descriptor: int) -> list[str]:
        raise raised

    monkeypatch.setattr(contract_module.os, "listdir", fail_listdir)
    failure = _assert_skill_discovery_fails_before_binding_closure(
        contract,
        "canonical workflow Skill root",
        code=code,
        causal_category=causal_category,
    )
    assert failure.detail


def test_workflow_skill_discovery_rejects_direct_child_collection_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    _write_workflow_skill(repo_root / ".agents/skills")
    original_listdir = contract_module.os.listdir
    calls = 0

    def drifting_listdir(descriptor: int) -> list[str]:
        nonlocal calls
        calls += 1
        current = list(original_listdir(descriptor))
        if calls == 2:
            current.append("concurrent-added-skill")
        return current

    monkeypatch.setattr(contract_module.os, "listdir", drifting_listdir)
    _assert_skill_discovery_fails_before_binding_closure(
        contract,
        "direct-child 集合",
        code="HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
        causal_category="concurrent_drift",
    )


def test_workflow_skill_discovery_rejects_opened_skill_identity_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    skill_path = _write_workflow_skill(repo_root / ".agents/skills")
    original_read = contract_module._secure_read_regular_file
    replaced = False

    def replacing_read(
        parent_fd: int,
        name: str,
        *,
        label: str,
    ) -> tuple[str, tuple[int, int, int, int, int, int, int]]:
        nonlocal replaced
        result = original_read(parent_fd, name, label=label)
        if not replaced:
            replaced = True
            replacement = skill_path.with_name("SKILL.md.replacement")
            replacement.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
            os.replace(replacement, skill_path)
        return result

    monkeypatch.setattr(contract_module, "_secure_read_regular_file", replacing_read)
    _assert_skill_discovery_fails_before_binding_closure(
        contract,
        "身份替换",
        code="HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
        causal_category="concurrent_drift",
    )


@pytest.mark.parametrize(("skill_text", "expected"), [
    ("# no frontmatter\n", "缺合法 frontmatter"),
    ("---\nname: [\n---\n", "frontmatter YAML 非法"),
    ("---\n- not\n- a-mapping\n---\n", "frontmatter 非 mapping"),
    (
        "---\nname: dynamic-skill\ndescription: valid\n---\n",
        "metadata 非 mapping",
    ),
    (
        "---\nname: dynamic-skill\ndescription: valid\nmetadata: []\n---\n",
        "metadata 非 mapping",
    ),
    (
        "---\nname: dynamic-skill\ndescription: valid\nmetadata: {}\n---\n",
        "metadata.kind 必须为 workflow",
    ),
    (
        "---\nname: dynamic-skill\ndescription: valid\nmetadata:\n  kind: reference\n---\n",
        "metadata.kind 必须为 workflow",
    ),
    (
        "---\nname: drift\ndescription: valid\nmetadata:\n  kind: workflow\n---\n",
        "name 与目录不一致",
    ),
    (
        "---\nname: dynamic-skill\nmetadata:\n  kind: workflow\n---\n",
        "description 必须为非空字符串",
    ),
])
def test_workflow_skill_discovery_rejects_invalid_frontmatter(
    skill_text: str, expected: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    _write_workflow_skill(repo_root / ".agents/skills", skill_text)
    _assert_skill_discovery_fails_before_binding_closure(contract, expected)


def test_workflow_skill_discovery_accepts_valid_dynamic_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    contract = _temporary_workflow_contract()
    repo_root = _temporary_contract_repo(monkeypatch, tmp_path)
    _write_workflow_skill(repo_root / ".agents/skills")
    validate_contract(contract)


def test_dynamic_workflow_skills_bind_pre_during_post_without_static_inventory() -> None:
    contract = load_contract()
    workflow = contract["workflow_interaction_binding"]
    skill_root = ROOT / workflow["skill_root"]
    workflow_skills = {}
    for skill_path in sorted(skill_root.glob("*/SKILL.md")):
        frontmatter = yaml.safe_load(skill_path.read_text(encoding="utf-8").split("---\n", 2)[1])
        if (frontmatter.get("metadata") or {}).get("kind") == "workflow":
            workflow_skills[skill_path.parent.name] = skill_path
    assert set(workflow) == {
        "canonical_projector", "skill_root", "required_phases",
        "required_binding_fields", "dynamic_audience_role", "bindings",
    }
    assert set(workflow["bindings"]) == set(workflow_skills)
    schema_fields = set(contract["schemas"]["role_interaction_envelope"]["required_fields"])
    for skill, skill_path in workflow_skills.items():
        bindings = workflow["bindings"][skill]
        assert [item["phase"] for item in bindings] == ["PRE", "DURING", "POST"]
        skill_text = skill_path.read_text(encoding="utf-8")
        headings = [line[3:] for line in skill_text.splitlines() if line.startswith("## ")]
        assert headings == [
            "触发与输入", "执行", "完成证据", "失败与停止", "条件性交接",
        ]
        binding_ref = f"#workflow_interaction_binding.bindings.{skill}"
        assert binding_ref in skill_text
        assert "canonical projector" in skill_text
        assert not schema_fields.issubset(set(skill_text.split()))

    missing = deepcopy(contract)
    missing["workflow_interaction_binding"]["bindings"].pop(next(iter(workflow_skills)))
    with pytest.raises(ContractError, match="动态覆盖"):
        validate_contract(missing)
    extra = deepcopy(contract)
    extra["workflow_interaction_binding"]["bindings"]["hard-coded-shadow"] = deepcopy(
        next(iter(extra["workflow_interaction_binding"]["bindings"].values()))
    )
    with pytest.raises(ContractError, match="动态覆盖"):
        validate_contract(extra)

