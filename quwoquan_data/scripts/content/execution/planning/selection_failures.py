"""Failure projection for execution selection."""

from __future__ import annotations

from core.control_types import ExecutionStateStatus
from core.data_issue import DataIssue

from content.execution.planning.selection import (
    Any,
    ExecutionStateTransition,
    Mapping,
)


def execution_failure_items(state: ExecutionStateTransition) -> list[dict[str, Any]]:
    status = state.status
    if status in {
        ExecutionStateStatus.SUCCEEDED,
        ExecutionStateStatus.STOPPED_AT_UNTIL,
    }:
        return []
    items: list[dict[str, Any]] = []
    records = state.failed_issue_records
    for raw in records if isinstance(records, list) else []:
        if not isinstance(raw, Mapping):
            continue
        try:
            issue = DataIssue.from_dict(raw)
        except (TypeError, ValueError):
            continue
        entity = issue.ref.rsplit("/", 1)[-1].strip() if issue.ref else "__execution__"
        items.append(
            {
                "entity": entity,
                "lane": "execution" if issue.lane.value == "all" else issue.lane.value,
                "issues": [str(issue)],
            }
        )
    if not items:
        failed_objects = [
            str(item) for item in state.failed_objects or [] if str(item).strip()
        ]
        items.append(
            {
                "entity": "__execution__",
                "lane": "execution",
                "issues": failed_objects or [f"execution status={status.value}"],
            }
        )
    return items
