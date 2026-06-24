from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_download_repair_includes_replace_source_image_hint():
    task_id = _make_task()
    batch_id = "download_repair_low_res_hint"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
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

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image too small"],
    )
    repair = read_json(repair_path)
    hints = repair["entities"][0]["imageRepairHints"]
    assert hints[0]["lane"] == "article"
    assert hints[0]["sourceId"] == "article_baike"
    assert hints[0]["action"] == "replace_image_or_source_unit"
    assert hints[0]["sameSourceHighResCandidate"] == ""
    assert repair["entities"][0]["researchLaneIssues"]["article"]

def test_download_repair_includes_same_source_high_res_hint():
    task_id = _make_task()
    batch_id = "download_repair_recoverable_hint"
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

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: image_fetch_gate rejected low-res source image"],
    )
    repair = read_json(repair_path)
    hints = repair["entities"][0]["imageRepairHints"]
    retry_hints = [
        hint for hint in hints
        if hint["action"] == "retry_with_same_source_high_resolution_url"
    ]
    assert retry_hints
    assert retry_hints[0]["sameSourceHighResCandidate"].endswith("/foo.jpg")

def test_download_plan_prompt_surfaces_image_repair_hints():
    task_id = _make_task()
    batch_id = "download_repair_prompt_hint"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
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
    run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image too small"],
    )

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "源图修复指令" in article_prompts[0]
    assert "replace_image_or_source_unit" in article_prompts[0]
    assert "sourceUseMode 是文字来源权利模式，不是图片许可" in article_prompts[0]

def test_download_repair_includes_diagnostic_rejected_source_image_hint():
    hints = run_mod._download_diagnostic_image_repair_hints(
        {
            "sampleRejected": [
                "sourceImage:article_official_planning: "
                "测试景区甲/article_official_planning#1: "
                "imageFetch failed/non-image/too small "
                "(https://x.invalid/bad.jpg)"
            ]
        },
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "article"
    assert hints[0]["sourceId"] == "article_official_planning"
    assert hints[0]["action"] == "replace_unfetchable_or_low_quality_image"
    assert hints[0]["url"] == "https://x.invalid/bad.jpg"

def test_download_repair_lanes_are_driven_by_failure_summary_not_extra_hints():
    repair = {
        "issues": [
            "地点/景区/测试景区甲/1.download/sources: article research needs >= 4 text-qualified base sources"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "homepage", "issue": "generic homepage imageFetch failed"},
            {"lane": "article", "issue": "sourceImage:article_a failed"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"article"}

def test_download_repair_lanes_recognize_image_fetch_summary():
    repair = {
        "issues": [
            "测试景区甲: imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "homepage", "issue": "legacy diagnostic fallback"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"image"}

def test_download_repair_lanes_route_encyclopedia_core_gap_to_homepage():
    repair = {
        "issues": [
            "天下第一泉景区: missing core source categories ['encyclopedia']"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "article", "issue": "sourceImage:article_a failed"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"homepage"}
    hints = run_mod._download_issue_repair_hints(
        repair["issues"],
        entity_id="天下第一泉景区",
    )
    assert hints[0]["lane"] == "homepage"
    assert hints[0]["action"] == "add_or_replace_homepage_encyclopedia_or_official_seed_source"

def test_download_issue_repair_hints_classify_image_gate_failure():
    hints = run_mod._download_issue_repair_hints(
        ["测试景区甲: image gates failed (rights/fetch/safety/min-count)"],
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "image"
    assert hints[0]["action"] == "add_or_replace_image_source_collections_with_complete_rights"

def test_download_plan_prompt_includes_repair_only_article_lane():
    task_id = _make_task()
    batch_id = "download_repair_prompt_repair_only_lane"
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
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: article research needs >= 4 text-qualified base sources"
                    ],
                    "sourcePlanPath": str(plan_paths[0]),
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
                    "reportPaths": ["reports/entity_source_bundle_gate/测试景区甲.json"],
                    "downloadDiagnostics": {
                        "entityId": _EID,
                        "sampleRejected": [
                            "sourceImage:article_official_planning: "
                            "测试景区甲/article_official_planning#1: "
                            "imageFetch failed/non-image/too small "
                            "(https://x.invalid/bad.jpg)"
                        ],
                    },
                    "researchLaneIssues": {},
                    "imageRepairHints": [
                        {
                            "lane": "article",
                            "sourceId": "article_official_planning",
                            "imageIndex": 1,
                            "action": "replace_unfetchable_or_low_quality_image",
                            "issue": "imageFetch failed/non-image/too small",
                        }
                    ],
                }
            ],
        },
    )

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "download_repair" in article_prompts[0]
    assert "text-qualified base sources" in article_prompts[0]
    assert "replace_unfetchable_or_low_quality_image" in article_prompts[0]

def test_download_plan_prompt_ignores_stale_repair_when_static_issue_remains():
    task_id = _make_task()
    batch_id = "download_repair_stale_static_issue"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: old fetch repair should be stale after source plan changes"],
    )
    assert repair_path.exists()

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["license"] = "factual_reference_only"
    write_json(plan_path, plan)
    current = plan_path.stat().st_mtime_ns
    os.utime(plan_path, ns=(current + 1_000_000_000, current + 1_000_000_000))

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "unsupported license factual_reference_only" in article_prompts[0]
    assert "old fetch repair should be stale" not in article_prompts[0]
    assert "这是 download_repair" not in article_prompts[0]

