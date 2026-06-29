from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_download_requirements_single_image_work_is_score_bonus_by_default():
    from download.gate import download_requirements

    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec["content"]["quotas"]["entityHomepagesPerTarget"] = 1
    store.save_spec(spec)

    requirements = download_requirements(task_id)

    assert requirements["minImages"] == 0
    assert requirements["minHomepageSources"] == 1
    assert requirements["minArticleBaseSources"] == 4

def test_reference_only_image_strategy_does_not_require_publishable_image_lane():
    from download.gate import download_requirements

    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["content"]["research"]["imageAssetStrategy"] = "reference_only_no_image_release"
    store.save_spec(spec)

    requirements = download_requirements(task_id)

    assert requirements["minImages"] == 0
    assert requirements["minHomepageSources"] == 1

def test_recover_stale_agent_scheduler_clears_orphaned_waiting_state(monkeypatch):
    task_id = _make_task()
    batch_id = "stale_scheduler_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state.update(
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "produce_author",
            "heartbeatAt": "2000-01-01T00:00:00+00:00",
            "activeAgentScheduler": {
                "stage": "produce_author",
                "runtime": "local",
                "promptCount": 10,
                "startedAt": "2000-01-01T00:00:00+00:00",
            },
        }
    )
    monkeypatch.setattr(run_mod, "MANAGED_SCHEDULER_STALE_SECONDS", 60)
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_agent_scheduler(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "running"
    assert "activeAgentScheduler" not in recovered
    assert recovered["waitingCheckpoint"] == "produce_author"
    assert recovered["schedulerRecoveryActions"][-1]["stage"] == "produce_author"

def test_recover_agent_scheduler_clears_fresh_orphan_without_waiting_for_stale_timeout(monkeypatch):
    task_id = _make_task()
    batch_id = "fresh_orphan_scheduler_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state.update(
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "produce_author",
            "heartbeatAt": store.now_iso(),
            "activeAgentScheduler": {
                "stage": "produce_author",
                "runtime": "local",
                "promptCount": 10,
                "startedAt": store.now_iso(),
            },
        }
    )
    monkeypatch.setattr(run_mod, "MANAGED_SCHEDULER_STALE_SECONDS", 900)
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_agent_scheduler(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    action = recovered["schedulerRecoveryActions"][-1]
    assert recovered["status"] == "running"
    assert "activeAgentScheduler" not in recovered
    assert action["previous"]["recoveredBeforeStaleTimeout"] is True

def test_recover_stale_controller_yield_clears_dead_controller(monkeypatch):
    from _common import ops_governance as og

    task_id = _make_task()
    batch_id = "stale_controller_yield_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state.update(
        {
            "status": "repairing",
            "waitingCheckpoint": "produce_author",
            "controllerYield": {
                "stage": "produce_author",
                "reason": "managed ref slice partially completed",
                "yieldedAt": "2000-01-01T00:00:00+00:00",
            },
            "activeAgentScheduler": {"stage": "produce_author", "runtime": "local"},
            "failedObjects": ["old yield"],
        }
    )
    run_mod.save_workflow_state(state)
    og.controller_lease_path(task_id, batch_id, create=True).write_text(
        '{"status":"active","pid":999999,"controllerRunId":"dead"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_controller_yield(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "running"
    assert recovered["waitingCheckpoint"] == "produce_author"
    assert recovered["failedObjects"] == []
    assert "controllerYield" not in recovered
    assert "activeAgentScheduler" not in recovered
    assert recovered["controllerYieldRecoveryActions"][-1]["stage"] == "produce_author"
    assert not og.controller_lease_path(task_id, batch_id, create=False).exists()

def test_recover_controller_yield_keeps_live_controller(monkeypatch):
    from _common import ops_governance as og

    task_id = _make_task()
    batch_id = "live_controller_yield_kept"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state.update(
        {
            "status": "repairing",
            "waitingCheckpoint": "produce_author",
            "controllerYield": {"stage": "produce_author", "reason": "bounded slice"},
        }
    )
    run_mod.save_workflow_state(state)
    og.controller_lease_path(task_id, batch_id, create=True).write_text(
        '{"status":"active","pid":12345,"controllerRunId":"live"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)
    monkeypatch.setattr(og, "pid_alive", lambda pid: int(pid or 0) == 12345)

    assert run_mod._recover_stale_controller_yield(ctx, state) is False

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["controllerYield"]["reason"] == "bounded slice"

def test_keyboard_interrupt_marks_workflow_manual_required(monkeypatch):
    task_id = _make_task()
    batch_id = "keyboard_interrupt_manual_required"
    ctx = _ctx(task_id, batch_id)
    original_dag = run_mod.DAG
    monkeypatch.setattr(
        run_mod,
        "DAG",
        [
            (
                "download_plan",
                run_mod.CHECKPOINT,
                lambda _ctx: (_ for _ in ()).throw(KeyboardInterrupt("workflow interrupted by signal 15")),
            )
        ],
    )
    try:
        try:
            run_mod.run_pipeline(ctx)
        except KeyboardInterrupt:
            pass
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "manual_required"
    assert state["waitingCheckpoint"] == "download_plan"
    assert state["lastFailedStage"] == "download_plan"
    assert state["failedObjects"] == [
        "download_plan: interrupted; workflow stopped before checkpoint completion; workflow interrupted by signal 15"
    ]
    assert state["interruptReason"] == (
        "download_plan: interrupted; workflow stopped before checkpoint completion; "
        "workflow interrupted by signal 15"
    )

def test_rewind_drops_target_and_subsequent():
    """ReAct 回退：rewind 到 produce_compose 应清掉它及之后所有 stage，保留之前。"""
    completed = set(run_mod.STAGE_NAMES)  # 全完成
    kept = run_mod._rewind_to(completed, "produce_compose")
    assert "produce_compose" not in kept
    assert "produce_review" not in kept
    assert "publish" not in kept
    assert "download_fetch" in kept and "build_validate" in kept

def test_react_rewind_respects_max_and_writes_repair():
    """ReAct 回退计数到上限后不再回退；回退时写 repair_report。"""
    task_id = _make_task()
    state = run_mod.load_workflow_state(task_id, "rw1")
    ctx = _ctx(task_id, "rw1")
    completed = set(run_mod.STAGE_NAMES)
    fail = run_mod.StageResult("produce_review", run_mod.AUTO, "failed",
                               "发布门未过", fallback_stage="download", issues=["x"])
    # 前 MAX 次应成功回退
    for i in range(run_mod.MAX_REACT_REWINDS):
        completed, ok = run_mod._react_rewind(ctx, state, completed, fail)
        assert ok, f"rewind {i} should succeed"
        assert "download_plan" not in completed  # download→download_plan 已回退
        completed = set(run_mod.STAGE_NAMES)  # 模拟重跑后再次失败
    # 超限后不再回退
    _, ok = run_mod._react_rewind(ctx, state, completed, fail)
    assert ok is False
    # repair_report 已落盘
    from _common.paths import batch_results_dir
    repair_dir = batch_results_dir(task_id, "rw1", "workflow_run", "repair_report")
    assert repair_dir.is_dir() and any(repair_dir.glob("*.json"))

def test_react_rewind_reloads_state_after_stage_side_effects():
    task_id = _make_task()
    batch_id = "rw_reload_latest_state"
    ctx = _ctx(task_id, batch_id)
    stale_state = run_mod.load_workflow_state(task_id, batch_id)
    stale_state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS}
    latest = run_mod.load_workflow_state(task_id, batch_id)
    latest["reactRewinds"] = {}
    run_mod.save_workflow_state(latest)
    completed = {"download_plan", "download_fetch"}
    fail = run_mod.StageResult(
        "download_fetch",
        run_mod.AUTO,
        "failed",
        "replacement activated; rerun from download_plan",
        fallback_stage="download_plan",
        issues=["replacement activated"],
    )

    new_completed, ok = run_mod._react_rewind(ctx, stale_state, completed, fail)

    assert ok is True
    assert new_completed == set()
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["reactRewinds"]["download_fetch"] == 1

def test_waiting_checkpoint_replaces_stale_failed_objects(monkeypatch):
    task_id = _make_task()
    batch_id = "waiting_replaces_stale_failed_objects"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["failedObjects"] = ["旧景区: article sources=1 need>=2"]
    run_mod.save_workflow_state(state)

    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["新景区: image collections=1 need>=2"]),
    )
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {_EID: {"image": ["image collections=1 need>=2"]}},
    )
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")

    code = run_mod.run_pipeline(ctx)

    assert code == 10
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["waitingCheckpoint"] == "download_plan"
    assert state["failedObjects"] == [
        f"{_EID}: source_plan: image: image collections=1 need>=2"
    ]

