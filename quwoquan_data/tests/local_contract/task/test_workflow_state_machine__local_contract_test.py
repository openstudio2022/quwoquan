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

def test_publish_anchor_pruning_rejects_managed_article_and_image_without_batch_homepage():
    task_id = _make_task()
    batch_id = "publish_anchor_prune_managed"
    _seed_publish_inputs(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.release_only = True

    missing_entity = "缺主页景区"
    mirror_entity_dir = task_data(task_id).entities_dir() / "地点" / "景区" / missing_entity
    mirror_entity_dir.mkdir(parents=True, exist_ok=True)
    (mirror_entity_dir / "page.md").write_text(f"# {missing_entity}\n\n仅存在于 task mirror。", encoding="utf-8")
    write_json(
        mirror_entity_dir / "_entity.json",
        {"entityRef": f"/entity/地点/景区/{missing_entity}", "label": missing_entity},
    )
    write_json(
        mirror_entity_dir / "manifest.json",
        {"entityRef": f"/entity/地点/景区/{missing_entity}", "tagRefs": ["景区"]},
    )

    article_ref = "missing-homepage-article"
    image_ref = "missing-homepage-image"
    content_object.register_content_object(
        task_id, batch_id, article_ref, content_type="article", angle="攻略", title="缺主页文章"
    )
    content_object.register_content_object(
        task_id, batch_id, image_ref, content_type="image", angle="画报", title="缺主页图片"
    )
    article_dir = content_object.content_object_dir(task_id, batch_id, article_ref)
    image_dir = content_object.content_object_dir(task_id, batch_id, image_ref)
    article_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    (article_dir / "article.md").write_text("# 缺主页文章\n\n成品不应进入 release。", encoding="utf-8")
    write_json(
        article_dir / "manifest.json",
        {
            "contentType": "article",
            "topicId": article_ref,
            "entityRefs": [f"/entity/地点/景区/{missing_entity}"],
            "tagRefs": ["景区"],
        },
    )
    write_json(
        image_dir / "manifest.json",
        {
            "contentType": "image",
            "carrier": "image",
            "topicId": image_ref,
            "entityRefs": [f"/entity/地点/景区/{missing_entity}"],
            "tagRefs": ["景区"],
            "assets": [],
        },
    )

    assert f"/entity/地点/景区/{missing_entity}" not in run_mod._publishable_homepage_refs(ctx)

    added = run_mod._abandon_publish_content_anchor_shortfalls(ctx)

    assert set(added) == {article_ref, image_ref}
    rows = run_mod.load_workflow_state(task_id, batch_id)["abandonedContentObjects"]
    reasons = {row["ref"]: row["reason"] for row in rows}
    assert "publish_content_anchor_unavailable_after_homepage_filter" in reasons[article_ref]
    assert "publish_content_anchor_unavailable_after_homepage_filter" in reasons[image_ref]
    assert not (article_dir / "manifest.json").exists()
    assert not (image_dir / "manifest.json").exists()


def test_publish_anchor_pruning_skips_image_only_batch_without_homepage_quota():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["content"]["quotas"]["entityHomepagesPerTarget"] = 0
    spec["content"]["quotas"]["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec["content"]["research"]["lanes"] = ["image"]
    spec["content"]["carriers"] = ["image"]
    store.save_spec(spec)

    batch_id = "publish_anchor_prune_image_only"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.release_only = True

    image_ref = "image-only-without-homepage"
    content_object.register_content_object(
        task_id, batch_id, image_ref, content_type="image", angle="画报", title="图片-only 内容"
    )
    image_dir = content_object.content_object_dir(task_id, batch_id, image_ref)
    image_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        image_dir / "manifest.json",
        {
            "contentType": "image",
            "carrier": "image",
            "topicId": image_ref,
            "entityRefs": ["/entity/地点/景区/测试图片景区"],
            "tagRefs": ["景区"],
            "assets": [],
        },
    )

    assert run_mod._workflow_requires_publish_anchor_pruning(ctx) is False
    assert run_mod._abandon_publish_content_anchor_shortfalls(ctx) == []
    assert (image_dir / "manifest.json").is_file()


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

def test_run_pipeline_clears_target_set_rerun_marker_on_success(monkeypatch):
    task_id = _make_task()
    batch_id = "clear_target_set_marker_on_success"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["targetSetRequiresRerunFrom"] = "download_fetch"
    state["targetSetInvalidatedStages"] = ["download_fetch"]
    run_mod.save_workflow_state(state)
    original_dag = run_mod.DAG
    original_stage_names = run_mod.STAGE_NAMES
    monkeypatch.setattr(
        run_mod,
        "DAG",
        [("publish", run_mod.AUTO, lambda _ctx: run_mod.StageResult("publish", run_mod.AUTO, "done", "ok"))],
    )
    monkeypatch.setattr(run_mod, "STAGE_NAMES", ["publish"])
    try:
        assert run_mod.run_pipeline(ctx) == 0
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)
        monkeypatch.setattr(run_mod, "STAGE_NAMES", original_stage_names)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "succeeded"
    assert "targetSetRequiresRerunFrom" not in state
    assert "targetSetInvalidatedStages" not in state


