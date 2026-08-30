"""Human-Agent Delivery contract/router local contract.

Clause bindings stay next to the test that actually asserts each outcome.
"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/human_agent_delivery.py"
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.human_agent_delivery import (  # noqa: E402
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


def test_s4_not_admitted_and_write_concurrency_is_one() -> None:
    assert production_concurrency_policy() == {"s4_admission": "not_admitted", "write_concurrency": 1}


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


def test_all_twelve_skills_bind_pre_during_post_without_copying_schema() -> None:
    contract = load_contract()
    workflow = contract["workflow_interaction_binding"]
    assert workflow["natural_language_and_explicit_skill_same_track"] is True
    assert len(workflow["required_skills"]) == len(workflow["bindings"]) == 12
    schema_fields = set(contract["schemas"]["role_interaction_envelope"]["required_fields"])
    for skill in workflow["required_skills"]:
        bindings = workflow["bindings"][skill]
        assert [item["phase"] for item in bindings] == ["PRE", "DURING", "POST"]
        skill_text = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        headings = [line[3:] for line in skill_text.splitlines() if line.startswith("## ")]
        assert headings == [
            "触发与输入", "执行", "完成证据", "失败与停止", "条件性交接",
        ]
        binding_ref = f"#workflow_interaction_binding.{skill}"
        assert binding_ref in skill_text
        assert "canonical projector" in skill_text
        assert not schema_fields.issubset(set(skill_text.split()))

