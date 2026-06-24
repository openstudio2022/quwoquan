from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_source_plan_filled_does_not_block_discovery_platform_name_when_rights_complete():
    task_id = _make_task()
    batch_id = "discovery_platform_asset_rights"
    _seed_source_plan(task_id, batch_id)
    obj = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    image_plan = read_json(obj / STAGE_DOWNLOAD / "image_source_plan.json")
    for collection in image_plan["payload"]["collections"]:
        collection["platform"] = "Pinterest"
        collection["collectionPageUrl"] = "https://example.com/original-author-gallery"
        collection["authorizationProof"] = "https://example.com/original-author-license"
        for image in collection["images"]:
            image["platform"] = "Pinterest"
            image["sourceUrl"] = "https://example.com/original-file"
    write_json(obj / STAGE_DOWNLOAD / "image_source_plan.json", image_plan)

    ok, issues = run_mod._source_plan_filled(_ctx(task_id, batch_id))

    assert ok is True, issues

def test_active_spec_preserves_min_entities_when_target_shortfall():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["acceptance"] = {"minEntities": 2}
    store.save_spec(spec)
    batch_id = "active_spec_preserves_min_entities"
    ctx = _ctx(task_id, batch_id)
    run_mod.mark_abandoned_entities(
        task_id,
        batch_id,
        [_EID],
        stage="download_plan",
        reason="source unavailable",
    )

    active_spec = run_mod._active_spec(ctx)

    assert [
        target["name"]
        for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
    ] == ["稳定景区乙"]
    assert active_spec["acceptance"]["minEntities"] == 2

def test_download_plan_repair_unresolved_becomes_deterministic_after_fetch_rewind():
    task_id = _make_task()
    batch_id = "download_plan_repair_exhausted"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    unresolved = {
        _EID: {
            "homepage": [
                (
                    "download_repair required: 地点/景区/测试景区甲/1.download/sources: "
                    "homepage retained sources=0 need>=1 (homepage lane must yield a readable encyclopedia/wiki/official source unit)"
                )
            ]
        }
    }

    exhausted = run_mod._download_plan_repair_exhausted_unresolved(ctx, unresolved)

    assert exhausted == unresolved

def test_source_plan_filled_ignores_stale_download_repair_without_batch_gate(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "source_plan_filled_clears_stale_download_repair"
    ctx = _ctx(task_id, batch_id)
    repair_path = batch_root(task_id, batch_id) / "_shared" / "download_repair.json"
    write_json(
        repair_path,
        {
            "entities": [
                {
                    "entityId": "不在当前作用域",
                    "status": "pending",
                    "issues": ["stale repair"],
                }
            ]
        },
    )

    def _unexpected_gate(*_args, **_kwargs):
        raise AssertionError("stale repair cleanup must not run batch download gate")

    monkeypatch.setattr("download.gate.gate_download", _unexpected_gate)

    ok, missing = run_mod._source_plan_filled(ctx)

    assert ok is False
    assert missing
    assert repair_path.exists()

def test_stale_source_plan_uses_entity_scoped_signature(monkeypatch):
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_signature_scoped_stale"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    etype = "地点/景区"
    for entity_id in ctx.entity_ids:
        dl = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=etype) / STAGE_DOWNLOAD
        dl.mkdir(parents=True, exist_ok=True)
        signature_hash = "old" if entity_id == _EID else "current"
        for lane in ("homepage", "article", "image"):
            write_json(
                dl / f"{lane}_source_plan.json",
                {
                    "taskId": task_id,
                    "batchId": batch_id,
                    "ref": entity_id,
                    "sourceRuleSignature": {"hash": signature_hash},
                    "payload": {"entityId": entity_id, "researchLane": lane},
                },
            )

    monkeypatch.setattr(
        "task.run.source_plan_rule_signature",
        lambda _vertical, entity_id: {"hash": "old" if entity_id == "unrelated" else "current"},
    )

    stale = run_mod._stale_source_plan_entities(ctx, entity_ids=ctx.entity_ids)
    assert [item["entityId"] for item in stale] == [_EID]
    assert stale[0]["sourcePlanRuleState"] == "signature_stale"

def test_download_plan_hint_uses_full_unresolved_entities(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_full_unresolved_hint"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]

    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, [f"{_EID}: article sources=1 need>=2"]),
    )
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {
            _EID: {"article": ["article sources=1 need>=2"]},
            "额外景区乙": {"article": ["article sources=0 need>=2"]},
        },
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "waiting"
    assert _EID in result.checkpoint_hint
    assert "额外景区乙" in result.checkpoint_hint
    availability = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert availability["ineligibleTargetCount"] == 2

