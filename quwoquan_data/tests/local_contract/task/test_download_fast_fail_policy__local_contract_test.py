from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_download_plan_deterministic_license_failure_fast_fails_strict_task(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_deterministic_strict"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["九寨沟 article source has unsupported license"]),
    )
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {_EID: {"article": ["imageRights: unsupported license CC BY-SA 1.0"]}},
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "failed"
    assert "deterministic_source_unavailable" in result.issues[0]
    assert "allowPartialContent is not true" in result.issues[0]

def test_download_plan_deterministic_license_failure_activates_reserve(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "替补景区乙"}]
    store.save_spec(spec)
    batch_id = "download_plan_deterministic_reserve"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )

    def _filled(current_ctx):
        if _EID not in current_ctx.entity_ids:
            return True, []
        return False, ["测试景区甲 article source has unsupported license"]

    monkeypatch.setattr("task.run._source_plan_filled", _filled)
    monkeypatch.setattr("task.run._replacement_fetch_gate_passed", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr("task.run._homepage_base_draft_gate_for_entity", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr(
        "task.run._content_capacity_gate_for_entity",
        lambda *_args, **_kwargs: (True, [], {"fixture": "passed"}),
    )
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda current_ctx: (
            {_EID: {"article": ["imageRights: unsupported license CC BY-SA 1.0"]}}
            if _EID in current_ctx.entity_ids
            else {}
        ),
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "done"
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID]
    assert [item["entityId"] for item in state["replacementObjects"]] == ["替补景区乙"]
    availability = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert availability["readyTargets"] == ["替补景区乙"]

def test_mark_abandoned_entities_records_fast_fail_state():
    task_id = _make_task()
    batch_id = "abandon_entity"
    report = run_mod.mark_abandoned_entities(
        task_id,
        batch_id,
        [_EID],
        stage="download_plan",
        reason="source_unavailable",
    )
    assert report["added"] == [_EID]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["abandonedObjects"][0]["entityId"] == _EID
    assert state["abandonedObjects"][0]["reason"] == "source_unavailable"

def test_download_fast_fail_classifies_duplicate_limited_images(monkeypatch):
    task_id = _make_task()
    ctx = _ctx(task_id, "download_fast_fail_duplicate_images")
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

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [f"{_EID}: only 2 unique publishable images (need >= 3)"],
    )

    assert _EID in reasons
    assert "need >= 3" in reasons[_EID]

def test_download_retained_source_shortfall_fast_fails_after_repair_rewind():
    task_id = _make_task()
    batch_id = "download_retained_shortfall_fast_fail"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "article retained sources=3 need>=4"
            )
        ],
    )

    assert _EID in reasons
    assert "source/category shortfall survived repair" in reasons[_EID]

def test_download_retained_source_shortfall_repairs_before_fast_fail():
    task_id = _make_task()
    batch_id = "download_retained_shortfall_repair_first"
    ctx = _ctx(task_id, batch_id)
    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "article retained sources=3 need>=4"
            )
        ],
    )

    assert reasons == {}

def test_download_homepage_base_ready_shortfall_fast_fails_after_repair_rewind():
    task_id = _make_task()
    batch_id = "download_homepage_base_ready_fast_fail"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "homepage baseDraft-ready sources=0 need>=1"
            )
        ],
    )

    assert _EID in reasons
    assert "source/category shortfall survived repair" in reasons[_EID]

def test_source_availability_fast_fails_unrecoverable_subset():
    names = ["可用景区甲", "缺图景区乙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability subset",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
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
        created_by="test",
    )
    spec["workflowPolicy"] = {"allowPartialContent": True}
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_fast_fail",
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
                    "entityId": "缺图景区乙",
                    "issues": ["缺图景区乙: no rights-compatible open-license images discovered"],
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

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == ["缺图景区乙"]
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == {"缺图景区乙"}
    assert "source_unavailable_after_auto_research" in state["abandonedObjects"][0]["reason"]

def test_source_availability_does_not_fast_fail_strict_task():
    names = ["可用景区甲", "缺图景区乙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability strict",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
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
        created_by="test",
    )
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_strict",
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
                    "entityId": "缺图景区乙",
                    "issues": ["缺图景区乙: no rights-compatible open-license images discovered"],
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

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == []
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()

