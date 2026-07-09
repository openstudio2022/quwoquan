from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_cursor_bridge_startup_errors_are_retryable_infra():
    assert run_mod._cursor_bridge_error_is_retryable(
        "Bridge exited before discovery with status 1: "
        "cursor-sdk-bridge failed: Error: Missing value for --tool-callback-auth-token"
    )
    assert run_mod._cursor_bridge_error_is_retryable(
        "Bridge request failed: ConnectError: [Errno 61] Connection refused"
    )
    assert not run_mod._cursor_bridge_error_is_retryable("CURSOR_API_KEY missing")

def test_cursor_callback_token_factory_never_starts_with_dash():
    calls = iter(["-bad-token", "ok-token"])
    factory = run_mod._cursor_safe_auth_token_factory(lambda: next(calls))
    assert factory() == "qwq_bad-token"
    assert factory() == "ok-token"

def test_managed_lane_limits_are_configurable():
    assert run_mod._parse_managed_lane_limits("article:8,image=5,homepage:2") == {
        "homepage": 2,
        "article": 8,
        "image": 5,
    }
    assert run_mod._parse_managed_lane_limits("article:not-a-number,unknown:9") == {
        "homepage": 3,
        "article": 3,
        "image": 4,
    }

def test_managed_agent_default_timeout_covers_homepage_generation_long_tail():
    assert run_mod.MANAGED_AGENT_TIMEOUT_SECONDS >= 360

def test_managed_keyboard_interrupt_preserves_resumable_checkpoint_state(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_keyboard_interrupt_resumable"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    original_dag = run_mod.DAG
    original_stage_names = run_mod.STAGE_NAMES

    def _runner(_ctx):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["status"] = "repairing"
        state["waitingCheckpoint"] = "produce_author"
        state["failedObjects"] = ["produce_author: interrupted; resume will retry remaining agent job(s)"]
        state["lastAgentRun"] = {
            "stage": "produce_author",
            "status": "interrupted",
            "finishedCount": 1,
        }
        state["managedCheckpointInterruption"] = {
            "stage": "produce_author",
            "resumable": True,
            "finishedCount": 1,
        }
        run_mod.save_workflow_state(state)
        raise KeyboardInterrupt("workflow interrupted by signal 15")

    monkeypatch.setattr(
        run_mod,
        "DAG",
        [("produce_author", run_mod.CHECKPOINT, _runner)],
    )
    monkeypatch.setattr(run_mod, "STAGE_NAMES", ["produce_author"])
    try:
        try:
            run_mod.run_pipeline(ctx)
        except KeyboardInterrupt:
            pass
    finally:
        monkeypatch.setattr(run_mod, "DAG", original_dag)
        monkeypatch.setattr(run_mod, "STAGE_NAMES", original_stage_names)

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["waitingCheckpoint"] == "produce_author"
    assert state["managedCheckpointInterruption"]["resumable"] is True
    assert state["failedObjects"] == [
        "produce_author: interrupted; resume will retry remaining agent job(s)"
    ]
    assert state["interruptReason"] == "workflow interrupted by signal 15"

def test_managed_author_interrupt_keeps_partial_progress_resumable():
    task_id = _make_task()
    batch_id = "managed_author_interrupt_resumable"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.max_workers = 1

    shared_source = batch_root(task_id, batch_id) / "_shared/source.md"
    shared_source.parent.mkdir(parents=True, exist_ok=True)
    shared_source.write_text("测试景区甲的可核验来源。", encoding="utf-8")
    refs = ["已完成文章", "待恢复文章"]
    for ref in refs:
        content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
        write_writing_pack(
            task_id,
            batch_id,
            ref,
            {
                "carrier": "article",
                "sourcePaths": ["_shared/source.md"],
                "baseDraftText": _long_base_text(ref),
            },
        )
        prompt_path(task_id, batch_id, ref).parent.mkdir(parents=True, exist_ok=True)
        prompt_path(task_id, batch_id, ref).write_text(f"# prompt\n\n内容 ref: {ref}", encoding="utf-8")
        write_placeholder_draft(task_id, batch_id, ref)

    def _runner(prompt: str) -> dict[str, object]:
        ref = run_mod._managed_author_ref(prompt)
        if ref == "已完成文章":
            draft_article_path(task_id, batch_id, ref).write_text(
                "# 正文\n\n先说结论，这是一篇已经由 Agent 写回的正文。",
                encoding="utf-8",
            )
            write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "agent", "model": "cursor"})
            return {
                "started": True,
                "status": "finished",
                "runId": "run-before-interrupt",
                "agentId": "agent-before-interrupt",
            }
        raise KeyboardInterrupt("workflow interrupted by signal 15")

    ctx.agent_runner = _runner

    try:
        run_mod._run_managed_checkpoint(ctx, "produce_author")
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("expected managed checkpoint interruption")

    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["waitingCheckpoint"] == "produce_author"
    assert state["managedCheckpointInterruption"]["resumable"] is True
    assert state["lastAgentRun"]["status"] == "interrupted"
    assert state["lastAgentRun"]["finishedCount"] == 1
    assert state["lastAgentRun"]["plannedJobCount"] == 2
    assert state["lastAgentRun"]["refs"] == ["已完成文章"]
    assert "resume will retry remaining agent job" in state["nextAction"]
    meta = read_json(draft_meta_path(task_id, batch_id, "已完成文章"))
    assert meta["agentRunId"] == "run-before-interrupt"
    assert meta["agentId"] == "agent-before-interrupt"
    assert meta["promptSha256"].startswith("sha256:")
    assert meta["writingPackSha256"].startswith("sha256:")

