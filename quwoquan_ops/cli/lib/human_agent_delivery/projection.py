"""Neutral human-readable card and projection-only authorization helpers."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contract import (
    ContractError, closed_values, load_contract, schema_fields, typed_blocker, validate_exact_fields,
)
from .router import stable_option_order

RECOVERY_ACTIONS = ("request_evidence", "transfer_to_correct_role", "pause_or_stop")


def _symmetric_options(options: Sequence[Mapping[str, Any]], seed: str) -> list[dict[str, Any]]:
    fields = schema_fields("decision_option", "symmetric_fields")
    projected: list[dict[str, Any]] = []
    for option in stable_option_order(options, seed):
        validate_exact_fields(option, "decision_option", "symmetric_fields")
        projected.append({field: option[field] for field in fields})
    return projected


def project_role_card(
    *,
    card_type: str,
    decision_kind: str,
    current_role: str,
    question: str,
    known_facts: Sequence[str],
    unknowns: Sequence[str],
    hard_constraints: Sequence[str],
    options: Sequence[Mapping[str, Any]],
    consequences: Mapping[str, Any],
    seed: str,
    agent_recommendation: Mapping[str, Any] | None = None,
    independent_inputs_sealed: bool = False,
) -> dict[str, Any]:
    """Project one neutral card; it never records a decision or authority."""
    contract = load_contract()
    if card_type not in closed_values("card_type"):
        return typed_blocker("HAD.CONTRACT_INVALID", detail=f"unknown card_type={card_type}")
    if decision_kind not in closed_values("decision_kind"):
        return typed_blocker("HAD.UNKNOWN_DECISION_KIND", detail=decision_kind)
    if not 2 <= len(options) <= 4:
        return typed_blocker(
            "HAD.CONTRACT_INVALID", detail="human choice cards require 2..4 legal options"
        )
    forbidden = contract["recommendation_policy"]["forbidden_decision_kinds"]
    if agent_recommendation is not None and decision_kind in forbidden:
        return typed_blocker("HAD.RECOMMENDATION_FORBIDDEN", detail=decision_kind)
    if agent_recommendation is not None and not independent_inputs_sealed:
        return typed_blocker("HAD.RECOMMENDATION_FORBIDDEN", detail="independent inputs are not sealed")
    projected = {
        "schema_version": contract["schema_version"],
        "card_type": card_type,
        "current_role": current_role,
        "question": question,
        "known_facts": list(known_facts),
        "unknowns": list(unknowns),
        "hard_constraints": list(hard_constraints),
        "options": _symmetric_options(options, seed),
        "selected_option_id": None,
        "agent_recommendation": dict(agent_recommendation) if agent_recommendation else None,
        "actions": list(RECOVERY_ACTIONS),
        "consequences": dict(consequences),
    }
    validate_exact_fields(projected, "card_projection")
    return projected


def project_authorization_grant(decision_record: Mapping[str, Any]) -> dict[str, Any] | None:
    """Derive an audit projection, never authenticated/executable authority."""
    validate_exact_fields(decision_record, "decision_record")
    if decision_record["decision_kind"] == "commercial_readiness":
        return None
    if decision_record["decision_kind"] not in {
        "delivery_authorization", "production_campaign_approval", "channel_publication"
    }:
        return None
    projection_id = hashlib.sha256(
        f"grant-projection\0{decision_record['decision_id']}".encode("utf-8")
    ).hexdigest()
    projection = {
        "grant_projection_id": projection_id,
        "source_decision_id": decision_record["decision_id"],
        "target": decision_record["decision_kind"],
        "scope": decision_record["scope"],
        "actions": [],
        "expires_at": decision_record["expires_at"],
        "stop_conditions": ["authority_provider_unavailable"],
        "projection_only_until_authority_provider": True,
        "authenticated_authority": False,
        "executable": False,
    }
    validate_exact_fields(projection, "authorization_grant")
    return projection

_VISIBLE_INTERACTION_FIELDS = (
    "event_type", "delivery_stage", "audience_role", "what_happened",
    "user_or_business_impact", "decision_owner", "legal_actions",
    "safe_actions_taken", "next_acceptance", "next_acceptance_role",
)
_INTERNAL_TERM_PATTERNS = {
    "digest": re.compile(r"(?i)(?<![a-z0-9])digest(?![a-z0-9])|摘要身份"),
    "cas": re.compile(r"(?i)(?<![a-z0-9])cas(?![a-z0-9])"),
    "gate_block": re.compile(r"(?i)gate[_ -]?block"),
    "typed_blocker": re.compile(r"(?i)typed[_ -]?block(?:er)?"),
    "fingerprint": re.compile(r"(?i)(?<![a-z0-9])fingerprint(?![a-z0-9])|指纹"),
    "owner_manifest": re.compile(r"(?i)owner[_ -]?manifest|归属清单"),
    "receipt": re.compile(r"(?i)(?<![a-z0-9])receipt(?![a-z0-9])|回执"),
    "readback": re.compile(r"(?i)(?<![a-z0-9])readback(?![a-z0-9])|读回"),
    "exact_byte": re.compile(r"(?i)exact[_ -]?byte|逐字节"),
    "sha": re.compile(r"(?i)(?<![a-z0-9])sha(?:1|224|256|384|512)?(?::|\b)"),
    "internal_absolute_path": re.compile(r"(?<![A-Za-z0-9_])/(?:Users|home|private|var|tmp|opt|workspace)/[^\s,，；;]+"),
    "internal_command": re.compile(r"(?i)(?:^|[\s`])(?:make|python3?|pytest|bash|zsh|git|stackctl)(?:[\s`]|$)"),
    "internal_tool_name": re.compile(r"(?i)(?:cursor|codex|mcp|shell tool|readfile|applypatch|todowrite|subagent)"),
}


def _interaction_blocker(code: str, detail: str) -> dict[str, Any]:
    return typed_blocker(code, detail=detail)


def _required_nonempty_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} 必须为非空角色可见文本")
    return value


def _validate_optional_role(value: object, field: str, human_roles: set[str]) -> None:
    if value is not None and value not in human_roles:
        raise ContractError(f"{field} 必须显式为 null 或 HumanAuthorityRole")


def _validate_closed_string_list(
    payload: Mapping[str, Any], field: str, allowed: set[str], *, allow_empty: bool,
) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ContractError(f"{field} 必须为{'可空' if allow_empty else '非空'}数组")
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise ContractError(f"{field} 含未声明动作")
    if len(value) != len(set(value)):
        raise ContractError(f"{field} 含重复动作")
    return value


def _visible_interaction_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        {field: value for field, value in payload.items() if field != "audit_details"},
        ensure_ascii=False, sort_keys=True,
    )


def visible_interaction_term_leaks(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return internal terms found outside audit_details."""
    visible = _visible_interaction_text(payload)
    return tuple(name for name, pattern in _INTERNAL_TERM_PATTERNS.items() if pattern.search(visible))