def test_download_plan_rejects_low_resolution_article_source_image():
    task_id = _make_task()
    batch_id = "download_plan_low_res_article"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("article source article_baike image[1]: imagePixels" in issue for issue in issues), issues

def test_download_plan_allows_recoverable_compressed_article_source_image():
    task_id = _make_task()
    batch_id = "download_plan_recoverable_article_image"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["url"] = (
        "https://img1.qunarzz.com/travel/d1/1509/f3/"
        "foo.jpg_r_720x480x95_abcd1234.jpg"
    )
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    assert run_mod._source_plan_filled(ctx)[0] is True

def test_download_plan_allows_single_primary_authority_homepage_source():
    task_id = _make_task()
    batch_id = "download_plan_single_authoritative_homepage"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"] = plan["payload"]["sources"][:1]
    plan["payload"]["sources"][0]["platform"] = "维基百科"
    plan["payload"]["sources"][0]["category"] = "encyclopedia"
    plan["payload"]["sources"][0]["sourceRole"] = "primary"
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is True
    assert not any("homepage sources=" in issue for issue in issues), issues

def test_download_plan_blocks_travelogue_as_homepage_source():
    task_id = _make_task()
    batch_id = "download_plan_homepage_travelogue"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"].append(
        {
            "source_id": "home_qunar_guide",
            "platform": "去哪儿攻略",
            "url": "https://touch.travel.qunar.com/youji/fixture",
            "category": "travelogue",
            "sourceUseMode": "factual_reference_only",
        }
    )
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("entity homepage cannot use author/guide/review source category travelogue" in i for i in issues), issues

def test_download_fast_fail_classifies_repeated_homepage_category_shortfall():
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "download_fast_fail_homepage_category"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [f"{_EID}: missing core source categories ['encyclopedia']"],
    )

    assert list(reasons) == [_EID]
    assert "source/category shortfall survived repair" in reasons[_EID]