def test_managed_author_finished_requires_real_draft_output():
    task_id = _make_task()
    batch_id = "managed_author_finished_without_draft"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    ref = "口头完成未落盘"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(task_id, batch_id, ref, {"carrier": "article", "sourcePaths": ["_shared/source.md"]})

    issues = run_mod._managed_checkpoint_job_issues(
        ctx,
        stage="produce_author",
        prompt=f"内容 ref: {ref}",
    )

    assert issues == [
        f"{ref}: agent finished but did not write {draft_article_path(task_id, batch_id, ref)}"
    ]

def test_managed_author_prompts_can_be_sliced_by_ref_limit(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_author_ref_limit"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    for idx in range(3):
        ref = f"待写{idx}"
        content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
        write_writing_pack(
            task_id,
            batch_id,
            ref,
            {
                "carrier": "article",
                "sourcePaths": ["_shared/source.md"],
                "baseDraftText": _long_base_text(ref),
                "sourceUseMode": "licensed_adaptation",
            },
        )
        write_placeholder_draft(task_id, batch_id, ref)
    monkeypatch.setenv("QWQ_MANAGED_CHECKPOINT_REF_LIMIT", "2")

    prompts = run_mod._checkpoint_prompts(ctx, "produce_author")

    assert len(prompts) == 2
    assert "内容 ref: 待写0" in prompts[0]
    assert "内容 ref: 待写1" in prompts[1]
    assert "严格以 prompt/writing_pack 的「底稿」为初稿骨架做轻编辑" in prompts[0]
    assert "成稿应保留至少 60% 的相关底稿原句群/三连字符覆盖" in prompts[0]
    assert "baseDraftFidelity 55%~99.5%" in prompts[0]
    assert "baseDraftFidelityStrategy" in prompts[0]
    assert "主实体硬合同" in prompts[0]
    assert "「待写0」" in prompts[0]
    assert "正文必须至少自然出现一次完整主实体名称" in prompts[0]
    assert "去过…之后" in prompts[0]
    assert "普通网页只取事实" not in prompts[0]

def test_managed_author_prompt_for_factual_reference_uses_base_draft_contract(monkeypatch):
    """产品裁定 full light-edit：factual_reference_only 与 licensed 同走底稿轻改合同。"""
    task_id = _make_task()
    batch_id = "managed_author_factual_ref"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    ref = "事实引用文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {
            "carrier": "article",
            "sourcePaths": ["_shared/source.md"],
            "baseDraftText": _long_base_text(ref),
            "sourceUseMode": "factual_reference_only",
        },
    )
    write_placeholder_draft(task_id, batch_id, ref)

    prompts = run_mod._checkpoint_prompts(ctx, "produce_author")

    assert len(prompts) == 1
    assert "严格以 prompt/writing_pack 的「底稿」为初稿骨架做轻编辑" in prompts[0]
    assert "成稿应保留至少 60% 的相关底稿原句群/三连字符覆盖" in prompts[0]
    assert "baseDraftFidelity 55%~99.5%" in prompts[0]
    assert "baseDraftFidelityStrategy" in prompts[0]

