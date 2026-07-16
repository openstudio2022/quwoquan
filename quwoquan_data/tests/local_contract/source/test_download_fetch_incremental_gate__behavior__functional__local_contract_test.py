from __future__ import annotations

from support.source_plan_guidance_fixtures import *  # noqa: F401,F403


def test_download_fetch_result_writes_entity_screen_gates_incrementally():
    from content.source.handler import _write_fetch_result_screen_outputs
    from content.source.handler_images import _source_screen_report_ref
    from content.execution.stage_reports import read_stage_envelope

    execution_id = "20260712--travel-homepage-fetch-gate--cn-test--canary-001"
    entity = "测试景区"
    source_id = "su_fetch_incremental"
    fetched_source = {
        "entityId": entity,
        "sourceId": source_id,
        "quality": "B-fact",
        "score": 82,
        "url": "https://example.test/source",
    }
    quality_row = {
        "entityId": entity,
        "sourceId": source_id,
        "quality": "B-fact",
        "score": 82,
    }

    _write_fetch_result_screen_outputs(
        execution_id=execution_id,
        entity_id=entity,
        entity_type="地点/景区",
        selected_lanes=set(),
        text_lane_selected=True,
        fetched_sources=[fetched_source],
        quality_rows=[quality_row],
    )

    screen_ref = _source_screen_report_ref(entity, source_id)
    screen_gate = read_stage_envelope(execution_id, "source", "source_screen_gate", screen_ref)
    bundle_gate = read_stage_envelope(execution_id, "source", "entity_source_bundle_gate", entity)
    assert screen_gate is not None
    assert screen_gate["payload"]["passed"] is True
    assert bundle_gate is not None
    assert bundle_gate["payload"]["passed"] is True
    assert bundle_gate["payload"]["evidenceSummary"]["retainedCount"] == 1
