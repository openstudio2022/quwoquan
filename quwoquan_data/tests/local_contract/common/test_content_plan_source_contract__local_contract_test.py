from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_content_object_index_schema_has_single_contract_name():
    task_id = _make_task()
    batch_id = "content_index_schema"
    content_object.write_brief_object(
        task_id,
        batch_id,
        "schema_ref",
        {
            "titleHint": f"{_EID}·行前建议",
            "templateId": "travel.entity.guide",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "mustIncludeFacts": ["fixture"],
        },
        content_type="article",
    )
    index = read_json(batch_root(task_id, batch_id) / "_shared" / "content_object_index.json")
    assert index["schemaVersion"] == "quwoquan_data.content_object_index"
    assert "/1" not in index["schemaVersion"]

def test_content_plan_prunes_briefs_outside_packet_index():
    from _common.content_plan import CONTENT_PLAN_SCHEMA, validate_content_plan

    task_id = _make_task()
    batch_id = "content_plan_prune_extra_brief"
    root = batch_root(task_id, batch_id)
    ensure_batch_layout(task_id, batch_id, "produce")
    evidence = (
        root
        / "entities"
        / "地点"
        / "景区"
        / _EID
        / "1.download"
        / "sources"
        / "01.article_fixture"
        / "source.md"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("fixture source", encoding="utf-8")
    evidence_ref = evidence.relative_to(root).as_posix()
    item = {
        "ref": f"{_EID}_planning_consultation",
        "kind": "entity",
        "carrier": "article",
        "researchLane": "article",
        "title": f"{_EID}·行前建议",
        "entityRefs": [f"/entity/地点/景区/{_EID}"],
        "evidenceRefs": [evidence_ref],
        "rationale": "fixture evidence plan",
    }
    write_json(
        root / "_shared" / "content_plan_packet.json",
        {"schemaVersion": CONTENT_PLAN_SCHEMA, "items": [item]},
    )
    content_object.write_brief_object(
        task_id,
        batch_id,
        item["ref"],
        {
            "titleHint": item["title"],
            "templateId": "travel.entity.guide",
            "carrier": "article",
            "entityRefs": item["entityRefs"],
            "mustIncludeFacts": ["fixture"],
        },
        content_type="article",
    )
    stale_brief = root / "posts" / "image" / "攻略" / f"{_EID}·旧图集" / "1" / "3.compose" / "brief.json"
    stale_brief.parent.mkdir(parents=True, exist_ok=True)
    write_json(stale_brief, {"titleHint": f"{_EID}·旧图集", "carrier": "image"})

    spec = {
        "scope": {"coverageTargets": [{"name": _EID}]},
        "content": {"modalityContract": "separated_research", "quotas": {}},
        "acceptance": {},
    }
    issues = validate_content_plan(task_id, batch_id, spec)
    assert any("posts contains brief(s) outside content_plan_packet/index" in issue for issue in issues), issues

    ctx = _ctx(task_id, batch_id)
    removed = run_mod._prune_content_plan_extra_briefs(ctx)
    assert any(f"{_EID}·旧图集" in item for item in removed), removed
    assert not stale_brief.exists()
    issues = validate_content_plan(task_id, batch_id, spec)
    assert not any("posts contains brief(s) outside content_plan_packet/index" in issue for issue in issues), issues

def test_content_plan_strict_source_unavailable_fails_before_agent(monkeypatch):
    task_id = _make_task()
    batch_id = "content_plan_strict_source_unavailable"
    ctx = _ctx(task_id, batch_id)
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "failed"
    assert "严格任务禁止继续消耗 Agent" in result.message
    assert result.issues == [issue]
    assert result.fallback_stage == "download_plan"

def test_content_plan_source_shortfall_waits_under_partial_delivery(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "替补景区乙"}]
    store.save_spec(spec)
    batch_id = "content_plan_source_shortfall_replacement"
    ctx = _ctx(task_id, batch_id)
    write_json(
        batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics",
            "taskId": task_id,
            "batchId": batch_id,
            "targets": {
                _EID: {
                    "rawArticleBaseSources": 3,
                    "qualifiedArticleBaseSources": 1,
                    "pickedArticleBaseSources": 1,
                    "pickedImageSources": 2,
                    "articleRejects": {"text_too_short": 2},
                }
            },
        },
    )
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )

    def _screen(*_args, **_kwargs):
        raise AssertionError("partial content_plan shortfall must not replace the entity")

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "waiting"
    assert "等待 Agent 证据驱动篇目规划" in result.message
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["abandonedObjects"] == []
    assert state.get("replacementObjects", []) == []