def test_managed_loop_consumes_checkpoint_instead_of_returning_10():
    task_id = _make_task()
    ctx = _ctx(task_id, "managed1")
    ctx.managed = True
    calls = {"pipeline": 0, "checkpoint": 0}
    original_pipeline = run_mod.run_pipeline
    original_checkpoint = run_mod._run_managed_checkpoint
    try:
        def _fake_pipeline(_ctx):
            calls["pipeline"] += 1
            if calls["pipeline"] == 1:
                state = run_mod.load_workflow_state(task_id, "managed1")
                state["waitingCheckpoint"] = "download_plan"
                run_mod.save_workflow_state(state)
                return 10
            return 0

        def _fake_checkpoint(_ctx, stage):
            calls["checkpoint"] += 1
            assert stage == "download_plan"
            return True

        run_mod.run_pipeline = _fake_pipeline
        run_mod._run_managed_checkpoint = _fake_checkpoint
        assert run_mod.run_managed_pipeline(ctx) == 0
    finally:
        run_mod.run_pipeline = original_pipeline
        run_mod._run_managed_checkpoint = original_checkpoint
    assert calls == {"pipeline": 2, "checkpoint": 1}

def test_managed_loop_continues_when_infra_fails_but_checkpoint_gate_passes(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_infra_gate_passes"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)
    calls = {"pipeline": 0, "checkpoint": 0}

    def _fake_pipeline(_ctx):
        calls["pipeline"] += 1
        if calls["pipeline"] == 1:
            state = run_mod.load_workflow_state(task_id, batch_id)
            state["waitingCheckpoint"] = "download_plan"
            run_mod.save_workflow_state(state)
            return 10
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["waitingCheckpoint"] = None
        state["completed"] = list(run_mod.STAGE_NAMES)
        state["status"] = "succeeded"
        state["failedObjects"] = []
        run_mod.save_workflow_state(state)
        return 0

    def _fake_checkpoint(_ctx, stage):
        calls["checkpoint"] += 1
        assert stage == "download_plan"
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [
                {
                    "started": False,
                    "status": "error",
                    "error": "agent subprocess timed out after 240s",
                }
            ],
        }
        state["failedObjects"] = ["agent subprocess timed out after 240s"]
        run_mod.save_workflow_state(state)
        return False

    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (True, []))
    monkeypatch.setattr(
        "task.target_selection.audit_managed_batch",
        lambda *_args, **_kwargs: {
            "failedLaneCount": 0,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "targetCount": 1,
        },
    )

    assert run_mod.run_managed_pipeline(ctx) == 0
    assert calls == {"pipeline": 2, "checkpoint": 1}
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert final_state["failedObjects"] == []
    assert "checkpoint gate passed" in final_state["nextAction"]
    assert final_state["lastAgentRun"]["recovered"] is True
    assert run_mod._workflow_completion_issues(ctx, final_state) == []

def test_managed_no_start_infra_failures_count_from_agent_history_when_counter_stale():
    state = {
        "infrastructureRetryCounts": {"produce_author": 1},
        "agentRunHistory": [
            {
                "stage": "produce_author",
                "startedCount": 0,
                "finishedCount": 0,
                "infrastructureFailures": 1,
            },
            {
                "stage": "produce_author",
                "startedCount": 0,
                "finishedCount": 0,
                "infrastructureFailures": 1,
            },
        ],
        "lastAgentRun": {
            "stage": "produce_author",
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
        },
    }

    assert run_mod._managed_consecutive_no_start_infra_failures(
        state,
        stage="produce_author",
    ) == 3

def test_managed_no_start_infra_failures_respect_recovery_cutoff():
    state = {
        "managedInfraRecoveryCutoffs": {
            "produce_author": "2026-07-01T00:02:00+00:00",
        },
        "agentRunHistory": [
            {
                "stage": "produce_author",
                "startedCount": 0,
                "finishedCount": 0,
                "infrastructureFailures": 1,
                "finishedAt": "2026-07-01T00:01:00+00:00",
            },
            {
                "stage": "produce_author",
                "startedCount": 0,
                "finishedCount": 0,
                "infrastructureFailures": 1,
                "finishedAt": "2026-07-01T00:03:00+00:00",
            },
        ],
        "lastAgentRun": {
            "stage": "produce_author",
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "finishedAt": "2026-07-01T00:04:00+00:00",
        },
    }

    assert run_mod._managed_consecutive_no_start_infra_failures(
        state,
        stage="produce_author",
    ) == 2

