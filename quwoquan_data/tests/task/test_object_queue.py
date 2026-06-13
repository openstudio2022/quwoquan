"""object-stage job 队列 contract tests：幂等 / lease / 崩溃恢复 / 同源互斥 / 失败升级。

可直接运行：python3 quwoquan_data/tests/task/test_object_queue.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 隔离 runtime 根目录，必须在 import paths 之前设置
_TMP = tempfile.mkdtemp(prefix="qwq_object_queue_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from task import object_queue as oq  # noqa: E402
from _common.io import read_json  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区精选"
BATCH = "test_batch_oq"


def test_enqueue_is_idempotent():
    j1 = oq.enqueue_ref_job(TASK, BATCH, "refA", "author")
    j2 = oq.enqueue_ref_job(TASK, BATCH, "refA", "author")
    assert j1["jobId"] == j2["jobId"]
    assert j2["attempt"] == 0
    assert j2["state"] == oq.STATE_QUEUED


def test_lease_complete_lifecycle():
    oq.enqueue_ref_job(TASK, BATCH, "refLife", "author")
    job = oq.acquire_lease(TASK, BATCH, worker="w1", stage="author")
    assert job is not None and job["ref"] in {"refLife", "refA"}
    assert job["state"] == oq.STATE_LEASED and job["attempt"] >= 1
    done = oq.complete_job(TASK, BATCH, job["jobId"], job["lease"])
    assert done["state"] == oq.STATE_SUCCEEDED


def test_same_source_mutex():
    batch = "test_batch_mutex"
    oq.enqueue_ref_jobs(
        TASK,
        batch,
        [
            {"ref": "r1", "baseSourceRef": "sources/shared.md"},
            {"ref": "r2", "baseSourceRef": "sources/shared.md"},
        ],
        "author",
    )
    first = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    assert first is not None
    second = oq.acquire_lease(TASK, batch, worker="w2", stage="author")
    assert second is None, "same baseSourceRef must be mutually exclusive while leased"


def test_crash_recovery_reclaims_expired_lease():
    batch = "test_batch_crash"
    oq.enqueue_ref_job(TASK, batch, "rc", "author")
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    assert job is not None
    # 模拟 worker 崩溃：lease 过期
    path = oq._job_path(TASK, batch, job["jobId"])
    payload = read_json(path)
    payload["leaseExpiresEpoch"] = 1
    from _common.io import write_json

    write_json(path, payload)
    reclaimed = oq.acquire_lease(TASK, batch, worker="w2", stage="author")
    assert reclaimed is not None and reclaimed["jobId"] == job["jobId"]
    assert reclaimed["attempt"] == 2


def test_failure_escalates_to_dead():
    batch = "test_batch_fail"
    oq.enqueue_ref_job(TASK, batch, "rf", "author", max_attempts=2)
    j1 = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    r1 = oq.fail_job(TASK, batch, j1["jobId"], j1["lease"], error="boom1")
    assert r1["state"] == oq.STATE_FAILED  # attempt 1 < max 2
    # 失败退避：模拟退避窗口已过，job 可再次重取
    path = oq._job_path(TASK, batch, j1["jobId"])
    payload = read_json(path)
    payload["notBeforeEpoch"] = 0
    from _common.io import write_json

    write_json(path, payload)
    j2 = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    r2 = oq.fail_job(TASK, batch, j2["jobId"], j2["lease"], error="boom2")
    assert r2["state"] == oq.STATE_DEAD  # attempt 2 >= max 2 → 转人工


def test_lease_mismatch_rejected():
    batch = "test_batch_lease"
    oq.enqueue_ref_job(TASK, batch, "rl", "author")
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    try:
        oq.complete_job(TASK, batch, job["jobId"], "someone-else:0")
    except RuntimeError as exc:
        assert "lease mismatch" in str(exc)
    else:
        raise AssertionError("expected lease mismatch RuntimeError")


def test_requeue_affected_refs():
    batch = "test_batch_requeue"
    oq.enqueue_ref_job(TASK, batch, "rq", "author")
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.complete_job(TASK, batch, job["jobId"], job["lease"])
    touched = oq.requeue_refs(TASK, batch, ["rq"], "author")
    assert touched == ["rq"]
    payload = read_json(oq._job_path(TASK, batch, job["jobId"]))
    assert payload["state"] == oq.STATE_QUEUED


def test_requeue_resets_dead_job_runtime_flags():
    batch = "test_batch_requeue_dead"
    oq.enqueue_ref_job(TASK, batch, "rdead", "author", max_attempts=1)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(TASK, batch, job["jobId"], job["lease"], error="dead now", fingerprint="fp-dead")
    touched = oq.requeue_refs(TASK, batch, ["rdead"], "author", reason="manual_repair")
    assert touched == ["rdead"]
    payload = read_json(oq._job_path(TASK, batch, job["jobId"]))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["lease"] is None
    assert payload["leaseExpiresEpoch"] == 0
    assert payload["deadlineEpoch"] == 0
    assert payload["notBeforeEpoch"] == 0
    assert payload["sameRunRetryable"] is True
    assert payload["lastError"] is None
    assert payload["failureFingerprints"] == []
    assert payload["timings"][-1]["reason"] == "manual_repair"


def test_requeue_resets_startup_failure_count():
    batch = "test_batch_requeue_startup"
    oq.enqueue_ref_job(TASK, batch, "rstartup", "author", max_attempts=2)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(
        TASK,
        batch,
        job["jobId"],
        job["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=True,
        startup_failure=True,
    )
    touched = oq.requeue_refs(TASK, batch, ["rstartup"], "author", reason="manual_repair")
    assert touched == ["rstartup"]
    payload = read_json(oq._job_path(TASK, batch, job["jobId"]))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["startupFailureCount"] == 0
    assert payload["lastError"] is None


def test_reconcile_completed_refs_marks_terminal_success():
    batch = "test_batch_reconcile"
    oq.enqueue_ref_job(TASK, batch, "rreconcile", "author", max_attempts=1)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(TASK, batch, job["jobId"], job["lease"], error="dead now")
    touched = oq.reconcile_completed_refs(TASK, batch, ["rreconcile"], "author", reason="publish_succeeded")
    assert touched == ["rreconcile"]
    payload = read_json(oq._job_path(TASK, batch, job["jobId"]))
    assert payload["state"] == oq.STATE_SUCCEEDED
    assert payload["lease"] is None
    assert payload["lastError"] is None
    assert payload["timings"][-1]["reason"] == "publish_succeeded"


def test_purge_jobs_removes_matching_stage_entries():
    batch = "test_batch_purge"
    oq.enqueue_ref_job(TASK, batch, "keep_download", "download")
    oq.enqueue_ref_job(TASK, batch, "drop_a", "author")
    oq.enqueue_ref_job(TASK, batch, "drop_b", "author")
    res = oq.purge_jobs(TASK, batch, stage="author", refs=["drop_b", "drop_a"])
    assert res["removed"] == ["drop_a", "drop_b"]
    summary = oq.queue_summary(TASK, batch)
    assert summary["byState"] == {"queued": ["keep_download"]}


def test_fail_sets_backoff_not_before():
    batch = "test_batch_backoff"
    oq.enqueue_ref_job(TASK, batch, "rb", "author", max_attempts=3)
    j1 = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(TASK, batch, j1["jobId"], j1["lease"], error="boom")
    payload = read_json(oq._job_path(TASK, batch, j1["jobId"]))
    assert payload["state"] == oq.STATE_FAILED
    assert payload["notBeforeEpoch"] > oq._now(), "failed job must back off before re-lease"
    # 退避未到期 → 不可重取
    assert oq.acquire_lease(TASK, batch, worker="w2", stage="author") is None


def test_startup_failure_can_skip_attempt_budget():
    batch = "test_batch_startup_no_consume"
    oq.enqueue_ref_job(TASK, batch, "rsu", "author", max_attempts=2)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    res = oq.fail_job(
        TASK,
        batch,
        job["jobId"],
        job["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res["state"] == oq.STATE_FAILED
    assert res["attempt"] == 1
    assert res["startupFailureCount"] == 1


def test_startup_failure_uses_independent_startup_budget():
    batch = "test_batch_startup_budget"
    oq.enqueue_ref_job(TASK, batch, "rsub", "author", max_attempts=1, max_startup_failures=3)
    job1 = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    res1 = oq.fail_job(
        TASK,
        batch,
        job1["jobId"],
        job1["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res1["state"] == oq.STATE_FAILED
    payload = read_json(oq._job_path(TASK, batch, job1["jobId"]))
    payload["notBeforeEpoch"] = 0
    from _common.io import write_json
    write_json(oq._job_path(TASK, batch, job1["jobId"]), payload)
    job2 = oq.acquire_lease(TASK, batch, worker="w2", stage="author")
    res2 = oq.fail_job(
        TASK,
        batch,
        job2["jobId"],
        job2["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res2["state"] == oq.STATE_FAILED
    payload = read_json(oq._job_path(TASK, batch, job2["jobId"]))
    payload["notBeforeEpoch"] = 0
    write_json(oq._job_path(TASK, batch, job2["jobId"]), payload)
    job3 = oq.acquire_lease(TASK, batch, worker="w3", stage="author")
    res3 = oq.fail_job(
        TASK,
        batch,
        job3["jobId"],
        job3["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res3["state"] == oq.STATE_DEAD
    assert res3["startupFailureCount"] == 3


def test_reaper_times_out_over_wall_clock():
    batch = "test_batch_reaper_timeout"
    oq.enqueue_ref_job(TASK, batch, "rt", "author", max_attempts=1, max_wall_clock_seconds=1)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    # 模拟墙钟超时：deadline 已过
    path = oq._job_path(TASK, batch, job["jobId"])
    payload = read_json(path)
    payload["deadlineEpoch"] = 1
    from _common.io import write_json

    write_json(path, payload)
    res = oq.reap_jobs(TASK, batch)
    assert "rt" in res["timedOut"]
    after = read_json(path)
    assert after["state"] == oq.STATE_DEAD  # attempt 1 >= max 1
    assert "timeout" in (after["lastError"] or "")


def test_reaper_reclaims_expired_lease_within_deadline():
    batch = "test_batch_reaper_reclaim"
    oq.enqueue_ref_job(TASK, batch, "rr", "author", max_wall_clock_seconds=99999)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    path = oq._job_path(TASK, batch, job["jobId"])
    payload = read_json(path)
    payload["leaseExpiresEpoch"] = 1  # lease 过期但 deadline 未到
    from _common.io import write_json

    write_json(path, payload)
    res = oq.reap_jobs(TASK, batch)
    assert "rr" in res["reclaimed"]
    after = read_json(path)
    assert after["state"] == oq.STATE_QUEUED


def test_spillover_dead_to_repair_batch():
    batch = "test_batch_spill_src"
    target = "test_batch_spill_dst"
    oq.enqueue_ref_job(TASK, batch, "rs", "author", max_attempts=1)
    j1 = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(TASK, batch, j1["jobId"], j1["lease"], error="dead now")
    assert read_json(oq._job_path(TASK, batch, j1["jobId"]))["state"] == oq.STATE_DEAD
    res = oq.spillover_dead(TASK, batch, target_batch_id=target)
    assert "rs" in res["spilled"]
    # 原批留痕 spilled，目标批是全新 queued job
    assert read_json(oq._job_path(TASK, batch, j1["jobId"]))["state"] == oq.STATE_SPILLED
    new_job_id = oq.stable_job_id(TASK, target, "rs", "author")
    new_job = read_json(oq._job_path(TASK, target, new_job_id))
    assert new_job["state"] == oq.STATE_QUEUED and new_job["attempt"] == 0
    assert new_job["meta"]["spilledFromBatch"] == batch


def test_revive_dead_startup_jobs_requeues_without_manual_edit():
    batch = "test_batch_revive_startup"
    oq.enqueue_ref_job(TASK, batch, "rrevive", "author", max_attempts=1, max_startup_failures=1)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    oq.fail_job(
        TASK,
        batch,
        job["jobId"],
        job["lease"],
        error="startup: Bridge request failed",
        same_run_retryable=False,
        startup_failure=True,
    )
    revived = oq.revive_dead_startup_jobs(TASK, batch, refs=["rrevive"], stage="author")
    assert revived["revived"] == ["rrevive"]
    payload = read_json(oq._job_path(TASK, batch, job["jobId"]))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["attempt"] == 1
    assert payload["startupFailureCount"] == 0


def test_lease_packet_carries_ralph_exit_contract():
    batch = "test_batch_packet"
    oq.enqueue_ref_job(TASK, batch, "rp", "author")
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    packet = oq.build_lease_packet(job)
    assert packet["ref"] == "rp" and packet["lease"] == job["lease"]
    assert packet["deadlineEpoch"] > 0
    assert "ref_review_gate" in packet["ralphLoop"]
    assert packet["objectPacketRefs"]["draft"].endswith("draft.article.md")


def test_lease_packet_carries_execution_contract_five_elements():
    batch = "test_batch_exec_contract"
    oq.enqueue_ref_job(TASK, batch, "rec", "author")
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    contract = oq.build_lease_packet(job)["executionContract"]
    for key in ("inputs", "budget", "permissions", "completionConditions", "outputPaths"):
        assert contract.get(key), f"executionContract missing {key}"
    assert "read_ref_packet" in contract["permissions"]  # 最小工具集 allow-list
    assert contract["budget"]["maxWallClockSeconds"] == job["maxWallClockSeconds"]
    assert any("ref_review_gate" in c for c in contract["completionConditions"])


def test_stuck_detection_forces_dead_before_max_attempts():
    batch = "test_batch_stuck"
    # maxAttempts 高、stuckThreshold 低：同一 issues 指纹连续 3 次 → 直接 dead（不空耗 attempts）。
    oq.enqueue_ref_job(TASK, batch, "rstuck", "author", max_attempts=10, stuck_threshold=3)
    fp = oq.issues_fingerprint(["travelogueDensity: opening lacks a real hook"])
    job_id = oq.stable_job_id(TASK, batch, "rstuck", "author")
    from _common.io import write_json

    last = None
    for _ in range(3):
        payload = read_json(oq._job_path(TASK, batch, job_id))
        payload["notBeforeEpoch"] = 0
        write_json(oq._job_path(TASK, batch, job_id), payload)
        job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
        assert job is not None
        last = oq.fail_job(TASK, batch, job["jobId"], job["lease"], error="same issue", fingerprint=fp)
    assert last["state"] == oq.STATE_DEAD, "同一 issues 指纹连续 stuckThreshold 次必须判 stuck→dead"
    assert last.get("stuckDetected") is True
    notes = oq.list_notifications(TASK, batch)
    assert any(n.get("event") == "stuck" and n.get("ref") == "rstuck" for n in notes)


def test_usage_budget_exceeded_forces_dead():
    batch = "test_batch_budget"
    oq.enqueue_ref_job(TASK, batch, "rbudget", "author", token_budget=1000)
    job = oq.acquire_lease(TASK, batch, worker="w1", stage="author")
    mid = oq.record_usage(TASK, batch, job["jobId"], job["lease"], tokens=400)
    assert mid["state"] == oq.STATE_LEASED  # 未超预算仍在跑
    res = oq.record_usage(TASK, batch, job["jobId"], job["lease"], tokens=700)
    assert res["state"] == oq.STATE_DEAD
    assert "budget_exceeded" in (res["lastError"] or "")
    notes = oq.list_notifications(TASK, batch)
    assert any(n.get("event") == "budget_exceeded" for n in notes)


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"object_queue tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
