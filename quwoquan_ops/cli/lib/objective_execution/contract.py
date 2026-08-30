"""Objective execution canonical contract loader and strict v2 validator."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/objective_execution_contract.yaml"
BRANCH_POLICY_PATH = REPO_ROOT / "quwoquan_ops/policies/branch_policy.yaml"

_SCHEMA_VERSION = 2
_ADMISSION_STATUSES = ("admitted", "not_admitted", "blocked")
_ADMISSION_READBACK_FIELDS = (
    "status", "stage", "write_concurrency", "temporary_branch_allowed",
    "branch_policy_digest", "reason", "terminal",
)
_ADMISSION_TOP_LEVEL_FIELDS = (
    "source", "duplicated_allowed_branches", "readback_contract", "derivation",
    "writer_lease", "loser_effect_allowed", "loser_event_allowed",
    "reads_may_run_in_parallel",
)
_SUBJECT_STATES = {
    "objective": ("draft", "clarify", "approved", "planning", "executing", "review", "integrating", "observing", "accepted", "escalated", "aborted"),
    "increment": ("proposed", "authorized", "executing", "pending_readback", "verified", "integrated", "failed", "aborted"),
}
_TRANSITION_GRAPH = {
    "objective": (
        ("create_objective", None, "draft"),
        ("request_clarification", "draft", "clarify"),
        ("approve_objective", "clarify", "approved"),
        ("begin_planning", "approved", "planning"),
        ("begin_execution", "planning", "executing"),
        ("submit_review", "executing", "review"),
        ("request_rework", "review", "executing"),
        ("begin_integration", "review", "integrating"),
        ("begin_observation", "integrating", "observing"),
        ("accept_objective", "observing", "accepted"),
        ("escalate_objective", "executing", "escalated"),
        ("resolve_escalation", "escalated", "executing"),
        ("abort_objective", "executing", "aborted"),
        ("abort_objective", "escalated", "aborted"),
        ("reopen_objective", "accepted", "clarify"),
        ("restart_objective", "aborted", "draft"),
    ),
    "increment": (
        ("create_increment", None, "proposed"),
        ("authorize_increment", "proposed", "authorized"),
        ("start_increment", "authorized", "executing"),
        ("request_effect_readback", "executing", "pending_readback"),
        ("resume_effect_readback", "pending_readback", "executing"),
        ("verify_increment", "executing", "verified"),
        ("integrate_increment", "verified", "integrated"),
        ("fail_increment", "executing", "failed"),
        ("fail_increment", "pending_readback", "failed"),
        ("abort_increment", "proposed", "aborted"),
        ("abort_increment", "authorized", "aborted"),
        ("abort_increment", "executing", "aborted"),
        ("abort_increment", "pending_readback", "aborted"),
        ("abort_increment", "verified", "aborted"),
        ("retry_increment", "failed", "proposed"),
        ("restart_increment", "aborted", "proposed"),
    ),
}
_TERMINAL_STATES = {
    "objective": ("accepted", "aborted"),
    "increment": ("integrated", "failed", "aborted"),
}
_REOPENABLE_STATES = {
    "objective": ("accepted", "aborted"),
    "increment": ("failed", "aborted"),
}
_SCHEMA_FIELDS = {
    "transition_event": (
        "schema_version", "reducer_version", "event_id", "subject_kind", "subject_id",
        "event_kind", "action", "from_state", "to_state", "expected_head",
        "expected_generation", "generation", "previous_event_digest",
        "authority_receipt_ref", "effect_idempotency_key", "command_envelope_digest",
        "effect_id", "effect_readback", "occurred_at", "payload", "event_digest",
    ),
    "append_transition_command": (
        "subject_kind", "subject_id", "event_kind", "reducer_version", "action",
        "from_state", "to_state", "expected_head", "expected_generation",
        "authority_receipt_ref", "effect_idempotency_key", "command_envelope_digest",
        "effect_id", "effect_readback", "occurred_at", "payload",
    ),
    "command_envelope": (
        "schema_version", "subject_kind", "subject_id", "source_state", "target_state",
        "authority_receipt_ref", "expected_scope", "expected_evidence_fingerprint",
        "expected_decision_kind", "action", "effect_id", "effect_idempotency_key",
        "occurred_at", "payload", "authority_provider_kind",
        "authority_provider_receipt_ref", "authority_claims_digest",
        "authority_winner_idempotency_key", "authority_winner_command_digest",
        "authority_winner_previous_generation", "authority_winner_generation", "authority_chain_commit",
    ),
    "human_decision_recorded_payload": (
        "command_envelope", "command_envelope_digest", "authority_claims",
        "release_evidence_eligible", "provider_receipt_ref",
    ),
    "execution_readback": (
        "status", "subject_kind", "subject_id", "reduced_state", "head", "generation",
        "last_authority_receipt_ref", "last_effect_readback", "terminal",
    ),
    "authority_receipt_claims": (
        "receipt_id", "decision_id", "decision_unit_id", "actor_id", "actor_authenticated", "role", "scope", "expires_at",
        "evidence_fingerprint", "decision_kind", "actions", "provider_kind", "provider_version", "provider_commit",
        "contract_version", "issuer", "receipt_state", "receipt_previous_generation", "receipt_generation", "receipt_etag",
        "chain_commit", "winner_idempotency_key", "winner_command_digest",
    ),
    "authority_verification": (
        "provider_kind", "authenticated", "exact_bytes_verified", "claims",
        "release_evidence_eligible", "provider_receipt_ref",
    ),
    "execute_effect_command": (
        "subject_kind", "subject_id", "target_state", "authority_receipt_ref",
        "expected_scope", "expected_evidence_fingerprint", "expected_decision_kind",
        "action", "effect_id", "effect_idempotency_key", "occurred_at", "payload",
    ),
    "effect_readback": (
        "status", "effect_id", "idempotency_key", "exact_match", "provider_receipt_ref",
    ),
    "admission_readback": _ADMISSION_READBACK_FIELDS,
}
_ERROR_DESCRIPTORS = {
    "OEX.CONTRACT_INVALID": ("typed_blocker", "blocked", "repair_canonical_contract"),
    "OEX.JOURNAL_FAILED": ("typed_blocker", "blocked", "inspect_event_storage_io"),
    "OEX.JOURNAL_TAMPERED": ("typed_blocker", "blocked", "quarantine_and_restore_from_verified_authority"),
    "OEX.JOURNAL_RECOVERY_REQUIRED": ("typed_blocker", "blocked", "acquire_writer_lease_and_materialize_from_verified_events"),
    "OEX.CAS_CONFLICT": ("conflict", "conflict", "readback_then_reconcile_without_effect"),
    "OEX.WRITER_LEASE_CONFLICT": ("typed_blocker", "not_admitted", "readback_and_queue_without_effect"),
    "OEX.AUTHORITY_PROVIDER_UNAVAILABLE": ("typed_blocker", "blocked", "attach_authenticated_authority_provider"),
    "OEX.AUTHORITY_ABSENT": ("typed_blocker", "blocked", "obtain_authenticated_authority_receipt"),
    "OEX.AUTHORITY_INVALID": ("typed_blocker", "blocked", "repair_actor_role_scope_expiry_fingerprint_decision_or_action"),
    "OEX.AUTHORITY_CONSUME_UNKNOWN": ("pending_readback", "pending_readback", "reconcile_signed_winner_without_retry_or_local_mutation"),
    "OEX.AUTHORITY_CONSUME_CONFLICT": ("conflict", "conflict", "readback_signed_winner_without_local_mutation"),
    "OEX.AUTHORITY_WINNER_UNPROVEN": ("typed_blocker", "blocked", "repair_signed_consume_readback"),
    "OEX.AUTHORITY_PROJECTION_ONLY": ("typed_blocker", "blocked", "obtain_executable_authenticated_authority"),
    "OEX.TRANSITION_INVALID": ("typed_blocker", "blocked", "submit_action_allowed_by_versioned_transition_graph"),
    "OEX.PENDING_COMMAND_CONFLICT": ("conflict", "conflict", "resume_with_exact_persisted_command_envelope"),
    "OEX.EFFECT_IDENTITY_CONFLICT": ("pending_readback", "pending_readback", "reconcile_exact_persisted_effect_identity_without_retry"),
    "OEX.EFFECT_OUTCOME_UNKNOWN": ("pending_readback", "pending_readback", "reconcile_readback_without_retry"),
    "OEX.ADMISSION_BLOCKED": ("typed_blocker", "blocked", "repair_branch_policy_or_keep_single_writer"),
}
_EMERGENCY_BLOCKED_ADMISSION_FALLBACK = {
    "status": "blocked", "stage": "S4", "write_concurrency": 0,
    "temporary_branch_allowed": False, "branch_policy_digest": None,
    "reason": "dynamic_inspection_unavailable", "terminal": "OEX.ADMISSION_BLOCKED",
}
_EMERGENCY_CONTRACT_INVALID_TERMINAL = {
    "result": "typed_blocker", "code": "OEX.CONTRACT_INVALID", "terminal": "blocked",
    "recovery": "repair_canonical_contract",
}


class ObjectiveExecutionError(RuntimeError):
    """Typed fail-closed objective execution error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ContractError(ObjectiveExecutionError):
    def __init__(self, detail: str) -> None:
        super().__init__("OEX.CONTRACT_INVALID", detail)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must be a non-empty string list")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} contains duplicate values")
    return value