def test_content_plan_source_shortfall_does_not_start_replacement_waves(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    store.save_spec(spec)
    batch_id = "content_plan_source_shortfall_replacement_waves"
    ctx = _ctx(task_id, batch_id)
    write_json(
        batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics",
            "taskId": task_id,
            "batchId": batch_id,
            "targets": {
                _EID: {
                    "rawArticleBaseSources": 3,
                    "qualifiedArticleBaseSources": 1,
                    "pickedArticleBaseSources": 1,
                    "pickedImageSources": 2,
                    "articleRejects": {"text_too_short": 2},
                }
            },
        },
    )
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )
    calls: list[str] = []

    def _screen(*_args, **kwargs):
        scope = str(kwargs.get("scope") or "")
        calls.append(scope)
        raise AssertionError("partial content_plan shortfall must not screen replacements")

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "waiting"
    assert calls == []
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["abandonedObjects"] == []
    assert state.get("replacementObjects", []) == []

def test_issue_entity_matching_uses_full_path_segment_not_substring():
    rows = [
        "地点/景区/白云区白云山景区/1.download/sources: only 1 sources (need >= 4)",
    ]

    assert run_mod._entity_ids_from_issue_messages(
        ["白云山景区", "白云区白云山景区"],
        rows,
    ) == ["白云区白云山景区"]
    assert not run_mod._issue_mentions_entity_id("白云山景区", rows[0])
    assert run_mod._issue_mentions_entity_id("白云区白云山景区", rows[0])

def test_compose_base_draft_clear_removes_stale_source_occupant():
    ledger = {
        "schemaVersion": "quwoquan_data.base_draft_ledger",
        "assignments": {
            "entities/x/sources/07.article/source.md": "old_image_ref",
            "entities/x/sources/04.article/source.md": "selected_ref",
            "entities/y/sources/01.article/source.md": "other_ref",
        },
    }
    cleaned, duplicates, changed = run_mod._clear_compose_base_draft_assignments(
        ledger,
        ["selected_ref", "new_article_ref"],
        {
            "new_article_ref": {
                "baseSourceRef": "entities/x/sources/07.article/source.md",
            }
        },
    )

    assert duplicates == []
    assert changed is True
    assert cleaned["assignments"] == {
        "entities/y/sources/01.article/source.md": "other_ref",
    }

def test_compose_base_draft_clear_detects_duplicate_current_plan_sources():
    ledger = {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {}}
    cleaned, duplicates, changed = run_mod._clear_compose_base_draft_assignments(
        ledger,
        ["article_a", "article_b"],
        {
            "article_a": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
            "article_b": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
        },
    )

    assert cleaned["assignments"] == {}
    assert changed is False
    assert duplicates == [
        "entities/x/sources/07.article/source.md -> article_a, article_b"
    ]

def test_compose_base_draft_clear_allows_image_work_sharing_article_base():
    """图文同源是正常现象：image/gallery 作品与文章共用同一底稿不应触发 duplicate 门，
    与 content_plan 对 carrier==image 的 one-source-one-work 豁免一致（C 修复回归）。"""
    ledger = {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {}}
    cleaned, duplicates, changed = run_mod._clear_compose_base_draft_assignments(
        ledger,
        ["article_a", "image_b"],
        {
            "article_a": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
            "image_b": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
        },
        image_refs={"image_b"},
    )

    assert duplicates == []
    assert changed is False