def test_run_pipeline_writes_execution_metrics_before_completion_gate_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "metrics_before_completion_gate_failure"
    ctx = _ctx(task_id, batch_id)
    original_dag = run_mod.DAG
    original_stage_names = run_mod.STAGE_NAMES

    def _fake_metrics(_ctx, state):
        state["throughput"] = {"objectsPerHour": 12.5}
        state["quality"] = {"firstPassRate": 1.0}

    monkeypatch.setattr(
        run_mod,
        "DAG",
        [("publish", run_mod.AUTO, lambda _ctx: run_mod.StageResult("publish", run_mod.AUTO, "done", "ok"))],
    )
    monkeypatch.setattr(run_mod, "STAGE_NAMES", ["publish"])
    monkeypatch.setattr(run_mod, "_write_workflow_execution_metrics", _fake_metrics)
    monkeypatch.setattr(run_mod, "_workflow_completion_issues", lambda _ctx, _state: ["forced gate failure"])
    try:
        assert run_mod.run_pipeline(ctx) == 1
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)
        monkeypatch.setattr(run_mod, "STAGE_NAMES", original_stage_names)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "manual_required"
    assert state["throughput"]["objectsPerHour"] == 12.5
    assert state["quality"]["firstPassRate"] == 1.0
    # gate issues 落独立字段，不得污染对象级 failedObjects（自嵌套根因）。
    assert state["completionGateIssues"] == ["forced gate failure"]
    assert state["failedObjects"] == []


def test_run_pipeline_clears_stale_failed_objects_when_all_stages_completed(monkeypatch):
    """completion gate 不得把历史 waiting 快照当未收口信号（H100 卡终态根因）。

    时序：某轮 build_homepage waiting 时把「采纳门未过项」写进 failedObjects
    并 rc=10 暂停；后续轮该 stage 收口标记 completed。最终轮 resume 时全部
    stage 都在 completed 集合里被跳过（不触发 done 路径的清空），DAG 落入
    completion gate —— 此时 failedObjects 必然是 stale 快照，不得据此把
    workflow 打成 manual_required（rc=1），否则 run-recipe resume 循环永远
    无法收口。同时 gate issues 不得写回 failedObjects 造成自嵌套污染。
    """
    task_id = _make_task()
    batch_id = "stale_failed_objects_completion"
    ctx = _ctx(task_id, batch_id)
    original_dag = run_mod.DAG
    original_stage_names = run_mod.STAGE_NAMES
    monkeypatch.setattr(
        run_mod,
        "DAG",
        [("publish", run_mod.AUTO, lambda _ctx: run_mod.StageResult("publish", run_mod.AUTO, "done", "ok"))],
    )
    monkeypatch.setattr(run_mod, "STAGE_NAMES", ["publish"])
    state = run_mod.load_workflow_state(task_id, batch_id)
    # 模拟历史 waiting 快照残留：stage 已收口进 completed，但 failedObjects 未清。
    state["completed"] = ["publish"]
    state["waitingCheckpoint"] = None
    state["failedObjects"] = [
        "地点/景区/黄龙: page.md 缺失",
        "地点/景区/武侯祠: manifest.json 缺失",
    ]
    run_mod.save_workflow_state(state)
    try:
        assert run_mod.run_pipeline(ctx) == 0
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)
        monkeypatch.setattr(run_mod, "STAGE_NAMES", original_stage_names)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "succeeded"
    assert state["failedObjects"] == []
    # stale 快照须留审计痕迹，不允许静默丢弃。
    assert state.get("staleFailedObjectsCleared")


