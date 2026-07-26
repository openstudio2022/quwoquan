from __future__ import annotations

from content.execution.context import ExecutionContext
from content.execution.recovery.download_hints import _research_image_repair_hints
from content.source import source_inputs
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_research_image_repair_hints_uses_execution_entity_and_type_once(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []

    def _curated_sources(
        execution_id: str,
        entity_id: str,
        entity_type: str = "",
        *,
        research_lane: str | None = None,
    ) -> list[dict[str, object]]:
        calls.append((execution_id, entity_id, entity_type, research_lane))
        return []

    monkeypatch.setattr(source_inputs, "curated_sources_for_entity", _curated_sources)
    monkeypatch.setattr(source_inputs, "curated_images_for_entity", lambda *_args: [])

    context = ExecutionContext(
        execution_id="20260717--travel-homepage-coverage--test-region-a--scale-099",
        entity_ids=("杭州金沙湖",),
        spec=ExecutionFixtureBuilder(
            "20260717--travel-homepage-coverage--test-region-a--scale-099",
            targets=({"name": "杭州金沙湖", "entityType": "地点/公园"},),
        ).spec(),
    )

    assert _research_image_repair_hints(context, "杭州金沙湖", "地点/公园") == []
    assert calls == [
        (context.execution_id, "杭州金沙湖", "地点/公园", "homepage"),
        (context.execution_id, "杭州金沙湖", "地点/公园", "article"),
    ]
