"""Exit gate for explore command。"""
from __future__ import annotations

from typing import Iterable

from core.paths import resolve_existing_execution_shared_path
from core.io import read_ndjson


def gate_explore(execution_id: str, *, expected_topic_ids: Iterable[str] | None = None) -> list[str]:
    """检查 explore 准出条件；返回阻断问题列表。"""
    issues = []
    catalog_path = resolve_existing_execution_shared_path(execution_id, "catalog.ndjson")

    if not catalog_path.exists():
        issues.append(f"catalog.ndjson not found: {catalog_path}")
        return issues

    rows = read_ndjson(catalog_path)
    if len(rows) < 1:
        issues.append("catalog row count 0 < minimum 1")

    topic_ids = [r.get("topic_id") for r in rows]
    duplicates = len(topic_ids) - len(set(topic_ids))
    if duplicates > 0:
        issues.append(f"{duplicates} duplicate topic_ids found")

    if expected_topic_ids is not None:
        expected = {str(t) for t in expected_topic_ids if str(t)}
        actual = {str(t) for t in topic_ids if str(t)}
        missing = sorted(expected - actual)
        if missing:
            issues.append(f"missing expected topic_ids: {missing}")

    return issues
