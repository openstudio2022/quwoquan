"""Persist deterministic content-plan controller outputs."""
from __future__ import annotations

from typing import Any

from content.execution.workspace import execution_content_plan_packet_path
from content.post.content_plan import CONTENT_PLAN_SCHEMA
from core.io import write_json
from core.paths import execution_root


def write_content_plan_diagnostics(
    execution_id: str,
    *,
    source_diagnostics: dict[str, dict[str, Any]],
) -> None:
    write_json(
        execution_root(execution_id)
        / "_shared"
        / "content_plan_source_diagnostics.json",
        {
            "schema": "quwoquan_data.content_plan_source_diagnostics",
            "executionId": execution_id,
            "targets": source_diagnostics,
        },
    )


def write_content_plan_packet(
    execution_id: str,
    *,
    items: list[dict[str, Any]],
    source_site: dict[str, Any] | None,
) -> None:
    packet: dict[str, Any] = {
        "schema": CONTENT_PLAN_SCHEMA,
        "executionId": execution_id,
        "generatedBy": "deterministic_source_ready_planner",
        "items": items,
    }
    if source_site:
        packet["sourceSite"] = source_site
    write_json(execution_content_plan_packet_path(execution_id), packet)


__all__ = ["write_content_plan_diagnostics", "write_content_plan_packet"]