def test_download_repair_requires_source_plan_update_before_resume():
    task_id = _make_task()
    batch_id = "download_repair1"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: only 1 retained source; only 1 unique publishable image"],
    )
    repair = read_json(repair_path)
    assert repair["schemaVersion"] == "quwoquan.download_repair"
    assert repair["entities"][0]["downloadDiagnostics"]["entityId"] == _EID
    assert any(
        hint["action"] == "add_or_replace_image_source_collections_with_complete_rights"
        for hint in repair["entities"][0]["imageRepairHints"]
    )
    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("download_repair required" in issue for issue in issues), issues
    availability = run_mod._write_download_plan_availability(ctx, {})
    assert availability["readyTargets"] == []
    assert availability["ineligibleTargets"][0]["entityId"] == _EID
    assert "image" in availability["ineligibleTargets"][0]["lanes"]
    persisted = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert persisted["ineligibleTargets"][0]["entityId"] == _EID

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "image_source_plan.json"
    )
    current = plan_path.stat().st_mtime_ns
    os.utime(plan_path, ns=(current + 1_000_000_000, current + 1_000_000_000))
    assert run_mod._source_plan_filled(ctx)[0] is True
    assert repair_path.exists()
    assert run_mod._download_retry_entity_ids(ctx) == [_EID]

def test_download_retry_ignores_prefetch_missing_sources_without_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "download_retry_prefetch_missing_sources"
    ctx = _ctx(task_id, batch_id)
    assert not run_mod._download_repair_path(ctx).exists()

    monkeypatch.setattr(
        "download.gate.gate_download",
        lambda _task, _batch, target_entities=None: [
            f"地点/景区/{_EID}/1.download/sources: sources directory missing"
        ],
    )

    assert run_mod._download_retry_entity_ids(ctx) == []

def test_download_repair_fetch_only_image_failure_retries_fetch_before_agent():
    task_id = _make_task()
    batch_id = "download_repair_fetch_only_image_retry"
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
    repair_path = run_mod._download_repair_path(ctx)
    repair_entity = {
        "entityId": _EID,
        "issues": [
            f"{_EID}: imageCount: {_EID} 仅下到 0 张合格去重图（规模化任务要求 ≥3）",
            f"{_EID}: imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)",
        ],
        "sourcePlanPath": str(plan_paths[0]),
        "sourcePlanPaths": [str(path) for path in plan_paths],
        "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
        "fetchRetryCount": 0,
        "downloadDiagnostics": {
            "entityId": _EID,
            "plannedImages": 5,
            "downloadedImages": 0,
            "rejectedByCategory": {
                "fetch_or_non_image": 5,
                "rights": 0,
                "safety_or_watermark": 0,
                "duplicate": 0,
            },
        },
        "researchLaneIssues": {},
        "imageRepairHints": [
            {
                "lane": "image",
                "issue": "imageFetch failed/non-image/too small",
                "action": "replace_unfetchable_or_low_quality_image",
            }
        ],
    }
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [repair_entity],
        },
    )

    assert run_mod._source_plan_filled(ctx)[0] is True
    assert run_mod._checkpoint_prompts(ctx, "download_plan") == []
    assert run_mod._download_retry_entity_ids(ctx) == [_EID]

    repair_entity["fetchRetryCount"] = 1
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [repair_entity],
        },
    )
    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("download_repair required" in issue for issue in issues), issues
    unresolved = run_mod._download_plan_unresolved_entities(ctx)
    assert _EID in unresolved
    assert "image" in unresolved[_EID]
    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    assert any("[AGENT_LANE:image]" in prompt for prompt in prompts)

def test_download_fetch_preserves_nonzero_handler_stage_gate_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "download_stage_gate_failure"
    ctx = _ctx(task_id, batch_id)
    ensure_batch_layout(task_id, batch_id, "download")
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="image_fetch",
        ref=_EID,
        passed=False,
        issues=["imageCount: only 1 publishable image"],
        evidence_summary={},
        fallback_stage="source_plan",
    )

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _raise_nonzero(_args):
        raise SystemExit(1)

    monkeypatch.setattr("download.handler.handle_download", _raise_nonzero)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "failed"
    assert "imageCount: only 1 publishable image" in result.message
    repair = read_json(run_mod._download_repair_path(ctx))
    assert repair["entities"][0]["entityId"] == _EID
    assert "imageCount: only 1 publishable image" in repair["entities"][0]["issues"][0]

