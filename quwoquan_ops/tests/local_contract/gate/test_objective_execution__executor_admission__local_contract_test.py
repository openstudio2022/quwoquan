"""Objective executor authority/effect/admission local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t5
# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-004.t3
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.human_agent_delivery import production_concurrency_policy, project_authorization_grant  # noqa: E402
from lib.objective_execution import (  # noqa: E402
    AuthorityReadback,
    ExecutorDependencies,
    execute_authorized_effect,
    inspect_admission,
    read_events,
    readback,
)
from lib.objective_execution.journal import writer_lease  # noqa: E402
from lib.objective_execution.contract import (  # noqa: E402
    ContractError,
    admission_readback,
    admission_readback_contract,
    emergency_blocked_admission_fallback,
    load_contract,
    validate_admission_readback,
    validate_contract,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def claims(**overrides: Any) -> dict[str, Any]:
    value = {
        "receipt_id": "authority-1", "decision_id": "authority-1", "decision_unit_id": "unit-1",
        "actor_id": "actor-1", "actor_authenticated": True,
        "role": "engineering_delivery_owner", "scope": {"objective": "objective-1"},
        "expires_at": "2026-08-30T00:00:00Z", "evidence_fingerprint": "sha256:evidence",
        "decision_kind": "delivery_authorization", "actions": ["create_objective"],
        "provider_kind": "test", "provider_version": "test", "provider_commit": "sha256:" + "0" * 64,
        "contract_version": "test", "issuer": "test", "receipt_state": "available",
        "receipt_previous_generation": 0, "receipt_generation": 1, "receipt_etag": '"test-available"',
        "chain_commit": "sha256:" + "0" * 64, "winner_idempotency_key": "",
        "winner_command_digest": "",
    }
    value.update(overrides)
    return value


class Provider:
    provider_kind = "test"
    release_evidence_eligible = False

    def __init__(self, value: dict[str, Any] | None, *, status: str = "present") -> None:
        self.value = value
        self.status = status

    def readback(self, receipt_ref: str) -> AuthorityReadback:
        if self.status != "present":
            return AuthorityReadback(self.status, detail=self.status)
        assert self.value is not None
        return AuthorityReadback("present", canonical(self.value), "provider:test:receipt-1")


class Verifier:
    def verify(self, exact_bytes: bytes, provider_receipt_ref: str) -> dict[str, Any]:
        assert provider_receipt_ref == "provider:test:receipt-1"
        return json.loads(exact_bytes)


class Effect:
    def __init__(self, status: str = "applied") -> None:
        self.status = status
        self.invoke_count = 0
        self.keys: set[str] = set()

    def invoke(self, *, action: str, effect_id: str, idempotency_key: str, payload: dict[str, Any]) -> None:
        assert action in {"create_objective", "request_clarification"}
        assert effect_id
        self.invoke_count += 1
        self.keys.add(idempotency_key)

    def readback(self, *, effect_id: str, idempotency_key: str) -> dict[str, Any]:
        assert effect_id
        return {
            "status": self.status, "effect_id": effect_id, "idempotency_key": idempotency_key,
            "exact_match": self.status == "applied",
            "provider_receipt_ref": f"readback-{effect_id}",
        }


def command(*, key: str = "key-1") -> dict[str, Any]:
    return {
        "subject_kind": "objective", "subject_id": "objective-1", "target_state": "draft",
        "authority_receipt_ref": "authority:test:1", "expected_scope": {"objective": "objective-1"},
        "expected_evidence_fingerprint": "sha256:evidence",
        "expected_decision_kind": "delivery_authorization", "action": "create_objective",
        "effect_id": f"effect-{key}", "effect_idempotency_key": key,
        "occurred_at": "2026-08-29T12:00:00Z",
        "payload": {"increment": "increment-1"},
    }


def dependencies(value: dict[str, Any] | None = None, *, status: str = "present", effect: Effect | None = None) -> ExecutorDependencies:
    return ExecutorDependencies(
        authority_provider=Provider(value if value is not None else claims(), status=status),
        authority_verifier=Verifier(), effect_adapter=effect or Effect(),
    )


def decision_record() -> dict[str, object]:
    return {
        "decision_id": "decision-1", "decision_unit_id": "unit-1",
        "decision_kind": "delivery_authorization", "selected_option_id": "go",
        "accountable_role": "engineering_delivery_owner", "actor_id": "actor-1",
        "actor_authenticated": True, "authority_source": "projection-only",
        "recorded_at": "2026-08-29T00:00:00Z", "expires_at": "2026-08-30T00:00:00Z",
        "scope": {"objective": "objective-1"}, "append_only": True, "consumed": False,
    }


@pytest.mark.parametrize(
    ("value", "status"),
    [
        (None, "absent"),
        (claims(expires_at="2026-08-28T00:00:00Z"), "present"),
        (claims(scope={"objective": "other"}), "present"),
        (claims(evidence_fingerprint="sha256:other"), "present"),
        (claims(role=""), "present"),
        (claims(actor_authenticated=False), "present"),
        (claims(decision_kind="product_scope"), "present"),
        (claims(actions=[]), "present"),
    ],
)
def test_invalid_authority_has_zero_mutation_and_zero_effect(tmp_path: Path, value: dict[str, Any] | None, status: str) -> None:
    effect = Effect()
    result = execute_authorized_effect(
        tmp_path / "journal", command(), dependencies=dependencies(value, status=status, effect=effect), now=NOW
    )
    assert result["result"] == "typed_blocker"
    assert effect.invoke_count == 0
    assert readback(tmp_path / "journal", "objective", "objective-1").status == "absent"


def test_command_scope_must_bind_subject_identity_before_effect(tmp_path: Path) -> None:
    mismatched = command()
    mismatched["subject_id"] = "objective-other"
    effect = Effect()
    result = execute_authorized_effect(
        tmp_path / "journal", mismatched, dependencies=dependencies(effect=effect), now=NOW,
    )
    assert result["code"] == "OEX.AUTHORITY_INVALID"
    assert effect.invoke_count == 0
    assert readback(tmp_path / "journal", "objective", "objective-other").status == "absent"


def test_projection_grant_and_missing_production_provider_have_zero_mutation(tmp_path: Path) -> None:
    projection = project_authorization_grant(decision_record())
    assert projection is not None
    effect = Effect()
    rejected = execute_authorized_effect(
        tmp_path / "journal", command(), dependencies=dependencies(effect=effect),
        projection_authority=projection, now=NOW,
    )
    assert rejected["code"] == "OEX.AUTHORITY_PROJECTION_ONLY"
    assert effect.invoke_count == 0
    unavailable = execute_authorized_effect(tmp_path / "journal", command(), now=NOW)
    assert unavailable["code"] == "OEX.AUTHORITY_PROVIDER_UNAVAILABLE"
    assert readback(tmp_path / "journal", "objective", "objective-1").status == "absent"


def test_test_authority_and_exact_effect_readback_commit_two_events_but_not_release_evidence(tmp_path: Path) -> None:
    effect = Effect()
    result = execute_authorized_effect(
        tmp_path / "journal", command(), dependencies=dependencies(effect=effect), now=NOW
    )
    assert result["result"] == "committed"
    assert result["release_evidence_eligible"] is False
    assert effect.invoke_count == 1
    events = read_events(tmp_path / "journal", "objective", "objective-1")
    assert [event["event_kind"] for event in events] == [
        "human_decision_recorded", "state_transition_committed"
    ]
    assert result["readback"]["reduced_state"] == "draft"


def test_decision_recorded_without_transition_recovers_and_idempotency_does_not_repeat_effect(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    unknown = Effect(status="unknown")
    pending = execute_authorized_effect(journal, command(), dependencies=dependencies(effect=unknown), now=NOW)
    assert pending["result"] == "pending_readback"
    assert pending["retry_effect"] is False
    assert [event["event_kind"] for event in read_events(journal, "objective", "objective-1")] == [
        "human_decision_recorded"
    ]
    applied = Effect()
    recovered = execute_authorized_effect(journal, command(), dependencies=dependencies(effect=applied), now=NOW)
    assert recovered["result"] == "committed"
    assert recovered["effect_invoked"] is False
    assert applied.invoke_count == 0
    duplicate = execute_authorized_effect(journal, command(), dependencies=dependencies(effect=applied), now=NOW)
    assert duplicate["result"] == "duplicate"
    assert duplicate["effect_invoked"] is False
    assert applied.invoke_count == 0
    assert len(read_events(journal, "objective", "objective-1")) == 2


def test_pending_recovery_binds_full_command_envelope_and_persisted_effect_id(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    unknown = Effect(status="unknown")
    original = command()
    pending = execute_authorized_effect(journal, original, dependencies=dependencies(effect=unknown), now=NOW)
    assert pending["result"] == "pending_readback"
    decision = read_events(journal, "objective", "objective-1")[0]
    envelope = decision["payload"]["command_envelope"]
    assert decision["command_envelope_digest"] == decision["payload"]["command_envelope_digest"]
    assert decision["effect_id"] == original["effect_id"] == envelope["effect_id"]
    assert envelope["subject_kind"] == "objective" and envelope["target_state"] == "draft"
    assert envelope["expected_scope"] == original["expected_scope"]
    assert envelope["authority_provider_kind"] == "test"
    assert envelope["authority_claims_digest"].startswith("sha256:")

    class BoundEffect(Effect):
        def __init__(self) -> None:
            super().__init__()
            self.readback_effect_ids: list[str] = []
        def readback(self, *, effect_id: str, idempotency_key: str) -> dict[str, Any]:
            self.readback_effect_ids.append(effect_id)
            return super().readback(effect_id=effect_id, idempotency_key=idempotency_key)

    recovered_effect = BoundEffect()
    recovered = execute_authorized_effect(journal, original, dependencies=dependencies(effect=recovered_effect), now=NOW)
    assert recovered["result"] == "committed"
    assert recovered["effect_invoked"] is False and recovered_effect.invoke_count == 0
    assert recovered_effect.readback_effect_ids == [original["effect_id"]]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(target_state="accepted"),
        lambda value: value.update(action="request_clarification"),
        lambda value: value.update(payload={"increment": "other"}),
        lambda value: value.update(expected_scope={"objective": "other"}),
        lambda value: value.update(expected_evidence_fingerprint="sha256:other"),
        lambda value: value.update(expected_decision_kind="product_scope"),
        lambda value: value.update(authority_receipt_ref="authority:test:other"),
        lambda value: value.update(effect_id="effect-other"),
    ],
)
def test_pending_command_identity_mismatch_has_typed_conflict_zero_effect_zero_transition(
    tmp_path: Path, mutate: Any,
) -> None:
    journal = tmp_path / "journal"
    pending = execute_authorized_effect(journal, command(), dependencies=dependencies(effect=Effect(status="unknown")), now=NOW)
    assert pending["result"] == "pending_readback"
    before = read_events(journal, "objective", "objective-1")
    changed = command()
    mutate(changed)
    claims_value = claims(
        scope=changed["expected_scope"],
        evidence_fingerprint=changed["expected_evidence_fingerprint"],
        decision_kind=changed["expected_decision_kind"],
        actions=[changed["action"]],
    )
    effect = Effect()
    result = execute_authorized_effect(journal, changed, dependencies=dependencies(claims_value, effect=effect), now=NOW)
    if changed["expected_scope"].get(changed["subject_kind"]) != changed["subject_id"]:
        assert result["code"] == "OEX.AUTHORITY_INVALID"
        assert result["terminal"] == "blocked"
    else:
        assert result["code"] == "OEX.PENDING_COMMAND_CONFLICT"
        assert result["terminal"] == "conflict"
    assert effect.invoke_count == 0
    assert read_events(journal, "objective", "objective-1") == before


def test_provider_receipt_identity_drift_conflicts_without_effect(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    execute_authorized_effect(journal, command(), dependencies=dependencies(effect=Effect(status="unknown")), now=NOW)

    class OtherProvider(Provider):
        def readback(self, receipt_ref: str) -> AuthorityReadback:
            assert self.value is not None
            return AuthorityReadback("present", canonical(self.value), "provider:test:receipt-other")

    class OtherVerifier:
        def verify(self, exact_bytes: bytes, provider_receipt_ref: str) -> dict[str, Any]:
            assert provider_receipt_ref == "provider:test:receipt-other"
            return json.loads(exact_bytes)

    effect = Effect()
    result = execute_authorized_effect(
        journal, command(), dependencies=ExecutorDependencies(OtherProvider(claims()), OtherVerifier(), effect), now=NOW,
    )
    assert result["code"] == "OEX.PENDING_COMMAND_CONFLICT"
    assert effect.invoke_count == 0 and len(read_events(journal, "objective", "objective-1")) == 1


def test_effect_readback_identity_mismatch_never_transitions(tmp_path: Path) -> None:
    class WrongEffect(Effect):
        def readback(self, *, effect_id: str, idempotency_key: str) -> dict[str, Any]:
            assert effect_id
            return {"status": "applied", "effect_id": "effect-other", "idempotency_key": idempotency_key, "exact_match": True, "provider_receipt_ref": "wrong"}

    effect = WrongEffect()
    result = execute_authorized_effect(tmp_path / "journal", command(), dependencies=dependencies(effect=effect), now=NOW)
    assert result["code"] == "OEX.EFFECT_IDENTITY_CONFLICT"
    assert result["retry_effect"] is False and effect.invoke_count == 1
    assert [event["event_kind"] for event in read_events(tmp_path / "journal", "objective", "objective-1")] == ["human_decision_recorded"]


def test_illegal_transition_is_blocked_before_effect_and_journal_mutation(tmp_path: Path) -> None:
    invalid = command()
    invalid.update(action="accept_objective", target_state="accepted")
    effect = Effect()
    result = execute_authorized_effect(
        tmp_path / "journal", invalid,
        dependencies=dependencies(claims(actions=["accept_objective"]), effect=effect), now=NOW,
    )
    assert result["code"] == "OEX.TRANSITION_INVALID" and result["terminal"] == "blocked"
    assert effect.invoke_count == 0
    assert readback(tmp_path / "journal", "objective", "objective-1").status == "absent"




def test_observe_only_adapter_preserves_executor_effect_id_through_execution(tmp_path: Path) -> None:
    from lib.objective_execution.hosted_provider import ObserveOnlyEffectAdapter
    observe = command()
    observe.update(effect_id="observe-effect-1", payload={"environment": "gamma", "mutation": False})
    value = claims()
    adapter = ObserveOnlyEffectAdapter()
    result = execute_authorized_effect(tmp_path / "journal", observe, dependencies=dependencies(value, effect=adapter), now=NOW)
    assert result["result"] == "committed"
    event = read_events(tmp_path / "journal", "objective", "objective-1")[-1]
    assert event["effect_readback"]["effect_id"] == "observe-effect-1"

class HostedProvider(Provider):
    provider_kind = "hosted-human-authority"
    def __init__(self, initial: dict[str, Any], *, consume_outcome: str = "winner") -> None:
        super().__init__(initial)
        self.consume_outcome = consume_outcome
        self.consume_count = 0
        self.reconcile_count = 0
        self._responses_by_provider_ref: dict[str, Any] = {}
        self.client = self
        self.config = type("Config", (), {"expected_issuer": "https://authority.example.com"})()
    def consume(self, decision_id: str, **values: Any) -> Any:
        self.consume_count += 1
        if self.consume_outcome == "unknown":
            error = RuntimeError("unknown")
            error.code = "HOSTED_AUTHORITY.COMMAND_OUTCOME_UNKNOWN"
            raise error
        if self.consume_outcome == "conflict":
            error = RuntimeError("conflict")
            error.code = "HOSTED_AUTHORITY.CAS_CONFLICT"
            raise error
        winner = dict(self.value or {})
        winner.update(receipt_state="consumed", receipt_previous_generation=1, receipt_generation=2, receipt_etag='"consumed"',
            winner_idempotency_key=values["idempotency_key"], winner_command_digest=values["command_digest"],
            chain_commit="sha256:" + "9" * 64)
        self.value = winner
        return type("Response", (), {"exact_body": canonical(winner), "envelope": type("Envelope", (), {"provider_receipt_ref": "provider:hosted:1"})()})()
    def reconcile(self, decision_id: str, *, idempotency_key: str) -> Any:
        self.reconcile_count += 1
        return type("Response", (), {"exact_body": canonical(self.value or {}), "envelope": type("Envelope", (), {"provider_receipt_ref": "provider:hosted:1"})()})()

class HostedVerifier(Verifier):
    def verify(self, exact_bytes: bytes, provider_receipt_ref: str) -> dict[str, Any]:
        return json.loads(exact_bytes)


def hosted_dependencies(provider: HostedProvider, effect: Effect, failpoint: Any = None) -> ExecutorDependencies:
    return ExecutorDependencies(provider, HostedVerifier(), effect, failpoint)


def test_hosted_consume_winner_precedes_first_journal_event_and_effect(tmp_path: Path) -> None:
    provider = HostedProvider(claims(issuer="https://authority.example.com", provider_kind="hosted-human-authority"))
    effect = Effect()
    result = execute_authorized_effect(tmp_path / "journal", command(), dependencies=hosted_dependencies(provider, effect), now=NOW)
    assert result["result"] == "committed" and provider.consume_count == 1 and effect.invoke_count == 1
    assert read_events(tmp_path / "journal", "objective", "objective-1")[0]["payload"]["command_envelope"]["authority_winner_idempotency_key"] == "key-1"


def test_hosted_conflict_and_revoke_have_zero_journal_and_zero_effect(tmp_path: Path) -> None:
    for name, provider in (
        ("conflict", HostedProvider(claims(issuer="https://authority.example.com", provider_kind="hosted-human-authority"), consume_outcome="conflict")),
        ("revoked", HostedProvider(claims(issuer="https://authority.example.com", provider_kind="hosted-human-authority", receipt_state="revoked", receipt_previous_generation=1, receipt_generation=2, receipt_etag='"revoked"', winner_idempotency_key="revoke-1", winner_command_digest="sha256:" + "8" * 64))),
    ):
        effect = Effect(); root = tmp_path / name
        result = execute_authorized_effect(root, command(), dependencies=hosted_dependencies(provider, effect), now=NOW)
        assert result["code"] == "OEX.AUTHORITY_CONSUME_CONFLICT"
        assert effect.invoke_count == 0 and read_events(root, "objective", "objective-1") == ()


def test_consume_unknown_reconciles_once_without_retry_or_effect(tmp_path: Path) -> None:
    provider = HostedProvider(claims(issuer="https://authority.example.com", provider_kind="hosted-human-authority"), consume_outcome="unknown")
    effect = Effect()
    result = execute_authorized_effect(tmp_path / "journal", command(), dependencies=hosted_dependencies(provider, effect), now=NOW)
    assert result["code"] == "OEX.AUTHORITY_CONSUME_UNKNOWN"
    assert provider.consume_count == 1 and provider.reconcile_count == 1 and effect.invoke_count == 0
    assert read_events(tmp_path / "journal", "objective", "objective-1") == ()


def test_crash_after_consume_resumes_same_winner_without_second_consume(tmp_path: Path) -> None:
    provider = HostedProvider(claims(issuer="https://authority.example.com", provider_kind="hosted-human-authority"))
    effect = Effect()
    def crash() -> None: raise RuntimeError("crash-after-consume")
    with pytest.raises(RuntimeError, match="crash-after-consume"):
        execute_authorized_effect(tmp_path / "journal", command(), dependencies=hosted_dependencies(provider, effect, crash), now=NOW)
    assert provider.consume_count == 1 and effect.invoke_count == 0 and read_events(tmp_path / "journal", "objective", "objective-1") == ()
    resumed = execute_authorized_effect(tmp_path / "journal", command(), dependencies=hosted_dependencies(provider, effect), now=NOW)
    assert resumed["result"] == "committed" and provider.consume_count == 1 and effect.invoke_count == 1

def test_contract_freezes_pending_identity_transition_graph_and_errors() -> None:
    contract = load_contract()
    assert contract["commands"]["execute_authorized_effect"]["empty_effect_id_readback_allowed"] is False
    assert contract["commands"]["execute_authorized_effect"]["readback_effect_id_source"] == "persisted_human_decision_recorded"
    assert contract["transition_graph"]["graph_version"] == 1
    for mutation in (
        lambda value: value["commands"]["execute_authorized_effect"]["pending_identity_fields"].pop(),
        lambda value: value["transition_graph"]["subjects"]["increment"]["terminal_states"].remove("integrated"),
        lambda value: value["errors"]["OEX.PENDING_COMMAND_CONFLICT"].update(terminal="blocked"),
        lambda value: value["errors"]["OEX.EFFECT_IDENTITY_CONFLICT"].update(recovery="retry_effect"),
    ):
        broken = yaml.safe_load(yaml.safe_dump(contract, sort_keys=False))
        mutation(broken)
        with pytest.raises(ContractError):
            validate_contract(broken)


def test_s4_admission_is_dynamic_not_admitted_single_writer_and_no_temporary_branch() -> None:
    descriptor = admission_readback_contract()
    admission = inspect_admission()
    assert descriptor["schema"] == "admission_readback"
    assert descriptor["stage"] == "S4"
    assert admission == admission_readback(
        "not_admitted", branch_policy_digest=admission["branch_policy_digest"],
    )
    assert admission["write_concurrency"] == 1
    assert admission["temporary_branch_allowed"] is False
    assert production_concurrency_policy() == {"s4_admission": "not_admitted", "write_concurrency": 1}


def test_objective_contract_strictly_owns_admission_wire_reason_terminal_and_consistency() -> None:
    contract = load_contract()
    descriptor = admission_readback_contract()
    assert descriptor == contract["admission"]["readback_contract"]
    assert descriptor["statuses"]["admitted"]["reason"] == "temporary_execution_lifecycle_admitted"
    assert descriptor["statuses"]["not_admitted"]["reason"] == "temporary_execution_lifecycle_not_admitted"
    assert descriptor["statuses"]["blocked"]["terminal"] == "OEX.ADMISSION_BLOCKED"

    valid = admission_readback(
        "admitted", branch_policy_digest="sha256:" + "a" * 64,
    )
    assert validate_admission_readback(valid) == valid
    for mutation in (
        lambda value: value.update(stage="S3"),
        lambda value: value.update(reason="unknown_reason"),
        lambda value: value.update(write_concurrency=1),
        lambda value: value.update(temporary_branch_allowed=False),
        lambda value: value.update(branch_policy_digest=None),
        lambda value: value.update(terminal="not_admitted"),
    ):
        broken = dict(valid)
        mutation(broken)
        with pytest.raises(ContractError):
            validate_admission_readback(broken)

    blocked = admission_readback("blocked", detail="canonical parser failure")
    assert blocked["reason"] == "canonical parser failure"
    for detail in ("", " spaced ", "nul\x00detail"):
        if detail == "":
            assert admission_readback("blocked", detail=detail)["reason"] == descriptor["statuses"]["blocked"]["fallback_reason"]
        else:
            with pytest.raises(ContractError):
                admission_readback("blocked", detail=detail)

    broken_contract = yaml.safe_load(yaml.safe_dump(contract, sort_keys=False))
    broken_contract["admission"]["readback_contract"]["statuses"]["admitted"]["reason"] = "other"
    with pytest.raises(ContractError):
        validate_contract(broken_contract)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["closed_sets"]["admission_status"].append("eligible"),
        lambda value: value["closed_sets"]["admission_status"].pop(),
        lambda value: value["closed_sets"]["admission_status"].reverse(),
        lambda value: value["schemas"]["admission_readback"]["required_fields"].append("extra"),
        lambda value: value["schemas"]["admission_readback"]["required_fields"].pop(),
        lambda value: value["schemas"]["admission_readback"]["required_fields"].reverse(),
        lambda value: value["admission"]["readback_contract"]["statuses"].update(eligible={}),
        lambda value: value["admission"]["readback_contract"]["statuses"].pop("blocked"),
        lambda value: value["admission"]["readback_contract"]["statuses"].update(
            {
                "admitted": value["admission"]["readback_contract"]["statuses"].pop("not_admitted"),
                "not_admitted": value["admission"]["readback_contract"]["statuses"].pop("admitted"),
            }
        ),
    ],
)
def test_objective_v2_admission_status_and_readback_wire_are_exact_closed_sets(mutate: Any) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    mutate(broken)
    with pytest.raises(ContractError):
        validate_contract(broken)


@pytest.mark.parametrize(
    ("field", "drifted"),
    [
        ("loser_effect_allowed", True),
        ("loser_effect_allowed", 0),
        ("loser_event_allowed", True),
        ("loser_event_allowed", None),
        ("reads_may_run_in_parallel", False),
        ("reads_may_run_in_parallel", 1),
    ],
)
def test_admission_runtime_invariants_require_exact_bool_values(
    field: str, drifted: object,
) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["admission"][field] = drifted
    with pytest.raises(ContractError, match=field):
        validate_contract(broken)


@pytest.mark.parametrize(
    ("code", "field", "drifted"),
    [
        ("OEX.CONTRACT_INVALID", "terminal", "not_admitted"),
        ("OEX.CONTRACT_INVALID", "recovery", "other_recovery"),
        ("OEX.ADMISSION_BLOCKED", "terminal", "not_admitted"),
        ("OEX.ADMISSION_BLOCKED", "recovery", "other_recovery"),
        ("OEX.AUTHORITY_PROVIDER_UNAVAILABLE", "recovery", "other_recovery"),
        ("OEX.EFFECT_OUTCOME_UNKNOWN", "terminal", "blocked"),
    ],
)
def test_required_error_descriptors_are_exact_v2_mappings(
    code: str, field: str, drifted: object,
) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["errors"][code][field] = drifted
    with pytest.raises(ContractError, match=code):
        validate_contract(broken)


@pytest.mark.parametrize(
    "code",
    [
        "OEX.CONTRACT_INVALID",
        "OEX.JOURNAL_FAILED",
        "OEX.JOURNAL_TAMPERED",
        "OEX.JOURNAL_RECOVERY_REQUIRED",
        "OEX.CAS_CONFLICT",
        "OEX.WRITER_LEASE_CONFLICT",
        "OEX.AUTHORITY_PROVIDER_UNAVAILABLE",
        "OEX.AUTHORITY_ABSENT",
        "OEX.AUTHORITY_INVALID",
        "OEX.AUTHORITY_PROJECTION_ONLY",
        "OEX.TRANSITION_INVALID",
        "OEX.PENDING_COMMAND_CONFLICT",
        "OEX.EFFECT_IDENTITY_CONFLICT",
        "OEX.EFFECT_OUTCOME_UNKNOWN",
        "OEX.ADMISSION_BLOCKED",
    ],
)
def test_required_implementation_error_code_cannot_be_removed(code: str) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["errors"].pop(code)
    with pytest.raises(ContractError, match="typed errors v2 closed set drifted"):
        validate_contract(broken)


def test_required_error_descriptor_rejects_extra_fields() -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["errors"]["OEX.CONTRACT_INVALID"]["extra"] = "value"
    with pytest.raises(ContractError, match="typed error OEX.CONTRACT_INVALID fields drifted"):
        validate_contract(broken)


def test_admission_derivation_is_complete_closed_lifecycle_causes_only() -> None:
    contract = load_contract()
    assert contract["admission"]["derivation"] == {
        "admitted_requires_all": [
            "pull_request_prefix_declared",
            "isolated_writer_branch",
            "declared_promotion_path",
            "mandatory_cleanup_after_promotion_or_abort",
            "concurrency_evidence_required",
        ]
    }
    for mutation in (
        lambda value: value["admission"]["derivation"]["admitted_requires_all"].pop(),
        lambda value: value["admission"]["derivation"]["admitted_requires_all"].append("other"),
        lambda value: value["admission"]["derivation"]["admitted_requires_all"].reverse(),
    ):
        broken = yaml.safe_load(yaml.safe_dump(contract, sort_keys=False))
        mutation(broken)
        with pytest.raises(ContractError):
            validate_contract(broken)


@pytest.mark.parametrize(
    "duplicate_field", ["status", "write_concurrency", "temporary_branch_allowed"],
)
def test_admission_rejects_reintroduced_derivation_result_fields(duplicate_field: str) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["admission"]["derivation"][duplicate_field] = (
        "not_admitted" if duplicate_field == "status" else 1
    )
    with pytest.raises(ContractError):
        validate_contract(broken)


def test_admission_top_level_is_exact_and_emergency_fallback_is_yaml_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = yaml.safe_load(yaml.safe_dump(load_contract(), sort_keys=False))
    broken["admission"]["unexpected"] = False
    with pytest.raises(ContractError):
        validate_contract(broken)

    from lib.objective_execution import contract as contract_module

    monkeypatch.setattr(
        contract_module, "load_contract",
        lambda: (_ for _ in ()).throw(ContractError("canonical contract unavailable")),
    )
    assert emergency_blocked_admission_fallback() == {
        "status": "blocked", "stage": "S4", "write_concurrency": 0,
        "temporary_branch_allowed": False, "branch_policy_digest": None,
        "reason": "dynamic_inspection_unavailable", "terminal": "OEX.ADMISSION_BLOCKED",
    }


def test_temporary_prefix_alone_is_not_admitted_and_complete_lifecycle_is_admitted() -> None:
    from lib.objective_execution.admission import (
        temporary_execution_admitted_from_policy_bytes,
    )
    policy = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(encoding="utf-8")
    )
    policy["pull_request_branch_prefixes"] = ["increment/"]
    policy["allowed_pull_request_edges"].append(
        {"head": "increment/*", "base": "dev1.0"}
    )
    prefix_only_raw = yaml.safe_dump(policy, sort_keys=False).encode("utf-8")
    assert temporary_execution_admitted_from_policy_bytes(prefix_only_raw) is False

    policy["temporary_execution_admission"] = {
        "isolation": "branch_per_writer",
        "promotion": "declared_pull_request_edge_only",
        "cleanup": "mandatory_after_promotion_or_abort",
        "concurrency_evidence": "required",
    }
    complete_raw = yaml.safe_dump(policy, sort_keys=False).encode("utf-8")
    assert temporary_execution_admitted_from_policy_bytes(complete_raw) is True


def test_inspect_admission_has_no_path_injection_and_reads_canonical_bytes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inspect
    from lib.objective_execution import admission as admission_module

    assert tuple(inspect.signature(inspect_admission).parameters) == ()
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    read_count = 0
    seen: list[bytes] = []

    class ReadOncePath:
        def read_bytes(self) -> bytes:
            nonlocal read_count
            read_count += 1
            if read_count > 1:
                raise AssertionError("Objective admission read branch policy twice")
            return raw

    actual_parser = admission_module.load_policy_bytes

    def parser(payload: bytes) -> Any:
        seen.append(payload)
        return actual_parser(payload)

    monkeypatch.setattr(admission_module, "BRANCH_POLICY_PATH", ReadOncePath())
    monkeypatch.setattr(admission_module, "load_policy_bytes", parser)
    result = inspect_admission()
    assert read_count == 1
    assert seen == [raw]
    assert result["branch_policy_digest"] == "sha256:" + __import__("hashlib").sha256(raw).hexdigest()


def test_s4_parser_failure_detail_is_trimmed_and_nul_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import admission as admission_module

    monkeypatch.setattr(
        admission_module,
        "load_policy_bytes",
        lambda _raw: (_ for _ in ()).throw(ValueError("  parser\x00failure  ")),
    )
    blocked = inspect_admission()
    assert blocked == admission_readback("blocked", detail="parser\\x00failure")


def test_parallel_admission_queries_use_cached_import_and_independent_exact_reads() -> None:
    from lib.objective_execution import admission as admission_module

    assert "importlib.util" not in Path(admission_module.__file__).read_text(encoding="utf-8")
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: inspect_admission(), range(24)))
    assert len({result["branch_policy_digest"] for result in results}) == 1
    assert all(result["status"] == "not_admitted" for result in results)


def test_writer_lease_loser_has_zero_effect_and_zero_event(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    effect = Effect()
    with writer_lease(journal, "objective", "objective-1"):
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(
                execute_authorized_effect, journal, command(),
                dependencies=dependencies(effect=effect), now=NOW,
            ).result()
    assert result["code"] == "OEX.WRITER_LEASE_CONFLICT"
    assert result["effect_invoked"] is False
    assert effect.invoke_count == 0
    assert read_events(journal, "objective", "objective-1") == ()
