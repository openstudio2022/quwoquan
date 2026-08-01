from __future__ import annotations

from types import SimpleNamespace

from content.execution.agent import auto_research
from content.execution.context import ExecutionContext
from content.execution.recovery import download_unresolved
from content.source.research import auto_plan_public
from core.io import write_json
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_auto_research_dispatches_mixed_entity_types_in_one_worker_pool(monkeypatch, tmp_path):
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-001"
    entity_ids = ["测试景区", "测试博物馆"]
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=(
                {"name": entity_ids[0], "entityType": "地点/景区"},
                {"name": entity_ids[1], "entityType": "地点/博物馆"},
            ),
        ).spec(),
        managed=True,
    )
    calls: list[tuple[list[str], str, int]] = []

    monkeypatch.setattr(
        auto_research,
        "active_runtime_policy",
        lambda: SimpleNamespace(research_workers=4, research_max_waves_per_run=0),
    )
    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    monkeypatch.setattr(auto_research, "_auto_research_wave_size", lambda *_args, **_kwargs: 100)
    monkeypatch.setattr(download_unresolved, "_auto_research_plan_path", lambda _ctx: tmp_path / "plan.json")
    monkeypatch.setattr(auto_research, "_write_auto_research_report", lambda _ctx, report, **_kwargs: dict(report))

    def fake_write(execution_id, target_ids, *, entity_type, max_workers, **_kwargs):
        assert execution_id == ctx.execution_id
        calls.append((list(target_ids), entity_type, max_workers))
        return {"updated": [], "issues": [], "sourceUnavailable": []}

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    auto_research._run_download_auto_research(
        ctx,
        entity_ids,
        entity_type="地点/景区",
    )

    assert calls == [(entity_ids, "地点/景区", 4)]


def test_auto_research_resume_preserves_unstarted_waves(monkeypatch, tmp_path):
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-002"
    entity_ids = ["已完成甲", "已完成乙", "中断已完成丙", "当前未完成丁", "尚未开始戊"]
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=tuple(
                {"name": entity_id, "entityType": "地点/景区"}
                for entity_id in entity_ids
            ),
        ).spec(),
        managed=True,
    )
    plan_path = tmp_path / "plan.json"
    write_json(
        plan_path,
        {
            "schema": "quwoquan.content.source.auto_research_plan",
            "executionId": execution_id,
            "waveCount": 1,
            "waves": [{"scope": "primary", "entityIds": entity_ids[:2]}],
            "partialRun": True,
            # The source writer persists only the unfinished portion of the
            # interrupted wave, not the later waves that never began.
            "remainingEntityIds": [entity_ids[3]],
        },
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        auto_research,
        "active_runtime_policy",
        lambda: SimpleNamespace(research_workers=4, research_max_waves_per_run=0),
    )
    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    monkeypatch.setattr(auto_research, "_auto_research_wave_size", lambda *_args, **_kwargs: 100)
    monkeypatch.setattr(download_unresolved, "_auto_research_plan_path", lambda _ctx: plan_path)
    monkeypatch.setattr(auto_research, "_write_auto_research_report", lambda _ctx, report, **_kwargs: dict(report))

    def fake_write(_execution_id, target_ids, **_kwargs):
        calls.append(list(target_ids))
        return {"updated": [], "issues": [], "sourceUnavailable": []}

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    auto_research._run_download_auto_research(
        ctx,
        entity_ids,
        entity_type="地点/景区",
    )

    assert calls == [[entity_ids[3], entity_ids[4]]]
