"""Objective journal recovery, reducer and transition-graph local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t5
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t6
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t7
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t8
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t9
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t10
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t11
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.usefixtures("isolated_qwq_output_root")

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.objective_execution import (  # noqa: E402
    CASConflict, WriterLeaseConflict, append_event, load_contract, read_events,
    readback, recover_materialization, reduce_events, validate_contract,
)
from lib.objective_execution.contract import ContractError, ObjectiveExecutionError  # noqa: E402
from lib.objective_execution.journal import payload_digest  # noqa: E402


class SimulatedCrash(RuntimeError):
    pass


def authority_claims(action: str) -> dict[str, Any]:
    return {
        "receipt_id": "authority-1", "decision_id": "authority-1",
        "decision_unit_id": "unit-1", "actor_id": "actor-1",
        "actor_authenticated": True, "role": "engineering_delivery_owner",
        "scope": {"objective": "objective-1"},
        "expires_at": "2026-08-30T00:00:00Z",
        "evidence_fingerprint": "sha256:evidence",
        "decision_kind": "delivery_authorization", "actions": [action], "provider_kind": "test",
        "provider_version": "test", "provider_commit": "sha256:" + "0" * 64,
        "contract_version": "test", "issuer": "test", "receipt_state": "consumed",
        "receipt_previous_generation": 1, "receipt_generation": 2,
        "receipt_etag": '"test-consumed"',
        "chain_commit": "sha256:" + "1" * 64,
        "winner_idempotency_key": "create-1",
        "winner_command_digest": "sha256:" + "2" * 64,
    }


def envelope(*, action: str, target_state: str, effect_id: str, key: str, source_state: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 2, "subject_kind": "objective", "subject_id": "objective-1",
        "source_state": source_state, "target_state": target_state,
        "authority_receipt_ref": "authority:test:1", "expected_scope": {"objective": "objective-1"},
        "expected_evidence_fingerprint": "sha256:evidence", "expected_decision_kind": "delivery_authorization",
        "action": action, "effect_id": effect_id, "effect_idempotency_key": key,
        "occurred_at": "2026-08-29T12:00:00Z", "payload": {"case": key},
        "authority_provider_kind": "test", "authority_provider_receipt_ref": "provider:test:1",
        "authority_claims_digest": payload_digest(authority_claims(action)),
        "authority_winner_idempotency_key": authority_claims(action)["winner_idempotency_key"],
        "authority_winner_command_digest": authority_claims(action)["winner_command_digest"],
        "authority_winner_previous_generation": authority_claims(action)["receipt_previous_generation"],
        "authority_winner_generation": authority_claims(action)["receipt_generation"],
        "authority_chain_commit": authority_claims(action)["chain_commit"],
    }


def command(
    *, event_kind: str, action: str, from_state: str | None, to_state: str | None,
    expected_head: str, expected_generation: int, key: str, effect_id: str | None = None,
    effect_readback: dict[str, object] | None = None, command_envelope: dict[str, Any] | None = None,
) -> dict[str, object]:
    resolved_effect_id = effect_id or f"effect-{key}"
    resolved_envelope = command_envelope or envelope(action=action, target_state=str(to_state), effect_id=resolved_effect_id, key=key, source_state=from_state)
    digest = payload_digest(resolved_envelope)
    payload: dict[str, Any] = {"case": key}
    if event_kind == "human_decision_recorded":
        payload = {
            "command_envelope": resolved_envelope, "command_envelope_digest": digest,
            "authority_claims": authority_claims(action),
            "release_evidence_eligible": False,
            "provider_receipt_ref": "provider:test:1",
        }
    return {
        "subject_kind": "objective", "subject_id": "objective-1", "event_kind": event_kind,
        "reducer_version": 1, "action": action, "from_state": from_state, "to_state": to_state,
        "expected_head": expected_head, "expected_generation": expected_generation,
        "authority_receipt_ref": "authority:test:1", "effect_idempotency_key": key,
        "command_envelope_digest": digest, "effect_id": resolved_effect_id,
        "effect_readback": effect_readback, "occurred_at": "2026-08-29T12:00:00Z", "payload": payload,
    }


def applied(key: str, *, effect_id: str | None = None) -> dict[str, object]:
    resolved_effect_id = effect_id or f"effect-{key}"
    return {"status": "applied", "effect_id": resolved_effect_id, "idempotency_key": key, "exact_match": True, "provider_receipt_ref": f"effect-receipt-{key}"}


def record_and_transition(journal: Path, *, failpoint: str | None = None) -> dict[str, Any]:
    key = "create-1"
    effect_id = "effect-create-1"
    env = envelope(action="create_objective", target_state="draft", effect_id=effect_id, key=key)
    recorded = append_event(journal, command(event_kind="human_decision_recorded", action="create_objective", from_state=None, to_state=None, expected_head="absent", expected_generation=0, key=key, effect_id=effect_id, command_envelope=env))
    trigger = None
    if failpoint is not None:
        trigger = lambda name: (_ for _ in ()).throw(SimulatedCrash(name)) if name == failpoint else None
    return append_event(
        journal,
        command(event_kind="state_transition_committed", action="create_objective", from_state=None, to_state="draft", expected_head=recorded["readback"]["head"], expected_generation=recorded["readback"]["generation"], key=key, effect_id=effect_id, effect_readback=applied(key, effect_id=effect_id), command_envelope=env),
        failpoint=trigger,
    )


def test_contract_freezes_v2_schema_graph_and_recovery_terminals() -> None:
    contract = load_contract()
    validate_contract(contract)
    assert contract["schema_version"] == 2
    assert contract["schema_id"] == "objective-execution-contract"
    assert contract["journal"]["event_chain_authority"] is True
    assert contract["journal"]["exclusive_publish"] == {
        "darwin": "renameatx_np_RENAME_EXCL",
        "linux": "renameat2_RENAME_NOREPLACE",
        "unsupported_platform": "fail_closed",
        "overwrite_fallback_allowed": False,
    }
    assert contract["commands"]["read_execution_state"]["materialization_allowed"] is False
    assert contract["transition_graph"]["terminal_reopen_policy"] == "explicit_edges_only"
    assert contract["transition_graph"]["subjects"]["objective"]["terminal_states"] == ["accepted", "aborted"]
    for mutation in (
        lambda value: value["schemas"]["command_envelope"]["required_fields"].pop(),
        lambda value: value["transition_graph"]["subjects"]["objective"]["transitions"].append({"action": "approve_objective", "from_state": "draft", "to_state": "accepted"}),
        lambda value: value["errors"].pop("OEX.JOURNAL_RECOVERY_REQUIRED"),
        lambda value: value["errors"].pop("OEX.TRANSITION_INVALID"),
        lambda value: value["errors"].pop("OEX.PENDING_COMMAND_CONFLICT"),
        lambda value: value["journal"]["exclusive_publish"].pop("linux"),
        lambda value: value["journal"]["exclusive_publish"].update(
            {"linux": "renameat2_or_unsafe_fallback"}
        ),
    ):
        broken = deepcopy(contract)
        mutation(broken)
        with pytest.raises(ContractError):
            validate_contract(broken)


def test_retired_v1_contract_envelope_and_event_hard_fail_without_dual_read(tmp_path: Path) -> None:
    for field, retired_value in (("schema_id", "objective-execution-contract-v1"), ("schema_version", 1)):
        retired_contract = deepcopy(load_contract())
        retired_contract[field] = retired_value
        with pytest.raises(ContractError, match="identity/version"):
            validate_contract(retired_contract)

    journal = tmp_path / "retired-event"
    record_and_transition(journal)
    event_path = journal / "objective/objective-1/events/00000000000000000001.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["schema_version"] = 1
    event_path.write_text(json.dumps(event), encoding="utf-8")
    failed = readback(journal, "objective", "objective-1")
    assert failed.status == "failed" and failed.terminal == "OEX.JOURNAL_TAMPERED"

    retired_envelope = envelope(
        action="create_objective", target_state="draft", effect_id="effect-v1", key="retired-v1"
    )
    retired_envelope["schema_version"] = 1
    with pytest.raises(ContractError, match="retired v1 is not accepted"):
        append_event(journal / "envelope", command(
            event_kind="human_decision_recorded", action="create_objective",
            from_state=None, to_state=None, expected_head="absent",
            expected_generation=0, key="retired-v1", effect_id="effect-v1",
            command_envelope=retired_envelope,
        ))


def test_deterministic_replay_and_present_absent_readback(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    assert readback(journal, "objective", "objective-1").status == "absent"
    transitioned = record_and_transition(journal)
    events = read_events(journal, "objective", "objective-1")
    assert reduce_events("objective", events) == reduce_events("objective", events)
    assert transitioned["readback"]["reduced_state"] == "draft"
    present = readback(journal, "objective", "objective-1")
    assert present.status == "present" and present.head == events[-1]["event_digest"] and present.generation == 2


@pytest.mark.parametrize("failpoint", ["after_event_fsync", "after_snapshot_materialized"])
def test_restart_recovers_legal_partial_materialization_without_readback_write(tmp_path: Path, failpoint: str) -> None:
    journal = tmp_path / failpoint
    with pytest.raises(SimulatedCrash, match=failpoint):
        record_and_transition(journal, failpoint=failpoint)
    directory = journal / "objective/objective-1"
    before = {name: (directory / name).read_bytes() if (directory / name).exists() else None for name in ("snapshot.json", "head.json")}
    failed = readback(journal, "objective", "objective-1")
    after = {name: (directory / name).read_bytes() if (directory / name).exists() else None for name in ("snapshot.json", "head.json")}
    assert failed.status == "failed" and failed.terminal == "OEX.JOURNAL_RECOVERY_REQUIRED"
    assert after == before
    recovered = recover_materialization(journal, "objective", "objective-1")
    assert recovered["result"] == "recovered"
    assert recovered["readback"]["reduced_state"] == "draft"
    assert len(read_events(journal, "objective", "objective-1")) == 2


def test_restart_after_head_materialized_is_already_committed(tmp_path: Path) -> None:
    journal = tmp_path / "after-head"
    with pytest.raises(SimulatedCrash, match="after_head_materialized"):
        record_and_transition(journal, failpoint="after_head_materialized")
    present = readback(journal, "objective", "objective-1")
    assert present.status == "present" and present.reduced_state == "draft" and present.generation == 2
    recovered = recover_materialization(journal, "objective", "objective-1")
    assert recovered["result"] == "duplicate"


def test_append_recovers_partial_materialization_before_cas(tmp_path: Path) -> None:
    journal = tmp_path / "append-recovery"
    with pytest.raises(SimulatedCrash):
        record_and_transition(journal, failpoint="after_event_fsync")
    failed = readback(journal, "objective", "objective-1")
    assert failed.status == "failed" and failed.terminal == "OEX.JOURNAL_RECOVERY_REQUIRED"
    env = envelope(action="request_clarification", target_state="clarify", effect_id="effect-clarify", key="clarify", source_state="draft")
    persisted = json.loads((journal / "objective/objective-1/events/00000000000000000002.json").read_text(encoding="utf-8"))
    appended = append_event(journal, command(event_kind="human_decision_recorded", action="request_clarification", from_state="draft", to_state="draft", expected_head=persisted["event_digest"], expected_generation=2, key="clarify", effect_id="effect-clarify", command_envelope=env))
    assert appended["result"] == "committed" and appended["readback"]["generation"] == 3


def test_bad_event_gap_digest_and_identity_still_fail_closed(tmp_path: Path) -> None:
    for case in ("digest", "identity", "gap"):
        journal = tmp_path / case
        record_and_transition(journal)
        events = journal / "objective/objective-1/events"
        if case == "gap":
            (events / "00000000000000000002.json").rename(events / "00000000000000000003.json")
        else:
            path = events / "00000000000000000001.json"
            event = json.loads(path.read_text(encoding="utf-8"))
            event["event_digest" if case == "digest" else "subject_id"] = "sha256:" + "0" * 64 if case == "digest" else "other"
            path.write_text(json.dumps(event), encoding="utf-8")
        failed = readback(journal, "objective", "objective-1")
        assert failed.status == "failed" and failed.terminal == "OEX.JOURNAL_TAMPERED"
        with pytest.raises(ObjectiveExecutionError, match="OEX.JOURNAL_TAMPERED"):
            recover_materialization(journal, "objective", "objective-1")


def test_event_storage_io_failure_is_not_misclassified_as_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = tmp_path / "event-io"
    record_and_transition(journal)
    from lib.objective_execution import journal as journal_module
    actual_read_json = journal_module._read_json_at

    def fail_event_read(parent_fd: int, name: str, label: str, owner_uid: int, *, derived: bool = False) -> dict[str, Any]:
        if label == "transition event":
            raise journal_module.JournalError("event storage unavailable")
        return actual_read_json(parent_fd, name, label, owner_uid, derived=derived)

    monkeypatch.setattr(journal_module, "_read_json_at", fail_event_read)
    failed = readback(journal, "objective", "objective-1")
    assert failed.status == "failed" and failed.terminal == "OEX.JOURNAL_FAILED"


def test_illegal_closed_set_jump_and_terminal_reopen_require_explicit_edges(tmp_path: Path) -> None:
    journal = tmp_path / "illegal"
    env = envelope(action="accept_objective", target_state="accepted", effect_id="effect-illegal", key="illegal")
    with pytest.raises(ObjectiveExecutionError, match="OEX.TRANSITION_INVALID"):
        append_event(journal, command(event_kind="human_decision_recorded", action="accept_objective", from_state=None, to_state=None, expected_head="absent", expected_generation=0, key="illegal", effect_id="effect-illegal", command_envelope=env))
    # The decision record itself is non-mutating but must bind an action that is legal from its source.
    assert readback(journal, "objective", "objective-1").status == "absent"


def test_stale_writer_and_concurrent_cas_have_exactly_one_winner(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    first_env = envelope(action="create_objective", target_state="draft", effect_id="effect-winner", key="winner")
    first = command(event_kind="human_decision_recorded", action="create_objective", from_state=None, to_state=None, expected_head="absent", expected_generation=0, key="winner", effect_id="effect-winner", command_envelope=first_env)
    second_env = envelope(action="create_objective", target_state="draft", effect_id="effect-loser", key="loser")
    second = command(event_kind="human_decision_recorded", action="create_objective", from_state=None, to_state=None, expected_head="absent", expected_generation=0, key="loser", effect_id="effect-loser", command_envelope=second_env)
    def attempt(payload: dict[str, object]) -> str:
        try:
            return str(append_event(journal, payload)["result"])
        except (CASConflict, WriterLeaseConflict):
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, (first, second))) == ["committed", "conflict"]
    assert len(read_events(journal, "objective", "objective-1")) == 1