def _require_exact_mapping(value: object, expected: Mapping[str, object], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ContractError(f"{label} fields drifted")
    for field, expected_value in expected.items():
        actual = value[field]
        if type(actual) is not type(expected_value) or actual != expected_value:
            raise ContractError(f"{label}.{field} value/type drifted")
    return value


def _validate_schemas(value: Mapping[str, Any]) -> None:
    schemas = value.get("schemas")
    if not isinstance(schemas, Mapping) or set(schemas) != set(_SCHEMA_FIELDS):
        raise ContractError("schemas v2 closed set drifted")
    for name, expected in _SCHEMA_FIELDS.items():
        descriptor = schemas.get(name)
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"required_fields"}:
            raise ContractError(f"schema {name} descriptor fields drifted")
        if tuple(_string_list(descriptor["required_fields"], f"schemas.{name}.required_fields")) != expected:
            raise ContractError(f"schemas.{name}.required_fields v2 wire drifted")


def _validate_transition_graph(value: Mapping[str, Any], closed: Mapping[str, Any]) -> None:
    graph = value.get("transition_graph")
    if not isinstance(graph, Mapping) or set(graph) != {
        "graph_version", "reducer_version", "terminal_reopen_policy", "subjects",
    }:
        raise ContractError("transition_graph fields drifted")
    if graph.get("graph_version") != 1 or graph.get("reducer_version") != 1 or graph.get("terminal_reopen_policy") != "explicit_edges_only":
        raise ContractError("transition graph identity/version drifted")
    subjects = graph.get("subjects")
    if not isinstance(subjects, Mapping) or tuple(subjects) != tuple(_SUBJECT_STATES):
        raise ContractError("transition graph subject order/closed set drifted")
    actions: list[str] = []
    for subject_kind, expected_states in _SUBJECT_STATES.items():
        if tuple(_string_list(closed.get(f"{subject_kind}_state"), f"closed_sets.{subject_kind}_state")) != expected_states:
            raise ContractError(f"closed_sets.{subject_kind}_state v2 closed set drifted")
        descriptor = subjects.get(subject_kind)
        if not isinstance(descriptor, Mapping) or set(descriptor) != {
            "states_source", "initial_state", "terminal_states", "reopenable_terminal_states", "transitions",
        }:
            raise ContractError(f"transition_graph.subjects.{subject_kind} fields drifted")
        if descriptor["states_source"] != f"closed_sets.{subject_kind}_state" or descriptor["initial_state"] is not None:
            raise ContractError(f"transition_graph.subjects.{subject_kind} source/initial drifted")
        if tuple(descriptor["terminal_states"]) != _TERMINAL_STATES[subject_kind] or tuple(descriptor["reopenable_terminal_states"]) != _REOPENABLE_STATES[subject_kind]:
            raise ContractError(f"transition_graph.subjects.{subject_kind} terminal semantics drifted")
        raw = descriptor.get("transitions")
        if not isinstance(raw, list):
            raise ContractError(f"transition_graph.subjects.{subject_kind}.transitions must be a list")
        actual: list[tuple[str, str | None, str]] = []
        for index, transition in enumerate(raw):
            if not isinstance(transition, Mapping) or set(transition) != {"action", "from_state", "to_state"}:
                raise ContractError(f"transition {subject_kind}[{index}] fields drifted")
            action = transition["action"]
            from_state = transition["from_state"]
            to_state = transition["to_state"]
            if not isinstance(action, str) or from_state is not None and from_state not in expected_states or to_state not in expected_states:
                raise ContractError(f"transition {subject_kind}[{index}] contains illegal values")
            actual.append((action, from_state, to_state))
            actions.append(action)
        if tuple(actual) != _TRANSITION_GRAPH[subject_kind] or len(actual) != len(set(actual)):
            raise ContractError(f"transition graph {subject_kind} graph_version=1 edges drifted")
        for action, from_state, _to_state in actual:
            if from_state in _TERMINAL_STATES[subject_kind] and from_state not in _REOPENABLE_STATES[subject_kind]:
                raise ContractError(f"terminal {subject_kind} state has an undeclared reopen edge")
    if tuple(_string_list(closed.get("transition_action"), "closed_sets.transition_action")) != tuple(dict.fromkeys(actions)):
        raise ContractError("closed_sets.transition_action drifted from versioned graph")


