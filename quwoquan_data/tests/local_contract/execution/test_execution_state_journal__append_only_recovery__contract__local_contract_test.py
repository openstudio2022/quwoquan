from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution import context
from content.execution import execution_state_journal as journal
from core.control_types import ExecutionStateStatus
from core.io import read_json, write_json

EXECUTION_ID = "20260805--travel-article-state-journal--china--pilot-001"


def _bind_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state_path = tmp_path / EXECUTION_ID / "_shared" / "execution_state.json"
    monkeypatch.setattr(context, "_state_path", lambda _execution_id: state_path)
    return state_path


def _event_path(state_path: Path, sequence: int) -> Path:
    return state_path.with_name("execution_state_events") / f"{sequence:020d}.json"


def test_one_thousand_state_updates_keep_snapshot_and_head_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING

    for sequence in range(1_000):
        state.recovery_actions.append(
            {"sequence": sequence, "reason": "bounded-recovery-history"}
        )
        context.save_execution_state(state)

    event_paths = sorted(state_path.with_name("execution_state_events").glob("*.json"))
    event_sizes = [path.stat().st_size for path in event_paths]
    second_delta = read_json(event_paths[1])["stateDelta"]["set"]
    snapshot = read_json(state_path)
    head = read_json(state_path.with_name("execution_state_head.json"))

    assert len(event_paths) == 1_000
    assert len(snapshot["recoveryActions"]) == 64
    assert snapshot["recoveryActions"][-1]["sequence"] == 999
    assert state_path.stat().st_size < 32_000
    assert state_path.with_name("execution_state_head.json").stat().st_size < 1_024
    assert sum(event_sizes[500:]) <= sum(event_sizes[:500]) * 1.25
    assert max(event_sizes[1:]) < 16_000
    assert set(second_delta) <= {"recoveryActions", "updatedAt"}
    assert "executionId" not in second_delta
    assert head["sequence"] == 1_000
    assert journal.verify_execution_state_journal(state_path).sequence == 1_000


def test_stale_transition_is_rejected_under_the_execution_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_state_path(tmp_path, monkeypatch)
    first = context.load_execution_state(EXECUTION_ID)
    stale = context.load_execution_state(EXECUTION_ID)
    first.status = ExecutionStateStatus.RUNNING
    context.save_execution_state(first)

    stale.status = ExecutionStateStatus.INTERRUPTED
    with pytest.raises(journal.StaleExecutionStateError, match="stale writer rejected"):
        context.save_execution_state(stale)

    assert context.load_execution_state(EXECUTION_ID).status is ExecutionStateStatus.RUNNING


def test_replacing_with_canonical_reload_preserves_journal_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    context.save_execution_state(state)

    latest = context.load_execution_state(EXECUTION_ID)
    state.replace_with(latest)
    state.status = ExecutionStateStatus.REPAIRING
    context.save_execution_state(state)

    assert context.load_execution_state(EXECUTION_ID).status is ExecutionStateStatus.REPAIRING
    assert read_json(state_path.with_name("execution_state_head.json"))["sequence"] == 2


def test_replacing_with_a_different_execution_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    replacement = context.load_execution_state(EXECUTION_ID)
    replacement.execution_id = f"{EXECUTION_ID}-different"

    with pytest.raises(ValueError, match="executionId must match"):
        state.replace_with(replacement)

    assert state.execution_id == EXECUTION_ID


def test_succeeded_state_cannot_be_persisted_without_ship_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.SUCCEEDED

    with pytest.raises(ValueError, match="SUCCEEDED_WRITER_INVALID"):
        context.save_execution_state(state)