def test_managed_default_cursor_model_uses_single_current_default():
    ctx = run_mod.PipelineContext(task_id="t", batch_id="b", entity_ids=[], spec={})
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    run_mod.register_run_parser(sub)

    parsed = parser.parse_args(["run"])

    assert run_mod.DEFAULT_CURSOR_AGENT_MODEL == "composer"
    assert ctx.model == run_mod.DEFAULT_CURSOR_AGENT_MODEL
    assert parsed.model is None
    assert run_mod._resolve_managed_model("cursor_sdk", parsed.model) == run_mod.DEFAULT_CURSOR_AGENT_MODEL
    assert run_mod._resolve_managed_model("codex_cli", parsed.model) == run_mod.DEFAULT_CODEX_AGENT_MODEL

def test_codex_cli_agent_runner_uses_codex_exec_without_cursor_model(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(run_mod.shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)

    class _FakePopen:
        returncode = 0
        pid = 12345

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["kwargs"] = dict(kwargs)
            self._output_path = Path(cmd[cmd.index("--output-last-message") + 1])

        def communicate(self, input=None, timeout=None):
            captured["input"] = input
            captured["timeout"] = timeout
            self._output_path.write_text("codex wrote files", encoding="utf-8")
            return "", ""

    monkeypatch.setattr(run_mod.subprocess, "Popen", _FakePopen)
    ctx = run_mod.PipelineContext(
        task_id="t",
        batch_id="b",
        entity_ids=[],
        spec={},
        agent_provider="codex_cli",
        model="",
    )

    outcome = run_mod._default_codex_cli_agent_runner(ctx, "写入指定 draft 文件")

    assert outcome["status"] == "finished"
    assert outcome["started"] is True
    assert outcome["agentProvider"] == "codex_cli"
    assert "--model" not in captured["cmd"]
    assert captured["input"] == "写入指定 draft 文件"
    assert captured["kwargs"]["start_new_session"] is True

def test_managed_download_infra_failure_cannot_abandon_strict_task(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_strict_infra_no_abandon"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)

    def _fake_pipeline(_ctx):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["waitingCheckpoint"] = "download_plan"
        run_mod.save_workflow_state(state)
        return 10

    def _fake_checkpoint(_ctx, stage):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [{"started": False, "status": "error", "error": "internal error"}],
        }
        run_mod.save_workflow_state(state)
        return False

    unresolved = {_EID: {"article": ["article research needs >= 4 text-qualified base sources"]}}
    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: unresolved)

    assert run_mod.run_managed_pipeline(ctx) == 1
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert final_state["status"] == "manual_required"
    assert final_state.get("abandonedObjects") == []
    assert "allowPartialContent is not true" in final_state["failedObjects"][0]

def test_managed_download_infra_failure_can_fast_fail_partial_task(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"].append({"entityType": "地点/景区", "name": "测试景区乙"})
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    store.save_spec(spec)
    batch_id = "managed_partial_infra_abandon"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)
    calls = {"pipeline": 0}

    def _fake_pipeline(_ctx):
        calls["pipeline"] += 1
        if calls["pipeline"] == 1:
            state = run_mod.load_workflow_state(task_id, batch_id)
            state["waitingCheckpoint"] = "download_plan"
            run_mod.save_workflow_state(state)
            return 10
        return 0

    def _fake_checkpoint(_ctx, stage):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [{"started": False, "status": "error", "error": "internal error"}],
        }
        run_mod.save_workflow_state(state)
        return False

    unresolved = {_EID: {"article": ["article research needs >= 4 text-qualified base sources"]}}

    def _screen(current_ctx, *, entity_type, reason, needed, scope):
        del entity_type, reason, needed, scope
        run_mod._append_replacement_row(
            current_ctx,
            entity_id="替补景区丙",
            entity_type="地点/景区",
            status="active",
            reason="test gated replacement passed",
            source_gate_status="passed",
        )
        if "替补景区丙" not in current_ctx.entity_ids:
            current_ctx.entity_ids.append("替补景区丙")
        return ["替补景区丙"], [], {}

    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: unresolved)
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    assert run_mod.run_managed_pipeline(ctx) == 0
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in final_state["abandonedObjects"]] == [_EID]
    assert "fast-failing source-unavailable" in final_state["nextAction"]
    active_rows = [
        item
        for item in final_state["replacementObjects"]
        if item.get("status") == "active"
    ]
    assert [item["entityId"] for item in active_rows] == ["替补景区丙"]
    assert [item.get("sourceGateStatus") for item in active_rows] == ["passed"]