def _validate_admission_readback_contract(admission: Mapping[str, Any], closed_statuses: tuple[str, ...]) -> None:
    readback = admission.get("readback_contract")
    if not isinstance(readback, Mapping) or set(readback) != {"schema", "exact_fields_required", "stage", "status_source", "statuses"}:
        raise ContractError("admission.readback_contract fields drifted")
    if readback.get("schema") != "admission_readback" or readback.get("exact_fields_required") is not True or readback.get("stage") != "S4" or readback.get("status_source") != "closed_sets.admission_status":
        raise ContractError("admission readback identity/source drifted")
    statuses = readback.get("statuses")
    if not isinstance(statuses, Mapping) or tuple(statuses) != closed_statuses:
        raise ContractError("admission readback statuses drifted")
    expected = {
        "admitted": {"reason_policy": "fixed", "reason": "temporary_execution_lifecycle_admitted", "terminal": "admitted", "write_concurrency": 2, "temporary_branch_allowed": True, "branch_policy_digest": "sha256_required"},
        "not_admitted": {"reason_policy": "fixed", "reason": "temporary_execution_lifecycle_not_admitted", "terminal": "not_admitted", "write_concurrency": 1, "temporary_branch_allowed": False, "branch_policy_digest": "sha256_required"},
    }
    for status, mapping in expected.items():
        _require_exact_mapping(statuses.get(status), mapping, f"admission.readback_contract.statuses.{status}")
    blocked = statuses.get("blocked")
    if not isinstance(blocked, Mapping) or set(blocked) != {"reason_policy", "reason_constraints", "fallback_reason", "terminal", "write_concurrency", "temporary_branch_allowed", "branch_policy_digest"}:
        raise ContractError("admission readback blocked fields drifted")
    _require_exact_mapping(blocked["reason_constraints"], {"nonempty": True, "trimmed": True, "nul_forbidden": True}, "admission blocked reason constraints")
    expected_blocked = {"reason_policy": "dynamic_detail", "fallback_reason": "dynamic_inspection_unavailable", "terminal": "OEX.ADMISSION_BLOCKED", "write_concurrency": 0, "temporary_branch_allowed": False, "branch_policy_digest": None}
    for field, expected_value in expected_blocked.items():
        if type(blocked.get(field)) is not type(expected_value) or blocked.get(field) != expected_value:
            raise ContractError(f"admission readback blocked.{field} drifted")


