"""Governance pipeline anti-impersonation, activation, and determinism contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-003.t1
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.governance_pipeline_admission import inspect, load_contract  # noqa: E402
from lib.human_agent_delivery import summarize_calibration_sessions  # noqa: E402
from lib.governance_pipeline_admission import evaluator as evaluator_module  # noqa: E402
from lib.objective_execution.contract import admission_readback  # noqa: E402

FINGERPRINT = "sha256:" + "f" * 64
BRANCH_DIGEST = "sha256:" + "b" * 64


def readback(result: str, *, layer: str, provider_kind: str | None = None, release: bool | None = None, **overrides: Any) -> dict[str, Any]:
    contract = load_contract()
    policy = contract["layer_admission"][layer]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    value = {
        "status": "present", "schema_valid": True, "fresh": True,
        "fingerprint_match": True, "result": result,
        "provider_kind": provider_kind or policy["provider_kinds"][0],
        "release_evidence_eligible": policy["release_evidence_eligible"] if release is None else release,
        "detail": None, "receipt_ref": f".qwq_output/{layer}.json",
        "receipt_bytes_sha256": "sha256:" + "1" * 64,
        "verified_at": now, "provider_timestamp": now,
        "candidate_id": "candidate-1", "scope_id": "scope-1",
        "verifier_id": policy["verifier_id"],
    }
    value.update(overrides)
    return value


def _human_readback() -> dict[str, Any]:
    contract = load_contract()
    human = __import__("lib.human_agent_delivery", fromlist=["load_contract"]).load_contract()
    model = human["calibration_model"]
    mapping = model["principal_responsibility_mapping"]
    dimensions = human["closed_sets"]["human_calibration_observation_dimension"]
    sessions = []
    for principal, responsibilities in mapping.items():
        sessions.append({
            "schema_version": 2, "contract_version": model["contract_version"],
            "role_model_version": model["role_model_version"], "observation_model_version": model["observation_model_version"],
            "session_id": f"calibration-{principal.replace('_', '-')}", "principal_class": principal,
            "participant_ref": f"participant-{principal.replace('_', '-')}",
            "scope": {"decision_unit_id": "decision-unit-governance", "task_id": f"task-{principal}", "evidence_fingerprint": FINGERPRINT, "responsibility_classes": responsibilities},
            "started_at": "2026-08-30T00:00:00+00:00", "completed_at": "2026-08-30T00:30:00+00:00",
            "source_assurance": {"source_kind": "human_participant", "authentication_provider_ref": "provider", "participant_authenticated": True, "consent_obtained": True, "consent_recorded_at": "2026-08-29T23:59:00+00:00", "direct_identifiers_removed": True, "free_text_excluded": True, "observer_attested": True},
            "separation_policy": "role-record-only",
            "observations": [{"observation_id": f"observation-{index+1}", "dimension": dimension, "observed_at": "2026-08-30T00:10:00+00:00", "outcome": "demonstrated", "responsibility_classes": responsibilities} for index, dimension in enumerate(dimensions)],
        })
    return summarize_calibration_sessions(sessions, now=datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc))


def complete_input() -> dict[str, Any]:
    contract = load_contract()
    evidence = {
        name: readback(descriptor["qualifying_result"], layer=name)
        for name, descriptor in contract["evidence_layers"].items()
    }
    return {
        "subject": {"subject_id": "subject-1", "scope_id": "scope-1", "candidate_id": "candidate-1", "evidence_fingerprint": FINGERPRINT},
        "evidence": evidence, "human_calibration_readback": _human_readback(),
        "activation_receipt": None,
    }


@pytest.fixture(autouse=True)
def admitted_s4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        evaluator_module, "inspect_admission",
        lambda: admission_readback("admitted", branch_policy_digest=BRANCH_DIGEST),
    )


def assert_safe(result: dict[str, Any]) -> None:
    assert result["production_ready"] is False
    assert result["commercial_ready"] is False
    assert result["hotl_admitted"] is False
    assert result["mutation_allowed"] is False
    assert result["prod_mutation_allowed"] is False
    assert result["hotl_mutation_allowed"] is False
    assert result["max_write_concurrency"] <= 1
    assert result["external_effect_policy"]["production_effects_allowed"] is False
    assert result["external_effect_policy"]["unknown_outcome"] == "pending"
    assert result["external_effect_policy"]["retry_unknown"] is False


def test_all_layers_only_reach_eligible_without_independent_activation_provider() -> None:
    result = inspect(complete_input())
    assert result["status"] == "eligible_observe_only"
    assert result["allowed_mode"] == "observe_only"
    assert result["blockers"] == ["ACTIVATION_PROVIDER_UNAVAILABLE"]
    assert result["activation_required"] is True
    assert_safe(result)


@pytest.mark.parametrize(
    ("layer", "fake_result", "blocker"),
    [
        ("review_terminal", "READY", "REVIEW_NOT_PASS"),
        ("local_release_ready", "scope_ready", "LOCAL_RELEASE_NOT_READY"),
        ("human_calibration", "pass", "HUMAN_CALIBRATION_NOT_OBSERVED"),
        ("hosted_authority_live", "code_pass", "HOSTED_AUTHORITY_LIVE_RECEIPT_MISSING"),
        ("channel", "released", "CHANNEL_NOT_PUBLISHED"),
        ("outcome", "published", "OUTCOME_NOT_ATTAINED"),
    ],
)
def test_layer_impersonation_never_satisfies_downstream(layer: str, fake_result: str, blocker: str) -> None:
    payload = complete_input()
    payload["evidence"][layer]["result"] = fake_result
    result = inspect(payload)
    assert result["status"] == "not_admitted"
    assert blocker in result["blockers"]
    assert_safe(result)


def test_every_evidence_layer_rejects_a_wrong_result_without_cross_layer_inference() -> None:
    contract = load_contract()
    for layer, descriptor in contract["evidence_layers"].items():
        payload = complete_input()
        payload["evidence"][layer]["result"] = "absent"
        result = inspect(payload)
        expected = descriptor["unqualified_blocker"]
        assert result["status"] in {"blocked", "not_admitted"}, layer
        assert expected in result["blockers"], layer
        assert_safe(result)


def test_unknown_external_effect_stays_pending_without_retry() -> None:
    payload = complete_input()
    payload["evidence"]["effect_readback"]["result"] = "unknown"
    result = inspect(payload)
    assert result["status"] == "not_admitted"
    assert "EFFECT_OUTCOME_UNKNOWN" in result["blockers"]
    assert result["external_effect_policy"]["unknown_outcome"] == "pending"
    assert result["external_effect_policy"]["retry_unknown"] is False
    assert_safe(result)




def test_human_missing_expired_and_self_signed_readback_never_admits() -> None:
    missing = complete_input()
    missing["human_calibration_readback"] = None
    missing["evidence"]["human_calibration"].update(status="absent", result="not_observed", provider_kind="absent", release_evidence_eligible=False, receipt_ref=None, receipt_bytes_sha256=None, provider_timestamp=None, candidate_id=None, scope_id=None, verifier_id=None)
    result = inspect(missing)
    assert result["status"] == "not_admitted"
    assert "HUMAN_CALIBRATION_RECEIPT_MISSING" in result["blockers"]
    expired = complete_input()
    expired["evidence"]["human_calibration"]["fresh"] = False
    result = inspect(expired)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "EVIDENCE_STALE"
    self_signed = complete_input()
    self_signed["evidence"]["human_calibration"].update(provider_kind="local_runtime", release_evidence_eligible=False)
    result = inspect(self_signed)
    assert result["status"] == "not_admitted"
    assert "HUMAN_CALIBRATION_NOT_OBSERVED" in result["blockers"]
    assert_safe(result)


def test_governance_accepts_only_human_owned_v2_without_shadow_role_schema() -> None:
    result = inspect(complete_input())
    assert result["status"] == "eligible_observe_only"
    assert result["blockers"] == ["ACTIVATION_PROVIDER_UNAVAILABLE"]
    serialized = json.dumps(load_contract()["human_calibration_policy"], sort_keys=True)
    assert "desired_role_classes" not in serialized
    assert "desired_six_role" not in serialized
    assert_safe(result)


@pytest.mark.parametrize(("field", "blocker"), [("schema_valid", "EVIDENCE_SCHEMA_INVALID"), ("fresh", "EVIDENCE_STALE"), ("fingerprint_match", "EVIDENCE_FINGERPRINT_MISMATCH")])
def test_schema_stale_and_fingerprint_mismatch_block_first(field: str, blocker: str) -> None:
    payload = complete_input()
    payload["evidence"]["owner_manifest"][field] = False
    payload["evidence"]["review_terminal"]["result"] = "READY"
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == blocker
    assert "REVIEW_NOT_PASS" in result["blockers"]
    assert_safe(result)


def test_failed_schema_invalid_is_structural_blocked_first() -> None:
    payload = complete_input()
    payload["evidence"]["environment"].update(status="failed", schema_valid=False, result="absent")
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "EVIDENCE_SCHEMA_INVALID"
    assert "ENVIRONMENT_RECEIPT_FAILED" in result["blockers"]


def test_required_hosted_source_absent_is_structural_blocked() -> None:
    payload = complete_input()
    payload["evidence"]["hosted_authority_code"].update(
        status="absent", result="code_absent", provider_kind="absent",
        release_evidence_eligible=False, receipt_ref=None, receipt_bytes_sha256=None,
        provider_timestamp=None, candidate_id=None, scope_id=None, verifier_id=None,
    )
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "REQUIRED_CODE_EVIDENCE_ABSENT"


def test_missing_workflow_receipt_is_not_admitted_with_exact_blocker() -> None:
    payload = complete_input()
    payload["evidence"]["workflow_resolve"] = readback("absent", layer="workflow_resolve", status="absent", provider_kind="absent", release=False, receipt_ref=None, receipt_bytes_sha256=None, provider_timestamp=None, candidate_id=None, scope_id=None, verifier_id=None)
    result = inspect(payload)
    assert result["status"] == "not_admitted"
    assert "WORKFLOW_RESOLVE_RECEIPT_MISSING" in result["blockers"]
    assert_safe(result)


def test_objective_blocked_readback_is_typed_and_concurrency_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evaluator_module, "inspect_admission", lambda: admission_readback("blocked", detail="objective unavailable"))
    result = inspect(complete_input())
    assert result["status"] == "blocked"
    assert result["error_code"] == "GPA.OBJECTIVE_ADMISSION_BLOCKED"
    assert "OBJECTIVE_ADMISSION_BLOCKED" in result["blockers"]
    assert result["max_write_concurrency"] == 0
    assert_safe(result)


def test_caller_activation_receipt_cannot_self_assert_without_provider() -> None:
    eligible = inspect(complete_input())
    payload = complete_input()
    payload["activation_receipt"] = {
        "status": "present", "receipt_id": "caller-forged",
        "evaluation_digest": eligible["evaluation_digest"],
        "evaluation_bytes_sha256": eligible["evaluation_bytes_sha256"],
    }
    result = inspect(payload)
    assert result["status"] == "eligible_observe_only"
    assert result["blockers"] == ["ACTIVATION_PROVIDER_UNAVAILABLE"]
    assert_safe(result)


def test_v1_and_shadow_human_readbacks_fail_closed() -> None:
    for mutate in (
        lambda value: value.update(schema_version=1),
        lambda value: value.update(shadow_six_roles=[]),
    ):
        payload = complete_input()
        mutate(payload["human_calibration_readback"])
        result = inspect(payload)
        assert result["status"] == "not_admitted"
        assert result["blockers"][0] == "HUMAN_CALIBRATION_CONTRACT_INCOMPATIBLE"
        assert_safe(result)


def test_activation_mismatch_stays_not_admitted() -> None:
    eligible = inspect(complete_input())
    payload = complete_input()
    payload["activation_receipt"] = {
        "status": "present", "receipt_id": "external-receipt-1",
        "evaluation_digest": eligible["evaluation_digest"],
        "evaluation_bytes_sha256": eligible["evaluation_bytes_sha256"],
    }
    def verifier(_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "present", "provider_kind": "authenticated_external",
            "authenticated": True, "exact_bytes_verified": True,
            "release_evidence_eligible": True, "receipt_id": "external-receipt-1",
            "evaluation_digest": "sha256:" + "0" * 64,
            "evaluation_bytes_sha256": "sha256:" + "1" * 64,
        }
    result = inspect(payload, activation_verifier=verifier)
    assert result["status"] == "not_admitted"
    assert result["blockers"] == ["ACTIVATION_RECEIPT_MISMATCH"]
    assert_safe(result)


def test_wrong_caller_digest_rejected_even_when_verifier_echoes_current() -> None:
    payload = complete_input()
    current = inspect(payload)
    payload["activation_receipt"] = {
        "status": "present", "receipt_id": "external-receipt-1",
        "evaluation_digest": "sha256:" + "9" * 64,
        "evaluation_bytes_sha256": current["evaluation_bytes_sha256"],
    }
    def verifier(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "present", "provider_kind": "authenticated_external", "authenticated": True,
            "exact_bytes_verified": True, "release_evidence_eligible": True, "receipt_id": "external-receipt-1",
            "evaluation_digest": request["evaluation_digest"], "evaluation_bytes_sha256": request["evaluation_bytes_sha256"],
        }
    result = inspect(payload, activation_verifier=verifier)
    assert result["status"] == "not_admitted"
    assert result["blockers"] == ["ACTIVATION_RECEIPT_MISMATCH"]


def test_input_order_is_deterministic() -> None:
    first = complete_input()
    second = copy.deepcopy(first)
    second["evidence"] = dict(reversed(list(second["evidence"].items())))
    left = inspect(first)
    right = inspect(second)
    assert left == right
    assert json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(right, ensure_ascii=False, sort_keys=True)
