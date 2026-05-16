"""Exit gate for explore command."""
from __future__ import annotations

from pathlib import Path

from _common.paths import task_catalog
from _common.io import read_ndjson


def gate_explore(task_id: str, *, min_pois: int = 10) -> list[str]:
    """Check explore exit criteria. Returns list of blocking issues."""
    issues = []
    catalog_path = task_catalog(task_id)

    if not catalog_path.exists():
        issues.append(f"catalog.ndjson not found: {catalog_path}")
        return issues

    rows = read_ndjson(catalog_path)
    if len(rows) < min_pois:
        issues.append(f"POI count {len(rows)} < minimum {min_pois}")

    topic_ids = [r.get("topic_id") for r in rows]
    duplicates = len(topic_ids) - len(set(topic_ids))
    if duplicates > 0:
        issues.append(f"{duplicates} duplicate topic_ids found")

    return issues