def project_role_interaction(payload: Mapping[str, Any], *, harness: str) -> dict[str, Any]:
    """Validate and project one role-visible event; harness changes no output bytes."""
    try:
        contract = load_contract()
        harnesses = set(contract["harness_projection"]["harnesses"])
        if harness not in harnesses:
            return _interaction_blocker("HAD.UNKNOWN_HARNESS", f"unknown harness={harness}")
        if not isinstance(payload, Mapping):
            return _interaction_blocker("HAD.INTERACTION_FIELD_INVALID", "input must be an object")
        event_type = payload.get("event_type")
        event_types = set(closed_values("role_interaction_event_type"))
        if event_type not in event_types:
            return _interaction_blocker("HAD.INTERACTION_FIELD_INVALID", f"unknown event_type={event_type}")
        base_fields = set(schema_fields("role_interaction_envelope"))
        event_fields = set(
            contract["schemas"]["role_interaction_envelope"]["event_required_fields"][event_type]
        )
        expected_fields = base_fields | event_fields
        actual_fields = set(payload)
        if actual_fields != expected_fields:
            return _interaction_blocker(
                "HAD.INTERACTION_FIELD_INVALID",
                f"field drift: missing={sorted(expected_fields - actual_fields)}, extra={sorted(actual_fields - expected_fields)}",
            )
        if payload.get("delivery_stage") not in set(closed_values("delivery_stage")):
            raise ContractError("delivery_stage 不在闭集")
        human_roles = set(closed_values("role_interaction_audience_role"))
        if payload.get("audience_role") not in human_roles:
            raise ContractError("audience_role 不在角色闭集")
        _validate_optional_role(payload.get("decision_owner"), "decision_owner", human_roles)
        _validate_optional_role(payload.get("next_acceptance_role"), "next_acceptance_role", human_roles)
        _required_nonempty_text(payload, "what_happened")
        _required_nonempty_text(payload, "user_or_business_impact")
        _required_nonempty_text(payload, "next_acceptance")
        _validate_closed_string_list(
            payload, "legal_actions", set(closed_values("role_interaction_legal_action")), allow_empty=False,
        )
        _validate_closed_string_list(
            payload, "safe_actions_taken", set(closed_values("role_interaction_safe_action")), allow_empty=True,
        )
        audit_details = payload.get("audit_details")
        if not isinstance(audit_details, Mapping):
            raise ContractError("audit_details 必须为机器审计映射")
        if event_type == "exception_escalation":
            _required_nonempty_text(payload, "cannot_continue_reason")
            _required_nonempty_text(payload, "safest_default")
            if payload.get("decision_owner") is None:
                raise ContractError("异常升级必须声明 decision_owner")
        if event_type == "completion_report":
            proof = payload.get("proof")
            limits = payload.get("limits")
            if not isinstance(proof, list) or not proof or any(not isinstance(item, str) or not item.strip() for item in proof):
                raise ContractError("completion_report.proof 必须为非空角色可见文本数组")
            if not isinstance(limits, list) or not limits or any(not isinstance(item, str) or not item.strip() for item in limits):
                raise ContractError("completion_report.limits 必须为非空角色可见文本数组")
            if payload.get("decision_owner") not in {None, payload.get("audience_role")}:
                return _interaction_blocker(
                    "HAD.INTERACTION_ROLE_OVERRUN", "completion decision_owner exceeds audience role domain",
                )
            if payload.get("next_acceptance_role") not in {None, payload.get("audience_role")}:
                return _interaction_blocker(
                    "HAD.INTERACTION_ROLE_OVERRUN", "completion next_acceptance_role exceeds audience role domain",
                )
            completion_claim = json.dumps(
                {
                    "what_happened": payload.get("what_happened"),
                    "user_or_business_impact": payload.get("user_or_business_impact"),
                    "proof": proof,
                    "limits": limits,
                },
                ensure_ascii=False,
            )
            upper_layer_claim = re.compile(
                r"(?:测试|检查|评审|门禁|源码|契约).{0,24}(?:通过|完成).{0,24}"
                r"(?:因此|代表|证明).{0,24}(?:用户.{0,8}可用|可商用|可发布|生产可用)"
            )
            if upper_layer_claim.search(completion_claim):
                return _interaction_blocker(
                    "HAD.INTERACTION_ROLE_OVERRUN",
                    "upper-layer evidence cannot claim user or business availability",
                )
        leaks = visible_interaction_term_leaks(payload)
        if leaks:
            return _interaction_blocker(
                "HAD.INTERACTION_TERM_LEAK", "internal terms outside audit_details: " + ",".join(leaks),
            )
        return {field: payload[field] for field in schema_fields("role_interaction_envelope")} | {
            field: payload[field]
            for field in contract["schemas"]["role_interaction_envelope"]["event_required_fields"][event_type]
        }
    except ContractError as error:
        return _interaction_blocker("HAD.INTERACTION_FIELD_INVALID", str(error))

