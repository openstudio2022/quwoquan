"""homepage-only 批次的 content_plan/produce 车道确定性跳过契约。

背景：主页三件套的唯一真相源在 build_homepage/build_validate 车道；
content_plan packet 只承载 article/image/route 篇目合同。历史缺口是
`content_plan_quotas_required` 把 entityHomepagesPerTarget 算进"需要 packet"，
而 `_auto_content_plan` 只认 article/image 配额，导致 homepage-only 批次在
content_plan checkpoint 上进入 clean(删 packet) → auto-skip → 等 Agent 的死循环。
本合同锁定：homepage-only 批次 content_plan/produce 各 stage 确定性 done，
publish 走 entities 实体面。
"""
from __future__ import annotations

from support.task_workflow_fixtures import *  # noqa: F401,F403
from support.task_workflow_fixtures import (
    _EID,
    _ctx,
    _make_task,
    ensure_batch_layout,
    batch_root,
    read_json,
    run_mod,
    store,
    write_json,
)


def _make_homepage_only_task() -> str:
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "minBatchCompletionMode": "best_effort_with_reasoned_rejects",
        }
    )
    spec = store.load_spec(task_id)
    spec.setdefault("content", {})["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }
    store.save_spec(spec)
    return task_id


def test_homepage_only_spec_does_not_require_content_plan_packet():
    from _common.content_plan import content_plan_quotas_required
    from _common.execution_branch import is_homepage_only_spec

    task_id = _make_homepage_only_task()
    spec = store.load_spec(task_id)
    assert is_homepage_only_spec(spec) is True
    assert content_plan_quotas_required(spec) is False


def test_mixed_spec_still_requires_content_plan_packet():
    from _common.content_plan import content_plan_quotas_required
    from _common.execution_branch import is_homepage_only_spec

    task_id = _make_task()
    spec = store.load_spec(task_id)
    assert is_homepage_only_spec(spec) is False
    assert content_plan_quotas_required(spec) is True


def test_homepage_only_content_plan_checkpoint_deterministically_done():
    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_content_plan_skip"
    ensure_batch_layout(task_id, batch_id, "download")
    ctx = _ctx(task_id, batch_id)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "done"
    assert "homepage-only" in result.message


def test_homepage_only_content_plan_cleans_stale_packet_residue():
    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_content_plan_residue"
    ensure_batch_layout(task_id, batch_id, "download")
    root = batch_root(task_id, batch_id)
    stale_packet = root / "_shared" / "content_plan_packet.json"
    stale_index = root / "_shared" / "content_object_index.json"
    write_json(stale_packet, {"schemaVersion": "quwoquan_data.content_plan_packet", "items": []})
    write_json(stale_index, {})
    ctx = _ctx(task_id, batch_id)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "done"
    assert not stale_packet.exists()
    assert not stale_index.exists()


def test_homepage_only_produce_stages_deterministically_done():
    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_produce_skip"
    ensure_batch_layout(task_id, batch_id, "download")
    ctx = _ctx(task_id, batch_id)

    plan = run_mod._run_produce_plan(ctx)
    assert plan.status == "done"
    assert "homepage-only" in plan.message
    # legacy 分支不得为 coverageTargets 生成 article brief。
    assert not (batch_root(task_id, batch_id) / "posts" / "article").exists()

    compose = run_mod._run_produce_compose(ctx)
    assert compose.status == "done"
    assert "homepage-only" in compose.message

    author = run_mod._checkpoint_produce_author(ctx)
    assert author.status == "done"
    assert "homepage-only" in author.message

    annotate = run_mod._run_produce_annotate(ctx)
    assert annotate.status == "done"
    assert "homepage-only" in annotate.message

    review = run_mod._run_produce_review(ctx)
    assert review.status == "done"
    assert "homepage-only" in review.message
    shared = batch_root(task_id, batch_id) / "_shared"
    assert (shared / "base_draft_ledger.json").is_file()
    reducer_gate = read_json(shared / "batch_reducer_gate.json")
    payload = reducer_gate.get("payload") or reducer_gate
    assert payload.get("passed") is True


def _seed_homepage_only_entity(task_id: str, batch_id: str) -> None:
    runtime_batch = batch_root(task_id, batch_id)
    entity_dir = runtime_batch / "entities" / "地点" / "景区" / _EID
    entity_dir.mkdir(parents=True, exist_ok=True)
    write_json(entity_dir / "_entity.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "label": _EID,
        "tagRefs": ["测试省", "景区"],
        "geoTagRef": "测试省",
        "sourceTaskId": task_id,
    })
    (entity_dir / "page.md").write_text(
        f"# {_EID}\n\n{_EID}是 homepage-only 发布契约测试实体主页。",
        encoding="utf-8",
    )
    write_json(entity_dir / "manifest.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "sourceTaskId": task_id,
        "tagRefs": ["测试省", "景区"],
    })
    review_dir = entity_dir / "5.review"
    review_dir.mkdir(exist_ok=True)
    write_json(review_dir / "review.json", {"decision": "approved", "issues": []})


def test_homepage_only_release_assembles_entities_without_posts():
    from publish.assemble import assemble_release

    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_release_assemble"
    ensure_batch_layout(task_id, batch_id, "download")
    _seed_homepage_only_entity(task_id, batch_id)

    release_id = f"{task_id.replace('/', '__')}__{batch_id}"
    root = assemble_release(task_id, release_id, batch_id=batch_id)

    pages = list((root / "entities").rglob("page.md"))
    assert pages, "homepage-only release 必须发布 approved 实体主页"
    assert not list((root / "posts").rglob("manifest.json"))


def test_homepage_only_gate_publish_accepts_entity_only_release():
    from publish.assemble import assemble_release
    from publish.gate import gate_publish

    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_release_gate"
    ensure_batch_layout(task_id, batch_id, "download")
    _seed_homepage_only_entity(task_id, batch_id)

    release_id = f"{task_id.replace('/', '__')}__{batch_id}"
    assemble_release(task_id, release_id, batch_id=batch_id)

    issues = gate_publish(release_id)
    assert "No posts with manifest.json found" not in issues
    assert not any("homepage-only release must contain" in issue for issue in issues)


def test_homepage_only_gate_publish_blocks_release_without_entities():
    from publish.assemble import assemble_release
    from publish.gate import gate_publish
    import shutil

    task_id = _make_homepage_only_task()
    batch_id = "homepage_only_release_gate_empty"
    ensure_batch_layout(task_id, batch_id, "download")

    release_id = f"{task_id.replace('/', '__')}__{batch_id}"
    root = assemble_release(task_id, release_id, batch_id=batch_id)
    entities_dir = root / "entities"
    if entities_dir.exists():
        shutil.rmtree(entities_dir)

    issues = gate_publish(release_id)
    assert any("homepage-only release must contain" in issue for issue in issues)