def test_mark_abandoned_content_refs_reclassifies_retrying_rows():
    task_id = _make_task()
    batch_id = "abandon_retrying_content_ref"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["abandonedContentObjects"] = [
        {
            "ref": "candidate_retrying",
            "stage": "produce_author",
            "reason": "agent_infra_recovered",
            "status": "retrying",
            "abandonedAt": "2026-06-20T00:00:00+00:00",
        }
    ]
    run_mod.save_workflow_state(state)

    report = run_mod.mark_abandoned_content_refs(
        task_id,
        batch_id,
        ["candidate_retrying"],
        stage="content_plan",
        reason="baseDraftText_effective_length_below_600_release_gate",
    )

    assert report["added"] == ["candidate_retrying"]
    updated = run_mod.load_workflow_state(task_id, batch_id)["abandonedContentObjects"][0]
    assert updated["status"] == "abandoned"
    assert updated["stage"] == "content_plan"
    assert "baseDraftText" in updated["reason"]

def test_download_plan_source_shortfall_becomes_deterministic_after_fetch_rewind():
    task_id = _make_task()
    batch_id = "download_plan_source_shortfall_exhausted"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)
    unresolved = {
        _EID: {
            "article": [
                "article sources=3 need>=4",
                "article research needs >= 4 text-qualified base sources",
            ]
        }
    }

    exhausted = run_mod._download_plan_repair_exhausted_unresolved(ctx, unresolved)

    assert exhausted == unresolved

