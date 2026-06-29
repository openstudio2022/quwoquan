from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_review_fallback_does_not_rewind_to_download_for_traceability(monkeypatch):
    reports = [
        (
            "post-a",
            {
                "payload": {
                    "passed": False,
                    "fallbackStage": "download",
                    "issues": [
                        "factTraceability: mustIncludeFact not traceable: editorial advice"
                    ],
                }
            },
        )
    ]
    monkeypatch.setattr(
        "_common.stage_reports.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter(reports),
    )
    task_id = _make_task()
    assert run_mod._aggregate_review_fallback(_ctx(task_id, "b_review_fallback")) == "compose"

def test_review_fallback_rewinds_to_download_for_missing_source(monkeypatch):
    reports = [
        (
            "post-a",
            {
                "payload": {
                    "passed": False,
                    "fallbackStage": "download",
                    "issues": ["source file missing: entities/x/1.download/sources/01/source.md"],
                }
            },
        )
    ]
    monkeypatch.setattr(
        "_common.stage_reports.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter(reports),
    )
    task_id = _make_task()
    assert run_mod._aggregate_review_fallback(_ctx(task_id, "b_missing_source")) == "download"

def test_author_checkpoint_only_reads_packaged_drafts():
    task_id = _make_task()
    batch_id = "drafts1"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    legacy = batch_command_root(task_id, batch_id, "produce") / "drafts" / "旧.article.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# 旧平铺正文\n\n这不应被新 checkpoint 识别。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False
    assert pending == ["(no content objects; run compose-brief first)"]

    content_object.register_content_object(task_id, batch_id, "新", content_type="article", angle="体验", title="新")
    write_writing_pack(task_id, batch_id, "新", {"carrier": "article", "baseDraftText": _long_base_text("新")})
    write_placeholder_draft(task_id, batch_id, "新")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False and pending == ["新"]
    report = run_mod.mark_abandoned_content_refs(
        task_id,
        batch_id,
        ["新"],
        stage="produce_author",
        reason="agent_unrecoverable: fixture object skipped",
    )
    assert report["added"] == ["新"]
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []
    draft_article_path(task_id, batch_id, "新").write_text("# 新正文\n\n这是 Agent 完成的正文。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []

def test_author_checkpoint_skips_image_structured_packet_even_with_repair_report():
    task_id = _make_task()
    batch_id = "drafts_image_skip"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    content_object.register_content_object(
        task_id,
        batch_id,
        "图集",
        content_type="image",
        angle="画报",
        title="图集",
    )
    write_writing_pack(task_id, batch_id, "图集", {"carrier": "image", "assets": [{"assetId": "a1"}]})
    write_image_evidence_draft(task_id, batch_id, "图集", selected_asset_ids=["a1"])
    assert not draft_article_path(task_id, batch_id, "图集").exists()

    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True
    assert pending == []

    review_dir = content_object.content_object_stage_dir(task_id, batch_id, "图集", "5.review")
    review_dir.mkdir(parents=True, exist_ok=True)
    repair = review_dir / "repair_report.json"
    repair.write_text('{"issues":["galleryCaption: too long"]}', encoding="utf-8")
    os.utime(repair, None)

    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True
    assert pending == []

def test_author_checkpoint_finalizes_interrupted_finished_outputs():
    task_id = _make_task()
    batch_id = "drafts_finalize_interrupted"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    ref = "已写文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    source_path = batch_root(task_id, batch_id) / "entities/地点/景区/测试景区甲/1.download/sources/01/source.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("测试景区甲的可核验来源。", encoding="utf-8")
    source_rel = source_path.relative_to(batch_root(task_id, batch_id)).as_posix()
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {"carrier": "article", "sourcePaths": [source_rel], "baseDraftText": _long_base_text(ref)},
    )
    prompt_path(task_id, batch_id, ref).parent.mkdir(parents=True, exist_ok=True)
    prompt_path(task_id, batch_id, ref).write_text("# prompt", encoding="utf-8")
    draft_article_path(task_id, batch_id, ref).write_text("# 正文\n\n先说结论，这是一篇已经由 Agent 写回的正文。", encoding="utf-8")
    write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "agent", "model": "cursor"})

    state = run_mod.load_workflow_state(task_id, batch_id)
    state["agentRunHistory"] = [
        {
            "stage": "produce_author",
            "outcomes": [
                {
                    "status": "finished",
                    "ref": ref,
                    "runId": "run-finished-before-interrupt",
                    "agentId": "agent-before-interrupt",
                }
            ],
        }
    ]
    run_mod.save_workflow_state(state)

    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True
    assert pending == []
    meta = read_json(draft_meta_path(task_id, batch_id, ref))
    assert meta["agentRunId"] == "run-finished-before-interrupt"
    assert meta["agentId"] == "agent-before-interrupt"
    assert meta["promptSha256"].startswith("sha256:")
    assert meta["writingPackSha256"].startswith("sha256:")
    assert meta["draftSha256"].startswith("sha256:")
    assert meta["finalizedFromAgentRunHistory"] is True