def validate_contract(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ContractError("contract root must be a mapping")
    expected_top = {"schema_id", "schema_version", "owner_story", "human_authority_contract", "branch_policy_source", "authority_boundaries", "closed_sets", "transition_graph", "schemas", "commands", "journal", "authority_port", "admission", "errors"}
    if set(value) != expected_top or value.get("schema_id") != "objective-execution-contract" or value.get("schema_version") != _SCHEMA_VERSION:
        raise ContractError("contract top-level identity/version fields drifted")
    if value.get("owner_story") != "specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md" or value.get("branch_policy_source") != "quwoquan_ops/policies/branch_policy.yaml" or value.get("human_authority_contract") != "quwoquan_ops/policies/human_agent_delivery_contract.yaml":
        raise ContractError("contract owner/source drifted")
    boundaries = value.get("authority_boundaries")
    expected_boundaries = {"local_journal_authority": "execution_state_only", "human_identity_authority": "external_authenticated_provider", "local_json_is_human_authority": False, "production_provider_default": "unavailable", "test_provider": {"provider_kind": "test", "release_evidence_eligible": False}}
    _require_exact_mapping(boundaries, expected_boundaries, "authority_boundaries")
    closed = value.get("closed_sets")
    if not isinstance(closed, Mapping) or set(closed) != {"subject_kind", "objective_state", "increment_state", "transition_event_kind", "transition_action", "readback_status", "effect_readback_status", "admission_status", "command_result"}:
        raise ContractError("closed_sets fields drifted")
    expected_closed = {
        "subject_kind": ("objective", "increment"), "transition_event_kind": ("human_decision_recorded", "state_transition_committed"),
        "readback_status": ("present", "absent", "failed"), "effect_readback_status": ("applied", "not_applied", "unknown"),
        "admission_status": _ADMISSION_STATUSES, "command_result": ("committed", "duplicate", "conflict", "typed_blocker", "pending_readback", "recovered"),
    }
    for name, expected in expected_closed.items():
        if tuple(_string_list(closed.get(name), f"closed_sets.{name}")) != expected:
            raise ContractError(f"closed_sets.{name} v2 closed set drifted")
    _validate_transition_graph(value, closed)
    _validate_schemas(value)
    commands = value.get("commands")
    expected_commands = {
        "append_transition": {"order": ["acquire_writer_lease_capability", "validate_inode_scope", "recover_derived_materialization", "compare_cas", "write_private_staging", "fsync_staging", "exclusive_publish_event", "fsync_events_directory", "materialize_snapshot", "materialize_head"], "cas_fields": ["expected_head", "expected_generation"], "idempotency_fields": ["subject_kind", "subject_id", "event_kind", "effect_idempotency_key"]},
        "recover_materialization": {"mutation": True, "writer_lease_required": True, "source": "complete_verified_event_chain", "writes": ["snapshot", "head"]},
        "execute_authorized_effect": {"order": ["query_signed_authority_wrapper", "verify_claim_and_state_bindings", "validate_versioned_transition", "consume_authority_cas", "verify_signed_consume_winner", "append_human_decision_recorded", "invoke_effect_once", "readback_effect", "append_state_transition_committed"], "pending_identity_fields": ["subject_kind", "subject_id", "source_state", "target_state", "action", "payload", "authority_receipt_ref", "expected_scope", "expected_evidence_fingerprint", "expected_decision_kind", "authority_provider_kind", "authority_provider_receipt_ref", "authority_claims_digest", "authority_winner_idempotency_key", "authority_winner_command_digest", "authority_winner_previous_generation", "authority_winner_generation", "authority_chain_commit", "effect_id", "effect_idempotency_key"], "pending_identity_match": "exact_command_envelope_digest", "readback_effect_id_source": "persisted_human_decision_recorded", "empty_effect_id_readback_allowed": False, "unknown_effect_outcome": "pending_readback", "retry_unknown_effect": False},
        "hosted_consume": {"query_before_mutation": True, "validate_transition_before_mutation": True, "persist_intent_before_consume": False, "strong_if_match_required": True, "mutation_attempts": 1, "unknown_outcome": "reconcile_only", "signed_winner_required": True, "winner_fields": ["receipt_state", "receipt_previous_generation", "receipt_generation", "receipt_etag", "receipt_id", "decision_id", "decision_unit_id", "provider_kind", "provider_version", "provider_commit", "contract_version", "issuer", "chain_commit", "winner_idempotency_key", "winner_command_digest"], "local_journal_allowed_before_winner": False, "effect_allowed_before_winner": False},
        "inspect_admission": {"mutation": False},
        "read_execution_state": {"mutation": False, "materialization_allowed": False},
    }
    _require_exact_mapping(commands, expected_commands, "commands")
    journal = value.get("journal")
    expected_journal = {
        "append_only": True,
        "event_atomic_write": "private_staging_fsync_exclusive_publish_fsync_directory",
        "exclusive_publish": {"darwin": "renameatx_np_RENAME_EXCL", "unsupported_platform": "fail_closed", "overwrite_fallback_allowed": False},
        "derived_atomic_write": "descriptor_relative_fsync_replace_fsync_directory",
        "storage_trust": {"owner": "current_effective_uid", "directory_mode": "0700", "file_mode": "0600", "file_type": "regular", "file_link_count": 1, "symlink_policy": "reject_every_ancestor_and_component", "path_identity": "retained_dirfd_and_inode", "mkdir_durability": "fsync_parent_then_new_directory", "lease_capability": "internal_unforgeable_root_subject_inode_scoped", "public_lease_bypass_argument": "forbidden", "staging_authoritative": False, "staging_cleanup_requires_validated_lease": True},
        "hash_chain": "sha256_canonical_json", "cas": "expected_head_and_generation",
        "reducer": "deterministic_versioned", "event_chain_authority": True,
        "derived_artifacts": ["snapshot", "head"],
        "derived_drift_terminal": "OEX.JOURNAL_RECOVERY_REQUIRED",
        "recovery_requires_writer_lease": True,
        "recovery_source": "complete_verified_event_chain",
        "legal_crash_failpoints": ["after_staging_create", "after_staging_partial_write", "after_staging_fsync", "before_event_publish", "after_event_publish_before_directory_fsync", "after_event_fsync", "after_snapshot_materialized", "after_head_materialized"],
        "tamper_conditions": ["unsafe_storage_node", "inode_identity_drift", "event_gap", "event_digest_drift", "event_identity_drift", "event_hash_chain_drift", "reducer_version_drift"],
        "output_root": ".qwq_output/env/repo/local/objective-execution/process",
    }
    _require_exact_mapping(journal, expected_journal, "journal")
    authority = value.get("authority_port")
    expected_authority = {"exact_bytes_required": True, "verifier_injected": True, "checks": ["actor_authenticated", "actor_id", "role", "scope", "expiry", "evidence_fingerprint", "decision_kind", "action", "issuer", "provider_version", "provider_commit", "contract_version", "state", "etag", "chain_commit", "winner_identity"], "projection_authorization_grant": {"authenticated": False, "executable": False, "mutation_allowed": False}, "provider_unavailable": {"terminal_code": "OEX.AUTHORITY_PROVIDER_UNAVAILABLE", "mutation_allowed": False}}
    _require_exact_mapping(authority, expected_authority, "authority_port")
    admission = value.get("admission")
    if not isinstance(admission, Mapping) or set(admission) != set(_ADMISSION_TOP_LEVEL_FIELDS):
        raise ContractError("admission top-level fields drifted")
    if admission.get("source") != value["branch_policy_source"] or admission.get("duplicated_allowed_branches") != "forbidden" or admission.get("writer_lease") != "exclusive_nonblocking":
        raise ContractError("admission owner/single-writer invariants drifted")
    for field, expected in {"loser_effect_allowed": False, "loser_event_allowed": False, "reads_may_run_in_parallel": True}.items():
        if type(admission.get(field)) is not bool or admission.get(field) is not expected:
            raise ContractError(f"admission.{field} type/value drifted")
    expected_causes = ["pull_request_prefix_declared", "isolated_writer_branch", "declared_promotion_path", "mandatory_cleanup_after_promotion_or_abort", "concurrency_evidence_required"]
    if admission.get("derivation") != {"admitted_requires_all": expected_causes}:
        raise ContractError("admission derivation drifted")
    _validate_admission_readback_contract(admission, _ADMISSION_STATUSES)
    errors = value.get("errors")
    if not isinstance(errors, Mapping) or set(errors) != set(_ERROR_DESCRIPTORS):
        raise ContractError("typed errors v2 closed set drifted")
    for code, expected in _ERROR_DESCRIPTORS.items():
        _require_exact_mapping(errors.get(code), {"result": expected[0], "terminal": expected[1], "recovery": expected[2]}, f"typed error {code}")


@lru_cache(maxsize=1)
def _load_contract_cached() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_contract(value)
    return dict(value)


def load_contract() -> dict[str, Any]:
    return deepcopy(_load_contract_cached())


def schema_fields(name: str) -> tuple[str, ...]:
    contract = load_contract()
    schemas = contract["schemas"]
    if name not in schemas:
        raise ContractError(f"missing schema {name}")
    return tuple(schemas[name]["required_fields"])


def validate_exact_fields(payload: Mapping[str, Any], schema_name: str) -> None:
    expected = set(schema_fields(schema_name))
    actual = set(payload)
    if actual != expected:
        raise ContractError(f"{schema_name} fields drifted: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")


def canonical_payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def require_schema_v2(payload: Mapping[str, Any], label: str) -> None:
    if type(payload.get("schema_version")) is not int or payload.get("schema_version") != _SCHEMA_VERSION:
        raise ContractError(f"{label}.schema_version must be {_SCHEMA_VERSION}; legacy v1 is not accepted")


def validate_command_envelope(payload: Mapping[str, Any]) -> None:
    validate_exact_fields(payload, "command_envelope")
    require_schema_v2(payload, "command_envelope")
    if payload.get("subject_kind") not in closed_values("subject_kind"):
        raise ContractError("command_envelope.subject_kind is outside the closed set")
    for field in (
        "subject_id", "authority_receipt_ref", "expected_evidence_fingerprint",
        "expected_decision_kind", "action", "effect_id", "effect_idempotency_key",
        "occurred_at", "authority_provider_kind", "authority_provider_receipt_ref",
        "authority_winner_idempotency_key", "authority_winner_command_digest", "authority_chain_commit",
    ):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ContractError(f"command_envelope.{field} must be a non-empty string")
    if not isinstance(payload.get("expected_scope"), Mapping) or not isinstance(payload.get("payload"), Mapping):
        raise ContractError("command_envelope scope/payload must be objects")
    _validate_sha256(payload.get("authority_claims_digest"), "command_envelope.authority_claims_digest")
    _validate_sha256(payload.get("authority_winner_command_digest"), "command_envelope.authority_winner_command_digest")
    _validate_sha256(payload.get("authority_chain_commit"), "command_envelope.authority_chain_commit")
    if type(payload.get("authority_winner_previous_generation")) is not int or payload["authority_winner_previous_generation"] < 1:
        raise ContractError("command_envelope.authority_winner_previous_generation must prove the CAS source")
    if type(payload.get("authority_winner_generation")) is not int or payload["authority_winner_generation"] != payload["authority_winner_previous_generation"] + 1:
        raise ContractError("command_envelope.authority_winner_generation must prove one CAS transition")


def validate_authority_receipt_claims(payload: Mapping[str, Any]) -> None:
    validate_exact_fields(payload, "authority_receipt_claims")
    for field in ("receipt_id", "decision_id", "decision_unit_id", "actor_id", "role", "expires_at", "evidence_fingerprint", "decision_kind", "provider_kind", "provider_version", "provider_commit", "contract_version", "issuer", "receipt_state", "receipt_etag", "chain_commit"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ContractError(f"authority_receipt_claims.{field} must be a non-empty string")
    if type(payload.get("actor_authenticated")) is not bool:
        raise ContractError("authority_receipt_claims.actor_authenticated must be bool")
    if not isinstance(payload.get("scope"), Mapping):
        raise ContractError("authority_receipt_claims.scope must be an object")
    _string_list(payload.get("actions"), "authority_receipt_claims.actions")
    if payload["receipt_id"] != payload["decision_id"]:
        raise ContractError("authority_receipt_claims receipt/decision identity mismatch")
    if type(payload.get("receipt_previous_generation")) is not int or payload["receipt_previous_generation"] < 0:
        raise ContractError("authority_receipt_claims.receipt_previous_generation is invalid")
    if type(payload.get("receipt_generation")) is not int or payload["receipt_generation"] < 1:
        raise ContractError("authority_receipt_claims.receipt_generation is invalid")


def validate_effect_readback(payload: Mapping[str, Any]) -> None:
    validate_exact_fields(payload, "effect_readback")
    if payload.get("status") not in closed_values("effect_readback_status"):
        raise ContractError("effect_readback.status is outside the closed set")
    for field in ("effect_id", "idempotency_key", "provider_receipt_ref"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ContractError(f"effect_readback.{field} must be a non-empty string")
    if type(payload.get("exact_match")) is not bool:
        raise ContractError("effect_readback.exact_match must be bool")


def closed_values(name: str) -> tuple[str, ...]:
    return tuple(load_contract()["closed_sets"][name])


def reducer_version() -> int:
    return int(load_contract()["transition_graph"]["reducer_version"])


def transition_graph(subject_kind: str) -> dict[str, Any]:
    subjects = load_contract()["transition_graph"]["subjects"]
    if subject_kind not in subjects:
        raise ContractError(f"unknown subject kind {subject_kind}")
    return deepcopy(subjects[subject_kind])


def transition_allowed(subject_kind: str, action: str, from_state: str | None, to_state: str) -> bool:
    descriptor = transition_graph(subject_kind)
    return any(edge == {"action": action, "from_state": from_state, "to_state": to_state} for edge in descriptor["transitions"])


def require_transition(subject_kind: str, action: str, from_state: str | None, to_state: object) -> None:
    if not isinstance(to_state, str) or not transition_allowed(subject_kind, action, from_state, to_state):
        raise ObjectiveExecutionError("OEX.TRANSITION_INVALID", f"illegal graph_version=1 transition {subject_kind}:{from_state!r} --{action}--> {to_state!r}")


def admission_readback_contract() -> dict[str, Any]:
    return deepcopy(load_contract()["admission"]["readback_contract"])


def _validate_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ContractError(f"{label} must be a sha256 digest")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ContractError(f"{label} must be a lowercase sha256 digest")
    return value


def validate_admission_readback(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError("admission_readback must be an object")
    descriptor = admission_readback_contract()
    expected_fields = set(schema_fields(descriptor["schema"]))
    actual_fields = set(payload)
    if actual_fields != expected_fields:
        raise ContractError(f"admission_readback fields drifted: missing={sorted(expected_fields - actual_fields)}, extra={sorted(actual_fields - expected_fields)}")
    if type(payload["stage"]) is not str or payload["stage"] != descriptor["stage"]:
        raise ContractError("admission_readback.stage must be S4")
    status = payload["status"]
    statuses = descriptor["statuses"]
    if not isinstance(status, str) or status not in statuses:
        raise ContractError(f"admission_readback.status must be one of {list(statuses)}")
    policy = statuses[status]
    if type(payload["write_concurrency"]) is not int or payload["write_concurrency"] != policy["write_concurrency"]:
        raise ContractError("admission_readback status/write_concurrency is inconsistent")
    if type(payload["temporary_branch_allowed"]) is not bool or payload["temporary_branch_allowed"] is not policy["temporary_branch_allowed"]:
        raise ContractError("admission_readback status/temporary_branch_allowed is inconsistent")
    digest = payload["branch_policy_digest"]
    if policy["branch_policy_digest"] == "sha256_required":
        _validate_sha256(digest, "admission_readback.branch_policy_digest")
    elif digest is not None:
        raise ContractError("admission_readback blocked digest must be null")
    reason = payload["reason"]
    if not isinstance(reason, str) or not reason:
        raise ContractError("admission_readback.reason must be a non-empty string")
    if policy["reason_policy"] == "fixed":
        if reason != policy["reason"]:
            raise ContractError("admission_readback status/reason is inconsistent")
    elif reason.strip() != reason or "\x00" in reason:
        raise ContractError("admission_readback blocked reason is unsafe")
    if not isinstance(payload["terminal"], str) or payload["terminal"] != policy["terminal"]:
        raise ContractError("admission_readback status/terminal is inconsistent")
    return {field: payload[field] for field in schema_fields(descriptor["schema"])}


def admission_readback(status: str, *, branch_policy_digest: str | None = None, detail: str = "") -> dict[str, Any]:
    descriptor = admission_readback_contract()
    statuses = descriptor["statuses"]
    if status not in statuses:
        raise ContractError(f"unknown admission status: {status}")
    policy = statuses[status]
    reason = policy.get("reason")
    if policy["reason_policy"] == "dynamic_detail":
        reason = detail or policy["fallback_reason"]
    return validate_admission_readback({"status": status, "stage": descriptor["stage"], "write_concurrency": policy["write_concurrency"], "temporary_branch_allowed": policy["temporary_branch_allowed"], "branch_policy_digest": branch_policy_digest, "reason": reason, "terminal": policy["terminal"]})


def blocked_admission_fallback() -> dict[str, Any]:
    return admission_readback("blocked")


def emergency_blocked_admission_fallback() -> dict[str, Any]:
    return deepcopy(_EMERGENCY_BLOCKED_ADMISSION_FALLBACK)


def emergency_contract_invalid_terminal(detail: str = "") -> dict[str, Any]:
    result = deepcopy(_EMERGENCY_CONTRACT_INVALID_TERMINAL)
    result["detail"] = detail
    return result


def typed_result(code: str, *, detail: str = "") -> dict[str, Any]:
    errors = load_contract()["errors"]
    actual_code = code if code in errors else "OEX.CONTRACT_INVALID"
    descriptor = errors[actual_code]
    return {"result": descriptor["result"], "code": actual_code, "terminal": descriptor["terminal"], "recovery": descriptor["recovery"], "detail": detail}
