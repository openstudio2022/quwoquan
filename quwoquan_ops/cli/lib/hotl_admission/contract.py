"""HOTL admission canonical contract loader and strict input validator."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..objective_execution.contract import (
    ContractError as ObjectiveContractError,
    blocked_admission_fallback as load_objective_blocked_admission_fallback,
    emergency_blocked_admission_fallback as load_objective_emergency_blocked_admission_fallback,
    validate_admission_readback as validate_objective_admission_readback,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/hotl_admission_contract.yaml"
HUMAN_CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/human_agent_delivery_contract.yaml"


class HotlAdmissionError(ValueError):
    """Typed fail-closed HOTL admission error."""

    code = "HOTL.CONTRACT_INVALID"


class ContractError(HotlAdmissionError):
    """Canonical contract or inspection input drift."""


_CONTRACT_FAILURE_ERROR_CODE = "HOTL.CANONICAL_CONTRACT_INVALID"
_CONTRACT_FAILURE_BLOCKER = "CANONICAL_CONTRACT_INVALID"
_CONTRACT_FAILURE_RECOVERY = "repair_canonical_hotl_contract"


def contract_failure(detail: str) -> dict[str, Any]:
    """Build the YAML-independent terminal for an unavailable HOTL contract."""
    return {
        "result": "typed_blocker",
        "error_code": _CONTRACT_FAILURE_ERROR_CODE,
        "terminal": "blocked",
        "recovery": _CONTRACT_FAILURE_RECOVERY,
        "detail": detail,
        "blockers": [_CONTRACT_FAILURE_BLOCKER],
    }


def _string_list(value: object, label: str, *, exact: tuple[str, ...] | None = None) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must be a non-empty string list")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} contains duplicate values")
    if exact is not None and tuple(value) != exact:
        raise ContractError(f"{label} closed set drifted")
    return value


def _required_fields(contract: Mapping[str, Any], schema_name: str) -> tuple[str, ...]:
    schemas = contract.get("schemas")
    if not isinstance(schemas, Mapping) or not isinstance(schemas.get(schema_name), Mapping):
        raise ContractError(f"missing schema {schema_name}")
    return tuple(_string_list(schemas[schema_name].get("required_fields"), f"schemas.{schema_name}.required_fields"))


def validate_contract(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ContractError("contract root must be a mapping")
    if value.get("schema_id") != "hotl-admission-contract" or value.get("schema_version") != 1:
        raise ContractError("contract identity/version is invalid")
    if value.get("owner_story") != "specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md":
        raise ContractError("owner story drifted")
    if value.get("human_authority_source") != "quwoquan_ops/policies/human_agent_delivery_contract.yaml":
        raise ContractError("Human authority source drifted")
    if value.get("objective_admission_source") != "quwoquan_ops/policies/objective_execution_contract.yaml#admission.readback_contract":
        raise ContractError("Objective admission source drifted")
    if value.get("evidence_fingerprint_source") != "quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint":
        raise ContractError("EvidenceFingerprint source drifted")

    closed = value.get("closed_sets")
    if not isinstance(closed, Mapping):
        raise ContractError("closed_sets missing")
    expected_closed = {
        "risk_tier": ("R0", "R1", "R2", "R3", "R4"),
        "status": ("blocked", "not_admitted", "eligible_for_activation", "admitted"),
        "allowed_mode": ("manual", "observe_only", "hotl"),
        "control_action": ("pause", "deny", "abort", "revoke"),
        "readback_status": ("present", "absent", "failed"),
        "human_calibration_status": ("observed", "not_observed"),
        "wait_event_kind": ("decision_requested", "decision_recorded", "runner_queue", "job_started"),
        "authority_provider_kind": ("authenticated_external", "projection", "test"),
        "checkpoint_resolution": ("resolved", "unresolved"),
        "effect_status": ("applied", "not_applied", "unknown"),
    }
    if set(closed) != set(expected_closed):
        raise ContractError("closed_sets names drifted")
    for name, expected in expected_closed.items():
        _string_list(closed.get(name), f"closed_sets.{name}", exact=expected)

    expected_schema_fields = {
        "inspection_input": (
            "subject", "risk_tier", "requested_write_concurrency", "authority_readback",
            "role_responsibility_proof", "cohort_proof", "checkpoint_policy", "control_proofs",
            "commercial_authority_readback", "activation_receipt",
        ),
        "subject": ("subject_id", "scope_id", "action_id"),
        "authority_readback": (
            "status", "provider_kind", "authenticated", "exact_bytes_verified",
            "release_evidence_eligible", "expired", "subject_id", "scope_id",
            "allowed_action_id", "decision_kind",
        ),
        "role_responsibility_proof": (
            "status", "seven_responsibilities_closed", "sod_required", "sod_satisfied",
        ),
        "cohort_proof": (
            "status", "cohort_id", "member_count", "member_ids", "selection_query_frozen",
            "bottleneck_rule_frozen", "threshold_frozen", "coverage_basis_points",
            "human_calibration", "wait_event_kinds", "cohort_digest_before", "cohort_digest_after",
        ),
        "checkpoint_policy": (
            "status", "resolution", "checkpoint_delta_id", "removable_decision_kinds",
            "resume_requested", "new_human_decision_id", "human_override", "requested_reduction",
        ),
        "control_proof": (
            "proof_id", "action", "command_ack", "effect_readback", "connected",
            "audit_passed", "ack_timed_out", "post_revoke_new_action_count",
        ),
        "command_ack": ("status", "exact", "subject_id", "scope_id", "action_id", "command_id"),
        "effect_readback": (
            "status", "effect_status", "independent", "subject_id", "scope_id", "action_id",
            "command_id",
        ),
        "commercial_authority_readback": (
            "status", "authenticated", "exact_bytes_verified", "release_evidence_eligible",
            "commercial_readiness_closed", "production_campaign_closed",
        ),
        "activation_receipt": (
            "status", "receipt_id", "authenticated", "exact_bytes_verified",
            "release_evidence_eligible", "evaluation_digest", "evaluation_bytes_sha256",
        ),
        "contract_terminal": (
            "result", "error_code", "terminal", "recovery", "detail", "blockers",
        ),
        "inspection_result": (
            "schema_id", "schema_version", "result", "error_code", "detail", "subject",
            "risk_tier", "status", "allowed_mode", "checkpoint_reduction_allowed",
            "max_write_concurrency", "grant_executable", "mutation_allowed", "activation_required",
            "evaluation_digest", "evaluation_fingerprint_ref", "evaluation_bytes_sha256", "blockers",
            "s4_readback",
        ),
    }
    schemas = value.get("schemas")
    if not isinstance(schemas, Mapping) or set(schemas) != set(expected_schema_fields):
        raise ContractError("schemas closed set drifted")
    for name, expected_fields in expected_schema_fields.items():
        if _required_fields(value, name) != expected_fields:
            raise ContractError(f"schemas.{name}.required_fields drifted")

    policy = value.get("admission_policy")
    if not isinstance(policy, Mapping):
        raise ContractError("admission_policy missing")
    if policy.get("evaluable_risk_tiers") != ["R0", "R1"] or policy.get("blocked_risk_tiers") != ["R2", "R3", "R4"]:
        raise ContractError("risk admission policy drifted")
    threshold = policy.get("coverage_threshold_basis_points")
    if isinstance(threshold, bool) or threshold != 9000:
        raise ContractError("coverage threshold must stay integer 9000 basis points")
    immutable = set(_string_list(policy.get("immutable_decision_kinds"), "immutable_decision_kinds"))
    expected_immutable = {
        "problem_acceptance", "product_scope", "experience_direction", "solution_risk",
        "delivery_authorization", "quality_uat_acceptance", "integration_acceptance",
        "artifact_acceptance", "nonproduction_acceptance", "commercial_readiness",
        "production_campaign_approval", "channel_publication", "outcome_acceptance",
        "knowledge_landing",
    }
    if immutable != expected_immutable or policy.get("future_candidate_decision_kinds") != ["routine_execution"]:
        raise ContractError("immutable/future decision policy drifted")
    allowed_authority_kinds = _string_list(
        policy.get("allowed_authority_decision_kinds"),
        "allowed_authority_decision_kinds",
        exact=("delivery_authorization",),
    )
    human_contract = _load_yaml_mapping(HUMAN_CONTRACT_PATH, "Human authority contract")
    human_closed_sets = human_contract.get("closed_sets")
    if not isinstance(human_closed_sets, Mapping):
        raise ContractError("Human authority closed_sets missing")
    human_decision_kinds = set(
        _string_list(human_closed_sets.get("decision_kind"), "Human authority decision_kind")
    )
    if not set(allowed_authority_kinds).issubset(human_decision_kinds):
        raise ContractError("allowed authority decision kinds drifted from Human authority contract")
    if policy.get("human_wait_sources") != ["decision_requested", "decision_recorded"]:
        raise ContractError("durable human wait sources drifted")
    if policy.get("forbidden_human_wait_sources") != ["runner_queue", "job_started"]:
        raise ContractError("forbidden wait sources drifted")
    if policy.get("control_actions") != ["pause", "deny", "abort", "revoke"]:
        raise ContractError("control action policy drifted")
    if any(policy.get(key) is not True for key in (
        "control_effect_requires_ack_and_readback", "checkpoint_resume_requires_new_human_decision",
        "revoke_requires_zero_new_actions", "human_override_priority",
    )):
        raise ContractError("fail-safe control policy drifted")
    if policy.get("fail_closed_on") != ["disconnect", "audit_failure", "ack_timeout"]:
        raise ContractError("fail-closed triggers drifted")
    activation = policy.get("activation")
    if not isinstance(activation, Mapping) or set(activation) != {
        "provider_available", "supplied_receipt_trust",
        "external_authenticated_receipt_required", "exact_evaluation_bytes_required",
        "exact_evaluation_digest_required", "local_activation_command_available",
        "local_grant_command_available", "local_resume_command_available",
    } or activation.get("provider_available") is not False or activation.get("supplied_receipt_trust") != "audit_only" or any(
        activation.get(key) is not True for key in (
            "external_authenticated_receipt_required", "exact_evaluation_bytes_required",
            "exact_evaluation_digest_required",
        )
    ) or any(activation.get(key) is not False for key in (
        "local_activation_command_available", "local_grant_command_available",
        "local_resume_command_available",
    )):
        raise ContractError("external activation boundary drifted")
    fallback = policy.get("current_fallback")
    expected_fallback = {
        "status": "not_admitted",
        "allowed_mode": "manual",
        "checkpoint_reduction_allowed": False,
        "max_write_concurrency": 1,
        "grant_executable": False,
        "mutation_allowed": False,
    }
    if not isinstance(fallback, Mapping) or set(fallback) != set(expected_fallback):
        raise ContractError("current fallback fields drifted")
    for field, expected in expected_fallback.items():
        actual = fallback[field]
        if type(actual) is not type(expected) or actual != expected:
            raise ContractError(f"current fallback {field} type/value drifted")
    objective = policy.get("objective_admission")
    expected_objective = {
        "dynamic_inspect_required": True,
        "readback_contract_required": True,
        "requested_concurrency_must_not_exceed_readback": True,
        "duplicated_admission_facts": "forbidden",
    }
    if not isinstance(objective, Mapping) or objective != expected_objective:
        raise ContractError("dynamic Objective admission consumption policy drifted")
    evidence = policy.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("collection_order") != "stable_id":
        raise ContractError("stable evidence identity policy drifted")

    expected_priorities = (
        "CANONICAL_CONTRACT_INVALID", "INPUT_CONTRACT_INVALID",
        "RISK_TIER_NOT_ELIGIBLE",
        "AUTHORITY_READBACK_FAILED", "AUTHORITY_PROVIDER_UNAVAILABLE",
        "AUTHORITY_READBACK_INVALID", "ROLE_RESPONSIBILITY_READBACK_FAILED",
        "ROLE_RESPONSIBILITY_PROOF_MISSING", "SEGREGATION_OF_DUTIES_FAILED",
        "COHORT_READBACK_FAILED", "HUMAN_BOTTLENECK_COHORT_MISSING",
        "COHORT_SELECTION_UNFROZEN", "COHORT_THRESHOLD_UNFROZEN",
        "COHORT_COVERAGE_INSUFFICIENT", "COHORT_DRIFTED",
        "HUMAN_WAIT_SOURCE_INVALID", "HUMAN_CALIBRATION_NOT_OBSERVED",
        "CONTROL_PROOF_MISSING", "CONTROL_ACK_READBACK_FAILED",
        "CONTROL_ACK_MISSING", "CONTROL_ACK_NOT_EXACT",
        "CONTROL_EFFECT_READBACK_FAILED", "CONTROL_EFFECT_READBACK_MISSING",
        "CONTROL_EFFECT_NOT_APPLIED", "CONTROL_EFFECT_NOT_INDEPENDENT",
        "CONTROL_IDENTITY_DRIFTED",
        "CONTROL_DISCONNECTED", "CONTROL_AUDIT_FAILED", "CONTROL_ACK_TIMEOUT",
        "REVOKE_ZERO_ACTIONS_UNPROVEN", "COMMERCIAL_AUTHORITY_READBACK_FAILED",
        "COMMERCIAL_AUTHORITY_NOT_CLOSED", "HUMAN_OVERRIDE_ACTIVE",
        "CHECKPOINT_READBACK_FAILED", "CHECKPOINT_POLICY_UNRESOLVED",
        "IMMUTABLE_CHECKPOINT_REMOVAL_FORBIDDEN",
        "RESUME_REQUIRES_NEW_HUMAN_DECISION", "OBJECTIVE_ADMISSION_BLOCKED",
        "EVALUATION_IDENTITY_FAILED", "REQUESTED_WRITE_CONCURRENCY_EXCEEDED",
        "WRITE_EXPANSION_NOT_ADMITTED",
        "ACTIVATION_READBACK_FAILED", "ACTIVATION_PROVIDER_UNAVAILABLE",
        "ACTIVATION_RECEIPT_INVALID", "ACTIVATION_RECEIPT_MISMATCH",
    )
    _string_list(
        value.get("blocker_priority"), "blocker_priority", exact=expected_priorities,
    )
    errors = value.get("errors")
    if not isinstance(errors, Mapping) or not errors:
        raise ContractError("typed errors missing")
    expected_boundary_errors = {
        "HOTL.CANONICAL_CONTRACT_INVALID": {
            "terminal": "blocked", "recovery": "repair_canonical_hotl_contract",
        },
        "HOTL.CONTRACT_INVALID": {
            "terminal": "blocked", "recovery": "repair_inspection_input_or_source",
        },
        "HOTL.OBJECTIVE_ADMISSION_BLOCKED": {
            "terminal": "blocked", "recovery": "keep_single_writer_and_reinspect_dynamic_s4",
        },
        "HOTL.EVALUATION_IDENTITY_FAILED": {
            "terminal": "blocked",
            "recovery": "repair_evidence_fingerprint_contract_or_serializer",
        },
    }
    for code, expected in expected_boundary_errors.items():
        if errors.get(code) != expected:
            raise ContractError(f"typed boundary error drifted: {code}")
    terminals = set(expected_closed["status"])
    for code, descriptor in errors.items():
        if not isinstance(code, str) or not code.startswith("HOTL.") or not isinstance(descriptor, Mapping):
            raise ContractError("typed error declaration invalid")
        if descriptor.get("terminal") not in terminals or not descriptor.get("recovery"):
            raise ContractError(f"typed error invalid: {code}")


def _load_yaml_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"{label} could not be loaded: {error}") from error
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} root must be a mapping")
    return value


@lru_cache(maxsize=1)
def _load_contract_cached() -> dict[str, Any]:
    value = _load_yaml_mapping(CONTRACT_PATH, "HOTL admission contract")
    validate_contract(value)
    return dict(value)


def load_contract() -> dict[str, Any]:
    return deepcopy(_load_contract_cached())


def schema_fields(name: str) -> tuple[str, ...]:
    return _required_fields(load_contract(), name)


def closed_values(name: str) -> tuple[str, ...]:
    return tuple(load_contract()["closed_sets"][name])


def validate_objective_s4_readback(payload: object) -> dict[str, Any]:
    try:
        return validate_objective_admission_readback(payload)
    except (ObjectiveContractError, OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"Objective S4 readback invalid: {error}") from error


def objective_blocked_s4_fallback() -> dict[str, Any]:
    try:
        return load_objective_blocked_admission_fallback()
    except (ObjectiveContractError, OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"Objective blocked S4 fallback invalid: {error}") from error


def objective_emergency_blocked_s4_fallback() -> dict[str, Any]:
    return load_objective_emergency_blocked_admission_fallback()


def validate_exact_fields(payload: Mapping[str, Any], schema_name: str) -> None:
    expected = set(schema_fields(schema_name))
    actual = set(payload)
    if actual != expected:
        raise ContractError(
            f"{schema_name} fields drifted: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def error_descriptor(code: str) -> dict[str, Any]:
    errors = load_contract()["errors"]
    value = errors.get(code) or errors["HOTL.CONTRACT_INVALID"]
    return dict(value)
