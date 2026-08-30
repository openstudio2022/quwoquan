"""Human-Agent Delivery canonical machine contract loader and validator."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "policies/human_agent_delivery_contract.yaml"


class ContractError(ValueError):
    """Fail-closed contract validation error."""

    code = "HAD.CONTRACT_INVALID"


@lru_cache(maxsize=1)
def _load_contract_cached() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_contract(value)
    return value


def load_contract() -> dict[str, Any]:
    """Return a validated copy so callers cannot mutate the process cache."""
    return deepcopy(_load_contract_cached())


def _string_list(value: object, label: str, *, count: int | None = None) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} 必须为非空字符串闭集")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} 包含重复值")
    if count is not None and len(value) != count:
        raise ContractError(f"{label} 必须包含 {count} 项")
    return value


def validate_contract(value: object) -> None:
    if not isinstance(value, dict):
        raise ContractError("contract 必须为映射")
    if value.get("schema_id") != "human-agent-delivery-contract" or value.get("schema_version") != 2:
        raise ContractError("contract identity/version 非法")
    namespaces = value.get("namespaces")
    closed = value.get("closed_sets")
    if not isinstance(namespaces, dict) or not isinstance(closed, dict):
        raise ContractError("缺 namespaces 或 closed_sets")
    human = namespaces.get("human_authority_role")
    review = namespaces.get("review_role")
    if not isinstance(human, dict) or not isinstance(review, dict):
        raise ContractError("HumanAuthorityRole 与 ReviewRole namespace 必须物理分离")
    human_values = _string_list(human.get("values"), "HumanAuthorityRole", count=11)
    review_values = _string_list(review.get("values"), "ReviewRole")
    if set(human_values) & set(review_values) or human.get("prefix") == review.get("prefix"):
        raise ContractError("HumanAuthorityRole 与 ReviewRole namespace 冲突")
    if review.get("may_decide_or_authorize") is not False:
        raise ContractError("ReviewRole 不得决定或授权")
    stages = _string_list(closed.get("delivery_stage"), "DeliveryStage", count=15)
    kinds = _string_list(closed.get("decision_kind"), "DecisionKind")
    event_types = _string_list(
        closed.get("role_interaction_event_type"), "RoleInteractionEventType", count=4
    )
    if event_types != [
        "progress_update", "decision_request", "exception_escalation", "completion_report"
    ]:
        raise ContractError("RoleInteractionEventType 闭集漂移")
    interaction_roles = _string_list(
        closed.get("role_interaction_audience_role"), "RoleInteractionAudienceRole", count=11
    )
    if interaction_roles != human_values:
        raise ContractError("角色交互 audience_role 必须复用 HumanAuthorityRole 闭集")
    _string_list(closed.get("role_interaction_legal_action"), "RoleInteractionLegalAction")
    _string_list(closed.get("role_interaction_safe_action"), "RoleInteractionSafeAction")
    responsibilities = _string_list(
        closed.get("decision_unit_responsibility"), "DecisionUnit responsibility", count=7
    )
    schemas = value.get("schemas")
    if not isinstance(schemas, dict):
        raise ContractError("缺 schemas")
    decision_unit = schemas.get("decision_unit")
    if not isinstance(decision_unit, dict) or not set(responsibilities).issubset(
        set(_string_list(decision_unit.get("required_fields"), "DecisionUnit.required_fields"))
    ):
        raise ContractError("DecisionUnit 未闭合七责字段")
    option = schemas.get("decision_option")
    expected_symmetric = {
        "option_id", "neutral_label", "user_outcome", "business_outcome", "cost",
        "time_to_effect", "risk", "reversibility", "scope_change", "unknowns", "next_step",
    }
    if not isinstance(option, dict) or set(_string_list(option.get("symmetric_fields"), "DecisionOption.symmetric_fields")) != expected_symmetric:
        raise ContractError("DecisionOption 对称字段漂移")
    grant = schemas.get("authorization_grant")
    if not isinstance(grant, dict) or grant.get("projection_only_until_authority_provider") is not True:
        raise ContractError("AuthorizationGrant 必须保持 projection-only")
    if grant.get("authenticated_authority") is not False or grant.get("executable") is not False:
        raise ContractError("本地 AuthorizationGrant 不得冒充 authority")
    required_schemas = {
        "decision_unit", "role_submission", "decision_option", "eligibility", "hard_gate",
        "decision_record", "authorization_grant", "card_projection",
        "commercial_readiness_decision", "production_campaign_approval", "outcome_acceptance",
        "role_interaction_envelope", "human_calibration_session",
        "human_calibration_observation", "human_calibration_readback",
    }
    if not required_schemas.issubset(schemas):
        raise ContractError(f"schemas 缺定义: {sorted(required_schemas - set(schemas))}")
    for schema_name in required_schemas - {"decision_option"}:
        schema = schemas[schema_name]
        if not isinstance(schema, dict):
            raise ContractError(f"{schema_name} schema 必须为映射")
        _string_list(schema.get("required_fields"), f"{schema_name}.required_fields")
    principal_classes = _string_list(
        closed.get("human_calibration_principal_class"),
        "HumanCalibrationPrincipalClass", count=4,
    )
    if principal_classes != ["product", "engineering", "quality", "release_operations"]:
        raise ContractError("HumanCalibrationPrincipalClass 闭集漂移")
    responsibility_classes = _string_list(
        closed.get("human_calibration_responsibility_class"),
        "HumanCalibrationResponsibilityClass", count=6,
    )
    if responsibility_classes != [
        "business", "product", "experience", "quality", "engineering", "release_operations",
    ]:
        raise ContractError("HumanCalibrationResponsibilityClass 闭集漂移")
    dimensions = _string_list(
        closed.get("human_calibration_observation_dimension"),
        "HumanCalibrationObservationDimension", count=6,
    )
    if dimensions != [
        "understanding", "option_cross_role_impact_comprehension", "transfer",
        "pause_deny_abort", "recovery", "post_check",
    ]:
        raise ContractError("HumanCalibrationObservationDimension 闭集漂移")
    if _string_list(closed.get("human_calibration_status"), "HumanCalibrationStatus") != [
        "not_observed", "insufficient", "calibrated",
    ]:
        raise ContractError("HumanCalibrationStatus 闭集漂移")
    source_kinds = _string_list(
        closed.get("human_calibration_source_kind"), "HumanCalibrationSourceKind", count=5
    )
    if source_kinds != [
        "human_participant", "machine_fixture", "reviewer", "agent_self_test", "machine_baseline",
    ]:
        raise ContractError("HumanCalibrationSourceKind 闭集漂移")
    if _string_list(closed.get("human_calibration_observation_outcome"), "HumanCalibrationObservationOutcome") != [
        "demonstrated", "insufficient", "not_attempted",
    ]:
        raise ContractError("HumanCalibrationObservationOutcome 闭集漂移")
    _string_list(closed.get("human_calibration_blocker"), "HumanCalibrationBlocker")
    calibration = value.get("calibration_model")
    if not isinstance(calibration, dict):
        raise ContractError("缺 calibration_model")
    if calibration.get("contract_version") != "human-calibration-v2":
        raise ContractError("Human calibration contract version 漂移")
    if calibration.get("role_model_version") != "human-calibration-role-model-v2":
        raise ContractError("Human calibration role model version 漂移")
    if calibration.get("observation_model_version") != "human-calibration-observation-model-v2":
        raise ContractError("Human calibration observation model version 漂移")
    if calibration.get("freshness_seconds") != 86400 or calibration.get("minimum_qualifying_role_sessions") != 4:
        raise ContractError("Human calibration freshness/minimum sample 漂移")
    expected_mapping = {
        "product": ["business", "product", "experience"],
        "engineering": ["engineering"],
        "quality": ["quality"],
        "release_operations": ["release_operations"],
    }
    if calibration.get("principal_responsibility_mapping") != expected_mapping:
        raise ContractError("Human calibration principal/responsibility mapping 漂移")
    if (
        calibration.get("mapping_semantics") != "calibration_coverage_only"
        or calibration.get("authority_delegation") is not False
        or calibration.get("signoff_substitution") is not False
        or calibration.get("qualifying_source_kind") != "human_participant"
        or calibration.get("non_human_source_kinds") != ["machine_fixture", "reviewer", "agent_self_test", "machine_baseline"]
        or calibration.get("each_principal_requires_qualifying_role_session") is not True
        or calibration.get("same_participant_cross_principal_requires_separate_session_role_records") is not True
        or calibration.get("routine_calibration_requires_four_unique_participants") is not False
        or calibration.get("independent_principal_policy") != "independent-principal-required"
        or calibration.get("exact_session_bytes_required") is not True
        or calibration.get("timezone_aware_chronology_required") is not True
        or calibration.get("caller_status_flags_accepted") is not False
    ):
        raise ContractError("Human calibration authority/source semantics 漂移")
    session_schema = schemas["human_calibration_session"]
    observation_schema = schemas["human_calibration_observation"]
    readback_schema = schemas["human_calibration_readback"]
    if session_schema.get("free_text_allowed") is not False:
        raise ContractError("Human calibration 不得保存自由文本")
    if set(session_schema.get("raw_content_fields_forbidden") or ()) != {
        "prompt", "prompt_text", "message", "message_text", "payload", "raw_payload", "free_text", "transcript",
    }:
        raise ContractError("Human calibration raw-content 禁止字段漂移")
    if set(readback_schema.get("coverage_required_fields") or ()) != {
        "required_principal_classes", "completed_principal_classes",
        "required_responsibility_classes", "completed_responsibility_classes",
        "required_observation_dimensions", "completed_observation_dimensions",
    }:
        raise ContractError("Human calibration readback coverage 字段漂移")

    interaction = schemas["role_interaction_envelope"]
    expected_interaction_fields = {
        "event_type", "delivery_stage", "audience_role", "what_happened",
        "user_or_business_impact", "decision_owner", "legal_actions",
        "safe_actions_taken", "next_acceptance", "next_acceptance_role", "audit_details",
    }
    if set(interaction["required_fields"]) != expected_interaction_fields:
        raise ContractError("RoleInteractionEnvelope 公共字段漂移")
    event_required = interaction.get("event_required_fields")
    if not isinstance(event_required, dict) or set(event_required) != set(event_types):
        raise ContractError("RoleInteractionEnvelope 事件专属字段未覆盖四类事件")
    if event_required.get("exception_escalation") != ["cannot_continue_reason", "safest_default"]:
        raise ContractError("异常交互字段漂移")
    if event_required.get("completion_report") != ["proof", "limits"]:
        raise ContractError("完成交互字段漂移")
    audit_terms = _string_list(interaction.get("audit_only_internal_terms"), "RoleInteractionEnvelope.audit_only_internal_terms")
    required_audit_terms = {
        "digest", "cas", "gate_block", "typed_blocker", "fingerprint",
        "owner_manifest", "receipt", "readback", "exact_byte", "sha",
        "internal_absolute_path", "internal_command", "internal_tool_name",
    }
    if set(audit_terms) != required_audit_terms:
        raise ContractError("RoleInteractionEnvelope 审计专用术语漂移")
    sod_policies = value.get("sod_policies")
    if not isinstance(sod_policies, dict) or set(sod_policies) != {
        "role-record-only", "independent-principal-required"
    }:
        raise ContractError("SoD policy 必须为版本化两项闭集")
    if sod_policies["role-record-only"].get("distinct_authenticated_actors_required") is not False:
        raise ContractError("role-record-only 不得强制不同 principal")
    if sod_policies["independent-principal-required"].get("distinct_authenticated_actors_required") is not True:
        raise ContractError("independent-principal-required 必须强制不同 principal")
    risk_policy = value.get("risk_sod_policy")
    if not isinstance(risk_policy, dict) or risk_policy.get("default") not in sod_policies:
        raise ContractError("risk_sod_policy.default 非法")
    classifications = risk_policy.get("classifications")
    if not isinstance(classifications, dict) or not classifications or any(
        policy not in sod_policies for policy in classifications.values()
    ):
        raise ContractError("risk_sod_policy.classifications 非法")
    routes = value.get("router")
    if not isinstance(routes, list) or not routes:
        raise ContractError("router 必须为非空表")
    seen: set[tuple[str, str]] = set()
    terminals = set(_string_list(closed.get("default_terminal"), "default_terminal"))
    for route in routes:
        if not isinstance(route, dict):
            raise ContractError("router 项必须为映射")
        key = (route.get("stage"), route.get("decision_kind"))
        if key in seen or key[0] not in stages or key[1] not in kinds:
            raise ContractError(f"router key 非法或重复: {key!r}")
        seen.add(key)
        role = route.get("accountable_role")
        if role is not None and role not in human_values:
            raise ContractError(f"router accountable_role 非法: {role!r}")
        vetoes = route.get("hard_veto_roles")
        if not isinstance(vetoes, list) or any(role not in human_values for role in vetoes):
            raise ContractError(f"router hard_veto_roles 非法: {key!r}")
        if route.get("default_terminal") not in terminals:
            raise ContractError(f"router default_terminal 非法: {key!r}")
    harness = value.get("harness_projection")
    if (
        not isinstance(harness, dict)
        or harness.get("harnesses") != ["cursor", "codex"]
        or harness.get("canonical_cli") != "quwoquan_ops/cli/human_agent_delivery.py"
        or harness.get("projection_commands") != ["project-card", "project-interaction"]
        or harness.get("interaction_projection_command") != "project-interaction"
        or harness.get("harness_is_contract_field") is not True
        or harness.get("identical_json_projection") is not True
    ):
        raise ContractError("Cursor/Codex harness projection 必须显式校验且同源")
    workflow = value.get("workflow_interaction_binding")
    expected_skills = [
        "commit", "content-production", "continue", "design", "dev", "distill",
        "environment-ops", "explore", "incident-inspection", "plan-next", "prd", "review",
    ]
    if not isinstance(workflow, dict) or workflow.get("required_skills") != expected_skills:
        raise ContractError("角色交互 workflow binding 必须覆盖 12 份 canonical Skill")
    if workflow.get("natural_language_and_explicit_skill_same_track") is not True:
        raise ContractError("自然语言与显式 Skill 必须同轨")
    if workflow.get("canonical_projector") != "quwoquan_ops/cli/lib/human_agent_delivery/projection.py#project_role_interaction":
        raise ContractError("workflow binding 必须使用 canonical projector")
    bindings = workflow.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(expected_skills):
        raise ContractError("workflow binding 覆盖漂移")
    phases = workflow.get("required_phases")
    fields = workflow.get("required_binding_fields")
    if phases != ["PRE", "DURING", "POST"] or fields != ["phase", "event_type", "delivery_stage", "audience_role"]:
        raise ContractError("workflow binding phase/field 契约漂移")
    for skill, skill_bindings in bindings.items():
        if not isinstance(skill_bindings, list) or len(skill_bindings) != 3:
            raise ContractError(f"{skill} 必须声明 PRE/DURING/POST 三段交互")
        if [item.get("phase") for item in skill_bindings if isinstance(item, dict)] != phases:
            raise ContractError(f"{skill} 交互 phase 漂移")
        for item in skill_bindings:
            if not isinstance(item, dict) or list(item) != fields:
                raise ContractError(f"{skill} 交互字段漂移")
            if item["event_type"] not in event_types or item["delivery_stage"] not in stages:
                raise ContractError(f"{skill} 交互闭集值非法")
            if item["audience_role"] not in {*human_values, workflow.get("dynamic_audience_role")}:
                raise ContractError(f"{skill} 交互角色非法")
    production = value.get("production_policy")
    if (
        not isinstance(production, dict)
        or production.get("one_approval_per_frozen_campaign") is not True
        or production.get("objective_execution_admission_source")
        != "quwoquan_ops/policies/objective_execution_contract.yaml#admission"
        or any(key in production for key in ("s4_admission", "write_concurrency", "temporary_branch_bypass"))
    ):
        raise ContractError("production policy 必须引用 Objective execution admission，不能复制 S4 机器事实")
    recommendation = value.get("recommendation_policy")
    if not isinstance(recommendation, dict) or set(
        recommendation.get("forbidden_decision_kinds") or ()
    ) != {"product_scope", "experience_direction", "commercial_readiness", "outcome_acceptance"}:
        raise ContractError("偏好类决定的 recommendation policy 漂移")
    errors = value.get("errors")
    if not isinstance(errors, dict) or not errors:
        raise ContractError("缺 typed errors")
    for code, descriptor in errors.items():
        if not isinstance(code, str) or not code.startswith("HAD.") or not isinstance(descriptor, dict):
            raise ContractError("typed error 定义非法")
        if descriptor.get("terminal") not in terminals or not descriptor.get("recovery"):
            raise ContractError(f"typed error 缺 terminal/recovery: {code}")


def closed_values(name: str) -> tuple[str, ...]:
    contract = load_contract()
    return tuple(contract["closed_sets"][name])


def namespace_values(name: str) -> tuple[str, ...]:
    contract = load_contract()
    return tuple(contract["namespaces"][name]["values"])


def schema_fields(name: str, declaration: str = "required_fields") -> tuple[str, ...]:
    contract = load_contract()
    value = contract["schemas"][name][declaration]
    return tuple(value)


def validate_exact_fields(payload: Mapping[str, Any], schema_name: str, declaration: str = "required_fields") -> None:
    expected = set(schema_fields(schema_name, declaration))
    actual = set(payload)
    if actual != expected:
        raise ContractError(
            f"{schema_name} 字段漂移: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def typed_blocker(code: str, *, detail: str = "", terminal: str | None = None) -> dict[str, Any]:
    errors = load_contract()["errors"]
    descriptor = errors.get(code)
    if not isinstance(descriptor, dict):
        descriptor = errors["HAD.CONTRACT_INVALID"]
        code = "HAD.CONTRACT_INVALID"
    return {
        "result": "typed_blocker",
        "code": code,
        "terminal": terminal or descriptor["terminal"],
        "recovery": descriptor["recovery"],
        "detail": detail,
    }
