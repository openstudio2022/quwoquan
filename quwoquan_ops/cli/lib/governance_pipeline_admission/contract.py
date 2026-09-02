"""Strict loader for governance pipeline observe-only admission contract."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/governance_pipeline_admission_contract.yaml"


class GovernancePipelineAdmissionError(ValueError):
    """Fail-closed governance pipeline inspection error."""


class ContractError(GovernancePipelineAdmissionError):
    """Canonical contract or inspection input drift."""


class EvidenceAdapterError(ContractError):
    """Adapter failure with independent evidence validity dimensions."""

    def __init__(
        self,
        detail: str,
        *,
        schema_valid: bool,
        fresh: bool,
        fingerprint_match: bool,
    ) -> None:
        super().__init__(detail)
        self.schema_valid = schema_valid
        self.fresh = fresh
        self.fingerprint_match = fingerprint_match

    @classmethod
    def schema(cls, detail: str) -> "EvidenceAdapterError":
        return cls(detail, schema_valid=False, fresh=True, fingerprint_match=True)

    @classmethod
    def stale(cls, detail: str) -> "EvidenceAdapterError":
        return cls(detail, schema_valid=True, fresh=False, fingerprint_match=True)

    @classmethod
    def identity(cls, detail: str) -> "EvidenceAdapterError":
        return cls(detail, schema_valid=True, fresh=True, fingerprint_match=False)


def contract_failure(detail: str) -> dict[str, Any]:
    return {
        "result": "typed_blocker", "error_code": "GPA.CANONICAL_CONTRACT_INVALID",
        "terminal": "blocked", "recovery": "repair_canonical_governance_pipeline_contract",
        "detail": detail, "blockers": ["CANONICAL_CONTRACT_INVALID"],
    }


def _strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ContractError(f"{label} must be a string list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} contains duplicates")
    return list(value)


def _required_fields(contract: Mapping[str, Any], name: str) -> tuple[str, ...]:
    schemas = contract.get("schemas")
    if not isinstance(schemas, Mapping) or not isinstance(schemas.get(name), Mapping):
        raise ContractError(f"missing schema {name}")
    return tuple(_strings(schemas[name].get("required_fields"), f"schemas.{name}.required_fields"))


def _source_refs(value: Mapping[str, Any], key: str) -> list[str]:
    refs = _strings(value.get(key), f"hosted_authority_source.{key}")
    if any(Path(ref).is_absolute() or ".." in Path(ref).parts for ref in refs):
        raise ContractError(f"hosted_authority_source.{key} must contain repository-relative paths")
    return refs


def validate_contract(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ContractError("contract root must be a mapping")
    if value.get("schema_id") != "governance-pipeline-admission-contract" or value.get("schema_version") != 3:
        raise ContractError("contract identity/version is invalid")
    owner = "specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md"
    if value.get("owner_story") != owner:
        raise ContractError("owner story drifted")
    expected_sources = {
        "local_readiness_source": "quwoquan_ops/policies/local_readiness_contract.yaml",
        "human_eval_source": "quwoquan_ops/policies/evals/human_agent_delivery_interaction_v1.yaml",
        "human_authority_source": "quwoquan_ops/policies/human_agent_delivery_contract.yaml",
        "objective_source": "quwoquan_ops/policies/objective_execution_contract.yaml#admission.readback_contract",
        "hotl_source": "quwoquan_ops/policies/hotl_admission_contract.yaml",
    }
    for field, expected in expected_sources.items():
        if value.get(field) != expected:
            raise ContractError(f"{field} drifted")
    hosted = value.get("hosted_authority_source")
    if not isinstance(hosted, Mapping) or set(hosted) != {
        "owner_story", "service_contract_refs", "adapter_implementation_refs",
        "service_implementation_refs", "portal_implementation_refs", "live_provider_ref",
    }:
        raise ContractError("hosted authority source shape drifted")
    if hosted.get("owner_story") != "specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md":
        raise ContractError("hosted authority owner story drifted")
    for key in ("service_contract_refs", "adapter_implementation_refs", "service_implementation_refs", "portal_implementation_refs"):
        _source_refs(hosted, key)
    if hosted.get("live_provider_ref") is not None:
        raise ContractError("live provider must remain unset until external provider exists")
    activation_source = value.get("activation_authority_source")
    if not isinstance(activation_source, Mapping) or activation_source != {
        "provider_ref": None, "local_inspect_may_activate": False,
    }:
        raise ContractError("activation authority boundary drifted")
    boundaries = value.get("authority_boundaries")
    if not isinstance(boundaries, Mapping) or any(boundaries.get(field) is not False for field in (
        "evaluator_mutation", "creates_authority", "production_ready_claim", "commercial_ready_claim",
        "hotl_admitted_claim", "prod_mutation", "hotl_mutation", "local_fixture_release_evidence",
    )):
        raise ContractError("zero-authority/zero-mutation boundary drifted")
    closed = value.get("closed_sets")
    expected_closed = {
        "admission_status": ["blocked", "not_admitted", "eligible_observe_only", "observe_only"],
        "allowed_mode": ["manual", "observe_only"],
        "evidence_status": ["present", "absent", "failed"],
        "provider_kind": ["absent", "source_inspection", "local_fixture", "local_runtime", "hosted_code", "hosted_integration", "authenticated_external"],
        "metric_kind": ["histogram", "gauge", "counter"],
        "metric_unit": ["milliseconds", "ratio", "count"],
        "activation_verification_status": ["present", "absent", "failed"],
    }
    if not isinstance(closed, Mapping):
        raise ContractError("closed sets missing")
    for name, expected in expected_closed.items():
        if closed.get(name) != expected:
            raise ContractError(f"closed_sets.{name} drifted")
    _strings(closed.get("evidence_result"), "closed_sets.evidence_result")
    expected_schemas = {
        "inspection_input": ("subject", "evidence", "human_calibration_readback", "activation_receipt"),
        "subject": ("subject_id", "scope_id", "candidate_id", "evidence_fingerprint"),
        "evidence_readback": ("status", "schema_valid", "fresh", "fingerprint_match", "result", "provider_kind", "release_evidence_eligible", "detail", "receipt_ref", "receipt_bytes_sha256", "verified_at", "provider_timestamp", "candidate_id", "scope_id", "verifier_id"),
        "activation_receipt": ("status", "receipt_id", "evaluation_digest", "evaluation_bytes_sha256"),
        "activation_verification": ("status", "provider_kind", "authenticated", "exact_bytes_verified", "release_evidence_eligible", "receipt_id", "evaluation_digest", "evaluation_bytes_sha256"),
        "observation_metric": ("metric_id", "kind", "unit", "dimensions", "sensitive_fields"),
        "inspection_result": ("schema_id", "schema_version", "result", "error_code", "detail", "subject", "status", "allowed_mode", "production_ready", "commercial_ready", "hotl_admitted", "mutation_allowed", "prod_mutation_allowed", "hotl_mutation_allowed", "max_write_concurrency", "activation_required", "activation_receipt_ref", "evaluation_digest", "evaluation_bytes_sha256", "blockers", "evidence_summary", "objective_s4_readback", "external_effect_policy", "observation_metrics", "external_open"),
        "contract_terminal": ("result", "error_code", "terminal", "recovery", "detail", "blockers"),
        "evidence_bundle": ("schema_id", "schema_version", "subject_fingerprint", "subject_fingerprint_receipt", "assembled_at", "receipts"),
        "evidence_bundle_receipts": ("owner_manifest", "local_scope_ready", "local_release_ready", "review_plan", "named_evidence", "review_consolidation", "handoff", "human_calibration", "objective_inspect", "hotl_inspect", "hosted_authority_source", "external"),
        "bundle_receipt": ("provider_id", "receipt_ref", "exact_bytes_base64"),
    }
    schemas = value.get("schemas")
    if not isinstance(schemas, Mapping) or set(schemas) != set(expected_schemas):
        raise ContractError("schemas closed set drifted")
    for name, fields in expected_schemas.items():
        if _required_fields(value, name) != fields:
            raise ContractError(f"schemas.{name}.required_fields drifted")
    layers = value.get("evidence_layers")
    expected_layers = {
        "owner_manifest", "local_scope_ready", "local_release_ready", "review_terminal",
        "human_eval_machine_baseline", "human_calibration", "hosted_authority_code",
        "hosted_authority_integration", "hosted_authority_live", "handoff_freshness",
        "objective_readback", "objective_recovery", "effect_allowlist", "effect_readback",
        "portal_test", "portal_build", "portal_uat", "hosted_ci_clean_sha", "environment",
        "device", "uat", "commercial", "prod", "channel", "outcome", "hotl_inspect",
    }
    if not isinstance(layers, Mapping) or set(layers) != expected_layers:
        raise ContractError("evidence layers are incomplete")
    priorities = _strings(value.get("blocker_priority"), "blocker_priority")
    for name, descriptor in layers.items():
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"qualifying_result", "missing_blocker", "failed_blocker", "unqualified_blocker"}:
            raise ContractError(f"evidence layer descriptor drifted: {name}")
        if descriptor["qualifying_result"] not in closed["evidence_result"]:
            raise ContractError(f"evidence result not closed: {name}")
        for key in ("missing_blocker", "failed_blocker", "unqualified_blocker"):
            if descriptor[key] not in priorities:
                raise ContractError(f"evidence blocker lacks priority: {name}.{key}")
    matrix = value.get("layer_admission")
    if not isinstance(matrix, Mapping) or set(matrix) != set(layers):
        raise ContractError("layer admission matrix drifted")
    for layer, policy in matrix.items():
        if not isinstance(policy, Mapping) or set(policy) != {"provider_id", "provider_kinds", "release_evidence_eligible", "max_age_seconds", "verifier_id", "interface"}:
            raise ContractError(f"layer admission policy drifted: {layer}")
        kinds = _strings(policy.get("provider_kinds"), f"layer_admission.{layer}.provider_kinds")
        if any(kind not in closed["provider_kind"] for kind in kinds):
            raise ContractError(f"layer provider kind drifted: {layer}")
        if not isinstance(policy.get("release_evidence_eligible"), bool) or not isinstance(policy.get("max_age_seconds"), int) or policy["max_age_seconds"] <= 0:
            raise ContractError(f"layer admission eligibility/freshness drifted: {layer}")
        if policy.get("interface") not in {"local", "external"}:
            raise ContractError(f"layer interface drifted: {layer}")
    current = value.get("current_repository_evidence")
    expected_current = {"owner_manifest_root", "owner_manifest_target", "local_readiness_mode", "local_readiness_paths", "evidence_bundle_root", "managed_identity_paths", "named_evidence_plan_binding", "named_evidence_layers", "provider_adapters", "external_provider_interfaces"}
    if not isinstance(current, Mapping) or set(current) != expected_current:
        raise ContractError("current repository evidence source shape drifted")
    if current.get("owner_manifest_target") != owner or current.get("owner_manifest_root") != ".qwq_output/env/repo/runs/feature-tree/by-fingerprint" or current.get("evidence_bundle_root") != ".qwq_output/env/repo/runs/governance-pipeline":
        raise ContractError("current repository evidence roots drifted")
    _strings(current.get("local_readiness_paths"), "current_repository_evidence.local_readiness_paths")
    _strings(current.get("managed_identity_paths"), "current_repository_evidence.managed_identity_paths")
    expected_named_binding = {
        "workflow": "dev",
        "segment": "POST",
        "deliverable": "implementation",
        "scope": owner,
        "owner_manifest_target": owner,
        "registry_ref": ".agents/skills/review/references/registry.yaml",
        "subject": {
            "subject_id": "current-repository",
            "candidate_id": "working-tree",
            "scope_id": "governance-pipeline",
        },
    }
    if current.get("named_evidence_plan_binding") != expected_named_binding:
        raise ContractError("named evidence plan/subject binding drifted")
    named_layers = current.get("named_evidence_layers")
    if not isinstance(named_layers, Mapping) or set(named_layers) != {"portal_test", "portal_build"}:
        raise ContractError("named evidence layer mapping drifted")
    for layer, descriptor in named_layers.items():
        if (
            not isinstance(descriptor, Mapping)
            or set(descriptor) != {"evidence_id", "qualifying_result"}
            or not isinstance(descriptor.get("evidence_id"), str)
            or not descriptor["evidence_id"]
            or descriptor.get("qualifying_result") != layers[layer]["qualifying_result"]
        ):
            raise ContractError(f"named evidence descriptor drifted: {layer}")
    expected_adapters = {
        "owner_manifest", "local_readiness", "review_consolidation", "named_evidence",
        "handoff", "human_calibration", "objective_inspect", "hotl_inspect",
        "hosted_authority_source",
    }
    if (
        not isinstance(current.get("provider_adapters"), Mapping)
        or set(current["provider_adapters"]) != expected_adapters
        or not isinstance(current.get("external_provider_interfaces"), Mapping)
    ):
        raise ContractError("provider adapter/interface definitions missing")
    precedence = value.get("precedence")
    if not isinstance(precedence, Mapping) or precedence.get("blocked_before_admission")[:5] != [
        "CANONICAL_CONTRACT_INVALID", "INPUT_CONTRACT_INVALID", "EVIDENCE_SCHEMA_INVALID", "EVIDENCE_STALE", "EVIDENCE_FINGERPRINT_MISMATCH",
    ]:
        raise ContractError("evidence precedence drifted")
    rules = precedence.get("rules")
    if not isinstance(rules, Mapping) or any(rules.get(key) is not True for key in (
        "machine_baseline_does_not_satisfy_human_calibration", "review_ready_does_not_satisfy_pass",
        "scope_ready_does_not_satisfy_release_ready", "hosted_code_does_not_satisfy_live",
        "released_published_outcome_are_independent", "missing_schema_stale_or_fingerprint_mismatch_blocks_first",
    )):
        raise ContractError("anti-impersonation precedence drifted")
    policy = value.get("admission_policy")
    if not isinstance(policy, Mapping) or policy.get("current_max_write_concurrency") != 1 or policy.get("objective_s4_upper_bound") != 1:
        raise ContractError("current concurrency ceiling drifted")
    activation = policy.get("activation")
    if not isinstance(activation, Mapping) or activation.get("provider_available") is not False or activation.get("local_inspect_may_self_assert") is not False:
        raise ContractError("activation provider boundary drifted")
    effects = policy.get("external_effects")
    if not isinstance(effects, Mapping) or effects.get("production_effects_allowed") is not False or effects.get("retry_unknown") is not False:
        raise ContractError("external effect safety policy drifted")
    calibration = value.get("human_calibration_policy")
    if not isinstance(calibration, Mapping) or set(calibration) != {
        "owner_contract_version", "readback_schema_source", "verifier_source",
        "required_status", "incompatibility_blocker", "missing_session_bytes_blocker",
        "machine_baseline_is_substitute", "governance_may_recompute_human_semantics",
    }:
        raise ContractError("Human-owned calibration policy shape drifted")
    if (
        calibration.get("owner_contract_version") != 2
        or calibration.get("required_status") != "calibrated"
        or calibration.get("readback_schema_source") != "quwoquan_ops/policies/human_agent_delivery_contract.yaml#schemas.human_calibration_readback"
        or calibration.get("verifier_source") != "quwoquan_ops/cli/lib/human_agent_delivery/calibration.py#verify_calibration_readback"
        or calibration.get("incompatibility_blocker") != "HUMAN_CALIBRATION_CONTRACT_INCOMPATIBLE"
        or calibration.get("missing_session_bytes_blocker") != "HUMAN_CALIBRATION_CONTRACT_INCOMPATIBLE"
        or calibration.get("machine_baseline_is_substitute") is not False
        or calibration.get("governance_may_recompute_human_semantics") is not False
    ):
        raise ContractError("Human-owned calibration policy drifted")
    human_layer = matrix.get("human_calibration")
    if human_layer != {
        "provider_id": "human_calibration_readback_v2",
        "provider_kinds": ["authenticated_external"],
        "release_evidence_eligible": True,
        "max_age_seconds": 86400,
        "verifier_id": "governance.human_calibration.v2",
        "interface": "external",
    }:
        raise ContractError("Human calibration layer must consume authenticated exact v2 single-track")
    metrics = value.get("observation_metrics")
    if not isinstance(metrics, Mapping) or not isinstance(metrics.get("definitions"), list):
        raise ContractError("observation metrics missing")
    forbidden = set(_strings(metrics.get("forbidden_dimensions"), "observation_metrics.forbidden_dimensions"))
    expected_metric_ids = {
        "governance_edit_latency_ms", "governance_idle_latency_ms",
        "governance_scope_latency_ms", "governance_release_latency_ms",
        "governance_cache_hit_ratio", "governance_deferred_age_ms",
        "governance_commit_freshness_ms", "governance_hosted_mismatch_total",
        "governance_authority_wait_ms", "governance_authority_transfer_total",
        "governance_authority_timeout_total", "governance_review_incomplete_total",
        "governance_handoff_stale_total", "governance_objective_pending_total",
        "governance_objective_revoke_total",
    }
    actual_ids: set[str] = set()
    for item in metrics["definitions"]:
        if not isinstance(item, Mapping) or set(item) != set(_required_fields(value, "observation_metric")):
            raise ContractError("observation metric shape drifted")
        metric_id = item.get("metric_id")
        if not isinstance(metric_id, str) or not metric_id:
            raise ContractError("observation metric id invalid")
        actual_ids.add(metric_id)
        dimensions = set(_strings(item.get("dimensions"), f"metric.{metric_id}.dimensions", allow_empty=True))
        sensitive = _strings(item.get("sensitive_fields"), f"metric.{metric_id}.sensitive_fields", allow_empty=True)
        if dimensions & forbidden or sensitive:
            raise ContractError(f"observation metric leaks prompt/PII: {metric_id}")
    if actual_ids != expected_metric_ids:
        raise ContractError("observation metric required set drifted")
    if priorities[:7] != ["CANONICAL_CONTRACT_INVALID", "INPUT_CONTRACT_INVALID", "EVIDENCE_SCHEMA_INVALID", "EVIDENCE_STALE", "EVIDENCE_FINGERPRINT_MISMATCH", "REQUIRED_CODE_EVIDENCE_ABSENT", "REQUIRED_CODE_EVIDENCE_FAILED"]:
        raise ContractError("blocker priority drifted")


def validate_named_evidence_plan_binding(
    *,
    plan: dict[str, Any],
    receipt: dict[str, Any],
    subject: Mapping[str, Any],
    expected_owner_manifest_ref: str,
    contract: Mapping[str, Any],
    label: str = "named evidence receipt",
) -> dict[str, Any]:
    """Bind one named receipt to the current governance Review plan and subject."""

    binding = contract["current_repository_evidence"]["named_evidence_plan_binding"]
    expected_subject = binding["subject"]
    for field in ("subject_id", "candidate_id", "scope_id"):
        if subject.get(field) != expected_subject[field]:
            raise EvidenceAdapterError.identity(
                f"named evidence governance subject {field} mismatch"
            )
    for field in ("workflow", "segment", "deliverable", "scope"):
        if plan.get(field) != binding[field]:
            raise EvidenceAdapterError.identity(
                f"named evidence Review plan {field} mismatch"
            )
    owner = plan.get("owner_manifest_identity")
    if not isinstance(owner, Mapping) or (
        owner.get("ref") != expected_owner_manifest_ref
        or owner.get("target") != binding["owner_manifest_target"]
        or owner.get("resolved_owner") != binding["owner_manifest_target"]
        or owner.get("scope") != binding["scope"]
    ):
        raise EvidenceAdapterError.identity(
            "named evidence Review plan owner/governance scope mismatch"
        )

    registry_ref = str(binding["registry_ref"] or "")
    registry_path = (REPO_ROOT / registry_ref).resolve()
    try:
        registry_path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ContractError("named evidence registry ref escapes repository") from error
    if registry_path.is_symlink() or not registry_path.is_file():
        raise ContractError("named evidence registry ref must be a regular non-symlink file")
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"named evidence registry could not be loaded: {error}") from error
    if not isinstance(registry, dict):
        raise ContractError("named evidence registry must be a mapping")
    try:
        import review_dispatch

        current_plan = review_dispatch.validate_current_review_plan(
            plan, registry, phase="evidence",
        )
    except Exception as error:
        raise EvidenceAdapterError.identity(
            f"named evidence Review plan is not current: {error}"
        ) from error
    if (
        receipt.get("plan_fingerprint_ref") != current_plan["ref"]
        or receipt.get("plan_fingerprint_digest") != current_plan["digest"]
    ):
        raise EvidenceAdapterError.identity(
            "named evidence receipt belongs to a different exact Review plan"
        )
    try:
        import handoff_consumer

        return handoff_consumer.validate_named_evidence_ref_payload(
            receipt, plan=plan, registry=registry, label=label,
        )
    except Exception as error:
        raise ContractError(f"named evidence canonical validation failed: {error}") from error


def validate_exact_fields(payload: Mapping[str, Any], schema_name: str) -> None:
    expected = set(_required_fields(load_contract(), schema_name))
    actual = set(payload)
    if actual != expected:
        raise ContractError(f"{schema_name} fields drifted: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


@lru_cache(maxsize=1)
def _load_cached() -> dict[str, Any]:
    try:
        value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContractError(f"canonical governance pipeline contract could not be loaded: {error}") from error
    validate_contract(value)
    return dict(value)


def load_contract() -> dict[str, Any]:
    return deepcopy(_load_cached())
