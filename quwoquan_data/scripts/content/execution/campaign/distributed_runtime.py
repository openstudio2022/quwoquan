"""Close the frozen campaign fence after all distributed lanes finish."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.runtime import (
    CampaignRunSession,
    read_lane_checkpoint,
    read_runtime_snapshot,
)
from content.execution.campaign.workspace import CampaignRuntimePaths


def _distributed_identity(plan: Mapping[str, Any]) -> tuple[str, int, str]:
    distributed = plan.get("distributedRun")
    if not isinstance(distributed, Mapping):
        raise ValueError("distributed campaign runtime identity is missing")
    run_id = str(distributed.get("campaignRunId") or "")
    generation = distributed.get("campaignGeneration")
    token = str(distributed.get("campaignFencingToken") or "")
    if (
        not run_id
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
        or not token.startswith("sha256:")
    ):
        raise ValueError("distributed campaign runtime identity is invalid")
    return run_id, generation, token


def _execution_root(runtime: CampaignRuntimePaths, value: object) -> Path:
    ref = Path(str(value or ""))
    if not ref.parts or ref.is_absolute() or ".." in ref.parts:
        raise ValueError("distributed campaign executionRootRef is invalid")
    root = (runtime.output_root / ref).resolve()
    tasks_root = (runtime.output_root / "data/tasks").resolve()
    if root.parent != tasks_root or not root.is_dir():
        raise ValueError("distributed campaign execution root is unavailable")
    return root


def _validate_terminal_checkpoint(
    row: Mapping[str, Any] | None,
    *,
    root_execution_id: str,
    run_id: str,
    generation: int,
    token: str,
    carrier: str,
    execution_id: str,
    execution_root: Path,
) -> bool:
    if row is None:
        return False
    expected = {
        "rootExecutionId": root_execution_id,
        "runId": run_id,
        "generation": generation,
        "fencingToken": token,
        "carrier": carrier,
        "executionId": execution_id,
        "phase": "run",
        "status": "succeeded",
        "returnCode": 0,
        "executionRoot": str(execution_root),
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{carrier} distributed runtime checkpoint drift")
    return True


def finalize_distributed_runtime(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan: Mapping[str, Any],
    lanes: Mapping[str, Mapping[str, Any]],
    status: str,
) -> None:
    """Project durable lane receipts into the original frozen runtime fence."""

    if status not in {"succeeded", "succeeded_partial"}:
        raise ValueError("distributed campaign runtime cannot close as unsuccessful")
    run_id, generation, token = _distributed_identity(plan)
    snapshot = read_runtime_snapshot(runtime, root_execution_id)
    if not isinstance(snapshot, Mapping):
        raise ValueError("distributed campaign runtime snapshot is missing")
    identity = {
        "rootExecutionId": root_execution_id,
        "runId": run_id,
        "generation": generation,
        "fencingToken": token,
        "planDigest": plan.get("planDigest"),
    }
    if any(snapshot.get(key) != value for key, value in identity.items()):
        raise ValueError("distributed campaign runtime fence drift")
    terminal = snapshot.get("status") in {"succeeded", "succeeded_partial"}
    if terminal:
        if snapshot.get("status") != status or snapshot.get("phase") != "completed":
            raise ValueError("distributed campaign terminal runtime drift")
    elif (
        snapshot.get("status") != "frozen"
        or snapshot.get("phase") != "capsule"
        or snapshot.get("failure") not in {None, ""}
        or not snapshot.get("finishedAt")
    ):
        raise ValueError("distributed campaign runtime is not a frozen fence")

    session = CampaignRunSession(
        runtime=runtime,
        root_execution_id=root_execution_id,
        run_id=run_id,
        generation=generation,
        fencing_token=token,
        lease_seconds=int(snapshot.get("leaseSeconds") or 0),
        process_termination_timeout_seconds=1.0,
        started_at=str(snapshot.get("startedAt") or ""),
        _mutex=threading.RLock(),
        _stop=threading.Event(),
        _finished=terminal,
    )
    snapshot_lanes = snapshot.get("lanes")
    for carrier in CAMPAIGN_CARRIERS:
        lane = lanes.get(carrier)
        if not isinstance(lane, Mapping):
            raise ValueError(f"{carrier} distributed finalized lane is missing")
        execution_id = str((plan.get("executionIds") or {}).get(carrier) or "")
        execution_root = _execution_root(runtime, lane.get("executionRootRef"))
        if (
            lane.get("executionId") != execution_id
            or lane.get("status") not in {"finalized", "partial"}
            or lane.get("phase") != "publish"
            or lane.get("reviewReturnCode") != 0
            or lane.get("publishReturnCode") != 0
            or lane.get("cleanupStatus") != "cleaned"
            or not str(lane.get("sourceCapsuleRef") or "")
        ):
            raise ValueError(f"{carrier} distributed lane is not finalized")
        checkpoint = read_lane_checkpoint(runtime, root_execution_id, carrier)
        checkpoint_ready = _validate_terminal_checkpoint(
            checkpoint,
            root_execution_id=root_execution_id,
            run_id=run_id,
            generation=generation,
            token=token,
            carrier=carrier,
            execution_id=execution_id,
            execution_root=execution_root,
        )
        snapshot_lane = (
            snapshot_lanes.get(carrier)
            if isinstance(snapshot_lanes, Mapping)
            else None
        )
        if checkpoint_ready and isinstance(snapshot_lane, Mapping):
            if (
                snapshot_lane.get("executionId") != execution_id
                or snapshot_lane.get("phase") != "run"
                or snapshot_lane.get("status") != "succeeded"
                or snapshot_lane.get("returnCode") != 0
            ):
                raise ValueError(f"{carrier} distributed snapshot lane drift")
            continue
        if terminal:
            raise ValueError(f"{carrier} terminal distributed checkpoint is missing")
        session.lane_checkpoint(
            carrier=carrier,
            execution_id=execution_id,
            phase="run",
            status="succeeded",
            capsule_ref=str(lane["sourceCapsuleRef"]),
            execution_root=execution_root,
            return_code=0,
            error=None,
        )
    if not terminal:
        session.finish(status=status, phase="completed", failure=None)


__all__ = ["finalize_distributed_runtime"]
