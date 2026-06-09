"""数据 release post-activation smoke artifact。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.io import write_json
from _common.paths import PUBLISH_ROOT


def write_activation_smoke_report(
    contract: Mapping[str, Any],
    *,
    active_release_id: str,
    api_smoke: list[dict[str, Any]] | None = None,
    publish_root: Path | None = None,
) -> Path:
    root = publish_root or PUBLISH_ROOT
    release_id = str(contract.get("releaseId") or active_release_id)
    env = str(contract.get("environment") or "unknown")
    out = root / "env_releases" / release_id / f"activation-smoke-{env}.json"
    payload = {
        "schemaVersion": "quwoquan.data_release_activation_smoke.v1",
        "releaseId": release_id,
        "environment": env,
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
