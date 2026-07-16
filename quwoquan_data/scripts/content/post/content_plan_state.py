"""Read-only content-plan packet state and policy projections."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.io import read_json
from core.paths import execution_content_plan_packet_path, execution_results_dir


def reject_source_ids(execution_id: str) -> set[str]:
    """Return source identifiers rejected by the canonical source-screen stage."""
    rejected: set[str] = set()
    results_dir = execution_results_dir(execution_id, "source", "source_screen")
    if not results_dir.is_dir():
        return rejected
    for path in results_dir.glob("*.json"):
        try:
            data = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("decision") or "").lower() == "reject":
            source_id = str(data.get("sourceId") or path.stem).strip()
            if source_id:
                rejected.add(source_id)
    return rejected


def load_content_plan_packet(execution_id: str) -> dict[str, Any] | None:
    path = execution_content_plan_packet_path(execution_id)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def packet_items(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (packet.get("items") or []) if isinstance(item, dict)]