def test_run_pipeline_preserves_stage_state_deltas(monkeypatch):
    task_id = _make_task()
    batch_id = "preserve_state_deltas"
    ctx = _ctx(task_id, batch_id)

    def _runner(_ctx: run_mod.PipelineContext) -> run_mod.StageResult:
        run_mod.mark_abandoned_content_refs(
            task_id,
            batch_id,
            [f"{_EID}_planning_consultation"],
            stage="content_plan",
            reason="source_unavailable: fixture lacks usable base source",
        )
        return run_mod.StageResult(
            "content_plan",
            run_mod.CHECKPOINT,
            "failed",
            "content_plan incomplete",
            issues=["fixture missing article source"],
        )

    monkeypatch.setattr("task.run.DAG", [("content_plan", run_mod.CHECKPOINT, _runner)])
    monkeypatch.setattr("task.run.STAGE_NAMES", ["content_plan"])

    assert run_mod.run_pipeline(ctx) == 1
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "manual_required"
    assert state["abandonedContentObjects"][0]["ref"] == f"{_EID}_planning_consultation"
    assert state["abandonedContentObjects"][0]["reason"].startswith("source_unavailable:")

def test_reset_stage_retries_records_infra_recovery():
    task_id = _make_task()
    batch_id = "retry_stage"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "build_homepage"
    state["status"] = "manual_required"
    state["completed"] = ["download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate", "content_plan"]
    state["retryCounts"] = {"build_homepage": 2, "content_plan": 1}
    state["infrastructureRetryCounts"] = {"build_homepage": 3, "content_plan": 1}
    state["reactRewinds"] = {"build_validate": 1, "content_plan": 2}
    state["failedObjects"] = ["Bridge request failed", "internal error"]
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="build_homepage",
        reason="cursor bridge recovered",
    )

    assert report["status"] == "waiting_agent"
    assert report["completed"] == ["download_plan", "download_fetch", "build_prepare"]
    assert report["retryCounts"] == {}
    assert report["infrastructureRetryCounts"] == {}
    assert report["reactRewinds"] == {"build_validate": 1, "content_plan": 2}
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["failedObjects"] == []
    assert state["completed"] == ["download_plan", "download_fetch", "build_prepare"]
    assert state["reactRewinds"] == {"build_validate": 1, "content_plan": 2}
    assert state["recoveryActions"][-1]["stage"] == "build_homepage"
    assert state["recoveryActions"][-1]["previous"]["infrastructureRetryCount"] == 3
    assert "content_plan" in state["recoveryActions"][-1]["previous"]["completed"]

