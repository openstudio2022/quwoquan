from __future__ import annotations

from support.source_plan_guidance_fixtures import *  # noqa: F401,F403


def test_download_fetch_result_writes_entity_screen_gates_incrementally():
    from download.handler import _write_fetch_result_screen_outputs
    from download.handler_images import _source_screen_report_ref
    from _common.stage_reports import read_stage_envelope

    task = "旅行/地域/测试省/景区/fetch增量门"
    batch = "fetch_incremental_gate"
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
        task_id=task,
        batch_id=batch,
        entity_id=entity,
        entity_type="地点/景区",
        selected_lanes=set(),
        text_lane_selected=True,
        fetched_sources=[fetched_source],
        quality_rows=[quality_row],
    )

    screen_ref = _source_screen_report_ref(entity, source_id)
    screen_gate = read_stage_envelope(task, batch, "download", "source_screen_gate", screen_ref)
    bundle_gate = read_stage_envelope(task, batch, "download", "entity_source_bundle_gate", entity)
    assert screen_gate is not None
    assert screen_gate["payload"]["passed"] is True
    assert bundle_gate is not None
    assert bundle_gate["payload"]["passed"] is True
    assert bundle_gate["payload"]["evidenceSummary"]["retainedCount"] == 1
