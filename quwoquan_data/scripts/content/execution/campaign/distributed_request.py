"""CLI request dispatch for distributed campaign lifecycle stages."""
from __future__ import annotations

import subprocess
from typing import Any


def handle_distributed_campaign_stage(args: Any, identity: Any) -> bool:
    stage = str(getattr(args, "stage", "run") or "run")
    if stage not in {
        "campaign-freeze",
        "campaign-lane-run",
        "campaign-finalize",
    }:
        return False
    root_execution_id = str(
        getattr(args, "campaign_root_execution_id", "")
        or (identity.execution_id if stage != "campaign-lane-run" else "")
    ).strip()
    if not root_execution_id:
        raise SystemExit(
            "[task execute] GATE_BLOCK campaign-lane-run requires "
            "--campaign-root-execution-id"
        )
    try:
        if stage == "campaign-lane-run":
            from content.execution.campaign.distributed import run_campaign_lane

            result_path = run_campaign_lane(
                root_execution_id,
                identity.content_type.value,
                recover_stage=getattr(args, "recover_stage", None),
                recovery_reason=getattr(args, "recovery_reason", None),
            )
        else:
            if root_execution_id != identity.execution_id:
                raise ValueError(
                    f"{stage} requires --execution-id to equal "
                    "--campaign-root-execution-id"
                )
            from content.execution.campaign.distributed import (
                finalize_campaign,
                freeze_campaign,
            )

            result_path = (
                freeze_campaign(
                    root_execution_id,
                    submission_timeout_seconds=getattr(
                        args,
                        "submission_timeout_seconds",
                        None,
                    ),
                )
                if stage == "campaign-freeze"
                else finalize_campaign(root_execution_id)
            )
    except (
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {stage}: {exc}") from exc
    print(
        f"[task execute] {stage.upper()} DONE "
        f"carrier={identity.content_type.value} report={result_path}"
    )
    return True


__all__ = ["handle_distributed_campaign_stage"]
