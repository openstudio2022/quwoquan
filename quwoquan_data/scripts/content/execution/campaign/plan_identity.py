"""Stable campaign plan paths, timestamps, and payload identity."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.campaign.submission import campaign_root
from content.execution.campaign.workspace import CampaignRuntimePaths


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def campaign_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_root(root_execution_id, root=runtime.campaigns_root)


def plan_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_path(runtime, root_execution_id) / "campaign_plan.json"


def report_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_path(runtime, root_execution_id) / "campaign_report.json"


__all__ = [
    "campaign_path",
    "plan_path",
    "report_path",
    "sha256_payload",
    "utc_now",
]