def test_run_download_auto_research_managed_local_pauses_after_one_wave_and_appends(monkeypatch):
    import download.research_plan as research_mod

    task_id = _make_task(workflow_policy={"autoResearchWaveSize": 1})
    batch_id = "auto_research_managed_local_partial"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.runtime = "local"
    ctx.max_workers = 3
    calls: list[list[str]] = []

    def _fake_write_auto_research_plans(
        task: str,
        batch: str,
        entity_ids: list[str],
        *,
        entity_type: str,
        force: bool = False,
        lanes=None,
        max_workers: int = 1,
        progress_callback=None,
    ) -> dict:
        del task, batch, entity_type, force, lanes, max_workers, progress_callback
        calls.append(list(entity_ids))
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
                "maxWorkers": 1,
                "entityCount": 1,
                "elapsedSeconds": 1,
                "entitiesPerMinute": 60,
            },
        }

    monkeypatch.setattr(research_mod, "write_auto_research_plans", _fake_write_auto_research_plans)

    report = run_mod._run_download_auto_research(
        ctx,
        ["测试景区甲", "测试景区乙", "测试景区丙"],
        entity_type="景区",
        scope="primary",
    )

    assert calls == [["测试景区甲"]]
    assert report["partialRun"] is True
    assert report["remainingEntityIds"] == ["测试景区乙", "测试景区丙"]
    assert report["waveCount"] == 1

    report = run_mod._run_download_auto_research(
        ctx,
        ["测试景区乙", "测试景区丙"],
        entity_type="景区",
        force=True,
        scope="primary",
    )

    assert calls == [["测试景区甲"], ["测试景区乙"]]
    assert report["waveCount"] == 2
    assert [wave["scope"] for wave in report["waves"]] == ["primary", "primary_wave_2"]
    assert report["sourceAvailability"]["readyTargets"] == ["测试景区甲", "测试景区乙"]

def test_real_local_cursor_runner_defaults_to_requested_workers(monkeypatch):
    task_id = _make_task()
    ctx = _ctx(task_id, "managed_cursor_workers")
    ctx.runtime = "local"
    ctx.max_workers = 10
    ctx.agent_runner = None
    monkeypatch.setattr("task.run.MANAGED_LOCAL_CURSOR_MAX_WORKERS", None)
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 5
    monkeypatch.setattr("task.run.MANAGED_LOCAL_CURSOR_MAX_WORKERS", 2)
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 2
    monkeypatch.setattr("task.run.MANAGED_LOCAL_CURSOR_MAX_WORKERS", 1)
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 1

    ctx.agent_runner = lambda _prompt: {"started": True, "status": "finished"}
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 5

def test_managed_download_job_must_satisfy_lane_gate():
    task_id = _make_task()
    batch_id = "managed_download_lane_gate"
    ctx = _ctx(task_id, batch_id)
    assert run_mod.run_pipeline(ctx) == 10

    calls = []

    def _fake_finished_without_output(prompt: str) -> dict:
        calls.append(prompt)
        return {"started": True, "status": "finished", "result": "done"}

    ctx.agent_runner = _fake_finished_without_output
    ctx.max_workers = 1
    ok = run_mod._run_managed_checkpoint(ctx, "download_plan")
    assert ok is False
    assert calls
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["lastAgentRun"]["plannedJobCount"] == len(calls)
    assert state["lastAgentRun"]["jobCount"] == len(calls)
    failed_outcomes = [
        outcome for outcome in state["lastAgentRun"]["outcomes"]
        if outcome.get("status") == "error"
    ]
    assert failed_outcomes
    for outcome in failed_outcomes:
        assert outcome["started"] is True
        assert "checkpoint lane gate still fails" in outcome["error"]
        assert outcome["gateIssues"]