def test_author_checkpoint_finalizes_object_queue_succeeded_outputs():
    task_id = _make_task()
    batch_id = "drafts_finalize_object_queue"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    ref = "外部队列文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    source_path = batch_root(task_id, batch_id) / "entities/地点/景区/测试景区乙/1.download/sources/01/source.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("测试景区乙的可核验来源。", encoding="utf-8")
    source_rel = source_path.relative_to(batch_root(task_id, batch_id)).as_posix()
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {"carrier": "article", "sourcePaths": [source_rel], "baseDraftText": _long_base_text(ref)},
    )
    prompt_path(task_id, batch_id, ref).parent.mkdir(parents=True, exist_ok=True)
    prompt_path(task_id, batch_id, ref).write_text("# prompt", encoding="utf-8")
    draft_article_path(task_id, batch_id, ref).write_text("# 正文\n\n先说结论，这是一篇外部 author-runner 写回的正文。", encoding="utf-8")
    write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "pending", "agentRunId": "run-queue"})
    oq.enqueue_ref_job(task_id, batch_id, ref, "author")
    job = oq.acquire_lease(task_id, batch_id, worker="w1", stage="author")
    oq.complete_job(task_id, batch_id, job["jobId"], job["lease"])

    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True
    assert pending == []
    meta = read_json(draft_meta_path(task_id, batch_id, ref))
    assert meta["generator"] == "agent"
    assert meta["agentRunId"] == "run-queue"
    assert meta["finalizedFromObjectQueue"] is True
    assert meta["promptSha256"].startswith("sha256:")
    assert meta["writingPackSha256"].startswith("sha256:")
    assert meta["draftSha256"].startswith("sha256:")

