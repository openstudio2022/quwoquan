"""Read the immutable entity IDs recorded by one execution research plan."""
from __future__ import annotations

from typing import Any

from core.io import read_json
from core.paths import execution_root


def execution_planned_entity_ids(execution_id: str) -> list[str]:
    shared = execution_root(execution_id) / "_shared"
    path = shared / "auto_research_plan.json"
    report: dict[str, Any] = read_json(path) if path.is_file() else {}
    availability = report.get("sourceAvailability")
    source_availability = availability if isinstance(availability, dict) else {}
    ids: list[str] = []
    seen: set[str] = set()
    for entity_id in source_availability.get("readyTargets") or []:
        text = str(entity_id or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    for item in source_availability.get("ineligibleTargets") or []:
        if isinstance(item, dict):
            text = str(item.get("entityId") or "").strip()
            if text and text not in seen:
                ids.append(text)
                seen.add(text)
    if ids:
        return ids
    for item in report.get("updated") or []:
        if isinstance(item, dict):
            text = str(item.get("entityId") or "").strip()
            if text and text not in seen:
                ids.append(text)
                seen.add(text)
    return ids


__all__ = ["execution_planned_entity_ids"]