def test_elastic_policy_classifies_source_category_shortfall_without_retry_loop():
    task_id = _make_task(
        workflow_policy={
            "elasticOverfetch": True,
            "allowQuotaShortfall": True,
            "allowContentQuotaShortfall": True,
            "allowMinEntityShortfall": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    batch_id = "download_fast_fail_elastic_source_category"
    ctx = _ctx(task_id, batch_id)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [f"{_EID}: {_EID}: source categories 2 < required 3 (covered=['encyclopedia', 'travelogue'])"],
    )

    assert list(reasons) == [_EID]
    assert "source/category shortfall survived repair" in reasons[_EID]


def test_elastic_fast_fail_skips_replacement_when_active_targets_still_meet_min(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "elasticOverfetch": True,
            "allowQuotaShortfall": True,
            "allowContentQuotaShortfall": True,
            "allowMinEntityShortfall": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    spec = store.load_spec(task_id)
    spec.setdefault("scope", {}).setdefault("coverageTargets", []).append(
        {"entityType": "地点/景区", "name": "测试景区乙"}
    )
    spec.setdefault("acceptance", {})["minEntities"] = 1
    store.save_spec(spec)
    batch_id = "download_fast_fail_no_replacement_when_min_met"
    ctx = _ctx(task_id, batch_id)

    def _fail_screen(*_args, **_kwargs):
        raise AssertionError("replacement screening should not run when active target count still meets minEntities")

    monkeypatch.setattr(run_mod, "_screen_replacements_for_abandoned_entities", _fail_screen)
    import download.gate as gate_mod

    monkeypatch.setattr(gate_mod, "gate_download", lambda *_args, **_kwargs: [])

    issues = run_mod._apply_download_fast_fail(
        ctx,
        [f"{_EID}: {_EID}: source categories 2 < required 3 (covered=['encyclopedia', 'travelogue'])"],
    )

    assert issues == []
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID]


def test_homepage_lane_source_screen_empty_is_homepage_only_reject(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "homepage_lane_source_screen_empty"
    ctx = _ctx(task_id, batch_id)

    def _unexpected_entity_abandon(*_args, **_kwargs):
        raise AssertionError("homepage lane sourceScreen empty must not abandon entity")

    monkeypatch.setattr(run_mod, "mark_abandoned_entities", _unexpected_entity_abandon)

    issues = run_mod._apply_homepage_download_fast_fail(
        ctx,
        [
            f"{_EID}: sourceScreen: no retained source for entity",
            f"{_EID}: unrelated article issue",
        ],
        target_entity_ids=[_EID],
        download_lane="homepage",
    )

    assert issues == [f"{_EID}: unrelated article issue"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    homepage_abandoned = [
        item["entityId"]
        for item in (state.get("abandonedObjects") or [])
        if item.get("abandonScope") == "homepage"
    ]
    assert homepage_abandoned == [_EID]


def test_article_official_source_id_cannot_use_travelogue_platform():
    task_id = _make_task()
    batch_id = "download_article_official_identity"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    for source in plan["payload"]["sources"]:
        if source["source_id"] == "article_official":
            source["platform"] = "去哪儿攻略"
            source["url"] = "https://touch.travel.qunar.com/comment/not-official"
            break
    write_json(plan_path, plan)

    issues = run_mod._download_research_lane_issues(ctx, _EID, "地点/景区", "article")
    assert any("source_id implies official" in issue for issue in issues), issues


def test_elastic_policy_does_not_loop_download_plan_for_article_quota_shortfall():
    task_id = _make_task(
        workflow_policy={
            "elasticOverfetch": True,
            "allowQuotaShortfall": True,
            "allowContentQuotaShortfall": True,
            "allowMinEntityShortfall": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    store.save_spec(spec)
    batch_id = "download_article_quota_shortfall_reasoned"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"] = plan["payload"]["sources"][:1]
    write_json(plan_path, plan)

    issues = run_mod._download_research_lane_issues(ctx, _EID, "地点/景区", "article")

    assert not any("article sources=" in issue for issue in issues), issues
    assert not any("article research needs >=" in issue for issue in issues), issues


def test_image_only_source_plan_does_not_require_article_sources():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    store.save_spec(spec)
    batch_id = "download_image_only_article_sources_ignored"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"] = plan["payload"]["sources"][:1]
    write_json(plan_path, plan)
    image_plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "image_source_plan.json"
    )
    image_plan = read_json(image_plan_path)
    for collection in image_plan["payload"]["collections"]:
        for image in collection.get("images") or []:
            image["modelReleaseStatus"] = "not_required"
    write_json(image_plan_path, image_plan)

    passed, issues = run_mod._source_plan_filled(ctx)

    assert passed, issues
    assert not any("article sources=" in issue for issue in issues), issues


def test_image_only_source_plan_gate_does_not_require_article_category_spread():
    from download.handler_plan import _source_plan_gate_issues

    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    store.save_spec(spec)

    issues = _source_plan_gate_issues(
        task_id=task_id,
        batch_id="download_image_only_category_gate",
        entity_id=_EID,
        entity_type="地点/景区",
        planned_sources=[
            {
                "source_id": "home_baike",
                "platform": "百度百科",
                "url": "https://example.invalid/baike",
                "category": "encyclopedia",
                "sourceUseMode": "factual_reference_only",
                "researchLane": "homepage",
                "expectedContentType": "entity",
            },
            {
                "source_id": "image_commons",
                "platform": "Wikimedia Commons",
                "url": "https://commons.wikimedia.org/wiki/File:one.jpg",
                "category": "open_license",
                "sourceUseMode": "factual_reference_only",
                "researchLane": "image",
                "expectedContentType": "image",
            },
        ],
        selected_lanes=None,
        vertical="travel",
    )

    assert not any("source categories" in issue for issue in issues), issues
    assert not any("missing core source categories" in issue for issue in issues), issues


def test_article_official_source_id_allows_official_article_category():
    task_id = _make_task()
    batch_id = "download_article_official_article_identity"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    for source in plan["payload"]["sources"]:
        if source["source_id"] == "article_official":
            source["platform"] = "景区官网"
            source["url"] = "https://www.example.gov.cn/2026/01/01/article.html"
            break
    write_json(plan_path, plan)

    issues = run_mod._download_research_lane_issues(ctx, _EID, "地点/景区", "article")

    assert not any("source_id implies official" in issue for issue in issues), issues
