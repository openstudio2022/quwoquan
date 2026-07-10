from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_publish_stage_materializes_task_inputs_and_release():
    task_id = _make_task()
    batch_id = "publish1"
    _seed_publish_inputs(task_id, batch_id)
    first_title = f"{_EID} 规划咨询"
    post_dir = batch_posts_root(task_id, batch_id) / "article" / "攻略" / first_title / "001"
    (post_dir / "_author_run.py").write_text("raise RuntimeError('must not ship')\n", encoding="utf-8")
    (post_dir / "_article_body.md").write_text("helper", encoding="utf-8")
    oq.enqueue_ref_job(task_id, batch_id, f"{_EID} 攻略", "author", max_attempts=1)
    job = oq.acquire_lease(task_id, batch_id, worker="w1", stage="author")
    assert job is not None
    oq.fail_job(task_id, batch_id, job["jobId"], job["lease"], error="dead now")
    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)
    assert result.status == "done", result.message
    assert task_entities(task_id).exists()
    assert task_tags(task_id).exists()
    assert task_shared_dir(task_id).is_dir()
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    assert (release_root_dir / "release_manifest.json").exists()
    assert (release_root_dir / "entities" / "地点" / "景区" / _EID / "page.md").exists()
    assert not (release_root_dir / "entity_pages").exists()
    assert not (release_root_dir / "graph").exists()
    assert not (release_root_dir / "tags").exists()
    release_post_dir = release_root_dir / "posts" / "article" / "攻略" / first_title / "001"
    assert (release_post_dir / "5.review" / "review_ledger.json").exists()
    assert not (release_post_dir / "_author_run.py").exists()
    assert not (release_post_dir / "_article_body.md").exists()
    queue = oq.queue_summary(task_id, batch_id)
    assert queue["total"] == 0, queue

def test_publish_stage_allows_site_supply_dynamic_posts_without_entity_homepages():
    task_id = _make_task(workflow_policy={"siteSupplyDynamicContentPlan": True})
    batch_id = "publish_site_supply_no_homepage"
    _seed_publish_inputs(task_id, batch_id)
    shutil.rmtree(batch_root(task_id, batch_id) / "entities", ignore_errors=True)
    shutil.rmtree(task_data(task_id).entities_dir(), ignore_errors=True)
    shutil.rmtree(batch_posts_root(task_id, batch_id) / "image", ignore_errors=True)
    shared = batch_root(task_id, batch_id) / "_shared"
    write_json(shared / "content_plan_packet.json", {
        "schemaVersion": "quwoquan_data.content_plan_packet",
        "taskId": task_id,
        "batchId": batch_id,
        "generatedBy": "site_supply_content_plan_bridge",
        "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": "real_100"},
        "items": [
            {
                "ref": f"{_EID}-article-001",
                "kind": "entity",
                "carrier": "article",
                "entityRefs": [f"/entity/地点/景区/{_EID}"],
            },
            {
                "ref": f"{_EID}-article-002",
                "kind": "entity",
                "carrier": "article",
                "entityRefs": [f"/entity/地点/景区/{_EID}"],
            },
        ],
    })

    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)

    assert result.status == "done", result.message
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    assert not (release_root_dir / "entities" / "地点" / "景区" / _EID / "page.md").exists()
    post_manifests = sorted((release_root_dir / "posts").rglob("manifest.json"))
    assert post_manifests
    first_manifest = read_json(post_manifests[0])
    assert first_manifest["entityRefs"] == []
    assert first_manifest["pendingEntityMentions"][0]["sourceEntityRef"] == f"/entity/地点/景区/{_EID}"

def test_publish_stage_allows_partial_posts_without_entity_homepages_for_entity_batch():
    task_id = _make_task()
    batch_id = "publish_entity_batch_no_homepage"
    _seed_publish_inputs(task_id, batch_id)
    shutil.rmtree(batch_root(task_id, batch_id) / "entities", ignore_errors=True)
    shutil.rmtree(task_data(task_id).entities_dir(), ignore_errors=True)

    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)

    assert result.status == "done", result.message
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    assert not (release_root_dir / "entities" / "地点" / "景区" / _EID / "page.md").exists()
    post_manifests = sorted((release_root_dir / "posts").rglob("manifest.json"))
    assert post_manifests
    first_manifest = read_json(post_manifests[0])
    assert first_manifest["entityRefs"] == []
    assert first_manifest["pendingEntityMentions"][0]["sourceEntityRef"] == f"/entity/地点/景区/{_EID}"

