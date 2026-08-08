"""Bounded campaign review checkpoint continuation."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from content.execution.context import load_execution_state
from content.execution.identity import parse_execution_id
from core.control_types import ExecutionStage, ExecutionStateStatus
from core.runtime_policy import active_runtime_policy


Execute = Callable[..., None]


def execute_until_checkpoint(
    recipe: dict[str, Any],
    execution_id: str,
    *,
    until: str,
    execute: Execute,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    """Keep one campaign lane alive across bounded managed-agent yields."""
    policy = active_runtime_policy()
    frozen_scale = parse_execution_id(execution_id).intent.upper()
    deadline = time.monotonic() + float(
        policy.campaign_lane_timeout_seconds_for_scale(frozen_scale)
    )
    poll_seconds = min(
        5.0,
        max(0.2, float(policy.agent_future_poll_timeout_seconds)),
    )
    while True:
        execute(
            recipe,
            execution_id,
            until=until,
            recover_stage=recover_stage,
            recovery_reason=recovery_reason,
        )
        state = load_execution_state(execution_id)
        if until in set(state.completed or []):
            return
        if (
            state.status is ExecutionStateStatus.MANUAL_REQUIRED
            or not state.waiting_checkpoint
        ):
            detail = "; ".join(str(item) for item in state.failed_objects[:3])
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                f"did not reach {until}; status={state.status.value}; "
                f"waitingCheckpoint={state.waiting_checkpoint or '-'}"
                + (f"; {detail}" if detail else "")
            )
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                f"timed out waiting for {until} from "
                f"{state.waiting_checkpoint}"
            )
        time.sleep(poll_seconds)


def execute_recipe_stage(
    recipe: dict[str, Any],
    execution_id: str,
    *,
    stage: str,
    execute: Execute,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    if stage == "review-only":
        execute_until_checkpoint(
            recipe,
            execution_id,
            until=ExecutionStage.POST_REVIEW.value,
            execute=execute,
            recover_stage=recover_stage,
            recovery_reason=recovery_reason,
        )
        return
    execute(
        recipe,
        execution_id,
        recover_stage=recover_stage,
        recovery_reason=recovery_reason,
    )


__all__ = ["execute_recipe_stage", "execute_until_checkpoint"]
