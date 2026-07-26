"""Reusable vertical content-policy inventory.

This module deliberately does not model rollout counts, named regions, pilots,
or execution maturity.  Those are frozen in a task work package.  A vertical
only declares the carriers it can produce and the per-entity supply contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.paths import _REPO_DATA_ROOT


VERTICALS_ROOT = _REPO_DATA_ROOT / "verticals"
CONTENT_POLICY_NAME = "content_policy.yaml"


def _policy_path(vertical: str) -> Path:
    return VERTICALS_ROOT / vertical / CONTENT_POLICY_NAME


def load_vertical_inventory(vertical: str) -> dict[str, Any]:
    """Read one reusable vertical policy as a carrier inventory."""
    path = _policy_path(vertical)
    if not path.is_file():
        raise FileNotFoundError(f"missing vertical content policy: {path}")
    policy = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(policy, dict):
        raise ValueError(f"{path}: content policy must be an object")
    policy_id = str(policy.get("policyId") or "").strip()
    content_per_entity = policy.get("contentPerEntity")
    if not policy_id:
        raise ValueError(f"{path}: policyId is required")
    if not isinstance(content_per_entity, dict) or not content_per_entity:
        raise ValueError(f"{path}: contentPerEntity must be a non-empty object")
    carriers: list[dict[str, Any]] = []
    for carrier, raw_count in sorted(content_per_entity.items()):
        count = int(raw_count)
        if count < 1:
            raise ValueError(f"{path}: {carrier} supply must be positive")
        carriers.append({"carrier": str(carrier), "perEntity": count})
    return {
        "schema": "quwoquan.vertical_content_inventory",
        "vertical": vertical,
        "policyId": policy_id,
        "carriers": carriers,
    }


def list_verticals() -> list[str]:
    if not VERTICALS_ROOT.is_dir():
        return []
    return sorted(
        path.name
        for path in VERTICALS_ROOT.iterdir()
        if path.is_dir() and _policy_path(path.name).is_file()
    )


def evaluate_vertical_inventory(vertical: str) -> dict[str, Any]:
    inventory = load_vertical_inventory(vertical)
    carriers = inventory["carriers"]
    return {
        "schema": "quwoquan.vertical_content_inventory_report",
        "vertical": vertical,
        "policyId": inventory["policyId"],
        "status": "passed" if carriers else "invalid",
        "totals": {"carriers": len(carriers)},
        "carriers": carriers,
    }


def render_inventory_report(report: dict[str, Any]) -> str:
    lines = [
        f"[vertical inventory] vertical={report['vertical']} status={report['status']}",
        f"  policy={report['policyId']} carriers={report['totals']['carriers']}",
    ]
    for carrier in report["carriers"]:
        lines.append(f"  {carrier['carrier']}: perEntity={carrier['perEntity']}")
    return "\n".join(lines)