def test_publish_stage_reasoned_rejects_articles_without_content_anchor():
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "allowQuotaShortfall": True,
            "elasticOverfetch": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    batch_id = "publish_reasoned_reject_no_homepage_anchor"
    _seed_publish_inputs(task_id, batch_id)
    shutil.rmtree(batch_root(task_id, batch_id) / "entities", ignore_errors=True)
    shutil.rmtree(task_data(task_id).entities_dir(), ignore_errors=True)

    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)

    assert result.status == "done", result.message
    state = read_json(batch_workflow_state_path(task_id, batch_id))
    abandoned = {
        item.get("ref"): item
        for item in state.get("abandonedContentObjects", [])
        if item.get("status") == "abandoned"
    }
    assert abandoned[f"{_EID}-article-001"]["stage"] == "publish"
    assert abandoned[f"{_EID}-article-002"]["stage"] == "publish"
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    article_manifests = sorted((release_root_dir / "posts" / "article").rglob("manifest.json"))
    image_manifests = sorted((release_root_dir / "posts" / "image").rglob("manifest.json"))
    assert article_manifests == []
    assert image_manifests

def test_post_verify_scope_excludes_unrelated_green_refs():
    from verify.verify_content_quality import verify_posts

    root = _TMP / "scoped_post_verify" / "posts"
    good = root / "article" / "攻略" / "Good" / "1"
    bad = root / "article" / "攻略" / "Bad" / "1"
    for post_dir, title, body in (
        (good, "Good", "这是一个正常正文。" * 220),
        (bad, "Bad", "这个正文含有批次边界词。" * 220),
    ):
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "article.md").write_text(body, encoding="utf-8")
        write_json(
            post_dir / "manifest.json",
            {
                "topicId": title,
                "carrier": "article",
                "sourceTaskId": "task",
                "tagRefs": ["tag/a", "tag/b"],
                "entityRefs": ["地点/景区/测试"],
                "normalizedEntityRefs": ["entity:地点:景区:测试"],
                "assets": [],
                "sourceUrls": ["https://example.com/source"],
                "intersectionHints": [],
            },
        )

    scoped_good = verify_posts(root, post_rels={"posts/article/攻略/Good/1"})
    assert not any("forbidden phrase found: 批次" in issue for issue in scoped_good)

    scoped_bad = verify_posts(root, post_rels={"posts/article/攻略/Bad/1"})
    assert any("forbidden phrase found: 批次" in issue for issue in scoped_bad)

def test_review_retry_maps_release_gate_issue_after_object_gates_are_green():
    task_id = _make_task()
    batch_id = "review_retry_release_issue"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    for ref in ("ref_ok", "ref_bad"):
        review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review_gate.json", {"passed": True})

    bad_rel = content_object.content_object_rel(task_id, batch_id, "ref_bad")
    refs, issue_map = run_mod._produce_review_retry_refs(
        ctx,
        [
            f"{bad_rel}/article.md: forbidden phrase found: 批次",
            "release missing planned post ref(s): ref_bad",
        ],
    )

    assert refs == ["ref_bad"]
    assert "批次" in issue_map["ref_bad"][0]
    assert "release missing planned post ref" in issue_map["ref_bad"][1]

def test_release_only_ship_report_records_no_import_claim():
    from ship.handler import write_release_only_ship_report

    task_id = _make_task()
    batch_id = "release_only_ship_report"
    path = write_release_only_ship_report(
        task_id=task_id,
        batch_id=batch_id,
        release_id="release_1",
        summary={"entityCount": 1, "postCount": 2},
    )

    payload = read_json(path)
    assert payload["closureType"] == "release_only"
    assert payload["sourceReleaseId"] == "release_1"
    assert payload["importRequested"] is False
    assert payload["importReports"] == []
