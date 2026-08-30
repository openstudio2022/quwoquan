"""Strict loader for the canonical workflow resolution contract."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/workflow_resolution_contract.yaml"
EXPECTED_WORKFLOWS = (
    "explore", "prd", "design", "dev", "continue", "plan-next", "review", "commit",
    "environment-ops", "content-production", "incident-inspection", "distill",
)
EXPLICIT_WORKFLOWS = EXPECTED_WORKFLOWS[:8]
AUTOMATIC_WORKFLOWS = EXPECTED_WORKFLOWS[8:]


class ContractError(ValueError):
    """Canonical workflow resolution contract is unavailable or drifted."""


def _strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{label} must be a string list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} contains duplicates")
    return list(value)


def _exact_fields(value: object, expected: list[str], label: str) -> None:
    if not isinstance(value, Mapping) or value.get("required_fields") != expected:
        raise ContractError(f"{label} fields drifted")


def validate_contract(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ContractError("contract root must be a mapping")
    if value.get("schema_id") != "workflow-resolution-contract" or value.get("schema_version") != 2:
        raise ContractError("contract identity/version is invalid")
    if value.get("owner_story") != "specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md":
        raise ContractError("contract owner story drifted")

    workflows = value.get("workflows")
    readiness = value.get("readiness_profiles")
    if not isinstance(workflows, Mapping) or tuple(workflows) != EXPECTED_WORKFLOWS:
        raise ContractError("canonical workflow closed set/order drifted")
    if not isinstance(readiness, Mapping) or tuple(readiness) != EXPECTED_WORKFLOWS:
        raise ContractError("readiness profile ownership drifted")
    commands: list[str] = []
    for workflow in EXPECTED_WORKFLOWS:
        definition = workflows[workflow]
        if not isinstance(definition, Mapping) or set(definition) != {
            "canonical_command", "host_explicit_entry_available", "automatic_only", "skill_ref", "natural_rules"
        }:
            raise ContractError(f"workflow {workflow} fields drifted")
        command = definition["canonical_command"]
        if command != f"/{workflow}" or definition["skill_ref"] != f".agents/skills/{workflow}/SKILL.md":
            raise ContractError(f"workflow {workflow} command/skill reference drifted")
        commands.append(command)
        explicit = workflow in EXPLICIT_WORKFLOWS
        if definition["host_explicit_entry_available"] is not explicit or definition["automatic_only"] is explicit:
            raise ContractError(f"workflow {workflow} host entry policy drifted")
        rules = definition["natural_rules"]
        if not isinstance(rules, list) or not rules:
            raise ContractError(f"workflow {workflow} needs declared natural rules")
        for rule in rules:
            if not isinstance(rule, Mapping) or set(rule) not in ({"id", "all_terms"}, {"id", "any_terms"}):
                raise ContractError(f"workflow {workflow} has invalid natural rule")
            if not isinstance(rule["id"], str) or not rule["id"]:
                raise ContractError(f"workflow {workflow} natural rule id invalid")
            selector = "all_terms" if "all_terms" in rule else "any_terms"
            _strings(rule[selector], f"workflows.{workflow}.{rule['id']}.{selector}")
    if len(commands) != len(set(commands)):
        raise ContractError("canonical commands must be unique")

    for workflow, definition in readiness.items():
        if not isinstance(definition, Mapping) or set(definition) != {"profile", "next_segment", "human_checkpoint"}:
            raise ContractError(f"readiness profile fields drifted: {workflow}")
        if not isinstance(definition["profile"], str) or not definition["profile"]:
            raise ContractError(f"readiness profile missing: {workflow}")
        if definition["next_segment"] != "PRE" or definition["human_checkpoint"] is not False:
            raise ContractError(f"routine readiness must not invent checkpoint: {workflow}")

    closed = value.get("closed_sets")
    expected_closed = {
        "input_mode": ["explicit", "natural_structured"],
        "input_category": ["explicit_command", "natural_text", "natural_structured_candidate", "natural_mixed"],
        "resolution_status": ["selected", "ask", "hold"],
        "ambiguity_terminal": ["none", "ask", "hold"],
        "next_segment": ["PRE", "hold", "terminal"],
        "owner_manifest_status": ["fresh", "missing", "stale"],
        "host_label": ["cursor", "codex", "unknown"],
        "host_adapter": ["cursor-command-shell", "cursor-natural-hook", "codex-repository-adapter", "direct-cli", "unknown"],
        "discovery_status": ["proven", "unproven"],
        "candidate_source": ["explicit_command", "rule", "structured_candidate"],
        "evidence_kind": ["exact_command", "contract_rule", "host_classification", "user_selection"],
        "evidence_reference": ["canonical_command", "host_classifier", "user_explicit_workflow_selection"],
        "confidence_basis": [
            "exact_canonical_command", "contract_rule_match", "structured_enumerated_evidence",
            "negated_mutation", "quoted_or_meta_mutation", "no_high_confidence_match", "unknown_candidate",
        ],
        "authorization_effect": ["none"],
    }
    if closed != expected_closed:
        raise ContractError("closed sets drifted")

    schemas = value.get("schemas")
    if not isinstance(schemas, Mapping):
        raise ContractError("schemas missing")
    _exact_fields(schemas.get("workflow_resolve_receipt"), [
        "schema_id", "schema_version", "result", "terminal_code", "recovery", "input_mode",
        "input_category", "input_digest", "input_length", "selected_workflow", "candidates", "rejections",
        "skill_ref", "skill_digest", "semantic_identity", "owner_manifest_ref",
        "owner_manifest_expected_target", "owner_manifest_expected_scope", "owner_manifest_status",
        "ambiguity_terminal", "readiness_profile", "next_segment", "authorization_effect",
        "human_interaction_binding_ref", "evidence_fingerprint", "host_audit", "receipt_digest",
    ], "workflow resolve receipt")
    _exact_fields(schemas.get("candidate"), ["workflow", "source", "confidence_basis", "evidence_kind", "evidence_digest", "evidence_ref"], "candidate")
    _exact_fields(schemas.get("rejection"), ["workflow", "code", "confidence_basis"], "rejection")
    _exact_fields(schemas.get("host_audit"), ["claimed_host", "adapter", "discovery_status", "discovery_evidence_ref"], "host audit")
    _exact_fields(schemas.get("owner_manifest_input"), ["ref", "expected_target", "expected_scope"], "owner manifest input")
    _exact_fields(schemas.get("structured_candidate"), ["workflow", "evidence"], "structured candidate")
    _exact_fields(schemas.get("structured_candidate_evidence"), ["kind", "digest", "reference"], "structured evidence")

    policy = value.get("resolution_policy")
    required_true = (
        "natural_rules_are_closed", "free_text_deterministic_claim_forbidden",
        "one_high_confidence_candidate_required", "unknown_candidate_precedes_ask",
        "manifest_failure_precedes_candidate_terminal", "owner_manifest_required_for_pre",
        "owner_manifest_caller_status_forbidden", "owner_manifest_ref_repo_relative_only",
        "owner_manifest_reject_symlink", "owner_manifest_validate_current_fingerprint",
        "stale_owner_manifest_blocks_pre", "dynamic_audience_reference_only",
    )
    if not isinstance(policy, Mapping) or any(policy.get(name) is not True for name in required_true):
        raise ContractError("fail-closed resolution policy drifted")
    if policy.get("routine_workflows_require_human_checkpoint") is not False or policy.get("resolver_grants_external_write_authority") is not False:
        raise ContractError("authority/checkpoint policy drifted")
    if policy.get("parity_fields") != ["selected_workflow", "skill_digest", "readiness_profile", "next_segment", "authorization_effect"]:
        raise ContractError("parity field declaration drifted")
    if policy.get("mutation_workflows") != ["dev", "commit", "environment-ops", "content-production"]:
        raise ContractError("mutation workflow policy drifted")
    for field in ("negation_markers", "meta_markers", "quote_pairs"):
        _strings(policy.get(field), f"resolution_policy.{field}")

    matrix = value.get("terminal_matrix")
    if not isinstance(matrix, Mapping) or tuple(matrix) != ("selected", "ask", "hold"):
        raise ContractError("terminal matrix drifted")
    errors = value.get("errors")
    if not isinstance(errors, Mapping) or tuple(errors)[0] != "WFR.SELECTED":
        raise ContractError("typed errors missing")
    recoveries: set[str] = set()
    for code, descriptor in errors.items():
        if not isinstance(code, str) or not code.startswith("WFR.") or not isinstance(descriptor, Mapping) or set(descriptor) != {"terminal", "recovery"}:
            raise ContractError("typed error descriptor invalid")
        if descriptor["terminal"] not in ("selected", "ask", "hold") or not isinstance(descriptor["recovery"], str) or not descriptor["recovery"]:
            raise ContractError(f"typed error descriptor drifted: {code}")
        if descriptor["recovery"] in recoveries:
            raise ContractError(f"typed recovery must be unique: {code}")
        recoveries.add(descriptor["recovery"])
    matrix_codes = {code for entry in matrix.values() for code in entry["terminal_codes"]}
    if matrix_codes != set(errors):
        raise ContractError("terminal matrix/error code closure drifted")

    projections = value.get("host_projections")
    if not isinstance(projections, Mapping) or projections.get("neutral_adapter") != "quwoquan_ops/cli/workflow_host_adapter.py":
        raise ContractError("neutral host adapter drifted")
    cursor = projections.get("cursor")
    codex = projections.get("codex")
    if not isinstance(cursor, Mapping) or cursor.get("explicit_workflows") != list(EXPLICIT_WORKFLOWS):
        raise ContractError("Cursor explicit projection policy drifted")
    if cursor.get("arbitrary_message_intercept_available") is not False or cursor.get("natural_discovery_status") != "unproven":
        raise ContractError("Cursor natural discovery must remain unproven")
    if not isinstance(codex, Mapping) or codex.get("native_explicit_entry_available") is not False or codex.get("arbitrary_message_intercept_available") is not False or codex.get("natural_discovery_status") != "unproven":
        raise ContractError("Codex discovery policy drifted")

    if value.get("human_interaction_binding_ref") != "quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding":
        raise ContractError("human interaction binding reference drifted")
    smoke = value.get("smoke_protocol")
    if not isinstance(smoke, Mapping) or smoke.get("status") != "OPEN" or smoke.get("claim_limit") != "local_contract_does_not_prove_real_cursor_or_codex_discovery":
        raise ContractError("real-host smoke OPEN boundary drifted")


@lru_cache(maxsize=1)
def _load_cached() -> dict[str, Any]:
    try:
        value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"canonical workflow resolution contract could not be loaded: {error}") from error
    validate_contract(value)
    return dict(value)


def load_contract() -> dict[str, Any]:
    return deepcopy(_load_cached())
