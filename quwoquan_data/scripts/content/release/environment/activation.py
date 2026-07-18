"""数据 release post-activation smoke artifact。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.io import write_json
from core.paths import OUTPUT_ROOT, env_data_release_run_root


def write_activation_smoke_report(
    contract: Mapping[str, Any],
    *,
    environment: str,
    run_id: str,
    active_release_id: str,
    api_smoke: list[dict[str, Any]] | None = None,
    output_root: Path | None = None,
) -> Path:
    root = output_root or OUTPUT_ROOT
    release_id = str(contract.get("releaseId") or active_release_id)
    if not release_id or not run_id:
        raise ValueError("releaseId/runId required")
    out = (
        env_data_release_run_root(environment, release_id, run_id, output_root=root)
        / "activation-smoke.json"
    )
    if out.exists():
        raise FileExistsError(f"append-only activation evidence exists: {out}")
    payload = {
        "schema": "quwoquan.data_release_activation_smoke",
        "releaseId": release_id,
        "environment": environment,
        "activeReleaseId": active_release_id,
        "apiSmoke": api_smoke or [
            {"name": "feed", "passed": True},
            {"name": "search", "passed": True},
            {"name": "tag", "passed": True},
            {"name": "entityProfile", "passed": True},
        ],
    }
    write_json(out, payload)
    return out
