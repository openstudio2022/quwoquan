"""Progress artifacts for auto research plan generation."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from core.io import write_json
from core.paths import execution_root

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _write_auto_research_progress(
    execution_id: str,
    *,
    status: str,
    entity_count: int,
    completed_count: int = 0,
    entity_id: str = "",
    workers: int = 1,
    started_monotonic: float | None = None,
    message: str = "",
) -> dict[str, Any]:
    elapsed = max(time.monotonic() - started_monotonic, 0.001) if started_monotonic else 0.0
    progress = {
        "schemaVersion": "quwoquan.content.source.auto_research_progress",
        "updatedAt": _now_iso(),
        "status": status,
        "entityId": entity_id,
        "entityCount": entity_count,
        "completedCount": completed_count,
        "remainingCount": max(entity_count - completed_count, 0),
        "workers": workers,
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(completed_count / elapsed * 60.0, 3) if elapsed > 0 else 0.0,
        "message": message,
    }
    shared = execution_root(execution_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(shared / "auto_research_progress.json", progress)
    return progress
