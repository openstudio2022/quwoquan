"""Current controller-fence validation for an active campaign workload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.canonical.campaign_submission_reader import campaign_root
from content.release.canonical.campaign_release_contract import (
    CampaignReleaseRoots,
    read_regular,
    typed_error,
)
from content.release.canonical.campaign_release_scope import active_campaign_scope


def validate_runtime(
    root_id: str,
    plan: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    runtime_root = campaign_root(root_id, root=roots.campaigns_root) / "runtime"
    snapshot_path = runtime_root / "snapshot.json"
    snapshot = read_regular(snapshot_path, label="campaign runtime snapshot")
    run_id = str(snapshot.get("runId") or "")
    try:
        generation = int(snapshot.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise typed_error(
            "RUNTIME_NOT_FINAL",
            "campaign runtime generation is invalid",
            evidence=snapshot_path,
        ) from exc
    token = str(snapshot.get("fencingToken") or "")
    if (
        snapshot.get("rootExecutionId") != root_id
        or not run_id
        or generation < 1
        or not token.startswith("sha256:")
        or snapshot.get("status") not in {"succeeded", "succeeded_partial"}
        or snapshot.get("phase") != "completed"
        or snapshot.get("planDigest") != plan["planDigest"]
        or snapshot.get("failure") not in {None, ""}
    ):
        raise typed_error(
            "RUNTIME_NOT_FINAL",
            "campaign runtime is not one current fenced completion",
            evidence=snapshot_path,
        )
    try:
        active, _workloads, execution_ids = active_campaign_scope(
            plan,
            root_execution_id=root_id,
        )
    except (TypeError, ValueError) as exc:
        raise typed_error("PLAN_LANES_INVALID", str(exc)) from exc
    lanes_root = runtime_root / "lanes"
    observed_carriers = {
        path.stem for path in lanes_root.glob("*.json")
    } if lanes_root.is_dir() else set()
    if observed_carriers != set(active):
        raise typed_error(
            "FENCE_DRIFT",
            "runtime checkpoints differ from active carriers",
            evidence=lanes_root,
        )
    checkpoints: dict[str, dict[str, Any]] = {}
    for carrier in active:
        path = runtime_root / "lanes" / f"{carrier}.json"
        row = read_regular(path, label=f"{carrier} runtime checkpoint")
        expected = {
            "rootExecutionId": root_id,
            "runId": run_id,
            "generation": generation,
            "fencingToken": token,
            "carrier": carrier,
            "executionId": execution_ids[carrier],
            "phase": "run",
            "status": "succeeded",
            "returnCode": 0,
            "executionRoot": str((roots.tasks_root / execution_ids[carrier]).resolve()),
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise typed_error(
                "FENCE_DRIFT",
                f"{carrier} checkpoint differs from current fenced run",
                evidence=path,
            )
        checkpoints[carrier] = row
    return snapshot, checkpoints


__all__ = ["validate_runtime"]
