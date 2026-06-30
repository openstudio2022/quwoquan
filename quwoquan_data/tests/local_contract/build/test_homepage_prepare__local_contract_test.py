from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_prepare_entity_pages_prunes_stale_inactive_inputs():
    from build.homepage import prepare_entity_pages

    task_id = "workflow_prepare_homepage_prune"
    batch_id = "batch"
    active = "当前有效景区"
    stale = "已放弃景区"
    stale_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", stale)
    write_json(stale_input, {"payload": {"name": stale}})

    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": active},
            ],
        },
    }

    prepare_entity_pages(task_id, batch_id, spec)

    active_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", active)
    assert active_input.is_file()
    assert not stale_input.exists()
    manifest = read_json(batch_assistant_task(task_id, batch_id, "build", "entity_page"))
    assert manifest["refs"] == ["地点__景区__当前有效景区"]

def test_build_prepare_blocks_missing_homepage_base_draft():
    task_id = _make_task()
    ctx = _ctx(task_id, "build_prepare_missing_homepage")

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert any("baseDraft.sourceRef is empty" in issue for issue in result.issues), result.issues

def test_build_prepare_abandons_unrepairable_homepage_after_react_budget():
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    good = "可用主页景区"
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": good},
    ]
    store.save_spec(spec)
    batch_id = "build_prepare_partial_homepage_unavailable"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"build_prepare": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    good_dir = resolve_entity_object_dir(task_id, batch_id, good, etype_hint="地点/景区")
    write_structured_source_unit(
        good_dir,
        ordinal=1,
        source_id="home_wikipedia",
        source_md=_long_base_text(good),
        quality={"sourceId": "home_wikipedia", "quality": "A-fact", "score": 8},
        platform="Wikipedia",
        source_category="encyclopedia",
        source_role="base",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        url="https://example.test/wiki",
        title=f"{good} - Wikipedia",
        target_ref=f"/entity/地点/景区/{good}",
    )

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "done", result.issues
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [row["entityId"] for row in state["abandonedObjects"]] == [_EID]
    good_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", good)
    bad_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", _EID)
    assert good_input.is_file()
    assert not bad_input.exists()