def test_download_repair_records_only_entity_scoped_issues():
    task_id = _make_task()
    batch_id = "download_repair_entity_scoped"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "无关景区乙"]
    issues = [
        f"{_EID}: imageCount: {_EID} 仅下到 2 张合格去重图（规模化任务要求 ≥3）",
        "batch diagnostic: source_screen worker completed",
    ]

    path = run_mod._record_download_repair(ctx, issues)
    repair = read_json(path)
    assert [row["entityId"] for row in repair["entities"]] == [_EID]
    assert repair["entities"][0]["issues"] == [issues[0]]

def test_pending_download_repair_ignores_stale_cross_entity_issues():
    task_id = _make_task()
    batch_id = "download_repair_stale_cross_entity"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "无关景区乙"]
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": "无关景区乙",
                    "issues": [
                        f"{_EID}: imageCount: {_EID} 仅下到 1 张合格图（要求 ≥2）"
                    ],
                    "sourcePlanMtimeNs": 0,
                    "imageRepairHints": [{"lane": "image", "issue": "stale cross entity"}],
                }
            ],
        },
    )

    assert run_mod._pending_download_repair_unresolved(ctx) == {}

def test_pending_download_repair_ignores_stale_source_category_rule_issue():
    task_id = _make_task()
    batch_id = "download_repair_stale_source_category_rule"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: missing core source categories ['travelogue']"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "article",
                            "entityId": _EID,
                            "issue": f"{_EID}: missing core source categories ['travelogue']",
                        }
                    ],
                }
            ],
        },
    )

    assert run_mod._pending_download_repair_unresolved(ctx) == {}
    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    assert not any("download_repair" in prompt for prompt in prompts)

def test_source_plan_filled_ignores_stale_cross_entity_download_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "source_plan_ignores_stale_cross_repair"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        "无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "image",
                            "entityId": _EID,
                            "issue": "无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）",
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "download.gate.gate_download",
        lambda *_args, **_kwargs: ["无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）"],
    )

    ok, issues = run_mod._source_plan_filled(ctx)

    assert ok is True
    assert issues == []

def test_pending_download_repair_is_scoped_to_context_entities():
    task_id = _make_task()
    batch_id = "download_repair_scoped_to_context"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: missing core source categories ['encyclopedia']"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "homepage",
                            "entityId": _EID,
                            "issue": f"{_EID}: missing core source categories ['encyclopedia']",
                        }
                    ],
                }
            ],
        },
    )

    scoped = copy.copy(ctx)
    scoped.entity_ids = ["替补候选景区"]
    assert run_mod._pending_download_repair_unresolved(scoped) == {}

def test_download_fetch_passes_ctx_max_workers_to_handler(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_workers"
    ctx = _ctx(task_id, batch_id)
    ctx.max_workers = 7
    captured: dict[str, int] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _fake_download(args):
        captured["max_workers"] = int(args.max_workers)

    monkeypatch.setattr("download.handler.handle_download", _fake_download)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["max_workers"] == 7

def test_download_fetch_scopes_single_lane_pending_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_lane_scope"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, str] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])
    monkeypatch.setattr(
        "task.run._pending_download_repair_unresolved",
        lambda _ctx: {_EID: {"homepage": ["homepage retained sources=0 need>=1"]}},
    )
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _fake_download(args):
        captured["lane"] = str(args.lane)

    monkeypatch.setattr("download.handler.handle_download", _fake_download)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["lane"] == "homepage"

def test_download_stage_gate_issues_are_scoped_to_current_entities():
    task_id = _make_task()
    batch_id = "download_stage_gate_scope"
    ctx = _ctx(task_id, batch_id)
    result_dir = batch_root(task_id, batch_id) / "task_download" / "results" / "source_plan_gate"
    write_json(
        result_dir / f"{_EID}.json",
        {"payload": {"passed": False, "ref": _EID, "issues": ["imageCount: only 2 images"]}},
    )
    write_json(
        result_dir / "无关景区乙.json",
        {"payload": {"passed": False, "ref": "无关景区乙", "issues": ["old stale issue"]}},
    )

    issues = run_mod._download_stage_gate_issues(ctx, entity_ids=[_EID])

    assert issues == [f"{_EID}: imageCount: only 2 images"]

def test_download_plan_checkpoint_does_not_full_refresh_ready_batch_on_rule_mtime(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_ready_batch_no_global_stale_refresh"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    calls: dict[str, object] = {}

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])

    def _fake_stale(_ctx, *, entity_ids):
        calls["stale_entity_ids"] = list(entity_ids)
        return [{"entityId": entity_ids[0]}]

    monkeypatch.setattr("task.run._stale_source_plan_entities", _fake_stale)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert calls == {}

