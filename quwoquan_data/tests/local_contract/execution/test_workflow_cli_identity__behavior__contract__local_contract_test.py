from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.execution.agent.agent_conflicts import _managed_command_execution_id  # noqa: E402
from content.execution.pipeline import cli as workflow_cli  # noqa: E402
from content.execution.pipeline.cli import register_run_parser  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    register_run_parser(parser.add_subparsers(dest="command", required=True))
    return parser


def test_workflow_cli_exposes_only_one_execution_identity():
    parser = _parser()
    args = parser.parse_args(
        ["run", "--execution-id", "20260712--travel-homepage-coverage--cn-zhejiang--m1-004"]
    )

    assert args.execution_id == "20260712--travel-homepage-coverage--cn-zhejiang--m1-004"
    assert not hasattr(args, "batch")


def test_workflow_cli_rejects_retired_batch_identity():
    parser = _parser()

    try:
        parser.parse_args(["run", "--execution-id", "execution-id", "--batch", "same"])
        raise AssertionError("retired --batch identity must be rejected")
    except SystemExit as exc:
        assert exc.code == 2


def test_managed_process_identity_uses_execution_id_only():
    execution_id = "20260712--travel-homepage-coverage--cn-zhejiang--m1-004"

    assert _managed_command_execution_id(
        f"python3 scripts/cli.py task geo-homepages --execution-id {execution_id}"
    ) == execution_id
    assert _managed_command_execution_id(
        f"python3 scripts/cli.py task geo-homepages --task {execution_id} --batch {execution_id}"
    ) == ""


def test_workflow_cli_loads_coverage_and_baseline_through_execution_boundaries(monkeypatch):
    from content.execution.pipeline import pipeline_control, pipeline_run

    execution_id = "20260715--travel-homepage-coverage--cn-zhejiang--canary-001"
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        workflow_cli.store,
        "load_spec",
        lambda _execution_id: {
            "scope": {
                "coverageTargets": [{"name": "普陀山", "entityType": "地点/景区"}],
            }
        },
    )
    monkeypatch.setattr(
        workflow_cli,
        "load_baseline_packet",
        lambda _execution_id, _path: (
            Path("/tmp/baseline.json"),
            {"executionId": execution_id},
        ),
    )

    @contextmanager
    def signal_guard(_ctx):
        yield

    monkeypatch.setattr(pipeline_control, "_workflow_signal_guard", signal_guard)
    monkeypatch.setattr(
        pipeline_run,
        "run_pipeline",
        lambda ctx: observed.setdefault("entityIds", list(ctx.entity_ids)) and 0,
    )

    workflow_cli.handle_run(
        argparse.Namespace(
            execution_id=execution_id,
            managed=False,
            agent_provider=None,
            model=None,
            reset_state=False,
            reset_stage_retries=None,
            reset_stage_reason=None,
            reset_react_rewinds=False,
            resume=True,
            until=None,
            baseline_packet=None,
            runtime="local",
            max_workers=1,
            release_only=False,
            agent_runner=None,
            force_clean_workspace_agent_state=False,
        )
    )

    assert observed["entityIds"] == ["普陀山"]


def test_workflow_guards_are_real_context_managers():
    from content.execution.agent.agent_runner import _managed_local_workspace_guard
    from content.execution.pipeline.pipeline_control import _workflow_signal_guard
    from content.execution.pipeline.preflight import _cursor_bridge_launch_guard
    from content.execution.context import ExecutionContext

    ctx = ExecutionContext(
        execution_id="20260715--travel-homepage-coverage--cn-zhejiang--canary-001",
        entity_ids=[],
        spec={},
        managed=False,
    )
    with _workflow_signal_guard(ctx), _managed_local_workspace_guard(ctx), _cursor_bridge_launch_guard():
        pass


def test_default_workflow_state_uses_the_schema_contract_version():
    from content.execution.context import WORKFLOW_STATE_VERSION, load_workflow_state

    state = load_workflow_state("20260715--travel-homepage-coverage--cn-zhejiang--canary-001")

    assert WORKFLOW_STATE_VERSION == "quwoquan.content.workflow_state"
    assert state["schemaVersion"] == WORKFLOW_STATE_VERSION


def test_unexpected_stage_issue_keeps_a_bounded_diagnostic_without_traceback_dump():
    from content.execution.pipeline.pipeline_run import _unexpected_stage_issue

    try:
        raise TypeError("sourceAvailability must be a mapping")
    except TypeError as exc:
        issue = _unexpected_stage_issue("download_plan", exc)

    attrs = dict(issue.attributes)
    assert issue.code.value == "DATA.INTERNAL.UNEXPECTED"
    assert attrs["errorType"] == "TypeError"
    assert attrs["errorMessage"] == "sourceAvailability must be a mapping"
    assert attrs["errorLocation"].startswith("test_workflow_cli_identity")
    assert "/" not in attrs["errorLocation"]
