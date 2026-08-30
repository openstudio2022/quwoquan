"""Deterministic, read-only HOTL admission evaluator."""
from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from ..evidence_fingerprint import canonical_digest, canonical_json_bytes, fingerprint_ref
from ..objective_execution import inspect_admission
from .contract import (
    ContractError, closed_values, load_contract, objective_blocked_s4_fallback,
    objective_emergency_blocked_s4_fallback, validate_exact_fields,
    validate_objective_s4_readback,
)


class _IssueCollector:
    def __init__(self, priorities: Sequence[str]) -> None:
        self._priorities = {code: index for index, code in enumerate(priorities)}
        self._issues: set[str] = set()

    def add(self, code: str) -> None:
        self._issues.add(code)

    def values(self) -> list[str]:
        return sorted(self._issues, key=lambda code: (self._priorities.get(code, len(self._priorities)), code))


def _mapping(value: object, schema: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object or null")
    validate_exact_fields(value, schema)
    return value


def _optional_mapping(value: object, schema: str, label: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, schema, label)


def _enum(value: object, closed_name: str, label: str) -> str:
    if not isinstance(value, str) or value not in closed_values(closed_name):
        raise ContractError(f"{label} must be one of {list(closed_values(closed_name))}")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{label} must be boolean")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _stable_id(value: object, label: str) -> str:
    return unicodedata.normalize("NFC", _nonempty_string(value, label))


def _nullable_string(value: object, label: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ContractError(f"{label} must be a non-empty string or null")
    return value


def _integer(value: object, label: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        limit = f"..{maximum}" if maximum is not None else ""
        raise ContractError(f"{label} must be integer {minimum}{limit}")
    return value


def _sha256_digest(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ContractError(f"{label} must be a sha256 digest")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ContractError(f"{label} must be a lowercase sha256 digest")
    return value


def _string_list(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must be a string list")
    if not allow_empty and not value:
        raise ContractError(f"{label} must be non-empty")
    normalized = [unicodedata.normalize("NFC", item) for item in value]
    if len(normalized) != len(set(normalized)):
        raise ContractError(f"{label} contains duplicate stable ids after NFC normalization")
    return sorted(normalized)


def _validate_subject(value: object) -> dict[str, str]:
    subject = _mapping(value, "subject", "subject")
    return {
        "subject_id": _nonempty_string(subject["subject_id"], "subject.subject_id"),
        "scope_id": _nonempty_string(subject["scope_id"], "subject.scope_id"),
        "action_id": _nonempty_string(subject["action_id"], "subject.action_id"),
    }


def _validate_authority(value: object) -> dict[str, Any] | None:
    authority = _optional_mapping(value, "authority_readback", "authority_readback")
    if authority is None:
        return None
    return {
        "status": _enum(authority["status"], "readback_status", "authority_readback.status"),
        "provider_kind": _enum(authority["provider_kind"], "authority_provider_kind", "authority_readback.provider_kind"),
        "authenticated": _bool(authority["authenticated"], "authority_readback.authenticated"),
        "exact_bytes_verified": _bool(authority["exact_bytes_verified"], "authority_readback.exact_bytes_verified"),
        "release_evidence_eligible": _bool(authority["release_evidence_eligible"], "authority_readback.release_evidence_eligible"),
        "expired": _bool(authority["expired"], "authority_readback.expired"),
        "subject_id": _nullable_string(authority["subject_id"], "authority_readback.subject_id"),
        "scope_id": _nullable_string(authority["scope_id"], "authority_readback.scope_id"),
        "allowed_action_id": _nullable_string(authority["allowed_action_id"], "authority_readback.allowed_action_id"),
        "decision_kind": _nullable_string(authority["decision_kind"], "authority_readback.decision_kind"),
    }


def _validate_roles(value: object) -> dict[str, Any] | None:
    proof = _optional_mapping(value, "role_responsibility_proof", "role_responsibility_proof")
    if proof is None:
        return None
    return {
        "status": _enum(proof["status"], "readback_status", "role_responsibility_proof.status"),
        "seven_responsibilities_closed": _bool(proof["seven_responsibilities_closed"], "role_responsibility_proof.seven_responsibilities_closed"),
        "sod_required": _bool(proof["sod_required"], "role_responsibility_proof.sod_required"),
        "sod_satisfied": _bool(proof["sod_satisfied"], "role_responsibility_proof.sod_satisfied"),
    }


def _validate_cohort(value: object) -> dict[str, Any] | None:
    proof = _optional_mapping(value, "cohort_proof", "cohort_proof")
    if proof is None:
        return None
    return {
        "status": _enum(proof["status"], "readback_status", "cohort_proof.status"),
        "cohort_id": (
            _stable_id(proof["cohort_id"], "cohort_proof.cohort_id")
            if proof["cohort_id"] is not None else None
        ),
        "member_count": _integer(proof["member_count"], "cohort_proof.member_count"),
        "member_ids": _string_list(proof["member_ids"], "cohort_proof.member_ids"),
        "selection_query_frozen": _bool(proof["selection_query_frozen"], "cohort_proof.selection_query_frozen"),
        "bottleneck_rule_frozen": _bool(proof["bottleneck_rule_frozen"], "cohort_proof.bottleneck_rule_frozen"),
        "threshold_frozen": _bool(proof["threshold_frozen"], "cohort_proof.threshold_frozen"),
        "coverage_basis_points": _integer(proof["coverage_basis_points"], "cohort_proof.coverage_basis_points", maximum=10000),
        "human_calibration": _enum(proof["human_calibration"], "human_calibration_status", "cohort_proof.human_calibration"),
        "wait_event_kinds": sorted(_enum(item, "wait_event_kind", "cohort_proof.wait_event_kinds[]") for item in _string_list(proof["wait_event_kinds"], "cohort_proof.wait_event_kinds")),
        "cohort_digest_before": _nullable_string(proof["cohort_digest_before"], "cohort_proof.cohort_digest_before"),
        "cohort_digest_after": _nullable_string(proof["cohort_digest_after"], "cohort_proof.cohort_digest_after"),
    }


def _validate_checkpoint(value: object) -> dict[str, Any] | None:
    policy = _optional_mapping(value, "checkpoint_policy", "checkpoint_policy")
    if policy is None:
        return None
    return {
        "status": _enum(policy["status"], "readback_status", "checkpoint_policy.status"),
        "resolution": _enum(policy["resolution"], "checkpoint_resolution", "checkpoint_policy.resolution"),
        "checkpoint_delta_id": _nullable_string(policy["checkpoint_delta_id"], "checkpoint_policy.checkpoint_delta_id"),
        "removable_decision_kinds": _string_list(policy["removable_decision_kinds"], "checkpoint_policy.removable_decision_kinds"),
        "resume_requested": _bool(policy["resume_requested"], "checkpoint_policy.resume_requested"),
        "new_human_decision_id": _nullable_string(policy["new_human_decision_id"], "checkpoint_policy.new_human_decision_id"),
        "human_override": _bool(policy["human_override"], "checkpoint_policy.human_override"),
        "requested_reduction": _bool(policy["requested_reduction"], "checkpoint_policy.requested_reduction"),
    }


def _validate_ack(value: object, label: str) -> dict[str, Any] | None:
    ack = _optional_mapping(value, "command_ack", label)
    if ack is None:
        return None
    return {
        "status": _enum(ack["status"], "readback_status", f"{label}.status"),
        "exact": _bool(ack["exact"], f"{label}.exact"),
        "subject_id": _nullable_string(ack["subject_id"], f"{label}.subject_id"),
        "scope_id": _nullable_string(ack["scope_id"], f"{label}.scope_id"),
        "action_id": _nullable_string(ack["action_id"], f"{label}.action_id"),
        "command_id": _nullable_string(ack["command_id"], f"{label}.command_id"),
    }


def _validate_effect(value: object, label: str) -> dict[str, Any] | None:
    effect = _optional_mapping(value, "effect_readback", label)
    if effect is None:
        return None
    return {
        "status": _enum(effect["status"], "readback_status", f"{label}.status"),
        "effect_status": _enum(effect["effect_status"], "effect_status", f"{label}.effect_status"),
        "independent": _bool(effect["independent"], f"{label}.independent"),
        "subject_id": _nullable_string(effect["subject_id"], f"{label}.subject_id"),
        "scope_id": _nullable_string(effect["scope_id"], f"{label}.scope_id"),
        "action_id": _nullable_string(effect["action_id"], f"{label}.action_id"),
        "command_id": _nullable_string(effect["command_id"], f"{label}.command_id"),
    }


def _validate_controls(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractError("control_proofs must be a list")
    controls: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        proof = _mapping(item, "control_proof", f"control_proofs[{index}]")
        controls.append({
            "proof_id": _stable_id(proof["proof_id"], f"control_proofs[{index}].proof_id"),
            "action": _enum(proof["action"], "control_action", f"control_proofs[{index}].action"),
            "command_ack": _validate_ack(proof["command_ack"], f"control_proofs[{index}].command_ack"),
            "effect_readback": _validate_effect(proof["effect_readback"], f"control_proofs[{index}].effect_readback"),
            "connected": _bool(proof["connected"], f"control_proofs[{index}].connected"),
            "audit_passed": _bool(proof["audit_passed"], f"control_proofs[{index}].audit_passed"),
            "ack_timed_out": _bool(proof["ack_timed_out"], f"control_proofs[{index}].ack_timed_out"),
            "post_revoke_new_action_count": _integer(proof["post_revoke_new_action_count"], f"control_proofs[{index}].post_revoke_new_action_count"),
        })
    proof_ids = [item["proof_id"] for item in controls]
    if len(proof_ids) != len(set(proof_ids)):
        raise ContractError("control_proofs contains duplicate proof_id")
    actions = [item["action"] for item in controls]
    if len(actions) != len(set(actions)):
        raise ContractError("control_proofs contains duplicate action")
    return sorted(controls, key=lambda item: (item["proof_id"], item["action"]))


def _validate_commercial(value: object) -> dict[str, Any] | None:
    readback = _optional_mapping(value, "commercial_authority_readback", "commercial_authority_readback")
    if readback is None:
        return None
    return {
        "status": _enum(readback["status"], "readback_status", "commercial_authority_readback.status"),
        "authenticated": _bool(readback["authenticated"], "commercial_authority_readback.authenticated"),
        "exact_bytes_verified": _bool(readback["exact_bytes_verified"], "commercial_authority_readback.exact_bytes_verified"),
        "release_evidence_eligible": _bool(readback["release_evidence_eligible"], "commercial_authority_readback.release_evidence_eligible"),
        "commercial_readiness_closed": _bool(readback["commercial_readiness_closed"], "commercial_authority_readback.commercial_readiness_closed"),
        "production_campaign_closed": _bool(readback["production_campaign_closed"], "commercial_authority_readback.production_campaign_closed"),
    }


def _validate_activation(value: object) -> dict[str, Any] | None:
    receipt = _optional_mapping(value, "activation_receipt", "activation_receipt")
    if receipt is None:
        return None
    return {
        "status": _enum(receipt["status"], "readback_status", "activation_receipt.status"),
        "receipt_id": _nullable_string(receipt["receipt_id"], "activation_receipt.receipt_id"),
        "authenticated": _bool(receipt["authenticated"], "activation_receipt.authenticated"),
        "exact_bytes_verified": _bool(receipt["exact_bytes_verified"], "activation_receipt.exact_bytes_verified"),
        "release_evidence_eligible": _bool(receipt["release_evidence_eligible"], "activation_receipt.release_evidence_eligible"),
        "evaluation_digest": _nullable_string(receipt["evaluation_digest"], "activation_receipt.evaluation_digest"),
        "evaluation_bytes_sha256": _nullable_string(receipt["evaluation_bytes_sha256"], "activation_receipt.evaluation_bytes_sha256"),
    }


def _normalize_input(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError("inspection input must be an object")
    validate_exact_fields(payload, "inspection_input")
    risk_tier = _enum(payload["risk_tier"], "risk_tier", "risk_tier")
    return {
        "subject": _validate_subject(payload["subject"]),
        "risk_tier": risk_tier,
        "requested_write_concurrency": _integer(payload["requested_write_concurrency"], "requested_write_concurrency", minimum=1),
        "authority_readback": _validate_authority(payload["authority_readback"]),
        "role_responsibility_proof": _validate_roles(payload["role_responsibility_proof"]),
        "cohort_proof": _validate_cohort(payload["cohort_proof"]),
        "checkpoint_policy": _validate_checkpoint(payload["checkpoint_policy"]),
        "control_proofs": _validate_controls(payload["control_proofs"]),
        "commercial_authority_readback": _validate_commercial(payload["commercial_authority_readback"]),
        "activation_receipt": _validate_activation(payload["activation_receipt"]),
    }


def _s4_readback() -> dict[str, Any]:
    return validate_objective_s4_readback(inspect_admission())


class S4ReadbackValidationError(ContractError):
    """The first Objective S4 provider result failed canonical validation."""

    def __init__(self, detail: str, fallback: Mapping[str, Any]) -> None:
        super().__init__(detail)
        self.fallback = dict(fallback)


def _inspect_s4_once() -> dict[str, Any]:
    try:
        return _s4_readback()
    except Exception as error:
        try:
            fallback = objective_blocked_s4_fallback()
        except Exception:
            fallback = objective_emergency_blocked_s4_fallback()
        detail = str(error) or type(error).__name__
        raise S4ReadbackValidationError(detail, fallback) from error


def _collect_evaluation(normalized: Mapping[str, Any], s4: Mapping[str, Any], issues: _IssueCollector, policy: Mapping[str, Any]) -> dict[str, Any]:
    subject = normalized["subject"]
    risk_tier = normalized["risk_tier"]
    if risk_tier in policy["blocked_risk_tiers"]:
        issues.add("RISK_TIER_NOT_ELIGIBLE")

    authority = normalized["authority_readback"]
    if authority is None or authority["status"] == "absent":
        issues.add("AUTHORITY_PROVIDER_UNAVAILABLE")
    elif authority["status"] == "failed":
        issues.add("AUTHORITY_READBACK_FAILED")
    elif (
        authority["provider_kind"] != "authenticated_external"
        or not authority["authenticated"] or not authority["exact_bytes_verified"]
        or not authority["release_evidence_eligible"] or authority["expired"]
        or authority["subject_id"] != subject["subject_id"]
        or authority["scope_id"] != subject["scope_id"]
        or authority["allowed_action_id"] != subject["action_id"]
        or authority["decision_kind"] not in policy["allowed_authority_decision_kinds"]
    ):
        issues.add("AUTHORITY_READBACK_INVALID")

    roles = normalized["role_responsibility_proof"]
    if roles is None or roles["status"] == "absent":
        issues.add("ROLE_RESPONSIBILITY_PROOF_MISSING")
    elif roles["status"] == "failed":
        issues.add("ROLE_RESPONSIBILITY_READBACK_FAILED")
    elif not roles["seven_responsibilities_closed"]:
        issues.add("ROLE_RESPONSIBILITY_PROOF_MISSING")
    elif roles["sod_required"] and not roles["sod_satisfied"]:
        issues.add("SEGREGATION_OF_DUTIES_FAILED")

    cohort = normalized["cohort_proof"]
    if cohort is None or cohort["status"] == "absent":
        issues.add("HUMAN_BOTTLENECK_COHORT_MISSING")
    elif cohort["status"] == "failed":
        issues.add("COHORT_READBACK_FAILED")
    elif cohort["member_count"] == 0 or len(cohort["member_ids"]) != cohort["member_count"]:
        issues.add("HUMAN_BOTTLENECK_COHORT_MISSING")
    else:
        if not cohort["selection_query_frozen"] or not cohort["bottleneck_rule_frozen"]:
            issues.add("COHORT_SELECTION_UNFROZEN")
        if not cohort["cohort_id"]:
            issues.add("HUMAN_BOTTLENECK_COHORT_MISSING")
        if not cohort["threshold_frozen"]:
            issues.add("COHORT_THRESHOLD_UNFROZEN")
        if cohort["coverage_basis_points"] < policy["coverage_threshold_basis_points"]:
            issues.add("COHORT_COVERAGE_INSUFFICIENT")
        if not cohort["cohort_digest_before"] or cohort["cohort_digest_before"] != cohort["cohort_digest_after"]:
            issues.add("COHORT_DRIFTED")
        if not cohort["wait_event_kinds"] or set(cohort["wait_event_kinds"]) - set(policy["human_wait_sources"]):
            issues.add("HUMAN_WAIT_SOURCE_INVALID")
        if cohort["human_calibration"] != "observed":
            issues.add("HUMAN_CALIBRATION_NOT_OBSERVED")

    controls = normalized["control_proofs"]
    actions = {item["action"] for item in controls}
    if actions != set(policy["control_actions"]):
        issues.add("CONTROL_PROOF_MISSING")
    for control in controls:
        ack = control["command_ack"]
        effect = control["effect_readback"]
        if ack is None or ack["status"] == "absent":
            issues.add("CONTROL_ACK_MISSING")
        elif ack["status"] == "failed":
            issues.add("CONTROL_ACK_READBACK_FAILED")
        elif not ack["exact"]:
            issues.add("CONTROL_ACK_NOT_EXACT")
        if effect is None or effect["status"] == "absent":
            issues.add("CONTROL_EFFECT_READBACK_MISSING")
        elif effect["status"] == "failed":
            issues.add("CONTROL_EFFECT_READBACK_FAILED")
        else:
            if effect["effect_status"] != "applied":
                issues.add("CONTROL_EFFECT_NOT_APPLIED")
            if not effect["independent"]:
                issues.add("CONTROL_EFFECT_NOT_INDEPENDENT")
        if (
            ack is not None and ack["status"] == "present"
            and effect is not None and effect["status"] == "present"
        ):
            expected = (subject["subject_id"], subject["scope_id"], control["action"])
            if (
                (ack["subject_id"], ack["scope_id"], ack["action_id"]) != expected
                or (effect["subject_id"], effect["scope_id"], effect["action_id"]) != expected
                or not ack["command_id"] or ack["command_id"] != effect["command_id"]
            ):
                issues.add("CONTROL_IDENTITY_DRIFTED")
        if not control["connected"]:
            issues.add("CONTROL_DISCONNECTED")
        if not control["audit_passed"]:
            issues.add("CONTROL_AUDIT_FAILED")
        if control["ack_timed_out"]:
            issues.add("CONTROL_ACK_TIMEOUT")
        if control["action"] == "revoke" and control["post_revoke_new_action_count"] != 0:
            issues.add("REVOKE_ZERO_ACTIONS_UNPROVEN")

    commercial = normalized["commercial_authority_readback"]
    if commercial is None or commercial["status"] == "absent":
        issues.add("COMMERCIAL_AUTHORITY_NOT_CLOSED")
    elif commercial["status"] == "failed":
        issues.add("COMMERCIAL_AUTHORITY_READBACK_FAILED")
    elif any((
        not commercial["authenticated"], not commercial["exact_bytes_verified"],
        not commercial["release_evidence_eligible"],
        not commercial["commercial_readiness_closed"],
        not commercial["production_campaign_closed"],
    )):
        issues.add("COMMERCIAL_AUTHORITY_NOT_CLOSED")

    checkpoint = normalized["checkpoint_policy"]
    checkpoint_valid = True
    if checkpoint is None or checkpoint["status"] == "absent":
        checkpoint_valid = False
        issues.add("CHECKPOINT_POLICY_UNRESOLVED")
    elif checkpoint["status"] == "failed":
        checkpoint_valid = False
        issues.add("CHECKPOINT_READBACK_FAILED")
    elif checkpoint["resolution"] != "resolved" or not checkpoint["checkpoint_delta_id"]:
        checkpoint_valid = False
        issues.add("CHECKPOINT_POLICY_UNRESOLVED")
    else:
        allowed_removals = set(policy["future_candidate_decision_kinds"])
        requested_removals = set(checkpoint["removable_decision_kinds"])
        if requested_removals & set(policy["immutable_decision_kinds"]) or requested_removals - allowed_removals:
            checkpoint_valid = False
            issues.add("IMMUTABLE_CHECKPOINT_REMOVAL_FORBIDDEN")
        if checkpoint["human_override"]:
            checkpoint_valid = False
            issues.add("HUMAN_OVERRIDE_ACTIVE")
    if checkpoint is not None and checkpoint["resume_requested"]:
        # v1 has no authenticated Human decision readback/provider. The supplied id
        # remains audit data and cannot establish authority, regardless of status.
        checkpoint_valid = False
        issues.add("RESUME_REQUIRES_NEW_HUMAN_DECISION")

    concurrency = s4["write_concurrency"]
    if s4["status"] == "blocked":
        issues.add("OBJECTIVE_ADMISSION_BLOCKED")
    if normalized["requested_write_concurrency"] > concurrency:
        issues.add("REQUESTED_WRITE_CONCURRENCY_EXCEEDED")
    if s4["status"] != "admitted":
        issues.add("WRITE_EXPANSION_NOT_ADMITTED")

    blockers = issues.values()
    facts_eligible = not blockers and risk_tier in policy["evaluable_risk_tiers"] and checkpoint_valid
    return {
        "normalized_input": {key: value for key, value in normalized.items() if key != "activation_receipt"},
        "s4_readback": dict(s4),
        "facts_eligible": facts_eligible,
        "checkpoint_reduction_requested": bool(checkpoint and checkpoint["requested_reduction"]),
        "blockers": blockers,
    }


def _canonical_fallback(policy: Mapping[str, Any]) -> dict[str, Any]:
    return dict(policy["current_fallback"])


def _result_template(
    *, subject: Mapping[str, Any] | None, risk_tier: str | None, status: str,
    blockers: list[str], s4: Mapping[str, Any], policy: Mapping[str, Any],
    detail: str = "", error_code: str | None = None,
) -> dict[str, Any]:
    fallback = _canonical_fallback(policy)
    output_status = status if status in {"blocked", "eligible_for_activation"} else fallback["status"]
    allowed_mode = "observe_only" if output_status == "eligible_for_activation" else fallback["allowed_mode"]
    return {
        "schema_id": "hotl-admission-inspection",
        "schema_version": 1,
        "result": "typed_blocker" if output_status == "blocked" else "inspection",
        "error_code": error_code,
        "detail": detail,
        "subject": dict(subject) if subject is not None else None,
        "risk_tier": risk_tier,
        "status": output_status,
        "allowed_mode": allowed_mode,
        "checkpoint_reduction_allowed": fallback["checkpoint_reduction_allowed"],
        "max_write_concurrency": fallback["max_write_concurrency"],
        "grant_executable": fallback["grant_executable"],
        "mutation_allowed": fallback["mutation_allowed"],
        "activation_required": True,
        "evaluation_digest": None,
        "evaluation_fingerprint_ref": None,
        "evaluation_bytes_sha256": None,
        "blockers": blockers,
        "s4_readback": dict(s4),
    }


def invalid_inspection(
    detail: str, *, policy: Mapping[str, Any],
    s4_fallback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if s4_fallback is None:
        try:
            s4_fallback = objective_blocked_s4_fallback()
        except Exception:
            s4_fallback = objective_emergency_blocked_s4_fallback()
    s4 = dict(s4_fallback)
    return _result_template(
        subject=None, risk_tier=None, status="blocked", blockers=["INPUT_CONTRACT_INVALID"],
        s4=s4, policy=policy, detail=detail, error_code="HOTL.CONTRACT_INVALID",
    )


def _evaluation_identity(payload: Mapping[str, Any]) -> tuple[bytes, str, str]:
    try:
        evaluation_bytes = canonical_json_bytes(payload)
    except Exception as error:
        detail = str(error) or type(error).__name__
        raise ContractError(f"EvidenceFingerprint canonical_json_bytes failed: {detail}") from error
    try:
        evaluation_digest = canonical_digest(payload)
    except Exception as error:
        detail = str(error) or type(error).__name__
        raise ContractError(f"EvidenceFingerprint canonical_digest failed: {detail}") from error
    try:
        evaluation_ref = fingerprint_ref(evaluation_digest)
    except Exception as error:
        detail = str(error) or type(error).__name__
        raise ContractError(f"EvidenceFingerprint fingerprint_ref failed: {detail}") from error
    return evaluation_bytes, evaluation_digest, evaluation_ref


def _blocked_inspection(
    *, detail: str, error_code: str, blocker: str, policy: Mapping[str, Any],
    s4: Mapping[str, Any], subject: Mapping[str, Any] | None = None,
    risk_tier: str | None = None,
) -> dict[str, Any]:
    result = _result_template(
        subject=subject, risk_tier=risk_tier, status="blocked", blockers=[blocker],
        s4=s4, policy=policy, detail=detail, error_code=error_code,
    )
    validate_exact_fields(result, "inspection_result")
    return result


def inspect(payload: object) -> dict[str, Any]:
    """Evaluate HOTL admission without performing any mutation."""
    contract = load_contract()
    policy = contract["admission_policy"]
    priorities = contract["blocker_priority"]
    normalized = _normalize_input(payload)
    try:
        s4 = _inspect_s4_once()
    except S4ReadbackValidationError as error:
        return _blocked_inspection(
            detail=str(error), error_code="HOTL.OBJECTIVE_ADMISSION_BLOCKED",
            blocker="OBJECTIVE_ADMISSION_BLOCKED", policy=policy,
            s4=error.fallback, subject=normalized["subject"],
            risk_tier=normalized["risk_tier"],
        )
    if s4["status"] == "blocked":
        return _blocked_inspection(
            detail=s4["reason"], error_code="HOTL.OBJECTIVE_ADMISSION_BLOCKED",
            blocker="OBJECTIVE_ADMISSION_BLOCKED", policy=policy, s4=s4,
            subject=normalized["subject"], risk_tier=normalized["risk_tier"],
        )
    issues = _IssueCollector(priorities)
    evaluation = _collect_evaluation(normalized, s4, issues, policy)
    evaluation_payload = {
        "schema_id": "hotl-admission-evaluation",
        "schema_version": 1,
        "subject": normalized["subject"],
        "risk_tier": normalized["risk_tier"],
        "evaluation": evaluation,
    }
    try:
        evaluation_bytes, evaluation_digest, evaluation_ref = _evaluation_identity(
            evaluation_payload,
        )
    except ContractError as error:
        return _blocked_inspection(
            detail=str(error), error_code="HOTL.EVALUATION_IDENTITY_FAILED",
            blocker="EVALUATION_IDENTITY_FAILED", policy=policy, s4=s4,
            subject=normalized["subject"], risk_tier=normalized["risk_tier"],
        )
    evaluation_bytes_sha256 = "sha256:" + hashlib.sha256(evaluation_bytes).hexdigest()
    blockers = list(evaluation["blockers"])
    status = "blocked" if normalized["risk_tier"] in policy["blocked_risk_tiers"] else (
        "eligible_for_activation" if evaluation["facts_eligible"] else "not_admitted"
    )
    activation = normalized["activation_receipt"]
    if activation is not None:
        # v1 has no activation verifier/provider. Caller-supplied booleans and
        # digests are audit-only bytes and can never authenticate themselves.
        if activation["status"] == "failed":
            issues.add("ACTIVATION_READBACK_FAILED")
        else:
            issues.add("ACTIVATION_PROVIDER_UNAVAILABLE")
        if status != "blocked":
            status = "not_admitted"
        blockers = issues.values()

    result = _result_template(
        subject=normalized["subject"], risk_tier=normalized["risk_tier"], status=status,
        blockers=blockers, s4=s4, policy=policy,
    )
    result.update({
        "evaluation_digest": evaluation_digest,
        "evaluation_fingerprint_ref": evaluation_ref,
        "evaluation_bytes_sha256": evaluation_bytes_sha256,
        "blockers": blockers,
    })
    validate_exact_fields(result, "inspection_result")
    return result