def test_produce_review_rewind_invalidates_failed_ref_outputs():
    task_id = _make_task()
    batch_id = "retry1"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    brief_ok = {
        "titleHint": f"{_EID}·顺游攻略",
        "templateId": "travel.route.guide",
        "carrier": "article",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["预约"],
    }
    brief_bad = {
        **brief_ok,
        "titleHint": f"{_EID}·避峰攻略",
    }
    content_object.write_brief_object(task_id, batch_id, "ref_ok", brief_ok, content_type="article")
    content_object.write_brief_object(task_id, batch_id, "ref_bad", brief_bad, content_type="article")
    write_writing_pack(
        task_id,
        batch_id,
        "ref_ok",
        {"carrier": "article", "baseDraftText": _long_base_text("ref_ok"), **_creator_assignment()},
    )
    write_writing_pack(
        task_id,
        batch_id,
        "ref_bad",
        {"carrier": "article", "baseDraftText": _long_base_text("ref_bad"), **_creator_assignment()},
    )

    write_placeholder_draft(task_id, batch_id, "ref_ok")
    write_placeholder_draft(task_id, batch_id, "ref_bad")
    oq.enqueue_ref_job(task_id, batch_id, "ref_ok", "author")
    oq.enqueue_ref_job(task_id, batch_id, "ref_bad", "author")
    draft_article_path(task_id, batch_id, "ref_ok").write_text("# 已完成\n\n正文。", encoding="utf-8")
    write_json(
        draft_meta_path(task_id, batch_id, "ref_ok"),
        {
            "generator": "agent",
            "model": "cursor-test",
            "citedSourcePaths": ["entities/地点/景区/测试景区甲/1.download/sources/01/source.md"],
            "agentRunId": "run-test",
            "promptSha256": "sha256:prompt",
            "writingPackSha256": "sha256:pack",
            "sourceBundleSha256": "sha256:source",
            "draftSha256": "sha256:draft",
        },
    )
    draft_article_path(task_id, batch_id, "ref_bad").write_text("# 旧稿\n\n需要重写。", encoding="utf-8")
    write_json(
        draft_article_path(task_id, batch_id, "ref_bad").parent / "author_self_check.json",
        {"ok": False},
    )

    bad_obj = content_object.content_object_dir(task_id, batch_id, "ref_bad")
    bad_obj.mkdir(parents=True, exist_ok=True)
    (bad_obj / "5.review").mkdir(parents=True, exist_ok=True)
    (bad_obj / "article.md").write_text("# 旧成品\n\n旧正文。", encoding="utf-8")
    write_json(bad_obj / "manifest.json", {"reviewDecision": "approved"})
    write_json(bad_obj / "5.review" / "ref_review_gate.json", {"passed": True})
    assets_dir = bad_obj / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "a.jpg").write_text("x", encoding="utf-8")

    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="review",
        ref="ref_bad",
        passed=False,
        issues=["skeletonSimilarity: heading sequence too similar to a peer (0.85)"],
        fallback_stage="agent_compose",
    )

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="agent_compose",
        issues=[f"{content_object.content_object_rel(task_id, batch_id, 'ref_bad')}: skeletonSimilarity"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is True
    assert "produce_compose" not in completed
    assert "produce_author" not in completed
    assert run_mod._drafts_authored(ctx) == (False, ["ref_bad"])
    assert "<!-- QWQ_AWAITING_AGENT_DRAFT -->" in draft_article_path(task_id, batch_id, "ref_bad").read_text(encoding="utf-8")
    assert not (bad_obj / "article.md").exists()
    assert not (bad_obj / "manifest.json").exists()
    assert not (bad_obj / "5.review" / "ref_review_gate.json").exists()
    assert not (bad_obj / "assets").exists()
    assert draft_article_path(task_id, batch_id, "ref_ok").read_text(encoding="utf-8") == "# 已完成\n\n正文。"
    queue = oq.queue_summary(task_id, batch_id)
    assert "ref_bad" in queue["byState"]["queued"], queue

def test_produce_review_rewind_to_download_purges_stale_author_queue():
    task_id = _make_task()
    batch_id = "retry_download"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    brief = {
        "titleHint": f"{_EID}·图集",
        "templateId": "travel.gallery",
        "carrier": "gallery",
        "writingIntent": "post_trip_journal",
        "mustIncludeFacts": ["云海"],
    }
    content_object.write_brief_object(task_id, batch_id, "ref_a", brief, content_type="image")
    content_object.write_brief_object(task_id, batch_id, "ref_b", brief, content_type="image")
    write_placeholder_draft(task_id, batch_id, "ref_a")
    write_placeholder_draft(task_id, batch_id, "ref_b")
    oq.enqueue_ref_job(task_id, batch_id, "ref_a", "author")
    oq.enqueue_ref_job(task_id, batch_id, "ref_b", "author")

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="download_plan",
        issues=["images must be recollected"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is True
    assert "download_fetch" not in completed
    queue = oq.queue_summary(task_id, batch_id)
    assert queue["total"] == 0, queue

def test_produce_author_skips_image_carrier_placeholders_without_repair_request():
    task_id = _make_task()
    batch_id = "image_author_prompt"
    ctx = _ctx(task_id, batch_id)
    ref = f"{_EID}_image_1"
    content_object.register_content_object(
        task_id,
        batch_id,
        ref,
        content_type="image",
        angle="攻略",
        title=f"{_EID} 图像作品",
    )
    write_writing_pack(task_id, batch_id, ref, {"carrier": "image"})
    write_placeholder_draft(task_id, batch_id, ref)

    ok, pending = run_mod._drafts_authored(ctx)
    prompts = run_mod._checkpoint_prompts(ctx, "produce_author")

    assert ok is True
    assert pending == []
    assert prompts == []

def test_reset_stage_retries_to_compose_invalidates_authored_drafts():
    from _common.draft_io import is_placeholder

    task_id = _make_task()
    batch_id = "retry_stage_compose_invalidates"
    ref = "已创作但需重建写包的文章"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(task_id, batch_id, ref, {"carrier": "article", "baseDraftText": _long_base_text(ref)})
    prompt_path(task_id, batch_id, ref).parent.mkdir(parents=True, exist_ok=True)
    prompt_path(task_id, batch_id, ref).write_text("# prompt", encoding="utf-8")
    draft_article_path(task_id, batch_id, ref).write_text("# 正文\n\n旧 agent 正文。", encoding="utf-8")
    write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "agent", "model": "cursor"})
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
    ]
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="produce_compose",
        reason="writing pack contract changed",
    )

    assert report["completed"] == [
        "download_plan",
        "download_fetch",
        "build_prepare",
        "build_homepage",
        "build_validate",
        "content_plan",
        "produce_plan",
    ]
    assert report["invalidatedContentRefs"] == [ref]
    assert read_json(draft_meta_path(task_id, batch_id, ref))["generator"] == "pending"
    assert is_placeholder(draft_article_path(task_id, batch_id, ref).read_text(encoding="utf-8"))