def test_reset_stage_retries_can_reset_react_rewinds_after_quality_contract_fix():
    task_id = _make_task()
    batch_id = "retry_stage_quality_contract"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["status"] = "manual_required"
    state["completed"] = [
        "download_plan",
        "download_fetch",
        "build_prepare",
        "build_homepage",
        "build_validate",
        "content_plan",
        "produce_plan",
        "produce_compose",
        "produce_author",
    ]
    state["reactRewinds"] = {"produce_review": 2, "download_fetch": 1}
    state["failedObjects"] = ["old quality contract failure"]
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="produce_compose",
        reason="quality contract fixed",
        reset_react_rewinds=True,
    )

    assert report["resetReactRewinds"] == ["produce_review"]
    assert report["reactRewinds"] == {"download_fetch": 1}
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["reactRewinds"] == {"download_fetch": 1}
    assert state["recoveryActions"][-1]["resetReactRewinds"] == ["produce_review"]

def test_reset_stage_retries_reactivates_abandoned_content_refs_for_stage():
    task_id = _make_task()
    batch_id = "retry_stage_abandoned_content"
    ctx = _ctx(task_id, batch_id)
    ref = "需要重试的文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(task_id, batch_id, ref, {"carrier": "article", "baseDraftText": _long_base_text(ref)})
    write_placeholder_draft(task_id, batch_id, ref)
    report = run_mod.mark_abandoned_content_refs(
        task_id,
        batch_id,
        [ref],
        stage="produce_author",
        reason="agent_infrastructure_unavailable_after_3_managed_retries",
    )
    assert report["added"] == [ref]
    assert run_mod._drafts_authored(ctx) == (True, [])

    reset = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="produce_author",
        reason="cursor bridge recovered",
    )

    assert reset["reactivatedContentRefs"] == [ref]
    state = run_mod.load_workflow_state(task_id, batch_id)
    row = state["abandonedContentObjects"][0]
    assert row["ref"] == ref
    assert row["status"] == "retrying"
    assert row["reactivationReason"] == "cursor bridge recovered"
    assert run_mod._drafts_authored(ctx) == (False, [ref])

def test_reset_stage_retries_reactivates_tail_stage_abandoned_objects():
    task_id = _make_task()
    batch_id = "retry_content_plan_reactivates_abandoned"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["status"] = "manual_required"
    state["completed"] = ["download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate"]
    state["abandonedObjects"] = [
        {
            "entityId": "上游失败景区",
            "stage": "download_plan",
            "reason": "source unavailable",
            "status": "abandoned",
        },
        {
            "entityId": "旧规则误判景区",
            "stage": "content_plan",
            "reason": "article source image shortfall",
            "status": "abandoned",
        },
    ]
    state["abandonedContentObjects"] = [
        {
            "ref": "旧规则误判景区_planning_consultation",
            "stage": "content_plan",
            "reason": "article source image shortfall",
            "status": "abandoned",
        }
    ]
    state["activeAutoResearch"] = {
        "stage": "download_plan",
        "status": "interrupted",
        "completedCount": 4,
    }
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="content_plan",
        reason="content plan scoring rule fixed",
    )

    assert report["reactivatedEntities"] == ["旧规则误判景区"]
    assert report["reactivatedContentRefs"] == ["旧规则误判景区_planning_consultation"]
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert [row["entityId"] for row in recovered["abandonedObjects"]] == ["上游失败景区"]
    assert recovered["abandonedContentObjects"][0]["status"] == "retrying"
    assert "activeAutoResearch" not in recovered

def test_download_plan_stale_source_rules_override_pending_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_stale_over_repair"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, object] = {}
    checks = iter([(False, ["download_repair required: old source_plan_gate"]), (True, [])])
    stale_checks = iter([
        [{"entityId": _EID, "sourcePlanMtimeNs": 1, "sourceRuleMtimeNs": 2}],
        [],
    ])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: next(stale_checks),
    )

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {"issues": [], "sourceUnavailable": []}

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": [_EID], "force": True}
    assert "过期 source_plan" in result.message
