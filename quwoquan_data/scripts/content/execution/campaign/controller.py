"""Public owner for the finite four-carrier campaign controller."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def run_campaign(
    root_execution_id: str,
    *,
    wait_for_submissions: bool = True,
    timeout_seconds: float | None = None,
    submission_timeout_seconds: int | None = None,
    lane_timeout_seconds: float | None = None,
    runtime_paths: Any = None,
    lane_runner: Any = None,
) -> Path:
    from content.execution.campaign.orchestrator import (
        run_campaign as run_central_campaign,
    )

    effective_submission_timeout = submission_timeout_seconds or timeout_seconds
    if not wait_for_submissions:
        effective_submission_timeout = 1
    return run_central_campaign(
        root_execution_id,
        submission_timeout_seconds=effective_submission_timeout,
        lane_timeout_seconds=lane_timeout_seconds,
        runtime_paths=runtime_paths,
        lane_runner=lane_runner,
    )


__all__ = ["run_campaign"]
