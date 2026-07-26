"""Typed internal entrypoint for the single execution controller."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from content.execution.baseline_packet import load_baseline_packet
from content.execution.coverage import coverage_entity_ids
from content.execution.support import (
    ExecutionContext,
    load_execution_state,
    save_execution_state,
    store,
)
from core.control_types import AgentProvider, ExecutionStage
from core.runtime_policy import active_runtime_policy


@dataclass(frozen=True, slots=True)
class ControllerRequest:
    execution_id: str
    resume: bool = True
    recover_stage: ExecutionStage | None = None
    recovery_reason: str | None = None
    baseline_packet: Path | None = None
    managed: bool = True
    release_only: bool = False
    agent_runner: Callable[[str], Mapping[str, object]] | None = None
    force_clean_workspace_agent_state: bool = False


def run_controlled_execution(request: ControllerRequest) -> None:
    from content.execution.agent.agent_managed import run_managed_controller
    from content.execution.agent.agent_runner import _managed_local_workspace_guard
    from content.execution.controller.control import _execution_signal_guard
    from content.execution.controller.orchestrator import run_controller
    from content.execution.controller.preflight import _managed_preflight, _write_managed_env_ready_report
    from content.execution.recovery.stage_reset import _clear_manual_repair_rewind_if_resuming, reset_stage_retries
    execution_id = request.execution_id
    if not execution_id:
        print("[execution run] ERROR: executionId is required", file=sys.stderr)
        raise SystemExit(2)
    spec = store.load_spec(execution_id)
    entity_ids = tuple(coverage_entity_ids(spec))
    if not entity_ids:
        print(f"[task execute] ERROR: {execution_id} 无 coverageTargets，无实体可编排", file=sys.stderr)
        raise SystemExit(2)
    managed = request.managed
    policy = active_runtime_policy()
    agent_provider = policy.cursor_provider.value
    from content.execution.model_contract import execution_model_pair_for_execution

    author_model = execution_model_pair_for_execution(execution_id).author
    if author_model.selection != policy.cursor_model_selection:
        raise RuntimeError(
            "recipe author model selection must match the active runtime policy"
        )
    managed_model = author_model.model_id
    preflight_args = argparse.Namespace(
        agent_provider=agent_provider,
        until=None,
        runtime=policy.cursor_runtime.value,
        agent_runner=request.agent_runner,
        force_clean_workspace_agent_state=request.force_clean_workspace_agent_state,
        model=managed_model,
        model_parameters=author_model.selection.parameters_document(),
        startup_timeout_seconds=policy.startup_timeout_seconds,
        baseline_packet=str(request.baseline_packet) if request.baseline_packet else None,
    )
    if managed:
        preflight_issues = _managed_preflight(execution_id, spec, preflight_args)
        if preflight_issues:
            print("[task execute] managed preflight FAILED:", file=sys.stderr)
            for issue in preflight_issues:
                print(f"  - {issue}", file=sys.stderr)
            raise SystemExit(2)
    reset_stage = request.recover_stage
    reset_reason = str(request.recovery_reason or "").strip()
    if bool(reset_stage) != bool(reset_reason):
        print(
            "[task execute] ERROR: --reset-stage-retries requires --reset-stage-reason",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if reset_stage:
        recovery = reset_stage_retries(
            execution_id,
            stage=reset_stage.value,
            reason=reset_reason,
            reset_react_rewinds=False,
        )
        print(json.dumps({"stageRecovery": recovery}, ensure_ascii=False))
    elif request.resume:
        _clear_manual_repair_rewind_if_resuming(execution_id)
    try:
        baseline_packet_path, baseline_packet = load_baseline_packet(
            execution_id,
            request.baseline_packet,
        )
    except RuntimeError as exc:
        print(f"[task execute] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    ctx = ExecutionContext(
        execution_id=execution_id, entity_ids=entity_ids,
        spec=spec, baseline_packet=baseline_packet, baseline_packet_path=baseline_packet_path,
        until=None,
        managed=managed,
        runtime=policy.cursor_runtime,
        max_workers=min(policy.author_workers, policy.cursor_bridge_instances),
        model=managed_model,
        model_parameters=author_model.parameters,
        agent_provider=AgentProvider(agent_provider),
        release_only=request.release_only,
        agent_runner=request.agent_runner,
        force_clean_workspace_agent_state=request.force_clean_workspace_agent_state,
    )
    if managed:
        _write_managed_env_ready_report(ctx, preflight_args)
    try:
        with _execution_signal_guard(ctx):
            if managed:
                from core import ops_governance as og
                with og.controller_lease(execution_id) as controller:
                    run_ctx = replace(
                        ctx,
                        controller_run_id=str(controller.get("controllerRunId") or "") or None,
                    )
                    state = load_execution_state(execution_id)
                    state.controller = {
                        "controllerRunId": controller.get("controllerRunId"),
                        "role": controller.get("role"),
                        "pid": controller.get("pid"),
                        "startedAt": controller.get("startedAt"),
                    }
                    state.heartbeat_at = store.now_iso()
                    save_execution_state(state)
                    with _managed_local_workspace_guard(run_ctx):
                        code = run_managed_controller(run_ctx)
            else:
                code = run_controller(ctx)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except RuntimeError as exc:
        print(f"[task execute] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if code != 0:
        raise SystemExit(code)
