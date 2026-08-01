# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Managed publish reconcile must not loop forever when promote keeps failing."""
from __future__ import annotations

from content.execution.agent import agent_managed as subject
from content.execution.context import ExecutionContext
from core.control_types import ExecutionStateStatus, RuntimeEnvironment
from support.execution_manifest_fixture import ExecutionFixtureBuilder


EXECUTION_ID = "20260731--travel-image-reconcile-bound--test-region-a--pilot-913"


def test_managed_controller_stops_after_second_reconcile_failure(monkeypatch) -> None:
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=({"name": "实体甲", "entityType": "地点/景区"},),
        approved_quota=1,
    )
    fixture.build()
    from content.execution.support import load_execution_state, save_execution_state

    state = load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    state.completed = ["publish"]
    state.failed_objects = ["promote failed"]
    save_execution_state(state)

    calls = {"controller": 0}

    def fake_controller(_ctx):
        calls["controller"] += 1
        return 0

    def fake_reconcile(_ctx):
        return False

    import content.execution.controller.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "run_controller", fake_controller)
    monkeypatch.setattr(subject, "_reconcile_completed_publish_state", fake_reconcile)

    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    code = subject.run_managed_controller(ctx)
    assert code == 1
    assert calls["controller"] == 2
    from content.execution.support import load_execution_state

    state = load_execution_state(EXECUTION_ID)
    assert state.status is ExecutionStateStatus.MANUAL_REQUIRED
    assert "reconcile failed" in str(state.next_action or "")