def test_run_pipeline_marks_reasoned_reject_completion_without_gating_success_rate(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "elasticOverfetch": True,
            "allowQuotaShortfall": True,
            "allowContentQuotaShortfall": True,
            "allowMinEntityShortfall": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    batch_id = "completed_with_reasoned_rejects"
    ctx = _ctx(task_id, batch_id)
    run_mod.mark_abandoned_content_refs(
        task_id,
        batch_id,
        [f"{_EID}_article_shortfall_2"],
        stage="content_plan",
        reason="fixture article source shortfall",
    )
    original_dag = run_mod.DAG
    original_stage_names = run_mod.STAGE_NAMES
    monkeypatch.setattr(
        run_mod,
        "DAG",
        [("publish", run_mod.AUTO, lambda _ctx: run_mod.StageResult("publish", run_mod.AUTO, "done", "ok"))],
    )
    monkeypatch.setattr(run_mod, "STAGE_NAMES", ["publish"])
    try:
        assert run_mod.run_pipeline(ctx) == 0
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)
        monkeypatch.setattr(run_mod, "STAGE_NAMES", original_stage_names)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "completed_with_reasoned_rejects"
    assert state["abandonedContentObjects"][0]["ref"] == f"{_EID}_article_shortfall_2"


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
    assert state["managedInfraRecoveryCutoffs"]["build_homepage"]
    assert state["managedInfraRecoveryCutoffs"]["produce_author"]
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

def test_reset_stage_retries_reactivates_only_retryable_tail_stage_abandoned_objects():
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
        {
            "entityId": "桥接中断景区",
            "stage": "content_plan",
            "reason": "cursor bridge interrupted during content_plan",
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

    assert report["reactivatedEntities"] == ["桥接中断景区"]
    assert report["reactivatedContentRefs"] == ["旧规则误判景区_planning_consultation"]
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert [
        row["entityId"]
        for row in recovered["abandonedObjects"]
        if row.get("status") == "abandoned"
    ] == ["上游失败景区", "旧规则误判景区"]
    assert [
        row["entityId"]
        for row in recovered["abandonedObjects"]
        if row.get("status") == "retrying"
    ] == ["桥接中断景区"]
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

def _stale_infra_last_agent_run() -> dict:
    return {
        "stage": "build_homepage",
        "jobCount": 1,
        "startedCount": 0,
        "finishedCount": 0,
        "infrastructureFailures": 1,
        "refs": [],
        "outcomes": [
            {
                "started": False,
                "status": "error",
                "error": "Bridge request failed: ConnectError: Connection refused",
                "retryable": True,
            }
        ],
    }

def test_completion_gate_recovers_stale_infra_snapshot_when_checkpoint_reverified(monkeypatch):
    """收口 gate 的 lastAgentRun 复核契约（WP5 乐山沙湾/市中区实测根因）。

    时序：build_homepage 的 agent run 因 bridge 基础设施失败留下 refs=[] 失败
    快照；随后对象在其它 cycle 成功物化（或被 reasoned 放弃），stage 进入
    completed 集合后不再发起 agent run，快照永远不会被成功 run 覆盖。最终
    resume 落入 completion gate 时必须用快照所属 stage 的 checkpoint 复核：
    现在通过 → 标记 recovered 豁免，不得据陈旧快照打 manual_required。
    """
    task_id = _make_task()
    batch_id = "gate_recovers_stale_infra_snapshot"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["lastAgentRun"] = _stale_infra_last_agent_run()

    monkeypatch.setattr(run_mod, "_checkpoint_is_done", lambda _ctx, _stage: (True, []))

    issues = run_mod._workflow_completion_issues(ctx, state)

    assert issues == []
    recovered = state["lastAgentRun"]
    assert recovered["recovered"] is True
    assert "checkpoint re-verified" in recovered["recoveryReason"]

def test_completion_gate_keeps_infra_snapshot_issues_when_checkpoint_still_failing(monkeypatch):
    """复核不过（成品真实缺失）时，陈旧快照豁免不得放行。"""
    task_id = _make_task()
    batch_id = "gate_keeps_real_infra_failure"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["lastAgentRun"] = _stale_infra_last_agent_run()

    monkeypatch.setattr(
        run_mod,
        "_checkpoint_is_done",
        lambda _ctx, _stage: (False, ["实体主页 page.md 缺失"]),
    )

    issues = run_mod._workflow_completion_issues(ctx, state)

    assert "lastAgentRun.infrastructureFailures=1" in issues
    assert "lastAgentRun has jobs but no started workers" in issues
    assert not state["lastAgentRun"].get("recovered")