def test_download_plan_repairs_build_prepare_homepage_base_draft_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_build_prepare_homepage_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["failedObjects"] = [
        f"地点/景区/{_EID}: homepage baseDraft 可用事实不足",
    ]
    run_mod.save_workflow_state(state)
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])
    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {"issues": [], "sourceUnavailable": []}

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": [_EID], "force": True}

def test_legacy_non_actionable_download_repair_does_not_block_static_valid_plan():
    task_id = _make_task()
    batch_id = "download_repair_legacy_non_actionable"
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
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [f"{_EID}: legacy fetch-only issue without actionable hint"],
                    "sourcePlanPath": str(plan_paths[0]),
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
                    "researchLaneIssues": {},
                    "imageRepairHints": [],
                }
            ],
        },
    )

    assert run_mod._source_plan_filled(ctx)[0] is True
    assert run_mod._checkpoint_prompts(ctx, "download_plan") == []

def test_download_repair_rejects_source_use_mode_as_image_license_hint():
    task_id = _make_task()
    batch_id = "download_repair_source_mode_as_license"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["license"] = "factual_reference_only"
    write_json(plan_path, plan)

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image unsupported license"],
    )
    repair = read_json(repair_path)
    actions = [hint["action"] for hint in repair["entities"][0]["imageRepairHints"]]
    assert "replace_image_or_source_unit_do_not_use_sourceUseMode_as_image_license" in actions

def test_download_repair_classifies_independent_image_fetch_hint_as_image_lane():
    hints = run_mod._download_diagnostic_image_repair_hints(
        {
            "sampleRejected": [
                "imageFetch: 测试景区甲#1 下载失败/非图片/过小 "
                "(https://x.invalid/gallery-bad.jpg)"
            ]
        },
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "image"
    assert hints[0]["sourceId"] == ""
    assert hints[0]["action"] == "replace_unfetchable_or_low_quality_image"

def test_download_fetch_refreshes_stale_source_plan_before_retry(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_stale_source_plan_refresh"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_content_capacity_preflight", lambda _ctx: [])
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: [{"entityId": _EID}] if list(entity_ids) == [_EID] else [],
    )

    def _fake_prepare_source_plan(_task_id, _batch_id, entities, **_kwargs):
        captured["prepared_entities"] = [entity["entityId"] for entity in entities]

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        captured["auto_entity_ids"] = list(entity_ids)
        captured["auto_force"] = force
        captured["auto_scope"] = scope
        captured["entity_type"] = entity_type
        return {"issues": [], "sourceUnavailable": []}

    def _fake_handle_download(ns):
        captured["download_entity_ids"] = ns.entity_ids

    monkeypatch.setattr("download.prepare.prepare_source_plan", _fake_prepare_source_plan)
    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)
    monkeypatch.setattr("download.handler.handle_download", _fake_handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["prepared_entities"] == [_EID]
    assert captured["auto_entity_ids"] == [_EID]
    assert captured["auto_force"] is True
    assert captured["auto_scope"] == "download_fetch_stale_source_plan"
    assert captured["download_entity_ids"] == _EID

def test_download_stage_gate_issues_scopes_source_screen_by_payload_entity():
    task_id = _make_task()
    batch_id = "download_source_screen_scope"
    ctx = _ctx(task_id, batch_id)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="source_screen",
        ref="测试景区甲__article_qunar_base_1",
        passed=False,
        issues=["sourceScreen: source scored Reject"],
        evidence_summary={"entityId": _EID, "sourceId": "article_qunar_base_1"},
    )
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="source_screen",
        ref="无关景区乙__article_qunar_base_1",
        passed=False,
        issues=["sourceScreen: source scored Reject"],
        evidence_summary={"entityId": "无关景区乙", "sourceId": "article_qunar_base_1"},
    )

    issues = run_mod._download_stage_gate_issues(ctx, entity_ids=[_EID])
    assert issues == [
        "测试景区甲__article_qunar_base_1: sourceScreen: source scored Reject"
    ]