def test_managed_pipeline_recovers_stale_controller_yield(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_controller_yield"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "download_plan"
    state["controllerYield"] = {
        "stage": "download_plan",
        "reason": "download_plan auto research partial wave completed",
    }
    run_mod.save_workflow_state(state)

    pipeline_codes = iter([10, 10, 0])
    checkpoint_calls: list[str] = []
    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: next(pipeline_codes))

    def _checkpoint(_ctx, stage):
        checkpoint_calls.append(stage)
        return True

    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", _checkpoint)

    assert run_mod.run_managed_pipeline(ctx) == 0
    assert checkpoint_calls == ["download_plan"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert "controllerYield" not in state
    assert state["controllerYieldRecoveryActions"]

def test_managed_pipeline_yields_after_ref_slice(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_slice_yield"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "produce_author"
    state["status"] = "waiting_agent"
    run_mod.save_workflow_state(state)

    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: 10)

    def _finish_slice(_ctx, _stage):
        current = run_mod.load_workflow_state(task_id, batch_id)
        current["controllerYield"] = {
            "stage": "produce_author",
            "reason": "managed ref slice completed",
        }
        run_mod.save_workflow_state(current)
        return True

    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", _finish_slice)

    assert run_mod.run_managed_pipeline(ctx) == 10

def test_managed_pipeline_clears_retry_budget_after_author_partial_progress(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_author_retry_budget_partial_progress"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "produce_author"
    state["status"] = "manual_required"
    state["retryCounts"] = {"produce_author": run_mod.MAX_REACT_REWINDS}
    state["lastAgentRun"] = {
        "stage": "produce_author",
        "finishedCount": 1,
        "outcomes": [
            {"ref": "已完成文章", "status": "finished"},
            {"ref": "待恢复文章", "status": "error", "error": "agent status=error"},
        ],
    }
    run_mod.save_workflow_state(state)
    called = {"checkpoint": 0}

    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: 10)

    def _finish_slice(_ctx, _stage):
        called["checkpoint"] += 1
        current = run_mod.load_workflow_state(task_id, batch_id)
        current["controllerYield"] = {
            "stage": "produce_author",
            "reason": "managed ref slice completed",
        }
        run_mod.save_workflow_state(current)
        return True

    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", _finish_slice)

    assert run_mod.run_managed_pipeline(ctx) == 10
    assert called["checkpoint"] == 1
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["retryCounts"] == {}
    assert recovered["failedObjects"] == ["待恢复文章"]

def test_managed_pipeline_yields_after_author_partial_progress_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_author_partial_failure_yield"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "produce_author"
    state["status"] = "waiting_agent"
    state["retryCounts"] = {"produce_author": 1}
    run_mod.save_workflow_state(state)

    monkeypatch.setenv("QWQ_MANAGED_YIELD_AFTER_REF_SLICE", "1")
    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: 10)

    def _partial_failure(_ctx, _stage):
        current = run_mod.load_workflow_state(task_id, batch_id)
        current["lastAgentRun"] = {
            "stage": "produce_author",
            "plannedJobCount": 2,
            "finishedCount": 1,
            "infrastructureFailures": 0,
            "outcomes": [
                {"ref": "已完成文章", "status": "finished"},
                {"ref": "待恢复文章", "status": "error", "error": "agent status=error"},
            ],
        }
        current["status"] = "repairing"
        run_mod.save_workflow_state(current)
        return False

    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", _partial_failure)

    assert run_mod.run_managed_pipeline(ctx) == 10
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["retryCounts"] == {}
    assert recovered["failedObjects"] == ["待恢复文章"]
    assert recovered["controllerYield"]["reason"] == "managed ref slice partially completed"
    assert "finished=1" in recovered["nextAction"]

def test_managed_pipeline_blocks_before_rerun_when_author_no_start_budget_exhausted(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": False})
    batch_id = "managed_author_no_start_budget_precheck"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ref = "未启动文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {
            "carrier": "article",
            "sourcePaths": ["_shared/source.md"],
            "baseDraftText": _long_base_text(ref),
        },
    )
    write_placeholder_draft(task_id, batch_id, ref)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "produce_author"
    state["agentRunHistory"] = [
        {
            "stage": "produce_author",
            "plannedJobCount": 1,
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "finishedAt": f"2026-07-01T00:0{idx}:00+00:00",
        }
        for idx in range(1, run_mod.MAX_MANAGED_INFRA_RETRIES + 1)
    ]
    run_mod.save_workflow_state(state)
    called = {"checkpoint": 0}

    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: 10)

    def _checkpoint(_ctx, _stage):
        called["checkpoint"] += 1
        return False

    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", _checkpoint)

    assert run_mod.run_managed_pipeline(ctx) == 1
    assert called["checkpoint"] == 0
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "manual_required"
    assert recovered["failedObjects"] == [
        f"produce_author:{ref}: infrastructure did not start"
    ]

