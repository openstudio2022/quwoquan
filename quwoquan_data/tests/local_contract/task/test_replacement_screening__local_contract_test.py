from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_react_rewind_allows_target_replacement_after_counter_limit():
    task_id = _make_task()
    batch_id = "rw_target_replacement_after_limit"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    completed = {"download_plan", "download_fetch"}
    fail = run_mod.StageResult(
        "download_fetch",
        run_mod.AUTO,
        "failed",
        "download source-unavailable entities abandoned and gated replacements activated; rerun from download_plan",
        fallback_stage="download_plan",
        issues=["activated replacement entities: 替补景区乙"],
    )

    new_completed, ok = run_mod._react_rewind(ctx, state, completed, fail)

    assert ok is True
    assert new_completed == set()
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["reactRewinds"]["download_fetch"] == 1

def test_build_prepare_repair_budget_isolates_homepage_without_replacement(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "build_prepare_replacement_before_partial"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"build_prepare": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    monkeypatch.setattr(
        "build.homepage.prepare_entity_pages",
        lambda *_args, **_kwargs: (batch_root(task_id, batch_id), []),
    )
    def _validate(_task_id, _batch_id, active_spec):
        names = {
            str(target.get("name") or "")
            for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
        }
        return [f"地点/景区/{_EID}: homepage baseDraft.text 缺失"] if _EID in names else []

    monkeypatch.setattr("build.homepage.validate_entity_page_inputs", _validate)

    def _unexpected_screen(*_args, **_kwargs):
        raise AssertionError("homepage-only shortfall must not screen entity replacements")

    monkeypatch.setattr("task.run._screen_replacements_for_abandoned_entities", _unexpected_screen)

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "done"
    assert "稳定景区乙" in result.message
    assert _EID not in result.message
    state = run_mod.load_workflow_state(task_id, batch_id)
    homepage_abandoned = [
        item["entityId"]
        for item in (state.get("abandonedObjects") or [])
        if item.get("abandonScope") == "homepage"
    ]
    assert homepage_abandoned == [_EID]
    assert state.get("replacementObjects") in (None, [])
    assert {target["name"] for target in run_mod._active_spec(ctx)["scope"]["coverageTargets"]} == {
        _EID,
        "稳定景区乙",
    }


def test_build_prepare_isolates_homepage_after_one_homepage_repair(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "build_prepare_replacement_after_one_repair"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"build_prepare": max(0, run_mod.MAX_REACT_REWINDS - 1)}
    run_mod.save_workflow_state(state)
    monkeypatch.setattr(
        "build.homepage.prepare_entity_pages",
        lambda *_args, **_kwargs: (batch_root(task_id, batch_id), []),
    )
    def _validate(_task_id, _batch_id, active_spec):
        names = {
            str(target.get("name") or "")
            for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
        }
        return [f"地点/景区/{_EID}: homepage baseDraft.text 缺失"] if _EID in names else []

    monkeypatch.setattr("build.homepage.validate_entity_page_inputs", _validate)

    def _unexpected_screen(*_args, **_kwargs):
        raise AssertionError("homepage-only shortfall must not screen entity replacements")

    monkeypatch.setattr("task.run._screen_replacements_for_abandoned_entities", _unexpected_screen)

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "done"
    assert "稳定景区乙" in result.message
    assert _EID not in result.message
    state = run_mod.load_workflow_state(task_id, batch_id)
    homepage_abandoned = [
        item["entityId"]
        for item in (state.get("abandonedObjects") or [])
        if item.get("abandonScope") == "homepage"
    ]
    assert homepage_abandoned == [_EID]
    assert state.get("replacementObjects") in (None, [])


def test_download_fetch_scopes_build_prepare_homepage_repair(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_fetch_build_prepare_homepage_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["failedObjects"] = [f"地点/景区/{_EID}: homepage baseDraft.text 缺失"]
    run_mod.save_workflow_state(state)
    calls = []

    def _handle_download(ns):
        calls.append(ns)

    monkeypatch.setattr("download.handler.handle_download", _handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("task.run._download_stage_gate_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: ["稳定景区乙"])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])

    result = run_mod._run_download_fetch(ctx)

    assert result.status == "done"
    assert len(calls) == 1
    assert calls[0].entity_ids == _EID
    assert calls[0].lane == "homepage"


def test_download_fetch_scopes_build_prepare_retry_from_repair_report(monkeypatch):
    from _common.stage_reports import write_repair_report

    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_fetch_build_prepare_repair_report_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    write_repair_report(
        task_id=task_id,
        batch_id=batch_id,
        command="workflow_run",
        ref="build_prepare",
        failed_stage="build_prepare",
        failed_gate="build_prepare_gate",
        issues=[f"地点/景区/{_EID}: homepage lane 无可发布图片资产"],
        fallback_stage="download_plan",
        rerun_chain=["download_plan", "download_fetch", "build_prepare"],
    )
    calls = []

    def _handle_download(ns):
        calls.append(ns)

    monkeypatch.setattr("download.handler.handle_download", _handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("task.run._download_stage_gate_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: ["稳定景区乙"])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])

    result = run_mod._run_download_fetch(ctx)

    assert result.status == "done"
    assert len(calls) == 1
    assert calls[0].entity_ids == _EID
    assert calls[0].lane == "homepage"


def test_content_plan_quota_shortfall_routes_to_replacement_not_agent(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "content_plan_quota_shortfall_replacement"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setattr(
        "task.run._content_plan_done",
        lambda _ctx: (False, ["content_plan_packet.json missing under batch _shared/"]),
    )
    monkeypatch.setattr(
        "task.run._auto_content_plan",
        lambda _ctx, _spec: [
            f"{_EID}: entityArticlesPerTarget quota 4 but only picked 3 qualified article source(s)"
        ],
    )

    def _replace(current_ctx, issues, *, entity_type):
        assert current_ctx is ctx
        assert entity_type == "地点/景区"
        assert "entityArticlesPerTarget quota 4" in issues[0]
        return [_EID], ["替补景区乙"], []

    monkeypatch.setattr("task.run._replace_content_plan_source_shortfall_entities", _replace)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert "content_plan source shortfall abandoned entities" in result.issues[0]
    assert "activated replacement entities: 替补景区乙" in result.issues


def test_download_content_capacity_preflight_does_not_treat_partial_as_quota_shortfall(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    store.save_spec(spec)
    ctx = _ctx(task_id, "download_capacity_partial_is_not_quota_shortfall")

    monkeypatch.setattr(
        "task.run._content_capacity_gate_for_entity",
        lambda *_args, **_kwargs: (
            False,
            [f"{_EID}: content capacity article base source shortfall 1<4"],
            {"pickedArticleBaseSources": 1, "qualifiedArticleBaseSources": 1},
        ),
    )

    issues = run_mod._download_content_capacity_preflight(ctx)

    assert issues == [
        f"{_EID}: content capacity article base source shortfall 1<4; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    ]


def test_build_prepare_homepage_only_reject_does_not_trip_min_entities(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["acceptance"] = {"minEntities": 1}
    store.save_spec(spec)
    batch_id = "build_prepare_partial_below_min_blocks"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"build_prepare": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    monkeypatch.setattr(
        "build.homepage.prepare_entity_pages",
        lambda *_args, **_kwargs: (batch_root(task_id, batch_id) / "entities", []),
    )
    def _validate(_task_id, _batch_id, active_spec):
        names = {
            str(target.get("name") or "")
            for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
        }
        return [f"地点/景区/{_EID}: homepage baseDraft.text 缺失"] if _EID in names else []

    monkeypatch.setattr("build.homepage.validate_entity_page_inputs", _validate)
    monkeypatch.setattr(
        "task.run._screen_replacements_for_abandoned_entities",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no replacement for homepage-only reject")),
    )

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "done"
    state = run_mod.load_workflow_state(task_id, batch_id)
    homepage_abandoned = [
        item["entityId"]
        for item in (state.get("abandonedObjects") or [])
        if item.get("abandonScope") == "homepage"
    ]
    assert homepage_abandoned == [_EID]


def test_build_prepare_blocks_active_shortfall_even_when_remaining_homepages_are_ready(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "build_prepare_active_shortfall_even_if_ready"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["abandonedObjects"] = [
        {
            "entityId": _EID,
            "stage": "build_prepare",
            "reason": "fixture abandoned primary",
            "status": "abandoned",
        }
    ]
    run_mod.save_workflow_state(state)

    def _unexpected_prepare(*_args, **_kwargs):
        raise AssertionError("build_prepare must stop before preparing partial active targets")

    monkeypatch.setattr("build.homepage.prepare_entity_pages", _unexpected_prepare)

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert "replacement active target shortfall 1<2" in result.issues


def test_download_plan_blocks_min_entity_shortfall_after_replacement_exhausted(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "download_plan_active_shortfall_blocks"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = ["稳定景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["abandonedObjects"] = [
        {
            "entityId": _EID,
            "stage": "download_plan",
            "reason": "fixture abandoned primary",
            "status": "abandoned",
        }
    ]
    run_mod.save_workflow_state(state)
    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "task.run._screen_replacements_for_abandoned_entities",
        lambda *_args, **_kwargs: ([], [], {}),
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "failed"
    assert any("replacement active target shortfall 1<2" in issue for issue in result.issues), result.issues
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert not state.get("replacementPolicy", {}).get("shortfallAllowed")

def test_replacement_screening_uses_budget_waves_when_not_explicit(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": f"替补景区{i}"}
        for i in range(1, 6)
    ]
    store.save_spec(spec)
    batch_id = "replacement_budget_waves"
    ctx = _ctx(task_id, batch_id)
    run_mod.mark_abandoned_entities(
        task_id,
        batch_id,
        [_EID],
        stage="download_fetch",
        reason="source_unavailable",
    )
    monkeypatch.setattr("task.run._replacement_screening_limits", lambda _ctx: (3, 1, 8))
    monkeypatch.delenv("QWQ_REPLACEMENT_MAX_WAVES", raising=False)
    calls: list[str] = []

    def _fake_screen(current_ctx, *, entity_type, reason, needed, scope):
        del entity_type, needed
        calls.append(scope)
        candidate = run_mod._next_replacement_candidates(current_ctx, needed=1)[0]
        status = "active" if len(calls) == 4 else "rejected"
        run_mod._append_replacement_row(
            current_ctx,
            entity_id=candidate["entityId"],
            entity_type=candidate["entityType"],
            status=status,
            reason=reason,
            source_gate_status="passed" if status == "active" else "failed",
            issues=[] if status == "active" else ["source unavailable"],
        )
        if status == "active":
            current_ctx.entity_ids.append(candidate["entityId"])
            return [candidate["entityId"]], [], {}
        return [], [candidate["entityId"]], {}

    monkeypatch.setattr("task.run._screen_replacement_targets", _fake_screen)

    activated, rejected, _report = run_mod._screen_replacements_for_abandoned_entities(
        ctx,
        entity_type="地点/景区",
        abandoned=[_EID],
        reason="keep target count after download_fetch source-unavailable entity",
        scope_prefix="download_fetch_source_unavailable_replacement",
    )

    assert activated == ["替补景区4"]
    assert rejected == ["替补景区1", "替补景区2", "替补景区3"]
    assert len(calls) == 4

def test_replacement_source_plan_check_skips_batch_download_repair_gate(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "replacement_source_plan_check_skips_download_repair"
    ctx = _ctx(task_id, batch_id)
    write_json(batch_root(task_id, batch_id) / "_shared" / "download_repair.json", {"issues": ["stale"]})

    def _unexpected_gate(*_args, **_kwargs):
        raise AssertionError("scoped replacement screening must not run batch download gate")

    monkeypatch.setattr("download.gate.gate_download", _unexpected_gate)

    ok, missing = run_mod._source_plan_filled_for_entities(ctx, [_EID])

    assert ok is False
    assert missing

def test_gated_replacement_invalidates_target_dependent_completed_stages(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "replacement_invalidates_downstream_stages"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["completed"] = [
        "download_plan",
        "download_fetch",
        "build_prepare",
        "build_homepage",
        "build_validate",
        "content_plan",
    ]
    state["waitingCheckpoint"] = "content_plan"
    state["retryCounts"] = {"download_plan": 1, "content_plan": 2}
    state["infrastructureRetryCounts"] = {"download_fetch": 1}
    state["reactRewinds"] = {"content_plan": 1}
    run_mod.save_workflow_state(state)

    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._run_download_auto_research",
        lambda *_args, **_kwargs: {
            "sourceAvailability": {
                "readyTargets": ["替补景区乙"],
                "ineligibleTargets": [],
            }
        },
    )
    monkeypatch.setattr("task.run._source_plan_filled_for_entities", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._homepage_base_draft_gate_for_entity", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._content_capacity_gate_for_entity", lambda *_args, **_kwargs: (True, [], {}))

    activated, rejected, _report = run_mod._screen_replacement_targets(
        ctx,
        entity_type="地点/景区",
        reason="keep target count after content_plan source shortfall",
        needed=1,
        scope="replacement_invalidation",
    )

    assert activated == ["替补景区乙"]
    assert rejected == []
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["completed"] == ["download_plan", "download_fetch"]
    assert state["waitingCheckpoint"] is None
    assert state["retryCounts"] == {"download_plan": 1}
    assert state["infrastructureRetryCounts"] == {"download_fetch": 1}
    assert state["reactRewinds"] == {}
    assert state["replacementPolicy"]["rerunFromStage"] == "build_prepare"
    assert state["targetSetChangeEvents"][-1]["entityIds"] == ["替补景区乙"]
    assert state["targetSetChangeEvents"][-1]["invalidatedStages"] == [
        "build_prepare",
        "build_homepage",
        "build_validate",
        "content_plan",
    ]

def test_replacement_screening_rejects_content_capacity_shortfall(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["content"]["research"]["imageCountPolicy"] = "hard_quota"
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "replacement_content_capacity_gate"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, "替补景区乙", etype_hint="地点/景区")
    for index in range(1, 3):
        image = _real_jpeg(700 + index)
        write_structured_source_unit(
            object_dir,
            ordinal=index,
            source_id=f"article_base_{index}",
            source_md=_long_base_text(f"替补景区乙底稿{index}"),
            clean_md=_long_base_text(f"替补景区乙底稿{index}"),
            quality={"quality": "A-story", "score": 9, "fetchSucceeded": True},
            source_category="travelogue",
            source_use_mode="factual_reference_only",
            source_role="base",
            research_lane="article",
            title=f"替补底稿 {index}",
            target_ref="/entity/地点/景区/替补景区乙",
            images=[
                {
                    "fileName": "article.jpg",
                    "bytes": image,
                    "ext": ".jpg",
                    "sha256": f"sha256:{hashlib.sha256(image).hexdigest()}",
                    "sourceCollectionId": f"article-collection-{index}",
                    "caption": "替补景区乙 文章源图",
                }
            ],
            task_id=task_id,
            batch_id=batch_id,
            build_variants=False,
        )

    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._run_download_auto_research",
        lambda *_args, **_kwargs: {"sourceAvailability": {"readyTargets": ["替补景区乙"], "ineligibleTargets": []}},
    )
    monkeypatch.setattr("task.run._source_plan_filled_for_entities", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._homepage_base_draft_gate_for_entity", lambda *_args, **_kwargs: (True, []))

    activated, rejected, _report = run_mod._screen_replacement_targets(
        ctx,
        entity_type="地点/景区",
        reason="keep target count after content_plan source shortfall",
        needed=1,
        scope="replacement_content_capacity",
    )

    assert activated == []
    assert rejected == ["替补景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    row = next(item for item in state["replacementObjects"] if item["entityId"] == "替补景区乙")
    assert row["sourceGateStatus"] == "failed"
    assert any("content capacity image source shortfall" in issue for issue in row["issues"])
    assert state["replacementContentCapacity"][-1]["status"] == "failed"

def test_replacement_screening_rejects_homepage_base_draft_shortfall(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "replacement_homepage_base_draft_gate"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._run_download_auto_research",
        lambda *_args, **_kwargs: {"sourceAvailability": {"readyTargets": ["替补景区乙"], "ineligibleTargets": []}},
    )
    monkeypatch.setattr("task.run._source_plan_filled_for_entities", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr(
        "task.run._homepage_base_draft_gate_for_entity",
        lambda *_args, **_kwargs: (
            False,
            ["地点/景区/替补景区乙: replacement homepage baseDraft unavailable"],
        ),
    )

    def _unexpected_content_capacity(*_args, **_kwargs):
        raise AssertionError("homepage base-draft failed replacements must not reach content capacity gate")

    monkeypatch.setattr("task.run._content_capacity_gate_for_entity", _unexpected_content_capacity)

    activated, rejected, _report = run_mod._screen_replacement_targets(
        ctx,
        entity_type="地点/景区",
        reason="keep target count after build_prepare homepage unavailable",
        needed=1,
        scope="replacement_homepage_gate",
    )

    assert activated == []
    assert rejected == ["替补景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    row = next(item for item in state["replacementObjects"] if item["entityId"] == "替补景区乙")
    assert row["status"] == "rejected"
    assert "replacement homepage baseDraft unavailable" in row["issues"][0]

def test_run_pipeline_preserves_replacement_invalidation_from_entry_state(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "entry_replacement_invalidation_reload"
    ctx = _ctx(task_id, batch_id)
    ctx.until = "download_plan"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["abandonedObjects"] = [
        {
            "entityId": _EID,
            "stage": "download_plan",
            "reason": "fixture abandoned primary",
            "status": "abandoned",
            "abandonedAt": "2026-06-19T00:00:00+00:00",
        }
    ]
    state["completed"] = ["download_plan", "download_fetch", "build_prepare"]
    run_mod.save_workflow_state(state)
    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._homepage_base_draft_gate_for_entity", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr(
        "task.run._content_capacity_gate_for_entity",
        lambda *_args, **_kwargs: (True, [], {"fixture": "passed"}),
    )

    code = run_mod.run_pipeline(ctx)

    assert code == 0
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert set(state["completed"]) == {"download_plan", "download_fetch"}
    assert state["stoppedAtStage"] == "download_plan"
    active_rows = [
        item
        for item in state["replacementObjects"]
        if item.get("status") == "active"
    ]
    assert [item["entityId"] for item in active_rows] == ["替补景区乙"]
    assert [item.get("sourceGateStatus") for item in active_rows] == ["passed"]
    assert "legacy_activation" not in {
        item.get("sourceGateStatus")
        for item in state["replacementObjects"]
    }
    assert state["targetSetChangeEvents"][-1]["invalidatedStages"] == [
        "build_prepare",
    ]

def test_legacy_replacement_activation_requires_screening():
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "legacy_replacement_activation_disabled"
    ctx = _ctx(task_id, batch_id)
    run_mod.mark_abandoned_entities(
        task_id,
        batch_id,
        [_EID],
        stage="download_plan",
        reason="fixture source unavailable",
    )

    activated = run_mod._activate_replacement_targets(
        ctx,
        reason="fixture must not bypass source screening",
    )

    assert activated == []
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert not [
        item
        for item in state.get("replacementObjects") or []
        if item.get("status") == "active"
    ]
    assert state["replacementPolicy"]["screeningRequired"] is True
    assert state["replacementPolicy"]["legacyActivationDisabled"] is True

def test_replacement_screening_stops_at_policy_total_limit(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "maxReplacementScreenedPerRun": 1,
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "replacement_screening_total_limit"
    ctx = _ctx(task_id, batch_id)
    run_mod._append_replacement_row(
        ctx,
        entity_id="已筛选景区",
        entity_type="地点/景区",
        status="rejected",
        reason="test previous screening",
        source_gate_status="failed",
        issues=["previous failure"],
    )

    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("replacement limit should stop before prepare")),
    )

    activated, rejected, report = run_mod._screen_replacement_targets(
        ctx,
        entity_type="地点/景区",
        reason="keep target count after abandoned source-unavailable entity",
        needed=1,
        scope="replacement_wave_limit",
    )

    assert activated == []
    assert rejected == []
    assert report["sourceAvailability"]["screeningStoppedReason"] == "replacement_screening_limit"
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["replacementPolicy"]["screeningStoppedReason"] == "replacement_screening_limit"

def test_download_plan_repairable_source_gap_does_not_screen_replacements(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_repairable_gap_no_replacement"
    ctx = _ctx(task_id, batch_id)
    calls: list[list[str]] = []

    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (
            False,
            [f"{_EID}: download_repair required: {_EID}: missing core source categories ['encyclopedia']"],
        ),
    )
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: [],
    )

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del current_ctx, entity_type, force, scope
        calls.append(list(entity_ids))
        return {
            "sourceAvailability": {
                "readyTargets": [],
                "ineligibleTargets": [
                    {
                        "entityId": _EID,
                        "status": "repairable",
                        "lanes": ["homepage"],
                        "issues": [
                            f"homepage: download_repair required: {_EID}: missing core source categories ['encyclopedia']"
                        ],
                        "nextActions": ["source_repair"],
                        "deterministic": False,
                    }
                ],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _auto)

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "waiting"
    assert calls == [[_EID]]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert not state.get("replacementObjects")

def test_download_fast_fail_does_not_abandon_when_replacement_capacity_insufficient(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    ctx = _ctx(task_id, "download_fast_fail_no_reserve")
    monkeypatch.setattr("download.gate.download_requirements", lambda _task_id: {"minImages": 3})
    monkeypatch.setattr(
        "_common.download_diagnostics.entity_download_diagnostics",
        lambda _root, _entity_id: {
            "downloadedImages": 2,
            "rejectedByCategory": {
                "duplicate": 1,
                "rights": 0,
                "safety_or_watermark": 0,
                "fetch_or_non_image": 0,
            },
        },
    )

    issues = run_mod._apply_download_fast_fail(
        ctx,
        [f"{_EID}: only 2 unique publishable images (need >= 3)"],
    )

    assert len(issues) == 1
    assert "replacement capacity exhausted" in issues[0]
    state = run_mod.load_workflow_state(task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()

def test_source_availability_does_not_fast_fail_when_replacement_capacity_insufficient():
    names = ["可用景区甲", "缺图景区乙", "缺图景区丙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability reserve shortage",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
            ],
            "reserveCoverageTargets": [
                {"entityType": "地点/景区", "name": "替补景区丁"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {"lanes": ["homepage", "article", "image"]},
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        acceptance={"minEntities": 3},
        created_by="test",
    )
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "deliveryMode": "partial_with_replacement_report",
    }
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_reserve_shortage",
        entity_ids=names,
        spec=spec,
        baseline_packet={},
        baseline_packet_path=Path("/tmp/nonexistent-baseline.json"),
    )
    report = {
        "sourceAvailability": {
            "readyTargets": ["可用景区甲"],
            "ineligibleTargets": [
                {
                    "entityId": entity,
                    "issues": [f"{entity}: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
                for entity in ("缺图景区乙", "缺图景区丙")
            ],
        }
    }

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == []
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()

def test_agent_active_throughput_is_diagnostic_not_wall_clock_replacement():
    metrics = run_mod._agent_active_throughput(
        {
            "agentRunHistory": [
                {
                    "stage": "produce_author",
                    "plannedJobCount": 4,
                    "finishedCount": 3,
                    "infrastructureFailures": 1,
                    "scheduler": {"elapsedSeconds": 120, "startedAt": "s1"},
                    "finishedAt": "t1",
                },
                {
                    "stage": "produce_author",
                    "plannedJobCount": 4,
                    "finishedCount": 3,
                    "infrastructureFailures": 1,
                    "scheduler": {"elapsedSeconds": 120, "startedAt": "s1"},
                    "finishedAt": "t1",
                }
            ],
            "lastAgentRun": {
                "stage": "produce_author",
                "plannedJobCount": 2,
                "finishedCount": 2,
                "infrastructureFailures": 0,
                "scheduler": {"elapsedSeconds": 60, "startedAt": "s2"},
                "finishedAt": "t2",
            },
        }
    )

    assert metrics["authorRunCount"] == 2
    assert metrics["finishedAuthorJobs"] == 5
    assert metrics["infrastructureFailures"] == 1
    assert metrics["finishedAuthorJobsPerHour"] == 100.0


def test_agent_active_throughput_falls_back_to_homepage_stage_for_homepage_only_trials():
    metrics = run_mod._agent_active_throughput(
        {
            "agentRunHistory": [
                {
                    "stage": "build_homepage",
                    "plannedJobCount": 4,
                    "finishedCount": 3,
                    "infrastructureFailures": 1,
                    "scheduler": {
                        "elapsedSeconds": 180,
                        "effectiveWorkerCount": 3,
                        "startedAt": "s1",
                    },
                    "finishedAt": "t1",
                }
            ]
        }
    )

    assert metrics["sourceStage"] == "build_homepage"
    assert metrics["jobKind"] == "homepage"
    assert metrics["authorRunCount"] == 1
    assert metrics["finishedAuthorJobs"] == 3
    assert metrics["effectiveWorkerCount"] == 3
    assert metrics["perWorkerObjectsPerHour"] == 20.0
