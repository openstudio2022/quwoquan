"""HOTL evaluator safety, controls, activation, and determinism local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-003.t2
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
SHA256_BRANCH = "sha256:" + "a" * 64
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.hotl_admission import ContractError, inspect  # noqa: E402
from lib.hotl_admission import evaluator as evaluator_module  # noqa: E402
from lib.objective_execution.contract import admission_readback  # noqa: E402

CURRENT_BLOCKERS = {
    "AUTHORITY_PROVIDER_UNAVAILABLE", "HUMAN_BOTTLENECK_COHORT_MISSING",
    "CONTROL_PROOF_MISSING", "COMMERCIAL_AUTHORITY_NOT_CLOSED",
    "CHECKPOINT_POLICY_UNRESOLVED", "WRITE_EXPANSION_NOT_ADMITTED",
}


def subject() -> dict[str, str]:
    return {"subject_id": "subject-1", "scope_id": "scope-1", "action_id": "hotl-expansion"}


def authority(**overrides: Any) -> dict[str, Any]:
    value = {
        "status": "present", "provider_kind": "authenticated_external", "authenticated": True,
        "exact_bytes_verified": True, "release_evidence_eligible": True, "expired": False,
        "subject_id": "subject-1", "scope_id": "scope-1", "allowed_action_id": "hotl-expansion",
        "decision_kind": "delivery_authorization",
    }
    value.update(overrides)
    return value


def roles(**overrides: Any) -> dict[str, Any]:
    value = {"status": "present", "seven_responsibilities_closed": True, "sod_required": True, "sod_satisfied": True}
    value.update(overrides)
    return value


def cohort(**overrides: Any) -> dict[str, Any]:
    value = {
        "status": "present", "cohort_id": "cohort-1", "member_count": 2,
        "member_ids": ["member-b", "member-a"], "selection_query_frozen": True,
        "bottleneck_rule_frozen": True, "threshold_frozen": True, "coverage_basis_points": 9000,
        "human_calibration": "observed", "wait_event_kinds": ["decision_recorded", "decision_requested"],
        "cohort_digest_before": "sha256:cohort", "cohort_digest_after": "sha256:cohort",
    }
    value.update(overrides)
    return value


def checkpoint(**overrides: Any) -> dict[str, Any]:
    value = {
        "status": "present", "resolution": "resolved", "checkpoint_delta_id": "delta-1",
        "removable_decision_kinds": [], "resume_requested": False, "new_human_decision_id": None,
        "human_override": False, "requested_reduction": True,
    }
    value.update(overrides)
    return value


def control(action: str, **overrides: Any) -> dict[str, Any]:
    command_id = f"command-{action}"
    value = {
        "proof_id": f"proof-{action}", "action": action,
        "command_ack": {"status": "present", "exact": True, "subject_id": "subject-1", "scope_id": "scope-1", "action_id": action, "command_id": command_id},
        "effect_readback": {"status": "present", "effect_status": "applied", "independent": True, "subject_id": "subject-1", "scope_id": "scope-1", "action_id": action, "command_id": command_id},
        "connected": True, "audit_passed": True, "ack_timed_out": False,
        "post_revoke_new_action_count": 0,
    }
    value.update(overrides)
    return value


def commercial(**overrides: Any) -> dict[str, Any]:
    value = {
        "status": "present", "authenticated": True, "exact_bytes_verified": True,
        "release_evidence_eligible": True, "commercial_readiness_closed": True,
        "production_campaign_closed": True,
    }
    value.update(overrides)
    return value


def complete_input(**overrides: Any) -> dict[str, Any]:
    value = {
        "subject": subject(), "risk_tier": "R1", "requested_write_concurrency": 1,
        "authority_readback": authority(), "role_responsibility_proof": roles(),
        "cohort_proof": cohort(), "checkpoint_policy": checkpoint(),
        "control_proofs": [control(action) for action in ("pause", "deny", "abort", "revoke")],
        "commercial_authority_readback": commercial(), "activation_receipt": None,
    }
    value.update(overrides)
    return value


def current_input() -> dict[str, Any]:
    return complete_input(
        authority_readback=None, role_responsibility_proof=None, cohort_proof=None,
        checkpoint_policy=None, control_proofs=[], commercial_authority_readback=None,
    )


def assert_not_admitted(payload: dict[str, Any], blocker: str) -> dict[str, Any]:
    result = inspect(payload)
    assert result["status"] in {"blocked", "not_admitted"}
    assert blocker in result["blockers"]
    assert result["allowed_mode"] == "manual"
    assert result["checkpoint_reduction_allowed"] is False
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False
    return result


def test_current_actual_prerequisites_are_deterministic_manual_single_writer_and_zero_grant() -> None:
    first = inspect(current_input())
    second = inspect(current_input())
    assert first == second
    assert first["status"] == "not_admitted"
    assert first["allowed_mode"] == "manual"
    assert first["checkpoint_reduction_allowed"] is False
    assert first["max_write_concurrency"] == 1
    assert first["grant_executable"] is False
    assert first["mutation_allowed"] is False
    assert CURRENT_BLOCKERS <= set(first["blockers"])
    assert first["s4_readback"]["status"] == "not_admitted"
    assert first["s4_readback"]["write_concurrency"] == 1


@pytest.mark.parametrize("risk_tier", ["R2", "R3", "R4"])
def test_r2_to_r4_are_blocked(risk_tier: str) -> None:
    result = assert_not_admitted(complete_input(risk_tier=risk_tier), "RISK_TIER_NOT_ELIGIBLE")
    assert result["status"] == "blocked"


@pytest.mark.parametrize(
    "authority_value",
    [
        authority(provider_kind="projection"), authority(provider_kind="test"),
        authority(expired=True), authority(authenticated=False),
        authority(exact_bytes_verified=False), authority(release_evidence_eligible=False),
    ],
)
def test_projection_test_expired_or_unpublishable_authority_is_not_admitted(authority_value: dict[str, Any]) -> None:
    assert_not_admitted(complete_input(authority_readback=authority_value), "AUTHORITY_READBACK_INVALID")


@pytest.mark.parametrize("decision_kind", ["routine_execution", "unknown_decision_kind"])
def test_authority_decision_kind_must_be_canonical_and_policy_allowed(decision_kind: str) -> None:
    assert_not_admitted(complete_input(authority_readback=authority(decision_kind=decision_kind)), "AUTHORITY_READBACK_INVALID")


@pytest.mark.parametrize(
    ("proof", "blocker"),
    [
        (None, "ROLE_RESPONSIBILITY_PROOF_MISSING"),
        (roles(seven_responsibilities_closed=False), "ROLE_RESPONSIBILITY_PROOF_MISSING"),
        (roles(sod_satisfied=False), "SEGREGATION_OF_DUTIES_FAILED"),
    ],
)
def test_role_proof_missing_or_sod_failure_blocks(proof: dict[str, Any] | None, blocker: str) -> None:
    assert_not_admitted(complete_input(role_responsibility_proof=proof), blocker)


@pytest.mark.parametrize(
    ("proof", "blocker"),
    [
        (cohort(member_count=0, member_ids=[]), "HUMAN_BOTTLENECK_COHORT_MISSING"),
        (cohort(cohort_id=None), "HUMAN_BOTTLENECK_COHORT_MISSING"),
        (cohort(coverage_basis_points=8999), "COHORT_COVERAGE_INSUFFICIENT"),
        (cohort(cohort_digest_after="sha256:drift"), "COHORT_DRIFTED"),
        (cohort(selection_query_frozen=False), "COHORT_SELECTION_UNFROZEN"),
        (cohort(bottleneck_rule_frozen=False), "COHORT_SELECTION_UNFROZEN"),
        (cohort(threshold_frozen=False), "COHORT_THRESHOLD_UNFROZEN"),
        (cohort(wait_event_kinds=["runner_queue"]), "HUMAN_WAIT_SOURCE_INVALID"),
        (cohort(wait_event_kinds=["job_started"]), "HUMAN_WAIT_SOURCE_INVALID"),
        (cohort(human_calibration="not_observed"), "HUMAN_CALIBRATION_NOT_OBSERVED"),
    ],
)
def test_cohort_must_be_fixed_covered_frozen_durable_and_human_observed(proof: dict[str, Any], blocker: str) -> None:
    assert_not_admitted(complete_input(cohort_proof=proof), blocker)


@pytest.mark.parametrize(
    ("policy", "blocker"),
    [
        (checkpoint(resolution="unresolved", checkpoint_delta_id=None), "CHECKPOINT_POLICY_UNRESOLVED"),
        (checkpoint(removable_decision_kinds=["product_scope"]), "IMMUTABLE_CHECKPOINT_REMOVAL_FORBIDDEN"),
        (checkpoint(removable_decision_kinds=["production_campaign_approval"]), "IMMUTABLE_CHECKPOINT_REMOVAL_FORBIDDEN"),
        (checkpoint(removable_decision_kinds=["implementation_exception"]), "IMMUTABLE_CHECKPOINT_REMOVAL_FORBIDDEN"),
        (checkpoint(resume_requested=True, new_human_decision_id=None), "RESUME_REQUIRES_NEW_HUMAN_DECISION"),
        (checkpoint(human_override=True), "HUMAN_OVERRIDE_ACTIVE"),
    ],
)
def test_checkpoint_removal_resume_and_human_override_are_fail_closed(policy: dict[str, Any], blocker: str) -> None:
    assert_not_admitted(complete_input(checkpoint_policy=policy), blocker)


@pytest.mark.parametrize("decision_id", [None, "decision-untrusted-1"])
@pytest.mark.parametrize("status", ["present", "absent", "failed"])
def test_v1_resume_never_trusts_caller_supplied_decision_id(
    decision_id: str | None, status: str,
) -> None:
    result = assert_not_admitted(
        complete_input(
            checkpoint_policy=checkpoint(
                status=status, resume_requested=True,
                new_human_decision_id=decision_id,
            ),
        ),
        "RESUME_REQUIRES_NEW_HUMAN_DECISION",
    )
    assert result["status"] == "not_admitted"
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False


@pytest.mark.parametrize("action", ["pause", "deny", "abort", "revoke"])
def test_every_control_action_requires_ack_and_independent_effect(action: str) -> None:
    missing_ack = [control(item, command_ack=None) if item == action else control(item) for item in ("pause", "deny", "abort", "revoke")]
    assert_not_admitted(complete_input(control_proofs=missing_ack), "CONTROL_ACK_MISSING")
    missing_effect = [control(item, effect_readback=None) if item == action else control(item) for item in ("pause", "deny", "abort", "revoke")]
    assert_not_admitted(complete_input(control_proofs=missing_effect), "CONTROL_EFFECT_READBACK_MISSING")


@pytest.mark.parametrize(
    ("ack_exact", "effect_status", "effect_independent", "expected_blocker"),
    [
        (False, "applied", True, "CONTROL_ACK_NOT_EXACT"),
        (True, "not_applied", True, "CONTROL_EFFECT_NOT_APPLIED"),
        (True, "unknown", True, "CONTROL_EFFECT_NOT_APPLIED"),
        (True, "applied", False, "CONTROL_EFFECT_NOT_INDEPENDENT"),
    ],
)
def test_present_negative_control_readbacks_have_single_typed_blocker(
    ack_exact: bool, effect_status: str, effect_independent: bool,
    expected_blocker: str,
) -> None:
    ack = dict(control("pause")["command_ack"])
    ack["exact"] = ack_exact
    effect = dict(control("pause")["effect_readback"])
    effect.update(effect_status=effect_status, independent=effect_independent)
    controls = [
        control("pause", command_ack=ack, effect_readback=effect),
        control("deny"), control("abort"), control("revoke"),
    ]
    result = assert_not_admitted(
        complete_input(control_proofs=controls), expected_blocker,
    )
    control_value_blockers = [
        blocker for blocker in result["blockers"] if blocker in {
            "CONTROL_ACK_NOT_EXACT", "CONTROL_EFFECT_NOT_APPLIED",
            "CONTROL_EFFECT_NOT_INDEPENDENT",
        }
    ]
    assert control_value_blockers == [expected_blocker]
    assert "CONTROL_ACK_MISSING" not in result["blockers"]
    assert "CONTROL_EFFECT_READBACK_MISSING" not in result["blockers"]


def test_combined_present_negative_controls_report_all_in_stable_priority() -> None:
    ack = dict(control("pause")["command_ack"])
    ack["exact"] = False
    effect = dict(control("pause")["effect_readback"])
    effect.update(effect_status="unknown", independent=False)
    controls = [
        control("pause", command_ack=ack, effect_readback=effect),
        control("deny"), control("abort"), control("revoke"),
    ]
    result = assert_not_admitted(
        complete_input(control_proofs=controls), "CONTROL_ACK_NOT_EXACT",
    )
    control_blockers = [
        blocker for blocker in result["blockers"] if blocker.startswith("CONTROL_")
    ]
    assert control_blockers == [
        "CONTROL_ACK_NOT_EXACT", "CONTROL_EFFECT_NOT_APPLIED",
        "CONTROL_EFFECT_NOT_INDEPENDENT",
    ]


def test_ack_without_effect_identity_drift_disconnect_audit_timeout_and_revoke_actions_block() -> None:
    ack_only = [control("pause", effect_readback=None), control("deny"), control("abort"), control("revoke")]
    assert_not_admitted(complete_input(control_proofs=ack_only), "CONTROL_EFFECT_READBACK_MISSING")
    drift_effect = control("pause")["effect_readback"]
    drift_effect["scope_id"] = "other"
    controls = [control("pause", effect_readback=drift_effect), control("deny"), control("abort"), control("revoke")]
    assert_not_admitted(complete_input(control_proofs=controls), "CONTROL_IDENTITY_DRIFTED")
    for override, blocker in (
        ({"connected": False}, "CONTROL_DISCONNECTED"),
        ({"audit_passed": False}, "CONTROL_AUDIT_FAILED"),
        ({"ack_timed_out": True}, "CONTROL_ACK_TIMEOUT"),
    ):
        controls = [control("pause", **override), control("deny"), control("abort"), control("revoke")]
        assert_not_admitted(complete_input(control_proofs=controls), blocker)
    controls = [control("pause"), control("deny"), control("abort"), control("revoke", post_revoke_new_action_count=1)]
    assert_not_admitted(complete_input(control_proofs=controls), "REVOKE_ZERO_ACTIONS_UNPROVEN")


def test_requested_concurrency_above_dynamic_s4_is_blocked() -> None:
    result = assert_not_admitted(complete_input(requested_write_concurrency=2), "REQUESTED_WRITE_CONCURRENCY_EXCEEDED")
    assert result["max_write_concurrency"] == 1


@pytest.mark.parametrize(
    ("payload_field", "failed_value", "absent_value", "failed_blocker", "absent_blocker"),
    [
        ("authority_readback", authority(status="failed"), authority(status="absent"), "AUTHORITY_READBACK_FAILED", "AUTHORITY_PROVIDER_UNAVAILABLE"),
        ("role_responsibility_proof", roles(status="failed"), roles(status="absent"), "ROLE_RESPONSIBILITY_READBACK_FAILED", "ROLE_RESPONSIBILITY_PROOF_MISSING"),
        ("cohort_proof", cohort(status="failed"), cohort(status="absent"), "COHORT_READBACK_FAILED", "HUMAN_BOTTLENECK_COHORT_MISSING"),
        ("commercial_authority_readback", commercial(status="failed"), commercial(status="absent"), "COMMERCIAL_AUTHORITY_READBACK_FAILED", "COMMERCIAL_AUTHORITY_NOT_CLOSED"),
        ("checkpoint_policy", checkpoint(status="failed"), checkpoint(status="absent"), "CHECKPOINT_READBACK_FAILED", "CHECKPOINT_POLICY_UNRESOLVED"),
    ],
)
def test_closed_readback_failed_is_distinct_from_absent(
    payload_field: str, failed_value: dict[str, Any], absent_value: dict[str, Any],
    failed_blocker: str, absent_blocker: str,
) -> None:
    failed = assert_not_admitted(complete_input(**{payload_field: failed_value}), failed_blocker)
    assert absent_blocker not in failed["blockers"]
    for missing_value in (None, absent_value):
        absent = assert_not_admitted(
            complete_input(**{payload_field: missing_value}), absent_blocker,
        )
        assert failed_blocker not in absent["blockers"]


@pytest.mark.parametrize(
    ("field", "failed_blocker", "absent_blocker"),
    [
        ("command_ack", "CONTROL_ACK_READBACK_FAILED", "CONTROL_ACK_MISSING"),
        ("effect_readback", "CONTROL_EFFECT_READBACK_FAILED", "CONTROL_EFFECT_READBACK_MISSING"),
    ],
)
def test_control_readback_failed_is_distinct_from_absent(
    field: str, failed_blocker: str, absent_blocker: str,
) -> None:
    failed_readback = dict(control("pause")[field])
    failed_readback["status"] = "failed"
    if field == "command_ack":
        failed_readback["exact"] = False
        present_value_blockers = {"CONTROL_ACK_NOT_EXACT"}
    else:
        failed_readback.update(effect_status="unknown", independent=False)
        present_value_blockers = {
            "CONTROL_EFFECT_NOT_APPLIED", "CONTROL_EFFECT_NOT_INDEPENDENT",
        }
    failed_controls = [
        control("pause", **{field: failed_readback}), control("deny"),
        control("abort"), control("revoke"),
    ]
    failed = assert_not_admitted(complete_input(control_proofs=failed_controls), failed_blocker)
    assert absent_blocker not in failed["blockers"]
    assert present_value_blockers.isdisjoint(failed["blockers"])

    for absent_readback in (None, {**failed_readback, "status": "absent"}):
        absent_controls = [
            control("pause", **{field: absent_readback}), control("deny"),
            control("abort"), control("revoke"),
        ]
        absent = assert_not_admitted(
            complete_input(control_proofs=absent_controls), absent_blocker,
        )
        assert failed_blocker not in absent["blockers"]
        assert present_value_blockers.isdisjoint(absent["blockers"])


def test_activation_failed_is_distinct_from_absent() -> None:
    failed_receipt = {
        "status": "failed", "receipt_id": None, "authenticated": False,
        "exact_bytes_verified": False, "release_evidence_eligible": False,
        "evaluation_digest": None, "evaluation_bytes_sha256": None,
    }
    failed = assert_not_admitted(
        complete_input(activation_receipt=failed_receipt),
        "ACTIVATION_READBACK_FAILED",
    )
    assert "ACTIVATION_PROVIDER_UNAVAILABLE" not in failed["blockers"]
    absent_receipt = {**failed_receipt, "status": "absent"}
    for absent_value in (None, absent_receipt):
        absent = inspect(complete_input(activation_receipt=absent_value))
        assert "ACTIVATION_READBACK_FAILED" not in absent["blockers"]
        if absent_value is not None:
            assert "ACTIVATION_PROVIDER_UNAVAILABLE" in absent["blockers"]


def canonical_s4(**overrides: Any) -> dict[str, Any]:
    value = admission_readback("admitted", branch_policy_digest=SHA256_BRANCH)
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("reason"),
        lambda value: value.update(extra="unexpected"),
        lambda value: value.update(status=1),
        lambda value: value.update(stage=4),
        lambda value: value.update(write_concurrency=True),
        lambda value: value.update(temporary_branch_allowed=1),
        lambda value: value.update(branch_policy_digest=1),
        lambda value: value.update(reason=1),
        lambda value: value.update(terminal=1),
        lambda value: value.update(stage="S3"),
        lambda value: value.update(status="eligible_for_activation"),
        lambda value: value.update(terminal="not_admitted"),
        lambda value: value.update(branch_policy_digest="sha256:branch"),
        lambda value: value.update(reason=""),
        lambda value: value.update(temporary_branch_allowed=False),
    ],
)
def test_malformed_dynamic_s4_readback_returns_objective_typed_blocked(
    monkeypatch: pytest.MonkeyPatch, mutate: Any,
) -> None:
    readback = canonical_s4()
    mutate(readback)
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission", lambda: readback,
    )
    result = inspect(complete_input())
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert result["s4_readback"] == admission_readback("blocked")
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False


def test_canonical_not_admitted_s4_readback_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readback = admission_readback(
        "not_admitted", branch_policy_digest="sha256:" + "b" * 64,
    )
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission", lambda: readback,
    )
    result = inspect(complete_input())
    assert result["s4_readback"] == readback
    assert result["status"] == "not_admitted"
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False


def test_canonical_blocked_s4_readback_returns_immediate_typed_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readback = admission_readback(
        "blocked", detail="canonical branch policy unavailable",
    )
    provider_call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        return dict(readback)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    result = inspect(complete_input())
    assert provider_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert result["detail"] == readback["reason"]
    assert result["s4_readback"] == readback
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False



@pytest.mark.parametrize(
    "readback",
    [
        canonical_s4(reason="unknown_reason"),
        canonical_s4(reason=admission_readback("not_admitted", branch_policy_digest="sha256:" + "b" * 64)["reason"]),
        {
            **admission_readback(
                "not_admitted", branch_policy_digest="sha256:" + "b" * 64,
            ),
            "reason": "unknown_reason",
        },
        {
            **admission_readback(
                "not_admitted", branch_policy_digest="sha256:" + "b" * 64,
            ),
            "reason": canonical_s4()["reason"],
        },
        {**admission_readback("blocked"), "reason": " whitespace "},
        {**admission_readback("blocked"), "reason": "parser\x00error"},
    ],
)
def test_s4_reason_drift_returns_objective_typed_blocked(
    monkeypatch: pytest.MonkeyPatch, readback: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission", lambda: readback,
    )
    result = inspect(complete_input())
    assert result["status"] == "blocked"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert result["s4_readback"] == admission_readback("blocked")


def test_all_evaluation_facts_satisfied_only_eligible_without_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission",
        lambda: canonical_s4(write_concurrency=2),
    )
    result = inspect(complete_input())
    assert result["status"] == "eligible_for_activation"
    assert result["allowed_mode"] == "observe_only"
    assert result["checkpoint_reduction_allowed"] is False
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False
    assert result["activation_required"] is True
    assert result["blockers"] == []


def test_any_activation_receipt_is_untrusted_audit_only_and_never_admits_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission",
        lambda: canonical_s4(),
    )
    eligible = inspect(complete_input())
    receipt = {
        "status": "present", "receipt_id": "forged-activation-1", "authenticated": True,
        "exact_bytes_verified": True, "release_evidence_eligible": True,
        "evaluation_digest": eligible["evaluation_digest"],
        "evaluation_bytes_sha256": eligible["evaluation_bytes_sha256"],
    }
    blocked = inspect(complete_input(activation_receipt=receipt))
    assert blocked["status"] == "not_admitted"
    assert blocked["allowed_mode"] == "manual"
    assert blocked["checkpoint_reduction_allowed"] is False
    assert blocked["max_write_concurrency"] == 1
    assert blocked["grant_executable"] is False
    assert blocked["mutation_allowed"] is False
    assert blocked["activation_required"] is True
    assert "ACTIVATION_PROVIDER_UNAVAILABLE" in blocked["blockers"]

    for override in (
        {"authenticated": False},
        {"release_evidence_eligible": False},
        {"exact_bytes_verified": False},
        {"evaluation_digest": "sha256:" + "0" * 64},
        {"evaluation_bytes_sha256": "sha256:" + "1" * 64},
    ):
        candidate = dict(receipt)
        candidate.update(override)
        result = inspect(complete_input(activation_receipt=candidate))
        assert result["status"] == "not_admitted"
        assert result["blockers"][0] == "ACTIVATION_PROVIDER_UNAVAILABLE"
        assert result["grant_executable"] is False
        assert result["max_write_concurrency"] == 1
        assert result["mutation_allowed"] is False


def test_non_admitted_results_always_use_canonical_fallback_even_when_s4_is_higher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission",
        lambda: canonical_s4(),
    )
    result = inspect(complete_input(authority_readback=None))
    assert result["status"] == "not_admitted"
    assert result["s4_readback"]["write_concurrency"] == 2
    assert result["allowed_mode"] == "manual"
    assert result["checkpoint_reduction_allowed"] is False
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False


def test_blocked_results_always_use_canonical_fallback_even_when_s4_is_higher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission",
        lambda: canonical_s4(),
    )
    result = inspect(complete_input(risk_tier="R4"))
    assert result["status"] == "blocked"
    assert result["s4_readback"]["write_concurrency"] == 2
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False



@pytest.mark.parametrize(
    "dependency_name",
    ["canonical_json_bytes", "canonical_digest", "fingerprint_ref"],
)
def test_evidence_fingerprint_dependency_failures_return_typed_blocked(
    monkeypatch: pytest.MonkeyPatch, dependency_name: str,
) -> None:
    class DependencyFailure(RuntimeError):
        pass

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise DependencyFailure(f"{dependency_name} dependency failed")

    provider_call_count = 0
    expected_s4 = canonical_s4()

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        return dict(expected_s4)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    monkeypatch.setattr(evaluator_module, dependency_name, fail)
    result = inspect(current_input())
    assert provider_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.EVALUATION_IDENTITY_FAILED"
    assert result["blockers"] == ["EVALUATION_IDENTITY_FAILED"]
    assert dependency_name in result["detail"]
    assert "dependency failed" in result["detail"]
    assert result["s4_readback"] == expected_s4
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False



def test_s4_provider_failure_is_called_once_and_returns_typed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        raise OSError("Objective admission provider unavailable")

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    result = inspect(complete_input())
    assert call_count == 1
    assert result["status"] == "blocked"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert "provider unavailable" in result["detail"]
    assert result["s4_readback"] == admission_readback("blocked")
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False

def test_s4_normal_fallback_failure_uses_objective_owned_emergency_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_call_count = 0
    normal_fallback_call_count = 0
    emergency_fallback_call_count = 0
    expected = admission_readback("blocked")

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        raise OSError("Objective admission provider unavailable")

    def normal_fallback() -> dict[str, Any]:
        nonlocal normal_fallback_call_count
        normal_fallback_call_count += 1
        raise ContractError("Objective canonical contract unavailable")

    def emergency_fallback() -> dict[str, Any]:
        nonlocal emergency_fallback_call_count
        emergency_fallback_call_count += 1
        return dict(expected)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    monkeypatch.setattr(evaluator_module, "objective_blocked_s4_fallback", normal_fallback)
    monkeypatch.setattr(
        evaluator_module, "objective_emergency_blocked_s4_fallback", emergency_fallback,
    )
    result = inspect(complete_input())
    assert provider_call_count == normal_fallback_call_count == emergency_fallback_call_count == 1
    assert result["status"] == "blocked"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert result["s4_readback"] == expected


def test_s4_malformed_then_valid_provider_is_called_once_and_preserves_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = canonical_s4()
    malformed = dict(valid)
    malformed["stage"] = "S3"
    readbacks = iter((malformed, valid))
    call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return next(readbacks)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    result = inspect(complete_input())
    assert call_count == 1
    assert result["status"] == "blocked"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert "stage must be S4" in result["detail"]
    assert result["s4_readback"] == admission_readback("blocked")

def test_nfc_normalized_member_and_proof_id_collisions_are_typed_contract_errors() -> None:
    member_collision = complete_input(
        cohort_proof=cohort(member_ids=["é", "e\u0301"]),
    )
    with pytest.raises(ContractError, match="NFC normalization"):
        inspect(member_collision)

    controls = [control(action) for action in ("pause", "deny", "abort", "revoke")]
    controls[0]["proof_id"] = "é"
    controls[1]["proof_id"] = "e\u0301"
    with pytest.raises(ContractError, match="duplicate proof_id"):
        inspect(complete_input(control_proofs=controls))


def test_nfc_normalized_stable_ids_produce_stable_output_and_digest() -> None:
    composed = complete_input(
        cohort_proof=cohort(
            cohort_id="cohort-é", member_count=1, member_ids=["member-é"],
        ),
        control_proofs=[
            control(action, proof_id=f"proof-é-{action}")
            for action in ("pause", "deny", "abort", "revoke")
        ],
    )
    decomposed = copy.deepcopy(composed)
    decomposed["cohort_proof"]["cohort_id"] = "cohort-e\u0301"
    decomposed["cohort_proof"]["member_ids"] = ["member-e\u0301"]
    for proof in decomposed["control_proofs"]:
        proof["proof_id"] = proof["proof_id"].replace("é", "e\u0301")

    left = inspect(composed)
    right = inspect(decomposed)
    assert left == right
    assert left["evaluation_digest"] == right["evaluation_digest"]
    assert left["evaluation_digest"].startswith("sha256:")
    assert left["subject"] == composed["subject"]


def test_input_collection_order_does_not_change_digest_or_blocker_order() -> None:
    first = current_input()
    first["cohort_proof"] = cohort(member_ids=["member-b", "member-a"], coverage_basis_points=8999, human_calibration="not_observed")
    first["control_proofs"] = [control("revoke"), control("pause"), control("abort"), control("deny")]
    second = copy.deepcopy(first)
    second["cohort_proof"]["member_ids"] = list(reversed(second["cohort_proof"]["member_ids"]))
    second["cohort_proof"]["wait_event_kinds"] = list(reversed(second["cohort_proof"]["wait_event_kinds"]))
    second["control_proofs"] = list(reversed(second["control_proofs"]))
    left = inspect(first)
    right = inspect(second)
    assert left["evaluation_digest"] == right["evaluation_digest"]
    assert left["evaluation_fingerprint_ref"] == right["evaluation_fingerprint_ref"]
    assert left["blockers"] == right["blockers"]