def test_placeholder_draft_refuses_incidental_agent_downgrade():
    from _common.draft_io import is_placeholder

    task_id = _make_task()
    batch_id = "placeholder_agent_downgrade_guard"
    ref = "已发布质量的正文"
    content_object.register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=ref)
    write_writing_pack(task_id, batch_id, ref, {"carrier": "article", "baseDraftText": _long_base_text(ref)})
    draft_article_path(task_id, batch_id, ref).parent.mkdir(parents=True, exist_ok=True)
    draft_article_path(task_id, batch_id, ref).write_text("# 正文\n\n这是一篇已经由 Agent 创作完成的正文。", encoding="utf-8")
    write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "agent", "model": "cursor"})

    try:
        write_placeholder_draft(task_id, batch_id, ref)
    except RuntimeError as exc:
        assert "refusing to downgrade completed agent draft" in str(exc)
    else:
        raise AssertionError("completed agent draft must not be downgraded by incidental prepare rerun")

    write_placeholder_draft(
        task_id,
        batch_id,
        ref,
        allow_agent_downgrade=True,
        downgrade_reason="explicit retry",
    )
    meta = read_json(draft_meta_path(task_id, batch_id, ref))
    assert meta["generator"] == "pending"
    assert meta["downgradedFrom"] == "agent"
    assert meta["downgradeReason"] == "explicit retry"
    assert is_placeholder(draft_article_path(task_id, batch_id, ref).read_text(encoding="utf-8"))

def test_approved_review_refs_exclude_failed_objects_from_batch_reducer():
    task_id = _make_task()
    batch_id = "approved_review_refs"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    ok_dir = content_object.content_object_dir(task_id, batch_id, "ref_ok") / "5.review"
    bad_dir = content_object.content_object_dir(task_id, batch_id, "ref_bad") / "5.review"
    ok_dir.mkdir(parents=True, exist_ok=True)
    bad_dir.mkdir(parents=True, exist_ok=True)
    write_json(ok_dir / "review_gate.json", {"passed": True})
    write_json(bad_dir / "review_gate.json", {"passed": False, "issues": ["skeletonSimilarity"]})

    assert run_mod._approved_review_refs(ctx) == ["ref_ok"]

def test_batch_reducer_payload_excludes_image_refs():
    task_id = _make_task()
    batch_id = "batch_reducer_payload_image_refs"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "article_ref", content_type="article", angle="攻略", title="Article"
    )
    content_object.register_content_object(
        task_id, batch_id, "image_ref", content_type="image", angle="攻略", title="Image"
    )
    for ref in ("article_ref", "image_ref"):
        review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review_gate.json", {"passed": True})
        draft = draft_article_path(task_id, batch_id, ref)
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(f"{ref} draft body with enough words to be visible.", encoding="utf-8")
        write_writing_pack(
            task_id,
            batch_id,
            ref,
            {
                "writingIntent": "planning_consultation",
                "baseSourceRef": f"sources/{ref}.md",
            },
        )

    payload = run_mod._batch_reducer_payload(ctx, refs={"article_ref", "image_ref"})

    assert [row["ref"] for row in payload] == ["article_ref"]

