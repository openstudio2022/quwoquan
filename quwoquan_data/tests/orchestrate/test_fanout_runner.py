"""fanout_runner contract tests（注入 mock agent_runner，不依赖真实云端）。

覆盖：lease→complete 回写、run 失败分流、startup 失败退避、usage 回写、端到端 drain。

可直接运行：python3 quwoquan_data/tests/orchestrate/test_fanout_runner.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
REPO_ROOT = DATA_ROOT.parent
for _path in (DATA_ROOT, SCRIPTS_ROOT, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_fanout_runner_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common import fanout_plan as fp  # noqa: E402
from _common import content_object  # noqa: E402
from _common.draft_io import read_draft_meta, write_agent_draft, write_placeholder_draft, write_prompt, write_writing_pack  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_root, fanout_run_matrix_path  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import production_contracts as pc  # noqa: E402
from task import store  # noqa: E402
from agent_ops.runners import fanout_runner as fr  # noqa: E402


def _frozen(plan_id: str, names: list[str]) -> dict:
    plan = fp.new_plan(plan_id, "四川景点主页", "travel", defaults={"entityType": "地点/景区"})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": n} for n in names])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def _frozen_prod(plan_id: str, names: list[str]) -> dict:
    plan = fp.new_plan(
        plan_id,
        "四川景点主页",
        "travel",
        defaults={"entityType": "地点/景区", "queueBackend": "reliabletask", "budget": {"maxAttempts": 1}},
    )
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": n} for n in names])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def _seed_source_task(task_id: str) -> str:
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
        content={"angles": ["攻略"], "quotas": {"entityArticles": 2}},
        created_by="test",
    )
    spec["taskId"] = task_id
    store.save_spec(spec)
    store.save_progress(store.init_progress(task_id, remaining=["地点/景区/九寨沟"]))
    return task_id


def _content_plan(plan_id: str, names: list[str]) -> dict:
    source_task_id = _seed_source_task(f"旅行/地域/四川省/景区/{plan_id}_源任务")
    plan = fp.new_plan(
        plan_id,
        "四川景点主页",
        "travel",
        defaults={"entityType": "地点/景区", "strategy": "by-partition"},
        source_task_id=source_task_id,
    )
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": n} for n in names])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def _seed_content_ref(task_id: str, batch_id: str, ref: str) -> None:
    brief = {
        "titleHint": f"{ref} 标题",
        "templateId": "travel.route.guide",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": [f"{ref} 事实"],
        "baseSourceRef": f"posts/article/攻略/{ref} 标题/1/1.download/sources/01.base/source.md",
    }
    content_object.write_brief_object(task_id, batch_id, ref, brief, content_type="article")
    write_writing_pack(
        task_id,
        batch_id,
        ref,
        {
            "ref": ref,
            "title": f"{ref} 标题",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": [f"{ref} 事实"],
            "baseSourceRef": f"posts/article/攻略/{ref} 标题/1/1.download/sources/01.base/source.md",
            "sourcePaths": [f"posts/article/攻略/{ref} 标题/1/1.download/sources/01.base/source.md"],
            "sourceUrls": [f"https://example.invalid/{ref}"],
            "assets": [],
        },
    )
    write_prompt(task_id, batch_id, ref, f"# {ref}\n\n请根据 writing pack 创作正文。")
    write_placeholder_draft(task_id, batch_id, ref)
    source_file = content_object.content_object_stage_dir(task_id, batch_id, ref, "1.download") / "sources" / "01.base" / "source.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(f"# {ref}\n\n{ref} 来源正文。", encoding="utf-8")


def test_all_pass_completes_all():
    plan = _frozen("r_pass", ["九寨沟", "稻城亚丁"])
    fd.dispatch(plan, strategy="flat-pool", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True, tokens=100, cost_usd=0.01)

    report = fr.run_fanout("r_pass", agent_runner=runner, strategy="flat-pool", concurrency=1)
    assert report["completed"] == 2
    assert report["failed"] == 0
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_pass")
    assert summary["byState"].get("succeeded") == ["地点_景区__九寨沟", "地点_景区__稻城亚丁"]


def _write_envelope_from_packet(packet: dict) -> str:
    root = batch_root(str(packet["taskId"]), str(packet["batchId"]))
    output = root / "posts/article/envelope-demo.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("# envelope demo\n\n正文与证据。", encoding="utf-8")
    digest = pc.sha256_file(output)
    envelope = pc.build_agent_result_envelope(
        job=packet,
        files=[{"path": "posts/article/envelope-demo.md", "sha256": digest, "role": "draft"}],
        gates=[pc.build_gate_verdict(gate_id="review", decision="passed", input_hash=digest, output_hash=digest)],
        agent_id="agent-envelope",
        run_id="run-envelope",
    )
    envelope_path = root / "_shared" / "envelopes" / f"{packet['jobId']}.json"
    write_json(envelope_path, envelope)
    return str(envelope_path)


def test_reliabletask_job_completes_only_with_result_envelope():
    _frozen_prod("r_envelope_ok", ["九寨沟"])
    fd.dispatch(fp.load_plan("r_envelope_ok"), strategy="flat-pool", concurrency=1)

    def runner(packet):
        return fr.RunOutcome(
            started=True,
            status="finished",
            passed=True,
            envelope_path=_write_envelope_from_packet(dict(packet)),
            run_id="run-envelope",
            agent_id="agent-envelope",
        )

    report = fr.run_fanout("r_envelope_ok", agent_runner=runner, strategy="flat-pool", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_envelope_ok")
    assert report["completed"] == 1
    assert report["failed"] == 0
    assert summary["byState"].get("succeeded") == ["地点_景区__九寨沟"]
    job = read_json(oq._job_path(sc, "fanout_r_envelope_ok", oq.stable_job_id(sc, "fanout_r_envelope_ok", "地点_景区__九寨沟", "author")))
    assert job["queueBackend"] == "reliabletask"
    assert job["resultEnvelopeRef"].endswith(".json")


def test_default_runner_envelope_discovery_uses_canonical_job_path():
    task = "旅行/地域/四川省/景区/信封发现"
    batch = "fanout_envelope_discovery"
    job = oq.enqueue_ref_job(task, batch, "refEnvelope", "author", queue_backend="reliabletask")
    packet = oq.build_lease_packet({**job, "lease": "w:1"})
    root = batch_root(task, batch)
    envelope_path = root / "_shared" / "envelopes" / f"{job['jobId']}.json"
    envelope_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(envelope_path, {"schemaVersion": pc.AGENT_RESULT_ENVELOPE_SCHEMA})
    assert fr._discover_result_envelope(packet) == str(envelope_path)


def test_reliabletask_job_missing_envelope_does_not_complete():
    _frozen_prod("r_envelope_missing", ["九寨沟"])
    fd.dispatch(fp.load_plan("r_envelope_missing"), strategy="flat-pool", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout("r_envelope_missing", agent_runner=runner, strategy="flat-pool", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_envelope_missing")
    assert report["completed"] == 0
    assert report["failed"] == 1
    assert "succeeded" not in summary["byState"]
    job = read_json(oq._job_path(sc, "fanout_r_envelope_missing", oq.stable_job_id(sc, "fanout_r_envelope_missing", "地点_景区__九寨沟", "author")))
    assert "missing result envelope" in (job["lastError"] or "")


def test_run_failure_marks_failed_or_dead():
    plan = _frozen("r_fail", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="error", passed=False, error="gate not approved",
                             fingerprint="fp1")

    original_backoff = oq._backoff_seconds
    try:
        oq._backoff_seconds = lambda attempt: 0.05
        report = fr.run_fanout("r_fail", agent_runner=runner, strategy="by-leaf", concurrency=1)
    finally:
        oq._backoff_seconds = original_backoff
    assert report["failed"] >= 1
    sc = "旅行/地域/四川省/四川景点主页"
    # maxAttempts 默认 2：单次失败后应为 failed（退避）或 dead，不应 succeeded
    summary = oq.queue_summary(sc, "fanout_r_fail")
    assert "succeeded" not in summary["byState"]


def test_failed_backoff_job_released_again_within_same_run():
    plan = _frozen("r_backoff_retry", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)
    seen_attempts: list[int] = []

    def runner(packet):
        seen_attempts.append(int(packet.get("attempt") or 0))
        if len(seen_attempts) == 1:
            return fr.RunOutcome(started=True, status="error", passed=False, error="needs revision", fingerprint="fp-retry")
        return fr.RunOutcome(started=True, status="finished", passed=True)

    original_backoff = oq._backoff_seconds
    try:
        oq._backoff_seconds = lambda attempt: 0.05
        report = fr.run_fanout("r_backoff_retry", agent_runner=runner, strategy="by-leaf", concurrency=1)
    finally:
        oq._backoff_seconds = original_backoff
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_backoff_retry")
    assert seen_attempts == [1, 2], seen_attempts
    assert report["completed"] == 1
    assert report["failed"] == 0
    assert report["attemptFailures"] == 1
    assert report["refsCompleted"] == ["地点_景区__九寨沟"]
    assert report["refsFailed"] == []
    assert summary["byState"].get("succeeded") == ["地点_景区__九寨沟"]


def test_non_retryable_startup_failure_does_not_wait_forever():
    plan = _frozen("r_startup_no_wait", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)
    started_at = time.time()

    def runner(_packet):
        return fr.RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)

    report = fr.run_fanout("r_startup_no_wait", agent_runner=runner, strategy="by-leaf", concurrency=1)
    elapsed = time.time() - started_at
    sc = "旅行/地域/四川省/四川景点主页"
    snapshot = oq.queue_runtime_snapshot(sc, "fanout_r_startup_no_wait", stage="author")
    assert elapsed < 2.0, elapsed
    assert report["completed"] == 0
    assert report["failed"] == 1
    assert report["startupFailures"] == 1
    assert snapshot["waitableLive"] == 0
    assert snapshot["byState"].get("failed") == 1
    matrix = read_json(fanout_run_matrix_path("r_startup_no_wait"))
    assert matrix["summary"]["startupFailures"] == 1
    assert matrix["summary"]["startupFailureRate"] == 1.0


def test_retryable_startup_failure_retried_within_same_run():
    plan = _frozen("r_startup_retry", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)
    attempts: list[int] = []

    def runner(packet):
        attempts.append(int(packet.get("attempt") or 0))
        if len(attempts) == 1:
            return fr.RunOutcome(started=False, error="Bridge request failed: ConnectError: [Errno 61] Connection refused", retryable=True)
        return fr.RunOutcome(started=True, status="finished", passed=True)

    original_base = fr.STARTUP_BACKOFF_BASE
    original_backoff = oq._backoff_seconds
    try:
        fr.STARTUP_BACKOFF_BASE = 0
        oq._backoff_seconds = lambda attempt: 0.05
        report = fr.run_fanout("r_startup_retry", agent_runner=runner, strategy="by-leaf", concurrency=1)
    finally:
        fr.STARTUP_BACKOFF_BASE = original_base
        oq._backoff_seconds = original_backoff
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_startup_retry")
    assert attempts == [1, 2], attempts
    assert report["completed"] == 1
    assert report["failed"] == 0
    assert report["startupFailures"] == 0
    assert report["refsCompleted"] == ["地点_景区__九寨沟"]
    assert summary["byState"].get("succeeded") == ["地点_景区__九寨沟"]
    job = read_json(oq._job_path(sc, "fanout_r_startup_retry", oq.stable_job_id(sc, "fanout_r_startup_retry", "地点_景区__九寨沟", "author")))
    assert job["attempt"] == 2
    assert job["startupFailureCount"] == 1


def test_retryable_startup_failure_stops_after_retry_budget():
    plan = _frozen("r_startup_retry_budget", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)
    attempts: list[int] = []

    def runner(packet):
        attempts.append(int(packet.get("attempt") or 0))
        return fr.RunOutcome(started=False, error="Bridge request failed: ConnectError: [Errno 61] Connection refused", retryable=True)

    original_base = fr.STARTUP_BACKOFF_BASE
    original_budget = fr.MAX_STARTUP_RETRIES
    original_backoff = oq._backoff_seconds
    try:
        fr.STARTUP_BACKOFF_BASE = 0
        fr.MAX_STARTUP_RETRIES = 2
        oq._backoff_seconds = lambda attempt: 0.05
        report = fr.run_fanout("r_startup_retry_budget", agent_runner=runner, strategy="by-leaf", concurrency=1)
    finally:
        fr.STARTUP_BACKOFF_BASE = original_base
        fr.MAX_STARTUP_RETRIES = original_budget
        oq._backoff_seconds = original_backoff
    sc = "旅行/地域/四川省/四川景点主页"
    snapshot = oq.queue_runtime_snapshot(sc, "fanout_r_startup_retry_budget", stage="author")
    assert attempts == [1, 2], attempts
    assert report["completed"] == 0
    assert report["failed"] == 1
    assert report["startupFailures"] == 1
    assert snapshot["waitableLive"] == 0
    job = read_json(oq._job_path(sc, "fanout_r_startup_retry_budget", oq.stable_job_id(sc, "fanout_r_startup_retry_budget", "地点_景区__九寨沟", "author")))
    assert job["attempt"] == 2
    assert job["startupFailureCount"] == 2


def test_startup_failure_does_not_complete():
    plan = _frozen("r_startup", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)

    report = fr.run_fanout("r_startup", agent_runner=runner, strategy="by-leaf", concurrency=1)
    assert report["completed"] == 0
    assert report["startupFailures"] >= 1


def test_usage_recorded_and_budget_enforced():
    plan = fp.new_plan("r_budget", "四川景点主页", "travel",
                       defaults={"entityType": "地点/景区", "budget": {"maxWallClockSeconds": 1200, "maxAttempts": 2, "tokenBudget": 50}})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        # 用量超 tokenBudget=50 → record_usage 强制 dead；passed 也不应 complete
        return fr.RunOutcome(started=True, status="finished", passed=True, tokens=200)

    fr.run_fanout("r_budget", agent_runner=runner, strategy="by-leaf", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_budget")
    # 预算超支强制 dead，complete 应失败（lease 已失效）→ 不进 succeeded
    assert "succeeded" not in summary["byState"]
    notes = oq.list_notifications(sc, "fanout_r_budget")
    assert any(n.get("event") == "budget_exceeded" for n in notes)


def test_orchestrator_packet_has_no_prose_and_targets_checkpoints():
    packet = fr.build_orchestrator_packet(
        {"taskId": "旅行/地域/四川省/x", "batchId": "fanout_x"},
        partition_path=["四川省"], refs=["地点_景区__九寨沟"],
    )
    assert packet["role"] == "orchestrator"
    assert packet["checkpoints"] == list(fr.ORCHESTRATOR_CHECKPOINTS)
    assert packet["until"] == fr.ORCHESTRATOR_UNTIL
    # 合约只含命令/checkpoint 语义/禁止项，不得含成文正文句子。
    contract = packet["executionContract"]
    assert "workflow run" in contract["command"]
    assert set(contract["checkpointSemantics"]) == set(fr.ORCHESTRATOR_CHECKPOINTS)
    assert any("CC" in f or "纯色块" in f for f in contract["forbidden"])


def test_by_partition_content_mode_syncs_content_refs_and_run_matrix():
    plan = _content_plan("r_content_sync", ["九寨沟", "稻城亚丁"])
    report0 = fd.dispatch(plan, strategy="by-partition", concurrency=1)
    sc = report0["perPartition"][0]["taskId"]
    batch = "fanout_r_content_sync"

    from task.run import load_workflow_state, save_workflow_state

    state = load_workflow_state(sc, batch)
    state["completed"] = list(fr.ORCHESTRATOR_CHECKPOINTS)
    save_workflow_state(state)
    _seed_content_ref(sc, batch, "route_九寨沟")
    _seed_content_ref(sc, batch, "route_稻城亚丁")

    def orch(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True, run_id="run-orch", agent_id="agent-orch")

    def leaf(packet):
        ref = str(packet.get("ref"))
        from _common.draft_io import write_agent_draft

        meta = packet.get("meta") or {}
        write_agent_draft(
            sc,
            batch,
            ref,
            f"# {ref}\n\n正文与事实：{ref} 事实。",
            model="runner-test",
            cited_source_paths=[str(x) for x in ((meta.get("sourcePaths") or packet.get("meta", {}).get("sourcePaths") or []))],
            covered_facts=[f"{ref} 事实"],
            session_trace="leaf-session",
        )
        return fr.RunOutcome(started=True, status="finished", passed=True, run_id=f"run-{ref}", agent_id=f"agent-{ref}")

    report = fr.run_fanout(
        "r_content_sync",
        agent_runner=leaf,
        orchestrator_runner=orch,
        strategy="by-partition",
        concurrency=1,
    )
    assert report["completed"] == 2
    assert sorted(report["refsCompleted"]) == ["route_九寨沟", "route_稻城亚丁"]
    matrix = read_json(fanout_run_matrix_path("r_content_sync"))
    assert matrix["refs"]["route_九寨沟"]["agentRunId"] == "run-route_九寨沟"
    assert matrix["refs"]["route_稻城亚丁"]["agentId"] == "agent-route_稻城亚丁"
    assert matrix["orchestrators"][0]["preparedRefs"] == ["route_九寨沟", "route_稻城亚丁"]
    assert matrix["summary"]["completed"] == 2
    assert matrix["summary"]["retryConvergence"] == 1.0
    assert matrix["workers"][0]["completed"] == 2
    meta = read_draft_meta(sc, batch, "route_九寨沟")
    assert meta is not None
    assert meta["agentRunId"] == "run-route_九寨沟"
    assert meta["agentId"] == "agent-route_九寨沟"
    assert meta["promptSha256"].startswith("sha256:")


def test_content_mode_refs_filter_refreshes_and_runs_only_requested_ref():
    plan = _content_plan("r_content_ref_filter", ["九寨沟", "稻城亚丁"])
    report0 = fd.dispatch(plan, strategy="by-partition", concurrency=1)
    sc = report0["perPartition"][0]["taskId"]
    batch = "fanout_r_content_ref_filter"

    _seed_content_ref(sc, batch, "route_九寨沟")
    _seed_content_ref(sc, batch, "route_稻城亚丁")
    write_agent_draft(
        sc,
        batch,
        "route_九寨沟",
        "# route_九寨沟\n\n旧正文。",
        model="runner-test",
        cited_source_paths=["posts/article/攻略/route_九寨沟 标题/1/1.download/sources/01.base/source.md"],
        covered_facts=["route_九寨沟 事实"],
        session_trace="done-session",
    )
    write_agent_draft(
        sc,
        batch,
        "route_稻城亚丁",
        "# route_稻城亚丁\n\n旧正文。",
        model="runner-test",
        cited_source_paths=["posts/article/攻略/route_稻城亚丁 标题/1/1.download/sources/01.base/source.md"],
        covered_facts=["route_稻城亚丁 事实"],
        session_trace="done-session",
    )
    write_writing_pack(
        sc,
        batch,
        "route_九寨沟",
        {
            "ref": "route_九寨沟",
            "title": "route_九寨沟 标题",
            "kind": "route",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "styleFamily": "route-guide",
            "mustIncludeFacts": ["route_九寨沟 事实"],
            "baseSourceRef": "posts/article/攻略/route_九寨沟 标题/1/1.download/sources/04.new/source.md",
            "sourcePaths": ["posts/article/攻略/route_九寨沟 标题/1/1.download/sources/04.new/source.md"],
            "sourceUrls": ["https://example.invalid/new-jzg"],
            "assets": [],
        },
    )

    seen_refs: list[str] = []

    def leaf(packet):
        ref = str(packet.get("ref"))
        seen_refs.append(ref)
        meta = packet.get("meta") or {}
        write_agent_draft(
            sc,
            batch,
            ref,
            f"# {ref}\n\n重跑正文与事实：{ref} 事实。",
            model="runner-test",
            cited_source_paths=[str(x) for x in (meta.get("sourcePaths") or [])],
            covered_facts=[f"{ref} 事实"],
            session_trace="leaf-session",
        )
        return fr.RunOutcome(started=True, status="finished", passed=True, run_id=f"run-{ref}", agent_id=f"agent-{ref}")

    report = fr.run_fanout(
        "r_content_ref_filter",
        agent_runner=leaf,
        strategy="by-partition",
        concurrency=1,
        orchestrator_runner=None,
        refs=["route_九寨沟"],
        force_refs=["route_九寨沟"],
    )
    assert report["completed"] == 1
    assert report["failed"] == 0
    assert report["refsCompleted"] == ["route_九寨沟"]
    assert seen_refs == ["route_九寨沟"]
    packet = read_json(content_object.content_object_stage_dir(sc, batch, "route_九寨沟", "4.draft") / "author_job_packet.json")
    assert packet["baseSourceRef"] == "posts/article/攻略/route_九寨沟 标题/1/1.download/sources/04.new/source.md"
    summary = oq.queue_summary(sc, batch)
    assert summary["byState"].get("succeeded") == ["route_九寨沟"]
    assert "route_稻城亚丁" not in (summary["byState"].get("succeeded") or [])


def test_by_partition_orchestrates_then_authors_leaves():
    plan = _frozen("r_orch", ["九寨沟", "稻城亚丁"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"

    # orchestrator 校验：注入「已到位」的 workflow_state（三 checkpoint 完成），再分发叶子。
    from task.run import load_workflow_state, save_workflow_state
    state = load_workflow_state(sc, "fanout_r_orch")
    state["completed"] = list(fr.ORCHESTRATOR_CHECKPOINTS)
    save_workflow_state(state)

    seen_roles: list[str] = []

    def orch(_packet):
        seen_roles.append("orchestrator")
        return fr.RunOutcome(started=True, status="finished", passed=True)

    def leaf(_packet):
        seen_roles.append("leaf")
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout(
        "r_orch", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrated"] == 1
    assert report["orchestrationFailed"] == 0
    assert report["completed"] == 2  # checkpoint 到位后叶子被授权
    assert "orchestrator" in seen_roles and "leaf" in seen_roles


def test_orchestrator_checkpoint_gap_blocks_leaf_dispatch():
    plan = _frozen("r_orch_gap", ["九寨沟"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)
    # 不预置 workflow_state（三 checkpoint 未完成）→ orchestrate 校验不通过 → 不分发叶子。

    leaf_calls = {"n": 0}

    def orch(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True)

    def leaf(_packet):
        leaf_calls["n"] += 1
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout(
        "r_orch_gap", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrationFailed"] == 1
    assert report["completed"] == 0
    assert leaf_calls["n"] == 0  # checkpoint 未到位，叶子不被空跑


def test_orchestrator_startup_failure_blocks_leaf_dispatch():
    plan = _frozen("r_orch_startup", ["九寨沟"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)

    def orch(_packet):
        return fr.RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)

    def leaf(_packet):
        raise AssertionError("leaf must not run when orchestrator failed to start")

    report = fr.run_fanout(
        "r_orch_startup", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrationFailed"] == 1
    assert report["completed"] == 0
    assert report["orchestrations"][0]["started"] is False


def test_runtime_selects_local_cwd_vs_cloud_repos():
    """_build_agent_options：local 走 cwd（本机写仓库），cloud 走 repos（clone VM）。"""
    import types

    captured: dict[str, dict] = {}

    def _AgentOptions(**kw):
        captured["agent"] = kw
        return kw

    def _LocalAgentOptions(**kw):
        captured["local"] = kw
        return ("local", kw)

    def _CloudAgentOptions(**kw):
        captured["cloud"] = kw
        return ("cloud", kw)

    fake = types.SimpleNamespace(
        AgentOptions=_AgentOptions,
        LocalAgentOptions=_LocalAgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
    )
    sys.modules["cursor_sdk"] = fake
    try:
        local_opts = fr._build_agent_options(
            api_key="k", model="composer-2.5", runtime=fr.RUNTIME_LOCAL, cwd="/repo", repos=None
        )
        assert local_opts["local"] == ("local", {"cwd": "/repo"})
        assert "cloud" not in local_opts
        cloud_opts = fr._build_agent_options(
            api_key="k", model="composer-2.5", runtime=fr.RUNTIME_CLOUD, cwd=None,
            repos=[{"repository": "r"}],
        )
        assert cloud_opts["cloud"] == ("cloud", {"repos": [{"repository": "r"}]})
        assert "local" not in cloud_opts
    finally:
        del sys.modules["cursor_sdk"]


def test_cloud_runtime_derives_repo_when_omitted():
    import types

    captured: dict[str, dict] = {}

    def _AgentOptions(**kw):
        captured["agent"] = kw
        return kw

    def _CloudAgentOptions(**kw):
        captured["cloud"] = kw
        return ("cloud", kw)

    def _LocalAgentOptions(**kw):
        return ("local", kw)

    fake = types.SimpleNamespace(
        AgentOptions=_AgentOptions,
        LocalAgentOptions=_LocalAgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
    )
    original_git_output = fr._git_output
    sys.modules["cursor_sdk"] = fake
    try:
        fr._git_output = lambda args, cwd=None: "https://github.com/openstudio2022/quwoquan.git" if args[:3] == ["remote", "get-url", "origin"] else "dev1.0"
        cloud_opts = fr._build_agent_options(
            api_key="k", model="composer-2.5", runtime=fr.RUNTIME_CLOUD, cwd="/repo", repos=None
        )
        assert cloud_opts["cloud"] == (
            "cloud",
            {"repos": [{"url": "https://github.com/openstudio2022/quwoquan.git", "startingRef": "dev1.0"}]},
        )
    finally:
        fr._git_output = original_git_output
        del sys.modules["cursor_sdk"]


def test_missing_key_blocks_both_runtimes():
    """无 CURSOR_API_KEY 时 local/cloud 均启动失败（不会偷偷本机裸跑）。"""
    saved = os.environ.pop("CURSOR_API_KEY", None)
    try:
        for rt in fr.VALID_RUNTIMES:
            out = fr.default_agent_runner({"ref": "x"}, runtime=rt, api_key=None)
            assert out.started is False
    finally:
        if saved is not None:
            os.environ["CURSOR_API_KEY"] = saved


def test_main_exit_code_uses_final_failed_refs_not_attempt_failures():
    plan = _frozen("r_exit_final_state", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    original_backoff = oq._backoff_seconds
    try:
        oq._backoff_seconds = lambda attempt: 0.01

        calls = {"n": 0}

        def runner(_packet):
            calls["n"] += 1
            if calls["n"] == 1:
                return fr.RunOutcome(started=True, status="error", passed=False, error="revise", fingerprint="fp-exit")
            return fr.RunOutcome(started=True, status="finished", passed=True)

        original_default_agent_runner = fr.default_agent_runner
        fr.default_agent_runner = lambda packet, **kwargs: runner(packet)
        try:
            exit_code = fr.main([
                "--plan", "r_exit_final_state",
                "--strategy", "by-leaf",
                "--concurrency", "1",
                "--runtime", "local",
            ])
        finally:
            fr.default_agent_runner = original_default_agent_runner
    finally:
        oq._backoff_seconds = original_backoff
    assert calls["n"] == 2
    assert exit_code == 0


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_runner tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
