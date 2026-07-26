from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.execution.agent.agent_conflicts import _managed_command_execution_id  # noqa: E402
from content.execution.controller import entrypoint as controller_entrypoint  # noqa: E402
from content.execution.controller.entrypoint import ControllerRequest  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


def test_controller_request_exposes_only_one_execution_identity():
    request = ControllerRequest(
        execution_id="20260712--travel-homepage-coverage--test-region-a--scale-004"
    )

    assert request.execution_id == "20260712--travel-homepage-coverage--test-region-a--scale-004"
    assert not hasattr(request, "batch")


def test_controller_request_is_immutable():
    request = ControllerRequest(
        execution_id="20260712--travel-homepage-coverage--test-region-a--scale-004"
    )
    try:
        request.execution_id = "changed"
        raise AssertionError("controller request must be frozen")
    except FrozenInstanceError:
        pass


def test_managed_process_identity_uses_execution_id_only():
    execution_id = "20260712--travel-homepage-coverage--test-region-a--scale-004"

    assert _managed_command_execution_id(
        f"python3 scripts/cli.py task execute --execution-id {execution_id}"
    ) == execution_id
    assert _managed_command_execution_id(
        f"python3 scripts/cli.py task execute --task {execution_id} --batch {execution_id}"
    ) == ""


def test_controller_entrypoint_loads_coverage_and_baseline_through_execution_boundaries(monkeypatch):
    from content.execution.controller import control, orchestrator

    execution_id = "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    observed: dict[str, object] = {}
    fixture = ExecutionFixtureBuilder(
        execution_id,
        targets=({"name": "测试实体甲", "entityType": "地点/景区"},),
    )
    fixture.build()

    monkeypatch.setattr(
        controller_entrypoint.store,
        "load_spec",
        lambda _execution_id: fixture.spec_payload(),
    )
    monkeypatch.setattr(
        controller_entrypoint,
        "load_baseline_packet",
        lambda _execution_id, _path: (
            Path("/tmp/baseline.json"),
            {"executionId": execution_id},
        ),
    )

    @contextmanager
    def signal_guard(_ctx):
        yield

    monkeypatch.setattr(control, "_execution_signal_guard", signal_guard)
    monkeypatch.setattr(
        orchestrator,
        "run_controller",
        lambda ctx: observed.setdefault("entityIds", list(ctx.entity_ids)) and 0,
    )

    controller_entrypoint.run_controlled_execution(
        ControllerRequest(
            execution_id=execution_id,
            managed=False,
            resume=True,
            baseline_packet=None,
            release_only=False,
            agent_runner=None,
            force_clean_workspace_agent_state=False,
        )
    )

    assert observed["entityIds"] == ["测试实体甲"]


def test_execution_guards_are_real_context_managers():
    from content.execution.agent.agent_runner import _managed_local_workspace_guard
    from content.execution.controller.control import _execution_signal_guard
    from content.execution.controller.preflight import _cursor_bridge_launch_guard
    from content.execution.context import ExecutionContext

    ctx = ExecutionContext(
        execution_id="20260715--travel-homepage-coverage--test-region-a--pilot-001",
        entity_ids=[],
        spec=ExecutionFixtureBuilder(
            "20260715--travel-homepage-coverage--test-region-a--pilot-001"
        ).spec(),
        managed=False,
    )
    with _execution_signal_guard(ctx), _managed_local_workspace_guard(ctx), _cursor_bridge_launch_guard():
        pass


def test_default_execution_state_uses_the_schema_contract_version():
    from content.execution.context import EXECUTION_STATE_CONTRACT, load_execution_state

    state = load_execution_state("20260715--travel-homepage-coverage--test-region-a--pilot-001")

    assert EXECUTION_STATE_CONTRACT == "quwoquan.content.execution_state"
    assert state.schema == EXECUTION_STATE_CONTRACT


def test_execution_state_snapshot_is_deeply_immutable_and_transition_is_explicit():
    from content.execution.contracts import ExecutionState, FrozenObject
    from core.control_types import ExecutionStateStatus

    snapshot = ExecutionState.from_mapping(
        {
            "schema": "quwoquan.content.execution_state",
            "executionId": "20260715--travel-homepage-coverage--test-region-a--pilot-001",
            "completed": [],
            "status": "queued",
            "updatedAt": "2026-07-15T00:00:00Z",
            "controller": {"runId": "run-1"},
        }
    )

    assert isinstance(snapshot.controller, FrozenObject)
    with pytest.raises(FrozenInstanceError):
        snapshot.status = ExecutionStateStatus.RUNNING

    transition = snapshot.open_transition()
    transition.status = ExecutionStateStatus.RUNNING
    transition.controller["runId"] = "run-2"

    assert snapshot.to_dict()["controller"] == {"runId": "run-1"}
    assert transition.freeze().to_dict()["controller"] == {"runId": "run-2"}


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    (
        ("status", "unknown", ValueError),
        ("retryCounts", {"download_plan": -1}, TypeError),
    ),
)
def test_execution_state_rejects_invalid_control_values(field, value, error_type):
    from content.execution.contracts import ExecutionState

    payload = {
        "schema": "quwoquan.content.execution_state",
        "executionId": "20260715--travel-homepage-coverage--test-region-a--pilot-001",
        "completed": [],
        "status": "queued",
        "updatedAt": "2026-07-15T00:00:00Z",
    }
    payload[field] = value

    with pytest.raises(error_type):
        ExecutionState.from_mapping(payload)


def test_unexpected_stage_issue_keeps_a_bounded_diagnostic_without_traceback_dump():
    from content.execution.controller.orchestrator import _unexpected_stage_issue

    try:
        raise TypeError("sourceAvailability must be a mapping")
    except TypeError as exc:
        issue = _unexpected_stage_issue("download_plan", exc)

    attrs = dict(issue.attributes)
    assert issue.code.value == "DATA.INTERNAL.UNEXPECTED"
    assert attrs["errorType"] == "TypeError"
    assert attrs["errorMessage"] == "sourceAvailability must be a mapping"
    assert attrs["errorLocation"].startswith("test_execution_controller_identity")
    assert "/" not in attrs["errorLocation"]


def test_publish_controller_binds_execution_state_to_the_context_contract():
    from content.execution import context
    from content.execution.controller import publish

    assert publish.load_execution_state is context.load_execution_state
    assert publish.save_execution_state is context.save_execution_state
