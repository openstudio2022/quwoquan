from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_recover_stale_auto_research_marks_manual_required(monkeypatch):
    task_id = _make_task()
    batch_id = "stale_auto_research_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["status"] = "running"
    state["heartbeatAt"] = "2000-01-01T00:00:00+00:00"
    state["activeAutoResearch"] = {
        "stage": "download_plan",
        "status": "running",
        "entityId": _EID,
        "entityCount": 1,
        "completedCount": 0,
        "updatedAt": "2000-01-01T00:00:00+00:00",
    }
    run_mod.save_workflow_state(state)
    monkeypatch.setattr("task.run._managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_auto_research(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "manual_required"
    assert recovered["waitingCheckpoint"] == "download_plan"
    assert recovered["failedObjects"] == [
        "download_plan: auto_research interrupted or stale; resume will revalidate checkpoint"
    ]
    assert "activeAutoResearch" not in recovered
    assert recovered["autoResearchRecoveryActions"][-1]["stage"] == "download_plan"

def test_recover_running_auto_research_without_live_process_immediately(monkeypatch):
    task_id = _make_task()
    batch_id = "fresh_auto_research_orphan_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["status"] = "running"
    state["heartbeatAt"] = run_mod.store.now_iso()
    state["activeAutoResearch"] = {
        "stage": "download_plan",
        "status": "running",
        "completedCount": 3,
    }
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_auto_research(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "manual_required"
    assert recovered["waitingCheckpoint"] == "download_plan"
    assert "activeAutoResearch" not in recovered
    assert (
        recovered["autoResearchRecoveryActions"][-1]["reason"]
        == "orphaned running auto research without live workflow process"
    )

def test_download_plan_auto_research_repeats_replacement_waves(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_auto_research_replacement_waves"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )

    def _filled(current_ctx):
        if "替补景区丙" in current_ctx.entity_ids:
            return True, []
        return False, ["image research needs enough rights-cleared source collections for 2 image work(s)"]

    def _report_for(entity_id: str) -> dict:
        if entity_id == "替补景区丙":
            return {
                "sourceAvailability": {
                    "readyTargets": ["替补景区丙"],
                    "ineligibleTargets": [],
                }
            }
        return {
            "sourceAvailability": {
                "readyTargets": [],
                "ineligibleTargets": [
                    {
                        "entityId": entity_id,
                        "issues": [f"{entity_id}: no rights-compatible open-license images discovered"],
                        "blockers": [
                            {
                                "lane": "image",
                                "reason": "no single-author/single-file rights-cleared image collection",
                                "nextAction": "manual_authorized_gallery_or_target_replacement",
                            }
                        ],
                        "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                    }
                ],
            }
        }

    calls: list[list[str]] = []

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del entity_type, force, scope
        calls.append(list(entity_ids))
        return _report_for(entity_ids[0])

    monkeypatch.setattr("task.run._source_plan_filled", _filled)
    monkeypatch.setattr("task.run._run_download_auto_research", _auto)
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr(
        "task.run._content_capacity_gate_for_entity",
        lambda *_args, **_kwargs: (True, [], {"fixture": "passed"}),
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "done"
    assert calls == [[_EID], ["替补景区乙"], ["替补景区丙"]]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID, "替补景区乙"]
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "active"
    ] == ["替补景区丙"]
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "rejected"
    ] == ["替补景区乙"]

def test_auto_research_replacement_continues_when_active_count_shortfall(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
            "maxReplacementWaves": 3,
            "maxReplacementCandidatesPerWave": 8,
            "maxReplacementScreenedPerRun": 8,
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "download_plan_replacement_active_shortfall"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = ["稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["abandonedObjects"] = [
        {
            "entityId": _EID,
            "stage": "download_plan",
            "reason": "source_unavailable_after_auto_research",
            "status": "abandoned",
        }
    ]
    run_mod.save_workflow_state(state)

    calls: list[int] = []

    def _screen(current_ctx, *, entity_type, reason, needed, scope):
        del entity_type, reason, scope
        calls.append(needed)
        run_mod._append_replacement_row(
            current_ctx,
            entity_id="替补景区丙",
            entity_type="地点/景区",
            status="active",
            reason="test replacement passed",
            source_gate_status="passed",
        )
        current_ctx.entity_ids.append("替补景区丙")
        return ["替补景区丙"], [], {"sourceAvailability": {"readyTargets": ["替补景区丙"], "ineligibleTargets": []}}

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    ok, abandoned, missing, _report = run_mod._rerun_auto_research_with_replacements(
        ctx,
        {"sourceAvailability": {"readyTargets": ["稳定景区乙"], "ineligibleTargets": []}},
        entity_type="地点/景区",
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert ok is True
    assert abandoned == []
    assert missing == []
    assert calls == [1]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "active"
    ] == ["替补景区丙"]

def test_auto_research_replacement_wave_stops_without_new_target(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = []
    store.save_spec(spec)
    batch_id = "download_plan_replacement_no_new_target"
    ctx = _ctx(task_id, batch_id)

    primary = {
        "sourceAvailability": {
            "readyTargets": [],
            "ineligibleTargets": [
                {
                    "entityId": _EID,
                    "issues": [f"{_EID}: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
            ],
        }
    }
    calls: list[list[str]] = []

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del current_ctx, entity_type, force, scope
        calls.append(list(entity_ids))
        return primary

    monkeypatch.setattr("task.run._run_download_auto_research", _auto)
    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (False, ["still missing source"]))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {_EID: {"image": ["still missing source"]}})

    ok, abandoned, missing, _report = run_mod._rerun_auto_research_with_replacements(
        ctx,
        primary,
        entity_type="地点/景区",
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert ok is False
    assert abandoned == [_EID]
    assert "still missing source" in missing
    assert "replacement active target shortfall 1<2" in missing
    assert calls == []

def test_auto_research_replacement_wave_preserves_primary_report():
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "auto_research_wave_report"
    ctx = _ctx(task_id, batch_id)
    primary = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "updated": [{"entityId": _EID, "lane": "article"}],
        "issues": [f"{_EID}: article base sources=1 need>=2"],
        "sourceUnavailable": [{"entityId": _EID, "lane": "article"}],
        "sourceAvailability": {
            "readyTargets": [],
            "readyTargetCount": 0,
            "ineligibleTargets": [{"entityId": _EID}],
            "ineligibleTargetCount": 1,
        },
        "throughput": {"maxWorkers": 8, "entityCount": 2, "elapsedSeconds": 20, "entitiesPerMinute": 6},
    }
    replacement = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "updated": [{"entityId": "替补景区乙", "lane": "article"}],
        "issues": [],
        "sourceUnavailable": [],
        "sourceAvailability": {
            "readyTargets": ["替补景区乙"],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        },
        "throughput": {"maxWorkers": 8, "entityCount": 1, "elapsedSeconds": 10, "entitiesPerMinute": 6},
    }

    run_mod._write_auto_research_report(ctx, primary, scope="primary", entity_ids=[_EID, "缺图景区乙"])
    run_mod._write_auto_research_report(
        ctx,
        replacement,
        scope="replacement_wave_1",
        entity_ids=["替补景区乙"],
    )
    availability = {
        "readyTargets": [_EID, "替补景区乙"],
        "readyTargetCount": 2,
        "ineligibleTargets": [],
        "ineligibleTargetCount": 0,
    }
    run_mod._sync_auto_research_availability(ctx, availability)

    report = read_json(batch_root(task_id, batch_id) / "_shared" / "auto_research_plan.json")
    assert report["waveCount"] == 2
    assert [wave["scope"] for wave in report["waves"]] == ["primary", "replacement_wave_1"]
    assert len(report["updated"]) == 2
    assert report["issues"] == [f"{_EID}: article base sources=1 need>=2"]
    assert report["sourceAvailability"]["readyTargetCount"] == 2
    assert report["latestWaveSourceAvailability"]["readyTargetCount"] == 1
    assert report["throughput"]["entityCount"] == 3
    assert report["throughput"]["elapsedSeconds"] == 30

def test_run_download_auto_research_chunks_primary_waves(monkeypatch):
    import download.research_plan as research_mod

    task_id = _make_task(workflow_policy={"autoResearchWaveSize": 1})
    batch_id = "auto_research_primary_chunked_waves"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = ["测试景区甲", "测试景区乙", "测试景区丙"]
    ctx.max_workers = 3
    calls: list[tuple[list[str], int]] = []

    def _fake_write_auto_research_plans(
        task: str,
        batch: str,
        entity_ids: list[str],
        *,
        entity_type: str,
        force: bool = False,
        max_workers: int = 1,
        progress_callback=None,
    ) -> dict:
        del task, batch, entity_type, force, progress_callback
        calls.append((list(entity_ids), max_workers))
        entity_id = entity_ids[0]
        return {
            "schemaVersion": "quwoquan.download.auto_research_plan",
            "taskId": task_id,
            "batchId": batch_id,
            "updated": [{"entityId": entity_id, "lane": "article"}],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [],
            "sourceAvailability": {
                "readyTargets": [entity_id],
                "readyTargetCount": 1,
                "ineligibleTargets": [],
                "ineligibleTargetCount": 0,
            },
            "throughput": {
                "maxWorkers": max_workers,
                "entityCount": 1,
                "elapsedSeconds": 2,
                "entitiesPerMinute": 30,
            },
        }

    monkeypatch.setattr(research_mod, "write_auto_research_plans", _fake_write_auto_research_plans)

    report = run_mod._run_download_auto_research(
        ctx,
        ctx.entity_ids,
        entity_type="景区",
        scope="primary",
    )

    assert calls == [
        (["测试景区甲"], 3),
        (["测试景区乙"], 3),
        (["测试景区丙"], 3),
    ]
    assert report["waveCount"] == 3
    assert [wave["scope"] for wave in report["waves"]] == [
        "primary",
        "primary_wave_2",
        "primary_wave_3",
    ]
    assert report["sourceAvailability"]["readyTargets"] == ["测试景区甲", "测试景区乙", "测试景区丙"]
    assert report["throughput"]["entityCount"] == 3
    persisted = read_json(batch_root(task_id, batch_id) / "_shared" / "auto_research_plan.json")
    assert persisted["waveCount"] == 3
    assert persisted["sourceAvailability"]["readyTargetCount"] == 3

def test_reset_download_plan_retry_clears_interrupted_auto_research_marker():
    task_id = _make_task()
    batch_id = "retry_download_plan_auto_research"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "download_plan"
    state["status"] = "manual_required"
    state["completed"] = ["download_plan", "download_fetch"]
    state["failedObjects"] = ["download_plan: auto_research interrupted"]
    state["activeAutoResearch"] = {
        "stage": "download_plan",
        "status": "interrupted",
        "entityCount": 4,
        "completedCount": 0,
    }
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="download_plan",
        reason="operator revalidated source readiness",
    )

    assert report["status"] == "waiting_agent"
    assert report["completed"] == []
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert "activeAutoResearch" not in recovered
    assert recovered["failedObjects"] == []
    assert recovered["recoveryActions"][-1]["previous"]["activeAutoResearch"]["status"] == "interrupted"

def test_download_plan_auto_research_uses_download_repair_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_repair_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    captured: dict[str, list[str]] = {}
    checks = iter([(False, ["download_repair required"]), (True, [])])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, force, scope)
        captured["entity_ids"] = list(entity_ids)
        return {
            "sourceAvailability": {
                "readyTargets": list(entity_ids),
                "ineligibleTargets": [],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured["entity_ids"] == [_EID]

def test_download_plan_auto_research_prefers_current_unresolved_lane_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_current_unresolved_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "当前文章不足景区", "旧fetch失败景区"]
    captured: dict[str, object] = {}
    checks = iter([(False, ["article research needs >= 4 text-qualified base sources"]), (True, [])])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {"当前文章不足景区": {"article": ["article sources=2 need>=4"]}},
    )
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: ["旧fetch失败景区"])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {
            "sourceAvailability": {
                "readyTargets": list(entity_ids),
                "ineligibleTargets": [],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": ["当前文章不足景区"], "force": True}

def test_download_plan_checkpoint_forces_auto_research_for_stale_source_rules():
    import download.prepare as prepare_mod
    import download.research_plan as research_mod

    task_id = _make_task()
    batch_id = "download_plan_stale_source_rules"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_dir = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
    )
    plan_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    rule_mtime = max(path.stat().st_mtime_ns for path in plan_paths) + 1_000_000_000
    calls: list[dict[str, object]] = []
    original_rule_mtime = run_mod._source_plan_rule_mtime_ns
    original_prepare = prepare_mod.prepare_source_plan
    original_auto = research_mod.write_auto_research_plans

    def fake_prepare_source_plan(*_args, **_kwargs):
        return None

    def fake_write_auto_research_plans(_task_id, _batch_id, entity_ids, **kwargs):
        calls.append({
            "entity_ids": list(entity_ids),
            "force": kwargs.get("force"),
            "has_progress_callback": callable(kwargs.get("progress_callback")),
        })
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback({
                "status": "running",
                "entityId": _EID,
                "entityCount": len(entity_ids),
                "completedCount": 1,
                "remainingCount": 0,
                "workers": kwargs.get("max_workers"),
                "entitiesPerMinute": 60.0,
                "updatedAt": "2026-06-17T00:00:00+00:00",
                "message": "auto research completed 1/1",
            })
        fresh_mtime = rule_mtime + 1_000_000_000
        for path in plan_paths:
            os.utime(path, ns=(fresh_mtime, fresh_mtime))
        return {"issues": [], "sourceUnavailable": []}

    run_mod._source_plan_rule_mtime_ns = lambda _ctx: rule_mtime
    prepare_mod.prepare_source_plan = fake_prepare_source_plan
    research_mod.write_auto_research_plans = fake_write_auto_research_plans
    try:
        result = run_mod._checkpoint_download_plan(ctx)
    finally:
        run_mod._source_plan_rule_mtime_ns = original_rule_mtime
        prepare_mod.prepare_source_plan = original_prepare
        research_mod.write_auto_research_plans = original_auto

    assert result.status == "done"
    assert calls == [{"entity_ids": [_EID], "force": True, "has_progress_callback": True}]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["activeAutoResearch"]["completedCount"] == 1
    assert "download_plan auto_research 1/1" in state["nextAction"]
    assert "过期 source_plan" in result.message

def test_download_fetch_does_not_auto_research_fetch_stale_only_entities(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_stale_only_no_research"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: [_EID, "额外景区乙"])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])

    def _unexpected_stale_source_plan_check(*_args, **_kwargs):
        raise AssertionError("fetch-stale-only entities must not be sent back to source-plan refresh")

    def _unexpected_auto_research(*_args, **_kwargs):
        raise AssertionError("fetch-stale-only entities must not trigger auto research")

    def _fake_handle_download(ns):
        captured["download_entity_ids"] = ns.entity_ids
        captured["download_lane"] = ns.lane

    monkeypatch.setattr("task.run._stale_source_plan_entities", _unexpected_stale_source_plan_check)
    monkeypatch.setattr("task.run._run_download_auto_research", _unexpected_auto_research)
    monkeypatch.setattr("download.handler.handle_download", _fake_handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["download_entity_ids"] == f"{_EID},额外景区乙"
    assert captured["download_lane"] == "all"

