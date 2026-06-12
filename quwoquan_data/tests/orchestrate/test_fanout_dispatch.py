"""fanout_dispatch contract tests：建 task + enqueue 叶子 + 幂等可重放。

可直接运行：python3 quwoquan_data/tests/orchestrate/test_fanout_dispatch.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 隔离 runtime + committed 根（避免污染仓库 quwoquan_data/tasks）
_TMP = tempfile.mkdtemp(prefix="qwq_fanout_dispatch_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common import fanout_plan as fp  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import store  # noqa: E402


def _seed_source_task(task_id: str = "旅行/地域/四川省/景区/源任务") -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="源任务",
        category="景区",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "九寨沟"}],
        },
        content={"angles": ["攻略", "体验"], "quotas": {"entityArticles": 2, "routeArticles": 1}},
        created_by="test",
    )
    spec["taskId"] = task_id
    store.save_spec(spec)
    store.save_progress(store.init_progress(task_id, remaining=["地点/景区/九寨沟"]))
    return task_id


def _frozen_plan(plan_id: str) -> dict:
    source_task_id = _seed_source_task(f"旅行/地域/四川省/景区/{plan_id}_源任务")
    plan = fp.new_plan(
        plan_id,
        "全国景点主页",
        "travel",
        defaults={
            "strategy": "by-partition",
            "concurrency": 3,
            "entityType": "地点/景区",
            "taskName": f"{plan_id}_全国景点主页",
        },
        source_task_id=source_task_id,
    )
    fp.add_partition(plan, "四川省")
    fp.add_partition(plan, "云南省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}, {"name": "稻城亚丁"}])
    fp.add_leaves(plan, ["云南省"], [{"name": "玉龙雪山"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def test_dispatch_requires_frozen():
    plan = fp.new_plan("p_unfrozen", "g", "travel")
    fp.add_partition(plan, "A")
    fp.add_leaves(plan, ["A"], [{"name": "x"}])
    try:
        fd.dispatch(plan)
    except ValueError as exc:
        assert "frozen" in str(exc)
    else:
        raise AssertionError("dispatch must require frozen plan")


def test_dispatch_creates_tasks_and_enqueues_leaves():
    plan = _frozen_plan("p_dispatch1")
    report = fd.dispatch(plan)
    assert report["totals"]["partitions"] == 2
    assert len(report["createdTasks"]) == 2
    assert report["contentRefAuthorMode"] is True
    assert report["totals"]["leafRefsPlanned"] == 3
    assert report["totals"]["leavesEnqueued"] == 0
    # committed task spec 真的落盘
    sc_task = report["perPartition"][0]["taskId"]
    assert store.spec_exists(sc_task)
    summary = oq.queue_summary(sc_task, "fanout_p_dispatch1")
    assert summary["total"] == 0


def test_dispatch_creates_partition_baseline_and_inherits_region():
    from _common.io import read_json, read_ndjson
    from _common.paths import task_baseline_freeze_packet_path, task_catalog

    plan = _frozen_plan("p_dispatch_baseline")
    report = fd.dispatch(plan)
    sc_task = report["perPartition"][0]["taskId"]
    yn_task = report["perPartition"][1]["taskId"]
    spec = store.load_spec(sc_task)
    yn_spec = store.load_spec(yn_task)
    assert str((spec.get("scope") or {}).get("region") or "") == "四川省"
    assert (spec.get("content") or {}).get("angles") == ["攻略", "体验"], spec
    assert "regions" not in (((spec.get("content") or {}).get("conditionAxes")) or {}), spec
    assert "regions" not in (((yn_spec.get("content") or {}).get("conditionAxes")) or {}), yn_spec
    assert ((spec.get("content") or {}).get("quotas") or {}).get("entityArticles") == 1, spec
    assert ((spec.get("content") or {}).get("quotas") or {}).get("routeArticles") == 1, spec
    assert ((yn_spec.get("content") or {}).get("quotas") or {}).get("entityArticles") == 1, yn_spec
    packet = read_json(task_baseline_freeze_packet_path(sc_task))
    assert packet["command"] == "data baseline", packet
    rows = read_ndjson(task_catalog(sc_task))
    assert rows and rows[0]["region"] == "四川省", rows


def test_dispatch_distributes_source_task_quotas_by_partition_leaf_weight():
    plan = _frozen_plan("p_dispatch_quota_split")
    report = fd.dispatch(plan)
    sc_task = report["perPartition"][0]["taskId"]
    yn_task = report["perPartition"][1]["taskId"]
    sc_q = ((store.load_spec(sc_task).get("content") or {}).get("quotas") or {})
    yn_q = ((store.load_spec(yn_task).get("content") or {}).get("quotas") or {})
    assert (sc_q.get("entityArticles"), sc_q.get("routeArticles")) == (1, 1), sc_q
    assert int(yn_q.get("entityArticles") or 0) == 1, yn_q
    assert int(yn_q.get("routeArticles") or 0) == 0, yn_q
    assert int(sc_q.get("entityArticles") or 0) + int(yn_q.get("entityArticles") or 0) == 2
    assert int(sc_q.get("routeArticles") or 0) + int(yn_q.get("routeArticles") or 0) == 1


def test_dispatch_is_idempotent():
    plan = _frozen_plan("p_dispatch2")
    r1 = fd.dispatch(plan)
    r2 = fd.dispatch(plan)
    assert r1["totals"]["leavesEnqueued"] == r2["totals"]["leavesEnqueued"]
    # 第二次不再新建 task
    assert r2["totals"]["tasksCreated"] == 0
    # 队列总数不翻倍
    assert r1["perPartition"][0]["queueSummary"]["total"] == r2["perPartition"][0]["queueSummary"]["total"]


def test_dispatch_state_persisted():
    plan = _frozen_plan("p_dispatch3")
    fd.dispatch(plan)
    state = fd.load_dispatch_state("p_dispatch3")
    assert state is not None
    assert state["planId"] == "p_dispatch3"
    assert state["strategy"] == "by-partition"


def test_strategy_invariant_job_set():
    """sourceTask 派生内容型 fanout 只允许 by-partition/flat-pool，by-leaf 应阻断。"""
    plan_a = _frozen_plan("p_inv_a")
    plan_b = _frozen_plan("p_inv_b")
    try:
        fd.dispatch(plan_a, strategy="by-leaf", concurrency=5)
    except ValueError as exc:
        assert "by-partition/flat-pool" in str(exc)
    else:
        raise AssertionError("content-ref author mode must reject by-leaf")
    rb = fd.dispatch(plan_b, strategy="flat-pool", concurrency=1)
    assert rb["totals"]["leafRefsPlanned"] == 3
    assert rb["totals"]["leavesEnqueued"] == 0


def test_rollup_aggregates_partitions():
    from task import fanout_rollup
    from task import object_queue as _oq
    from _common import content_object
    from _common.draft_io import write_placeholder_draft, write_prompt, write_writing_pack

    plan = _frozen_plan("p_rollup")
    report0 = fd.dispatch(plan)
    # 内容型 fanout：先 compose 后同步 content-ref author jobs，再让四川一个 ref 成功。
    sc = report0["perPartition"][0]["taskId"]
    yn = report0["perPartition"][1]["taskId"]
    batch = "fanout_p_rollup"
    brief = {
        "titleHint": "九寨沟·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["九寨沟 事实"],
        "baseSourceRef": "posts/article/攻略/九寨沟·攻略/1/1.download/sources/01.base/source.md",
    }
    content_object.write_brief_object(sc, batch, "route_九寨沟", brief, content_type="article")
    write_writing_pack(
        sc,
        batch,
        "route_九寨沟",
        {
            "ref": "route_九寨沟",
            "title": "九寨沟·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["九寨沟 事实"],
            "baseSourceRef": brief["baseSourceRef"],
            "sourcePaths": [brief["baseSourceRef"]],
            "sourceUrls": ["https://example.invalid/jzg"],
            "assets": [],
        },
    )
    write_prompt(sc, batch, "route_九寨沟", "# 九寨沟\n\n写作提示。")
    write_placeholder_draft(sc, batch, "route_九寨沟")
    plan = {
        **plan,
        "defaults": {
            **dict(plan.get("defaults") or {}),
            "budget": {
                **dict((plan.get("defaults") or {}).get("budget") or {}),
                "maxStartupFailures": 1,
            },
        },
    }
    fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])

    yn_brief = {
        "titleHint": "玉龙雪山·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["玉龙雪山 事实"],
        "baseSourceRef": "posts/article/攻略/玉龙雪山·攻略/1/1.download/sources/01.base/source.md",
    }
    content_object.write_brief_object(yn, batch, "route_玉龙雪山", yn_brief, content_type="article")
    write_writing_pack(
        yn,
        batch,
        "route_玉龙雪山",
        {
            "ref": "route_玉龙雪山",
            "title": "玉龙雪山·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["玉龙雪山 事实"],
            "baseSourceRef": yn_brief["baseSourceRef"],
            "sourcePaths": [yn_brief["baseSourceRef"]],
            "sourceUrls": ["https://example.invalid/yulong"],
            "assets": [],
        },
    )
    write_prompt(yn, batch, "route_玉龙雪山", "# 玉龙雪山\n\n写作提示。")
    write_placeholder_draft(yn, batch, "route_玉龙雪山")
    fd.sync_content_author_jobs(plan, {"taskId": yn, "batchId": batch}, partition_path=["云南省"])

    job = _oq.acquire_lease(sc, batch, worker="w", stage="author")
    _oq.complete_job(sc, "fanout_p_rollup", job["jobId"], job["lease"])

    report = fanout_rollup.rollup("p_rollup")
    assert report["totals"]["leaves"] == 2
    assert report["totals"]["succeeded"] == 1
    assert report["slo"]["partitionsTotal"] == 2
    assert 0.0 < report["slo"]["progress"] < 1.0


def test_sync_content_author_jobs_revives_dead_startup_jobs():
    from _common import content_object
    from _common.draft_io import write_agent_draft, write_placeholder_draft, write_prompt, write_writing_pack
    from _common.io import read_json

    plan = _frozen_plan("p_sync_revive")
    plan = {
        **plan,
        "defaults": {
            **dict(plan.get("defaults") or {}),
            "budget": {
                **dict((plan.get("defaults") or {}).get("budget") or {}),
                "maxStartupFailures": 1,
            },
        },
    }
    report = fd.dispatch(plan)
    sc = report["perPartition"][0]["taskId"]
    batch = "fanout_p_sync_revive"
    brief = {
        "titleHint": "九寨沟·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["九寨沟 事实"],
        "baseSourceRef": "posts/article/攻略/九寨沟·攻略/1/1.download/sources/01.base/source.md",
    }
    content_object.write_brief_object(sc, batch, "route_九寨沟", brief, content_type="article")
    write_writing_pack(
        sc,
        batch,
        "route_九寨沟",
        {
            "ref": "route_九寨沟",
            "title": "九寨沟·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["九寨沟 事实"],
            "baseSourceRef": brief["baseSourceRef"],
            "sourcePaths": [brief["baseSourceRef"]],
            "sourceUrls": ["https://example.invalid/jzg"],
            "assets": [],
        },
    )
    write_prompt(sc, batch, "route_九寨沟", "# 九寨沟\n\n写作提示。")
    write_placeholder_draft(sc, batch, "route_九寨沟")
    fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])
    job_id = oq.stable_job_id(sc, batch, "route_九寨沟", "author")
    job = oq.acquire_lease(sc, batch, worker="w1", stage="author", ref="route_九寨沟")
    assert job is not None
    oq.fail_job(
        sc,
        batch,
        job["jobId"],
        job["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=False,
        startup_failure=True,
    )
    dead_payload = read_json(oq._job_path(sc, batch, job_id))
    assert dead_payload["state"] == oq.STATE_DEAD
    fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])
    revived_payload = read_json(oq._job_path(sc, batch, job_id))
    assert revived_payload["state"] == oq.STATE_QUEUED
    assert revived_payload["startupFailureCount"] == 0
    assert revived_payload["lastError"] is None


def test_sync_content_author_jobs_skips_already_authored_refs():
    from _common import content_object
    from _common.draft_io import write_agent_draft, write_placeholder_draft, write_prompt, write_writing_pack

    plan = _frozen_plan("p_sync_skip_authored")
    report = fd.dispatch(plan)
    sc = report["perPartition"][0]["taskId"]
    batch = "fanout_p_sync_skip_authored"
    brief = {
        "titleHint": "九寨沟·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["九寨沟 事实"],
        "baseSourceRef": "posts/article/攻略/九寨沟·攻略/1/1.download/sources/01.base/source.md",
    }
    content_object.write_brief_object(sc, batch, "route_九寨沟", brief, content_type="article")
    write_writing_pack(
        sc,
        batch,
        "route_九寨沟",
        {
            "ref": "route_九寨沟",
            "title": "九寨沟·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["九寨沟 事实"],
            "baseSourceRef": brief["baseSourceRef"],
            "sourcePaths": [brief["baseSourceRef"]],
            "sourceUrls": ["https://example.invalid/jzg"],
            "assets": [],
        },
    )
    write_prompt(sc, batch, "route_九寨沟", "# 九寨沟\n\n写作提示。")
    write_placeholder_draft(sc, batch, "route_九寨沟")
    write_agent_draft(
        sc,
        batch,
        "route_九寨沟",
        "# 九寨沟\n\n这是一篇已经完成的正文。",
        model="runner-test",
        cited_source_paths=[brief["baseSourceRef"]],
        covered_facts=["九寨沟 事实"],
        session_trace="done-session",
    )
    result = fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])
    assert result["preparedRefs"] == []
    assert result["skippedAuthoredRefs"] == ["route_九寨沟"]
    summary = oq.queue_summary(sc, batch)
    assert summary["total"] == 0


def test_sync_content_author_jobs_refreshes_packet_for_authored_ref():
    from _common import content_object
    from _common.draft_io import draft_package_dir, write_agent_draft, write_placeholder_draft, write_prompt, write_writing_pack

    plan = _frozen_plan("p_sync_refresh_packet")
    report = fd.dispatch(plan)
    sc = report["perPartition"][0]["taskId"]
    batch = "fanout_p_sync_refresh_packet"
    old_source = "posts/article/攻略/都江堰·攻略/1/1.download/sources/01.old/source.md"
    new_source = "posts/article/攻略/都江堰·攻略/1/1.download/sources/04.new/source.md"
    brief = {
        "titleHint": "都江堰·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["都江堰 事实"],
        "baseSourceRef": old_source,
    }
    content_object.write_brief_object(sc, batch, "route_都江堰", brief, content_type="article")
    write_writing_pack(
        sc,
        batch,
        "route_都江堰",
        {
            "ref": "route_都江堰",
            "title": "都江堰·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["都江堰 事实"],
            "baseSourceRef": old_source,
            "sourcePaths": [old_source],
            "sourceUrls": ["https://example.invalid/old"],
            "assets": [],
        },
    )
    write_prompt(sc, batch, "route_都江堰", "# 都江堰\n\n写作提示。")
    write_placeholder_draft(sc, batch, "route_都江堰")
    write_agent_draft(
        sc,
        batch,
        "route_都江堰",
        "# 都江堰\n\n这是一篇已经完成的正文。",
        model="runner-test",
        cited_source_paths=[old_source],
        covered_facts=["都江堰 事实"],
        session_trace="done-session",
    )
    result1 = fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])
    assert result1["preparedRefs"] == []
    assert result1["skippedAuthoredRefs"] == ["route_都江堰"]

    write_writing_pack(
        sc,
        batch,
        "route_都江堰",
        {
            "ref": "route_都江堰",
            "title": "都江堰·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["都江堰 事实"],
            "baseSourceRef": new_source,
            "sourcePaths": [new_source],
            "sourceUrls": ["https://example.invalid/new"],
            "assets": [],
        },
    )
    result2 = fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"])
    assert result2["preparedRefs"] == []
    assert result2["skippedAuthoredRefs"] == ["route_都江堰"]
    packet = json.loads((draft_package_dir(sc, batch, "route_都江堰") / "author_job_packet.json").read_text(encoding="utf-8"))
    assert packet["baseSourceRef"] == new_source
    assert packet["sourcePaths"] == [new_source]
    assert oq.queue_summary(sc, batch)["total"] == 0


def test_sync_content_author_jobs_force_refs_requeues_authored_job():
    from _common import content_object
    from _common.draft_io import write_agent_draft, write_placeholder_draft, write_prompt, write_writing_pack

    plan = _frozen_plan("p_sync_force_ref")
    report = fd.dispatch(plan)
    sc = report["perPartition"][0]["taskId"]
    batch = "fanout_p_sync_force_ref"
    old_source = "posts/article/攻略/都江堰·攻略/1/1.download/sources/01.old/source.md"
    new_source = "posts/article/攻略/都江堰·攻略/1/1.download/sources/04.new/source.md"
    brief = {
        "titleHint": "都江堰·攻略",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["都江堰 事实"],
        "baseSourceRef": old_source,
    }
    content_object.write_brief_object(sc, batch, "route_都江堰", brief, content_type="article")
    write_writing_pack(
        sc,
        batch,
        "route_都江堰",
        {
            "ref": "route_都江堰",
            "title": "都江堰·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["都江堰 事实"],
            "baseSourceRef": old_source,
            "sourcePaths": [old_source],
            "sourceUrls": ["https://example.invalid/old"],
            "assets": [],
        },
    )
    write_prompt(sc, batch, "route_都江堰", "# 都江堰\n\n写作提示。")
    write_placeholder_draft(sc, batch, "route_都江堰")
    write_agent_draft(
        sc,
        batch,
        "route_都江堰",
        "# 都江堰\n\n这是一篇已经完成的正文。",
        model="runner-test",
        cited_source_paths=[old_source],
        covered_facts=["都江堰 事实"],
        session_trace="done-session",
    )
    fd.sync_content_author_jobs(plan, {"taskId": sc, "batchId": batch}, partition_path=["四川省"], force_refs=["route_都江堰"])
    write_writing_pack(
        sc,
        batch,
        "route_都江堰",
        {
            "ref": "route_都江堰",
            "title": "都江堰·攻略",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["都江堰 事实"],
            "baseSourceRef": new_source,
            "sourcePaths": [new_source],
            "sourceUrls": ["https://example.invalid/new"],
            "assets": [],
        },
    )

    result = fd.sync_content_author_jobs(
        plan,
        {"taskId": sc, "batchId": batch},
        partition_path=["四川省"],
        refs=["route_都江堰"],
        force_refs=["route_都江堰"],
    )
    assert result["preparedRefs"] == ["route_都江堰"]
    summary = oq.queue_summary(sc, batch)
    assert summary["byState"]["queued"] == ["route_都江堰"]
    jobs = [json.loads(path.read_text(encoding="utf-8")) for path in oq.queue_dir(sc, batch).glob("*.json")]
    assert len(jobs) == 1
    assert jobs[0]["stage"] == "author"
    assert jobs[0]["mutexKey"] == new_source
    assert jobs[0]["meta"]["baseSourceRef"] == new_source
    assert jobs[0]["meta"]["sourcePaths"] == [new_source]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_dispatch tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