def test_managed_author_infra_failure_never_abandons_partial_content_refs(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "managed_author_no_start_partial_still_blocks"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ref = "部分内容也不能因基础设施弃稿"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {
            "carrier": "article",
            "sourcePaths": ["_shared/source.md"],
            "baseDraftText": _long_base_text(ref),
        },
    )
    write_placeholder_draft(task_id, batch_id, ref)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "produce_author"
    state["agentRunHistory"] = [
        {
            "stage": "produce_author",
            "plannedJobCount": 1,
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "finishedAt": f"2026-07-01T00:0{idx}:00+00:00",
        }
        for idx in range(1, run_mod.MAX_MANAGED_INFRA_RETRIES + 1)
    ]
    run_mod.save_workflow_state(state)

    monkeypatch.setattr(run_mod, "run_pipeline", lambda _ctx: 10)
    monkeypatch.setattr(run_mod, "_run_managed_checkpoint", lambda _ctx, _stage: False)

    assert run_mod.run_managed_pipeline(ctx) == 1
    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "manual_required"
    assert recovered.get("abandonedContentObjects") in (None, [])
    assert recovered["failedObjects"] == [
        f"produce_author:{ref}: infrastructure did not start"
    ]

def test_managed_checkpoint_continues_after_one_job_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_partial_failure_continues"
    ctx = _ctx(task_id, batch_id)
    prompts = ["job-a", "job-b", "job-c"]
    calls: list[str] = []

    monkeypatch.setattr("task.run._checkpoint_prompts", lambda _ctx, stage: prompts if stage == "content_plan" else [])
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, ["content_plan still incomplete"]))

    def _runner(prompt: str) -> dict:
        calls.append(prompt)
        if prompt == "job-a":
            return {"started": True, "status": "error", "error": "deterministic bad object"}
        return {"started": True, "status": "finished", "result": "ok"}

    ctx.agent_runner = _runner
    ctx.max_workers = 3
    ok = run_mod._run_managed_checkpoint(ctx, "content_plan")
    assert ok is False
    assert sorted(calls) == sorted(prompts)
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["lastAgentRun"]["plannedJobCount"] == 3
    assert state["lastAgentRun"]["jobCount"] == 3
    assert state["lastAgentRun"]["finishedCount"] == 2
    assert state["lastAgentRun"]["scheduler"]["requestedMaxWorkers"] == 3
    assert state["lastAgentRun"]["scheduler"]["effectiveWorkerCount"] == 3
    assert state["lastAgentRun"]["scheduler"]["estimatedMinWaves"] == 1
    assert state["agentRunHistory"][-1]["scheduler"]["effectiveWorkerCount"] == 3
    assert all("timing" in outcome for outcome in state["lastAgentRun"]["outcomes"])
    assert state["failedObjects"] == ["deterministic bad object"]

def test_local_cursor_worker_cap_backs_off_after_infrastructure_failure():
    task_id = _make_task()
    batch_id = "managed_worker_backoff"
    ctx = _ctx(task_id, batch_id)
    ctx.runtime = "local"
    ctx.max_workers = 4
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["lastAgentRun"] = {
        "stage": "produce_author",
        "infrastructureFailures": 2,
        "scheduler": {"effectiveWorkerCount": 4},
    }
    run_mod.save_workflow_state(state)

    assert run_mod._managed_local_cursor_worker_cap(ctx) == 2

def test_managed_agent_subprocess_cleanup_clears_registered_pids(monkeypatch):
    with run_mod._MANAGED_AGENT_SUBPROCESS_LOCK:
        run_mod._MANAGED_AGENT_SUBPROCESS_PIDS.clear()
    calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(
        run_mod.os,
        "killpg",
        lambda pid, sig: calls.append(("killpg", pid, sig)),
    )

    def _gone(_pid, _sig):
        raise OSError("gone")

    monkeypatch.setattr(run_mod.os, "kill", _gone)

    run_mod._register_managed_agent_subprocess(12345)
    terminated = run_mod._terminate_managed_agent_subprocesses()

    assert terminated == [12345]
    assert calls == [("killpg", 12345, run_mod.signal.SIGTERM)]
    with run_mod._MANAGED_AGENT_SUBPROCESS_LOCK:
        assert run_mod._MANAGED_AGENT_SUBPROCESS_PIDS == set()