def test_gate_produce_passes_ref_scope_to_post_verify(monkeypatch):
    from produce.gate import gate_produce

    task_id = _make_task()
    batch_id = "gate_produce_ref_scope"
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    ok_dir = content_object.content_object_dir(task_id, batch_id, "ref_ok")
    ok_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        ok_dir / "manifest.json",
        {
            "entityRefs": ["地点/景区/测试"],
            "tagRefs": ["tag/a", "tag/b"],
            "reviewDecision": "approved",
            "storySpine": {"readerPromise": "ok"},
            "sourceUrls": ["https://example.com/source"],
        },
    )
    (ok_dir / "article.md").write_text("正文" * 400, encoding="utf-8")

    captured: list[set[str] | None] = []

    monkeypatch.setattr("produce.gate.gate_media_check", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("produce.gate.scan_runtime_batch_integrity", lambda *_args, **_kwargs: {"issues": []})
    monkeypatch.setattr(
        "produce.gate.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter([("ref_ok", {"payload": {"passed": True}})]),
    )

    def _fake_verify_posts_root(_root, **kwargs):
        captured.append(kwargs.get("post_rels"))
        return []

    monkeypatch.setattr("produce.gate.verify_posts_root", _fake_verify_posts_root)

    gate_produce(task_id, batch_id, "article", refs=["ref_ok"])

    assert captured == [{"posts/article/攻略/OK/1"}]

def test_produce_compose_reprepares_content_type_carrier_drift(monkeypatch):
    task_id = _make_task()
    batch_id = "compose_carrier_drift"
    ctx = _ctx(task_id, batch_id)
    ref = "image_ref"
    content_object.register_content_object(
        task_id, batch_id, ref, content_type="image", angle="画报", title="图片作品"
    )
    write_writing_pack(task_id, batch_id, ref, {"carrier": "article"})
    prompt = prompt_path(task_id, batch_id, ref)
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("prompt", encoding="utf-8")
    draft_article_path(task_id, batch_id, ref).write_text("agent draft", encoding="utf-8")
    write_json(draft_meta_path(task_id, batch_id, ref), {"generator": "agent"})

    calls: list[argparse.Namespace] = []

    def _fake_produce(ns):
        calls.append(ns)
        write_writing_pack(task_id, batch_id, ref, {"carrier": "image"})
        prompt.write_text("repaired prompt", encoding="utf-8")
        write_json(
            content_object.content_object_stage_dir(task_id, batch_id, ref, "3.compose")
            / "compose_brief_gate.json",
            {"payload": {"passed": True}},
        )

    monkeypatch.setattr("produce.handler.handle_produce", _fake_produce)

    result = run_mod._run_produce_compose(ctx)

    assert result.status == "done"
    assert calls and calls[0].refs == ref
    assert "1 repaired refs" in result.message

def test_produce_compose_abandons_deterministic_works_reject_when_partial_allowed(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "compose_partial_works_reject"
    ctx = _ctx(task_id, batch_id)
    good_ref = "good_ref"
    bad_ref = "bad_ref"
    for ref in (good_ref, bad_ref):
        content_object.register_content_object(
            task_id, batch_id, ref, content_type="article", angle="攻略", title=ref
        )

    def _fake_produce(_ns):
        for ref, passed in ((good_ref, True), (bad_ref, False)):
            write_writing_pack(task_id, batch_id, ref, {"carrier": "article"})
            prompt = prompt_path(task_id, batch_id, ref)
            prompt.parent.mkdir(parents=True, exist_ok=True)
            prompt.write_text("prompt", encoding="utf-8")
            draft = draft_article_path(task_id, batch_id, ref)
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text("<!-- QWQ_AWAITING_AGENT_DRAFT -->", encoding="utf-8")
            payload = {"passed": passed}
            if not passed:
                payload["issues"] = [
                    "works classifier rejected object as 'moment' "
                    "(abandonReason=casual_moment): 随记/低专业度来源不进入作品生产"
                ]
                payload["fallbackStage"] = "download"
            stage_dir = content_object.content_object_stage_dir(task_id, batch_id, ref, "3.compose")
            stage_dir.mkdir(parents=True, exist_ok=True)
            write_json(stage_dir / "compose_brief_gate.json", {"payload": payload})

    monkeypatch.setattr("produce.handler.handle_produce", _fake_produce)

    result = run_mod._run_produce_compose(ctx)
    state = run_mod.load_workflow_state(task_id, batch_id)

    assert result.status == "done"
    assert "abandoned 1 deterministic failed ref" in result.message
    abandoned = {
        row["ref"]: row
        for row in state.get("abandonedContentObjects", [])
    }
    assert bad_ref in abandoned
    assert abandoned[bad_ref]["stage"] == "produce_compose"
    assert good_ref not in abandoned

def test_produce_compose_accepts_structured_image_without_article_draft(monkeypatch):
    task_id = _make_task()
    batch_id = "compose_image_no_draft"
    ctx = _ctx(task_id, batch_id)
    ref = "image_ref"
    content_object.register_content_object(
        task_id, batch_id, ref, content_type="image", angle="画报", title="图片作品"
    )
    write_writing_pack(task_id, batch_id, ref, {"carrier": "image", "assets": [{"assetId": "a1"}]})
    prompt = prompt_path(task_id, batch_id, ref)
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("prompt", encoding="utf-8")
    write_image_evidence_draft(task_id, batch_id, ref, selected_asset_ids=["a1"])
    write_json(
        content_object.content_object_stage_dir(task_id, batch_id, ref, "3.compose")
        / "compose_brief_gate.json",
        {"payload": {"passed": True}},
    )

    calls: list[argparse.Namespace] = []
    monkeypatch.setattr("produce.handler.handle_produce", lambda ns: calls.append(ns))

    result = run_mod._run_produce_compose(ctx)

    assert result.status == "done"
    assert calls == []
    assert not draft_article_path(task_id, batch_id, ref).exists()

def test_runtime_materialization_issues_report_missing_planned_ref():
    task_id = _make_task()
    batch_id = "runtime_missing_materialized"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "image_ref", content_type="image", angle="画报", title="图片作品"
    )

    issues = run_mod._runtime_materialization_issues(ctx, ["image_ref"])

    assert issues == ["release missing planned post ref(s): image_ref"]

def test_produce_review_all_green_materializes_before_exit_gate(monkeypatch):
    task_id = _make_task()
    batch_id = "review_all_green_materializes"
    ctx = _ctx(task_id, batch_id)
    ref = "article_ref"
    content_object.register_content_object(
        task_id, batch_id, ref, content_type="article", angle="攻略", title="OK"
    )
    compose_dir = content_object.content_object_dir(task_id, batch_id, ref) / "3.compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    write_json(compose_dir / "writing_pack.json", {"baseDraftText": _long_base_text("OK")})
    review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
    review_dir.mkdir(parents=True, exist_ok=True)
    write_json(review_dir / "review_gate.json", {"passed": True})

    calls: list[tuple[str, list[str]]] = []

    def _fake_materialize(_ctx, refs):
        calls.append(("materialize", list(refs)))
        return []

    def _fake_gate(_ctx, refs):
        calls.append(("gate", list(refs)))
        return []

    monkeypatch.setattr(run_mod, "_review_gate_is_stale", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(run_mod, "_materialize_reviewed_refs", _fake_materialize)
    monkeypatch.setattr(run_mod, "_produce_exit_issues", _fake_gate)

    result = run_mod._run_produce_review(ctx)

    assert result.status == "done"
    assert calls == [("materialize", [ref]), ("gate", [ref])]

def test_produce_review_subset_retry_materializes_all_active_refs(monkeypatch):
    task_id = _make_task()
    batch_id = "review_subset_retry_materializes_all_active"
    ctx = _ctx(task_id, batch_id)
    article_ref = "article_needs_review"
    image_ref = "image_already_reviewed"
    content_object.register_content_object(
        task_id, batch_id, article_ref, content_type="article", angle="攻略", title="Article"
    )
    content_object.register_content_object(
        task_id, batch_id, image_ref, content_type="image", angle="画报", title="Image"
    )
    for ref in (article_ref, image_ref):
        compose_dir = content_object.content_object_dir(task_id, batch_id, ref) / "3.compose"
        compose_dir.mkdir(parents=True, exist_ok=True)
        write_json(compose_dir / "writing_pack.json", {"baseDraftText": _long_base_text(ref)})
    image_review_dir = content_object.content_object_dir(task_id, batch_id, image_ref) / "5.review"
    image_review_dir.mkdir(parents=True, exist_ok=True)
    write_json(image_review_dir / "review_gate.json", {"passed": True})

    calls: list[tuple[str, list[str]]] = []

    def _fake_handle_produce(ns):
        refs = [item for item in str(ns.refs or "").split(",") if item]
        calls.append(("handle", refs))
        article_review_dir = content_object.content_object_dir(task_id, batch_id, article_ref) / "5.review"
        article_review_dir.mkdir(parents=True, exist_ok=True)
        write_json(article_review_dir / "review_gate.json", {"passed": True})

    def _fake_materialize(_ctx, refs):
        calls.append(("materialize", list(refs)))
        return []

    def _fake_gate(_ctx, refs):
        calls.append(("gate", list(refs)))
        return []

    monkeypatch.setattr("produce.handler.handle_produce", _fake_handle_produce)
    monkeypatch.setattr(run_mod, "_review_gate_is_stale", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(run_mod, "_materialize_reviewed_refs", _fake_materialize)
    monkeypatch.setattr(run_mod, "_produce_exit_issues", _fake_gate)
    monkeypatch.setattr(
        run_mod,
        "_batch_reducer_payload",
        lambda _ctx, refs=None: [
            {
                "ref": article_ref,
                "article": _long_base_text("batch reducer"),
                "writingIntent": "planning_consultation",
                "baseSourceRef": "source/a",
                "baseSourceReusePolicy": "",
            }
        ],
    )

    result = run_mod._run_produce_review(ctx)

    assert result.status == "done"
    assert calls == [
        ("handle", [article_ref]),
        ("materialize", [article_ref, image_ref]),
        ("gate", [article_ref, image_ref]),
    ]

def test_produce_review_abandons_legacy_short_base_draft_refs(monkeypatch):
    task_id = _make_task()
    batch_id = "review_short_base_draft_legacy"
    ctx = _ctx(task_id, batch_id)
    good_ref = "article_good"
    bad_ref = "article_short"
    for ref, title, base_text in (
        (good_ref, "OK", _long_base_text("OK")),
        (bad_ref, "SHORT", "短底稿"),
    ):
        content_object.register_content_object(
            task_id, batch_id, ref, content_type="article", angle="攻略", title=title
        )
        compose_dir = content_object.content_object_dir(task_id, batch_id, ref) / "3.compose"
        compose_dir.mkdir(parents=True, exist_ok=True)
        write_json(compose_dir / "writing_pack.json", {"baseDraftText": base_text})
        review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review_gate.json", {"passed": True})

    calls: list[tuple[str, list[str]]] = []

    def _fake_materialize(_ctx, refs):
        calls.append(("materialize", list(refs)))
        return []

    def _fake_gate(_ctx, refs):
        refs = list(refs)
        calls.append(("gate", refs))
        return []

    monkeypatch.setattr(run_mod, "_review_gate_is_stale", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(run_mod, "_materialize_reviewed_refs", _fake_materialize)
    monkeypatch.setattr(run_mod, "_produce_exit_issues", _fake_gate)
    monkeypatch.setattr("produce.handler.handle_produce", lambda _ns: (_ for _ in ()).throw(AssertionError("no reauthor loop")))

    result = run_mod._run_produce_review(ctx)

    assert result.status == "done"
    assert calls == [
        ("materialize", [good_ref]),
        ("gate", [good_ref]),
    ]
    state = run_mod.load_workflow_state(task_id, batch_id)
    abandoned = state.get("abandonedContentObjects") or []
    assert any(
        row.get("ref") == bad_ref
        and row.get("stage") == "content_plan"
        and "legacy_content_plan_preflight" in row.get("reason", "")
        for row in abandoned
    )

def test_produce_author_checkpoint_abandons_short_base_draft_before_agent():
    task_id = _make_task()
    batch_id = "author_short_base_draft_preflight"
    ctx = _ctx(task_id, batch_id)
    good_ref = "article_good"
    bad_ref = "article_short"
    for ref, title, base_text in (
        (good_ref, "OK", _long_base_text("OK")),
        (bad_ref, "SHORT", "短底稿"),
    ):
        content_object.register_content_object(
            task_id, batch_id, ref, content_type="article", angle="攻略", title=title
        )
        compose_dir = content_object.content_object_dir(task_id, batch_id, ref) / "3.compose"
        compose_dir.mkdir(parents=True, exist_ok=True)
        write_json(compose_dir / "writing_pack.json", {"baseDraftText": base_text})

    good_draft = draft_article_path(task_id, batch_id, good_ref)
    good_draft.parent.mkdir(parents=True, exist_ok=True)
    good_draft.write_text(
        "# OK\n\n" + _long_base_text("OK"),
        encoding="utf-8",
    )
    write_json(
        draft_meta_path(task_id, batch_id, good_ref),
        {
            "generator": "agent",
            "model": "cursor",
            "agentRunId": "run-test",
            "citedSourcePaths": ["source.md"],
            "promptSha256": "sha256:prompt",
            "writingPackSha256": "sha256:pack",
            "sourceBundleSha256": "sha256:source",
            "draftSha256": "sha256:draft",
        },
    )

    ok, pending = run_mod._drafts_authored(ctx)

    assert ok is True
    assert pending == []
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert any(
        row.get("ref") == bad_ref
        and row.get("stage") == "content_plan"
        and "legacy_content_plan_author_preflight" in row.get("reason", "")
        for row in (state.get("abandonedContentObjects") or [])
    )

def test_completion_gate_ignores_stale_agent_run_for_abandoned_refs():
    task_id = _make_task()
    batch_id = "completion_ignores_abandoned_agent"
    ctx = _ctx(task_id, batch_id)
    state = {
        "waitingCheckpoint": None,
        "failedObjects": [],
        "abandonedContentObjects": [
            {
                "ref": "ref_dead",
                "stage": "produce_author",
                "reason": "agent failed",
                "status": "abandoned",
            }
        ],
        "lastAgentRun": {
            "stage": "produce_author",
            "jobCount": 1,
            "plannedJobCount": 1,
            "refs": ["ref_dead"],
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "outcomes": [{"ref": "ref_dead", "started": False, "status": "error"}],
        },
    }

    assert run_mod._workflow_completion_issues(ctx, state) == []

def test_completion_gate_blocks_active_failed_agent_run():
    task_id = _make_task()
    batch_id = "completion_blocks_active_agent"
    ctx = _ctx(task_id, batch_id)
    state = {
        "waitingCheckpoint": None,
        "failedObjects": [],
        "abandonedContentObjects": [],
        "lastAgentRun": {
            "stage": "produce_author",
            "jobCount": 1,
            "plannedJobCount": 1,
            "refs": ["ref_active"],
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "outcomes": [{"ref": "ref_active", "started": False, "status": "error"}],
        },
    }

    issues = run_mod._workflow_completion_issues(ctx, state)
    assert "lastAgentRun.infrastructureFailures=1" in issues

def test_produce_review_bulk_failure_retries_within_bounded_budget(monkeypatch):
    # 底稿中心快速失败：移除 20% bulk-repair 闸门后，批量失败不再阻塞整批等待人工诊断；
    # 失败 ref 一律按有界 ReAct 预算重写（写 repair report + invalidate + requeue）。
    task_id = _make_task()
    ctx = _ctx(task_id, "bulk_review")
    refs = [f"ref_{idx}" for idx in range(47)]
    invalidated: list[str] = []
    reports: list[str] = []

    monkeypatch.setattr(
        "task.run._produce_review_retry_refs",
        lambda *_args, **_kwargs: (refs, {ref: ["travelogueDensity: opening lacks a real hook"] for ref in refs}),
    )
    monkeypatch.setattr(
        "task.run._write_retry_reports_for_refs",
        lambda _ctx, *, refs, issue_map, target_stage: reports.extend(refs),
    )
    monkeypatch.setattr(
        "task.run._invalidate_ref_for_retry",
        lambda _ctx, ref: invalidated.append(ref) or True,
    )
    monkeypatch.setattr(
        "task.run._purge_author_queue_for_stale_workflow",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "task.object_queue.requeue_refs",
        lambda _task, _batch, reset, _stage, reason=None: list(reset),
    )

    prepared = run_mod._prepare_produce_review_retry(
        ctx,
        run_mod.StageResult(
            "produce_review",
            run_mod.AUTO,
            "failed",
            "发布门未过",
            fallback_stage="produce_compose",
            issues=["many failures"],
        ),
        "produce_compose",
    )

    assert prepared is True
    assert sorted(reports) == sorted(refs)
    assert sorted(invalidated) == sorted(refs)


def test_produce_review_budget_exhaustion_abandons_when_partial_allowed(monkeypatch):
    # 底稿中心快速失败：produce_review 有界重试耗尽后，allowPartialContent 下弃稿仍未过门的
    # 对象并重跑剩余内容，而非整批转人工空转。
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "review_budget_exhaustion"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    bad_ref = "ref_persistent_fail"

    monkeypatch.setattr(
        "task.run._produce_review_retry_refs",
        lambda *_args, **_kwargs: ([bad_ref], {bad_ref: ["travelogueDensity: opening lacks a real hook"]}),
    )

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="produce_compose",
        issues=[f"{bad_ref}: travelogueDensity"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"produce_review": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is True
    assert "produce_review" not in completed
    abandoned = {
        str(row.get("ref")): row
        for row in run_mod.load_workflow_state(task_id, batch_id).get("abandonedContentObjects", [])
    }
    assert bad_ref in abandoned
    assert abandoned[bad_ref]["stage"] == "produce_review"


def test_produce_review_budget_exhaustion_manual_when_partial_disallowed(monkeypatch):
    # 不允许部分交付时，保持原有“转人工”语义，不擅自弃稿。
    task_id = _make_task(workflow_policy={"allowPartialContent": False})
    batch_id = "review_budget_exhaustion_strict"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    bad_ref = "ref_persistent_fail_strict"

    monkeypatch.setattr(
        "task.run._produce_review_retry_refs",
        lambda *_args, **_kwargs: ([bad_ref], {bad_ref: ["travelogueDensity: opening lacks a real hook"]}),
    )

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="produce_compose",
        issues=[f"{bad_ref}: travelogueDensity"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"produce_review": run_mod.MAX_REACT_REWINDS}
    run_mod.save_workflow_state(state)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is False
    abandoned = {
        str(row.get("ref"))
        for row in run_mod.load_workflow_state(task_id, batch_id).get("abandonedContentObjects", [])
    }
    assert bad_ref not in abandoned

