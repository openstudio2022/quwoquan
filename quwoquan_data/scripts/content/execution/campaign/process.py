"""Coordinate concurrent execution for a selected campaign phase."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    LaneRunner,
    PhaseResultCallback,
)
from content.execution.campaign.lane_execution import run_lane
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
)
from content.execution.queue.reliabletask.transport import (
    FrozenReliableTaskFleetBinding,
)
from content.execution.runtime_evidence.reliabletask_process import (
    ReliableTaskObserverBinaryBinding,
)

if TYPE_CHECKING:
    from content.execution.campaign.runtime import CampaignRunSession


def run_phase(
    workspaces: dict[str, CampaignLaneWorkspace],
    submissions: dict[str, dict[str, Any]],
    *,
    stage: str,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    timeout_seconds: float,
    worker_count: int,
    lane_runner: LaneRunner | None = None,
    run_session: CampaignRunSession,
    observer_binary_binding: ReliableTaskObserverBinaryBinding | None = None,
    fleet_transport_binding: FrozenReliableTaskFleetBinding | None = None,
    carriers: tuple[str, ...] | None = None,
    on_result: PhaseResultCallback | None = None,
) -> dict[str, tuple[int, str | None]]:
    selected = CAMPAIGN_CARRIERS if carriers is None else carriers
    unknown = [carrier for carrier in selected if carrier not in CAMPAIGN_CARRIERS]
    if unknown:
        raise ValueError(f"campaign phase carriers are invalid: {', '.join(unknown)}")
    results: dict[str, tuple[int, str | None]] = {}
    if not selected:
        return results
    pool = ThreadPoolExecutor(max_workers=max(1, min(worker_count, len(selected))))
    futures = {}
    try:
        futures = {
            pool.submit(
                run_lane,
                workspaces[carrier],
                submissions[carrier],
                stage=stage,
                runtime=runtime,
                root_execution_id=root_execution_id,
                timeout_seconds=timeout_seconds,
                lane_runner=lane_runner,
                run_session=run_session,
                observer_binary_binding=observer_binary_binding,
                fleet_transport_binding=fleet_transport_binding,
            ): carrier
            for carrier in selected
        }
        for future in as_completed(futures):
            carrier = futures[future]
            result = future.result()
            results[carrier] = result
            if on_result is not None:
                on_result(carrier, result)
    except BaseException:
        # A controller interrupt must first stop every owned process group;
        # otherwise ThreadPoolExecutor.__exit__ waits for the full lane timeout.
        run_session.abort_active_lanes()
        for future in futures:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    return results


__all__ = ["run_phase"]