def test_concurrent_writers_are_serialized_and_exactly_one_cas_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    transitions = [
        context.load_execution_state(EXECUTION_ID),
        context.load_execution_state(EXECUTION_ID),
    ]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def save(transition, status: ExecutionStateStatus) -> None:
        transition.status = status
        barrier.wait()
        try:
            context.save_execution_state(transition)
        except journal.StaleExecutionStateError:
            outcomes.append("stale")
        else:
            outcomes.append("saved")

    threads = [
        threading.Thread(
            target=save,
            args=(transitions[0], ExecutionStateStatus.RUNNING),
        ),
        threading.Thread(
            target=save,
            args=(transitions[1], ExecutionStateStatus.INTERRUPTED),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert outcomes == ["saved", "stale"] or outcomes == ["stale", "saved"]
    assert read_json(state_path.with_name("execution_state_head.json"))["sequence"] == 1
    assert len(list(state_path.with_name("execution_state_events").glob("*.json"))) == 1


def test_legacy_snapshot_is_read_only_until_its_first_journaled_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    legacy = context.load_execution_state(EXECUTION_ID)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(state_path, legacy.freeze().to_dict())

    loaded = context.load_execution_state(EXECUTION_ID)
    assert not state_path.with_name("execution_state_head.json").exists()
    assert not state_path.with_name("execution_state_events").exists()

    loaded.status = ExecutionStateStatus.RUNNING
    context.save_execution_state(loaded)
    assert read_json(state_path.with_name("execution_state_head.json"))["sequence"] == 1
    assert _event_path(state_path, 1).is_file()


@pytest.mark.parametrize("crash_point", ("event", "snapshot", "head"))
def test_torn_save_recovers_deterministically_without_skipping_a_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    state.recovery_actions.append({"reason": crash_point})

    real_atomic_write = journal._atomic_write_json
    real_write_head = journal._write_head

    if crash_point == "event":
        def crash_before_snapshot(path: Path, payload) -> None:
            if path == state_path:
                raise RuntimeError("crash after event")
            real_atomic_write(path, payload)

        monkeypatch.setattr(journal, "_atomic_write_json", crash_before_snapshot)
    elif crash_point == "snapshot":
        def crash_before_head(path: Path, identity) -> None:
            raise RuntimeError("crash after snapshot")

        monkeypatch.setattr(journal, "_write_head", crash_before_head)
    else:
        def crash_after_head(path: Path, identity) -> None:
            real_write_head(path, identity)
            raise RuntimeError("crash after head")

        monkeypatch.setattr(journal, "_write_head", crash_after_head)

    with pytest.raises(RuntimeError, match=f"crash after {crash_point}"):
        context.save_execution_state(state)

    monkeypatch.setattr(journal, "_atomic_write_json", real_atomic_write)
    monkeypatch.setattr(journal, "_write_head", real_write_head)
    recovered = context.load_execution_state(EXECUTION_ID)

    assert recovered.status is ExecutionStateStatus.RUNNING
    assert recovered.recovery_actions == [{"reason": crash_point}]
    identity = journal.verify_execution_state_journal(state_path)
    assert identity.sequence == 1
    assert len(list(state_path.with_name("execution_state_events").glob("*.json"))) == 1


def test_snapshot_and_latest_event_tamper_fail_closed_on_normal_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    context.save_execution_state(state)

    snapshot = read_json(state_path)
    snapshot["owner"] = "tampered-owner"
    write_json(state_path, snapshot)
    with pytest.raises(journal.ExecutionStateJournalError, match="snapshot digest drift"):
        context.load_execution_state(EXECUTION_ID)

    state_path.write_text(json.dumps(state.freeze().to_dict()), encoding="utf-8")
    event = read_json(_event_path(state_path, 1))
    event["stateDelta"]["set"]["owner"] = "tampered-event"
    write_json(_event_path(state_path, 1), event)
    with pytest.raises(journal.ExecutionStateJournalError, match="event payload digest drift"):
        context.load_execution_state(EXECUTION_ID)


def test_full_audit_detects_historical_event_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    for sequence in range(3):
        state.recovery_actions.append({"sequence": sequence})
        context.save_execution_state(state)

    first_event = read_json(_event_path(state_path, 1))
    first_event["stateDelta"]["set"]["owner"] = "historical-tamper"
    _event_path(state_path, 1).write_text(
        json.dumps(first_event, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(journal.ExecutionStateJournalError, match="payload digest drift"):
        journal.verify_execution_state_journal(state_path)


def test_terminal_completion_and_readiness_boundaries_reject_early_event_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = _bind_state_path(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    for sequence in range(3):
        state.recovery_actions.append({"sequence": sequence})
        context.save_execution_state(state)

    first_event_path = _event_path(state_path, 1)
    first_event = read_json(first_event_path)
    first_event["stateDelta"]["set"]["owner"] = "early-event-tamper"
    first_event_path.write_text(
        json.dumps(first_event, ensure_ascii=False),
        encoding="utf-8",
    )
    root = state_path.parent.parent

    from content.execution import execution_supersession, workspace
    from content.execution.controller.execute import reconcile
    from content.execution.controller.completion import execution_completion_issues
    from content.execution.execution_terminal import load_terminal_execution_evidence
    from content.execution.planning.readiness_audit import audit_execution_readiness

    monkeypatch.setattr(workspace, "execution_state_path", lambda _execution_id: state_path)
    monkeypatch.setattr(reconcile, "execution_root", lambda _execution_id: root)

    gate_calls = (
        lambda: load_terminal_execution_evidence(root),
        lambda: reconcile.reconcile_stale_execution(EXECUTION_ID),
        lambda: execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="missing_canonical_input",
            executions_root=tmp_path,
        ),
        lambda: execution_completion_issues(SimpleNamespace(execution_id=EXECUTION_ID), state),
        lambda: audit_execution_readiness(EXECUTION_ID),
    )
    for gate_call in gate_calls:
        with pytest.raises(
            journal.ExecutionStateJournalError,
            match="payload digest drift",
        ):
            gate_call()
    assert not tuple((root / "_shared/reconciliation").glob("*.json"))
