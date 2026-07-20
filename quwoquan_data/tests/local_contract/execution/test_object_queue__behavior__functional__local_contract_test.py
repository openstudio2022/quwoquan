"""object-stage job 队列 contract tests：幂等 / lease / 崩溃恢复 / 同源互斥 / 失败升级。

可直接运行：python3 quwoquan_data/tests/local_contract/execution/test_object_queue__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 隔离唯一输出根，必须在 import paths 之前设置。
_TMP = tempfile.mkdtemp(prefix="qwq_object_queue_test_")
os.environ["QWQ_OUTPUT_ROOT"] = _TMP

from content.execution.queue import runtime as oq  # noqa: E402
from content.execution.queue import management as oqm  # noqa: E402
from content.execution.queue.model import QueueJob  # noqa: E402
from core.control_types import QueueFailureKind  # noqa: E402
from core.data_issue import DataRecoveryAction  # noqa: E402
from content.execution import store  # noqa: E402
from content.execution.queue.core import list_notifications  # noqa: E402
from content.execution.queue.jobs import enqueue_ref_jobs  # noqa: E402
from content.execution.queue.packets import build_lease_packet  # noqa: E402
from content.execution import production_contracts as pc  # noqa: E402
from core import ops_governance as og  # noqa: E402
from core.io import read_json, write_json  # noqa: E402


def _execution_id(label: str) -> str:
    sequence = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16) % 1_000_000
    return f"20260711--travel-homepage-queue--test--canary-{sequence:06d}"


BATCH = _execution_id("test_batch_oq")
FIXTURE_SOURCE_REVISION = "sha256:" + ("1" * 64)


def _reliable_identity(ref: str) -> dict:
    return {
        "entityRef": ref,
        "carrier": "homepage",
        "sourceRevision": FIXTURE_SOURCE_REVISION,
    }


def _creator_meta() -> dict:
    return {
        "authorId": "builtin_highland_travel_blogger",
        "creatorProfileId": "qwq_creator_highland_travel_blogger_001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
            "visible": True,
        },
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }


def _valid_assignment(
    batch: str,
    ref: str,
    *,
    controller_run_id: str = "ctrl-test",
    allowed_write_roots: list[str] | None = None,
) -> dict:
    roots = allowed_write_roots or ["posts/article"]
    assignment = og.build_assignment(
        execution_id=batch,
        controller_run_id=controller_run_id,
        assignment_path=["四川省", "阿坝藏族羌族自治州", ref],
        role="author_subagent",
        parent_assignment_id="partition-parent",
        scope={"sliceType": "content_ref", "ref": ref},
        allowed_read_roots=["_shared", *roots],
        allowed_write_roots=roots,
        budget={"maxAttempts": 2},
    )
    og.append_assignment(batch, assignment)
    return assignment


def _queue_issue(
    job: QueueJob,
    message: str,
    *,
    kind: QueueFailureKind = QueueFailureKind.EXECUTION,
) -> object:
    return job.issue(kind, message=message, recovery=DataRecoveryAction.REWIND_COMPOSE)


def _saved_job(batch: str, job_id: str) -> QueueJob:
    return QueueJob.from_document(read_json(oq._job_path(batch, job_id)))


def test_enqueue_is_idempotent():
    j1 = oq.enqueue_ref_job(BATCH, "refA", "author")
    j2 = oq.enqueue_ref_job(BATCH, "refA", "author")
    assert j1.job_id == j2.job_id
    assert j2.attempt == 0
    assert j2.state is oq.STATE_QUEUED
    assert j2.backend.value == "local_file"


def test_enqueue_does_not_downgrade_succeeded_job():
    batch = _execution_id("test_batch_no_success_downgrade")
    job = oq.enqueue_ref_job(batch, "refDone", "author", meta={"creatorProfileId": "first"})
    leased = oq.acquire_lease(batch, worker="w1", stage="author")
    assert leased is not None
    oq.complete_job(batch, leased.job_id, leased.lease.holder or "")

    again = oq.enqueue_ref_job(batch, "refDone", "author", meta={"creatorProfileId": "second"})
    assert again.state is oq.STATE_SUCCEEDED
    assert again.attempt == 1
    assert again.creator_profile_id == "first"
    assert _saved_job(batch, job.job_id).state is oq.STATE_SUCCEEDED


def test_reliabletask_backend_records_bridge_and_requires_envelope():
    batch = _execution_id("test_batch_reliabletask")
    job = oq.enqueue_ref_job(
        batch,
        "refProd",
        "author",
        queue_backend="reliabletask",
        meta={
            "contentType": "article",
            **_creator_meta(),
            **_reliable_identity("refProd"),
        },
    )
    assert job.backend.value == "reliabletask"
    assert job.result_envelope_required is True
    reliable_ref = job.reliable_task_ref_document()
    assert reliable_ref is not None
    assert reliable_ref["taskType"] == "data.content_object.execute"
    assert reliable_ref["queue"] == "reliabletask.data.content_supply"
    assert str(reliable_ref["idempotencyKey"]).count("|") == 3
    assert str(reliable_ref["idempotencyKey"]).endswith("|author")
    leased = oq.acquire_lease(batch, worker="w1", stage="author")
    packet = build_lease_packet(leased)
    assert packet["resultEnvelopeRequired"] is True
    assert packet["creatorProfileId"] == "qwq_creator_highland_travel_blogger_001"
    assert packet["authorId"] == "builtin_highland_travel_blogger"
    try:
        oq.complete_job(batch, leased.job_id, leased.lease.holder or "")
    except RuntimeError as exc:
        assert "result envelope required" in str(exc)
    else:
        raise AssertionError("reliabletask job must not complete without envelope")


def test_commercial_reliabletask_requires_source_revision():
    execution_id = _execution_id("commercial_source_identity")
    try:
        oq.enqueue_ref_job(
            execution_id,
            "entity/九寨沟",
            "author",
            queue_backend="reliabletask",
            meta={
                "carrier": "homepage",
                "supplyMode": "commercial",
                "entityRef": "entity/九寨沟",
            },
        )
        raise AssertionError("commercial ReliableTask 缺 sourceRevision 必须 fail-closed")
    except ValueError as exc:
        assert "sourceRevision" in str(exc)


def test_reliabletask_idempotency_separates_object_stages():
    execution_id = _execution_id("reliabletask_stage_identity")
    metadata = {
        "carrier": "homepage",
        "entityRef": "entity/九寨沟",
        "sourceRevision": FIXTURE_SOURCE_REVISION,
    }
    author = oq.enqueue_ref_job(
        execution_id,
        "entity/九寨沟",
        "author",
        queue_backend="reliabletask",
        meta=metadata,
    )
    publish = oq.enqueue_ref_job(
        execution_id,
        "entity/九寨沟",
        "publish",
        queue_backend="reliabletask",
        meta=metadata,
    )

    assert author.job_id != publish.job_id
    author_key = author.reliable_task_ref_document()["idempotencyKey"]
    publish_key = publish.reliable_task_ref_document()["idempotencyKey"]
    assert author_key != publish_key
    assert str(author_key).endswith("|author")
    assert str(publish_key).endswith("|publish")


def test_author_job_with_content_type_requires_creator_assignment():
    batch = _execution_id("test_batch_author_creator_required")
    try:
        oq.enqueue_ref_job(batch, "r_no_creator", "author", meta={"contentType": "article"})
    except ValueError as exc:
        assert "creatorAssignment.authorId required" in str(exc)
        assert "creatorAssignment.creatorProfileId required" in str(exc)
    else:
        raise AssertionError("author content object job must require creator assignment")


def test_strict_governance_requires_assignment_on_enqueue():
    batch = _execution_id("test_batch_governance_missing_assignment")
    try:
        oq.enqueue_ref_job(
            batch,
            "r_no_assignment",
            "author",
            meta={"requireGovernance": True, "controllerRunId": "ctrl-test"},
        )
    except ValueError as exc:
        assert "assignment required" in str(exc)
    else:
        raise AssertionError("strict governance job must require a parent assignment")


def test_malformed_governance_job_blocks_and_writes_failure_ledger():
    batch = _execution_id("test_batch_governance_block")
    job = oq.enqueue_ref_job(batch, "r_bad_governance", "author")
    path = oq._job_path(batch, job.job_id)
    payload = read_json(path)
    payload["requireGovernance"] = True
    payload["controllerRunId"] = "ctrl-test"
    payload["assignmentId"] = ""
    payload["assignmentPath"] = []
    payload["owner"] = ""
    write_json(path, payload)

    leased = oq.acquire_lease(batch, worker="w1", stage="author")

    assert leased is None
    blocked = read_json(path)
    assert blocked["state"] == oq.STATE_BLOCKED
    assert "assignmentId required" in blocked["lastIssue"]["message"]
    failures = og.read_jsonl(og.failure_ledger_path(batch))
    assert failures[-1]["category"] == og.FAILURE_GATE_BLOCK
    assert failures[-1]["ref"] == "r_bad_governance"


def test_lease_complete_lifecycle():
    oq.enqueue_ref_job(BATCH, "refLife", "author")
    job = oq.acquire_lease(BATCH, worker="w1", stage="author")
    assert job is not None and job.ref in {"refLife", "refA"}
    assert job.state is oq.STATE_LEASED and job.attempt >= 1
    done = oq.complete_job(BATCH, job.job_id, job.lease.holder or "")
    assert done.state is oq.STATE_SUCCEEDED


def test_governed_article_author_complete_requires_real_agent_draft():
    batch = _execution_id("test_batch_author_complete_gate")
    ref = "refArticle"
    content_dir = "posts/article/攻略/refArticle/1"
    assignment = _valid_assignment(batch, ref, allowed_write_roots=[content_dir])
    oq.enqueue_ref_job(
        batch,
        ref,
        "author",
        meta={
            "requireGovernance": True,
            "assignment": assignment,
            "contentObjectDir": content_dir,
        },
    )
    draft_dir = store.execution_root(batch) / content_dir / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft.article.md").write_text("TODO: pending agent draft\n", encoding="utf-8")
    write_json(draft_dir / "draft_meta.json", {"generator": "pending"})
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    completed = oq.complete_job(batch, job.job_id, job.lease.holder or "")
    assert completed.state is oq.STATE_FAILED
    assert completed.last_issue is not None
    assert "draft_meta.generator is pending" in completed.last_issue.message


def test_governed_article_author_complete_rejects_creator_identity_change():
    batch = _execution_id("test_batch_author_creator_locked")
    ref = "refArticleCreator"
    content_dir = "posts/article/攻略/refArticleCreator/1"
    assignment = _valid_assignment(batch, ref, allowed_write_roots=[content_dir])
    meta = {
        "requireGovernance": True,
        "assignment": assignment,
        "contentObjectDir": content_dir,
        "contentType": "article",
        **_creator_meta(),
    }
    oq.enqueue_ref_job(batch, ref, "author", meta=meta)
    draft_dir = store.execution_root(batch) / content_dir / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft.article.md").write_text("# 标题\n\n这是一篇真实草稿。\n", encoding="utf-8")
    write_json(
        draft_dir / "draft_meta.json",
        {
            "generator": "agent",
            "authorId": "builtin_travel_blogger",
            "creatorProfileId": "qwq_creator_travel_blogger_001",
            "creatorArchetype": "travel_blogger",
            "creatorProfileVersion": "1.0.0",
        },
    )
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    completed = oq.complete_job(batch, job.job_id, job.lease.holder or "")
    assert completed.state is oq.STATE_FAILED
    assert completed.last_issue is not None
    assert "draft_meta.authorId is builtin_travel_blogger" in completed.last_issue.message
    assert "expected locked creator assignment builtin_highland_travel_blogger" in completed.last_issue.message


def test_governed_article_author_complete_backfills_missing_locked_creator():
    """Agent 写了真实正文但漏写锁定创作者时，系统确定性回填后通过（治理元数据系统所有）。"""
    batch = _execution_id("test_batch_author_creator_backfill")
    ref = "refArticleBackfill"
    content_dir = "posts/article/攻略/refArticleBackfill/1"
    assignment = _valid_assignment(batch, ref, allowed_write_roots=[content_dir])
    meta = {
        "requireGovernance": True,
        "assignment": assignment,
        "contentObjectDir": content_dir,
        "contentType": "article",
        **_creator_meta(),
    }
    oq.enqueue_ref_job(batch, ref, "author", meta=meta)
    draft_dir = store.execution_root(batch) / content_dir / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft.article.md").write_text("# 标题\n\n这是一篇真实草稿，正文足够具体。\n", encoding="utf-8")
    # 真实 agent 草稿，但 draft_meta 漏写了全部锁定创作者字段。
    write_json(draft_dir / "draft_meta.json", {"generator": "agent"})
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    completed = oq.complete_job(batch, job.job_id, job.lease.holder or "")
    assert completed.state is oq.STATE_SUCCEEDED
    stamped = read_json(draft_dir / "draft_meta.json")
    assert stamped["authorId"] == "builtin_highland_travel_blogger"
    assert stamped["creatorProfileId"] == "qwq_creator_highland_travel_blogger_001"
    assert stamped["creatorArchetype"] == "travel_blogger"
    assert stamped["creatorProfileVersion"] == "1.0.0"


def test_governed_article_author_complete_backfill_does_not_rescue_placeholder():
    """占位正文即便回填创作者也必须失败：治理回填只救真正完成创作的草稿。"""
    batch = _execution_id("test_batch_author_creator_backfill_placeholder")
    ref = "refArticleBackfillPlaceholder"
    content_dir = "posts/article/攻略/refArticleBackfillPlaceholder/1"
    assignment = _valid_assignment(batch, ref, allowed_write_roots=[content_dir])
    meta = {
        "requireGovernance": True,
        "assignment": assignment,
        "contentObjectDir": content_dir,
        "contentType": "article",
        **_creator_meta(),
    }
    oq.enqueue_ref_job(batch, ref, "author", meta=meta)
    draft_dir = store.execution_root(batch) / content_dir / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft.article.md").write_text(
        "<!-- QWQ_AWAITING_AGENT_DRAFT -->\n# 待会话模型创作\n", encoding="utf-8"
    )
    write_json(draft_dir / "draft_meta.json", {"generator": "agent"})
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    completed = oq.complete_job(batch, job.job_id, job.lease.holder or "")
    assert completed.state is oq.STATE_FAILED
    assert completed.last_issue is not None
    assert "placeholder" in completed.last_issue.message


def test_concurrent_acquire_leases_single_job_once():
    batch = _execution_id("test_batch_concurrent_lease")
    oq.enqueue_ref_job(batch, "only_one", "author")

    def lease(worker: str):
        return oq.acquire_lease(batch, worker=worker, stage="author")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leased = list(pool.map(lease, ["w1", "w2"]))

    assert sum(1 for item in leased if item is not None) == 1
    assert oqm.queue_summary(batch)["byState"][oq.STATE_LEASED] == ["only_one"]


def test_same_source_mutex():
    batch = _execution_id("test_batch_mutex")
    enqueue_ref_jobs(
        batch,
        [
            {"ref": "r1", "baseSourceRef": "sources/shared.md"},
            {"ref": "r2", "baseSourceRef": "sources/shared.md"},
        ],
        "author",
    )
    first = oq.acquire_lease(batch, worker="w1", stage="author")
    assert first is not None
    second = oq.acquire_lease(batch, worker="w2", stage="author")
    assert second is None, "same baseSourceRef must be mutually exclusive while leased"


def test_crash_recovery_reclaims_expired_lease():
    batch = _execution_id("test_batch_crash")
    oq.enqueue_ref_job(batch, "rc", "author")
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    assert job is not None
    # 模拟 worker 崩溃：lease 过期
    path = oq._job_path(batch, job.job_id)
    payload = read_json(path)
    payload["leaseExpiresEpoch"] = 1
    from core.io import write_json

    write_json(path, payload)
    reclaimed = oq.acquire_lease(batch, worker="w2", stage="author")
    assert reclaimed is not None and reclaimed.job_id == job.job_id
    assert reclaimed.attempt == 2


def test_failure_escalates_to_dead():
    batch = _execution_id("test_batch_fail")
    oq.enqueue_ref_job(batch, "rf", "author", max_attempts=2)
    j1 = oq.acquire_lease(batch, worker="w1", stage="author")
    r1 = oq.fail_job(batch, j1.job_id, j1.lease.holder or "", issue=_queue_issue(j1, "boom1"))
    assert r1.state is oq.STATE_FAILED  # attempt 1 < max 2
    # 失败退避：模拟退避窗口已过，job 可再次重取
    path = oq._job_path(batch, j1.job_id)
    payload = read_json(path)
    payload["notBeforeEpoch"] = 0
    from core.io import write_json

    write_json(path, payload)
    j2 = oq.acquire_lease(batch, worker="w1", stage="author")
    r2 = oq.fail_job(batch, j2.job_id, j2.lease.holder or "", issue=_queue_issue(j2, "boom2"))
    assert r2.state is oq.STATE_DEAD  # attempt 2 >= max 2 → 转人工


def test_lease_mismatch_rejected():
    batch = _execution_id("test_batch_lease")
    oq.enqueue_ref_job(batch, "rl", "author")
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    try:
        oq.complete_job(batch, job.job_id, "someone-else:0")
    except RuntimeError as exc:
        assert "lease mismatch" in str(exc)
    else:
        raise AssertionError("expected lease mismatch RuntimeError")


def test_requeue_affected_refs():
    batch = _execution_id("test_batch_requeue")
    oq.enqueue_ref_job(batch, "rq", "author")
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.complete_job(batch, job.job_id, job.lease.holder or "")
    touched = oqm.requeue_refs(batch, ["rq"], "author", reason="manual_repair")
    assert touched == ["rq"]
    payload = read_json(oq._job_path(batch, job.job_id))
    assert payload["state"] == oq.STATE_QUEUED


def test_requeue_resets_dead_job_runtime_flags():
    batch = _execution_id("test_batch_requeue_dead")
    oq.enqueue_ref_job(batch, "rdead", "author", max_attempts=1)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.fail_job(
        batch,
        job.job_id,
        job.lease.holder or "",
        issue=_queue_issue(job, "dead now"),
        fingerprint=oq.issues_fingerprint((_queue_issue(job, "dead now"),)),
    )
    touched = oqm.requeue_refs(batch, ["rdead"], "author", reason="manual_repair")
    assert touched == ["rdead"]
    payload = read_json(oq._job_path(batch, job.job_id))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["lease"] is None
    assert payload["leaseExpiresEpoch"] == 0
    assert payload["deadlineEpoch"] == 0
    assert payload["notBeforeEpoch"] == 0
    assert payload["sameRunRetryable"] is True
    assert payload["lastIssue"] is None
    assert payload["failureFingerprints"] == []
    assert payload["timings"][-1]["reason"] == "manual_repair"


def test_requeue_resets_startup_failure_count():
    batch = _execution_id("test_batch_requeue_startup")
    oq.enqueue_ref_job(batch, "rstartup", "author", max_attempts=2)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.fail_job(
        batch,
        job.job_id,
        job.lease.holder or "",
        issue=_queue_issue(job, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=True,
        startup_failure=True,
    )
    touched = oqm.requeue_refs(batch, ["rstartup"], "author", reason="manual_repair")
    assert touched == ["rstartup"]
    payload = read_json(oq._job_path(batch, job.job_id))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["startupFailureCount"] == 0
    assert payload["lastIssue"] is None


def test_reconcile_completed_refs_marks_terminal_success():
    batch = _execution_id("test_batch_reconcile")
    oq.enqueue_ref_job(batch, "rreconcile", "author", max_attempts=1)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.fail_job(batch, job.job_id, job.lease.holder or "", issue=_queue_issue(job, "dead now"))
    touched = oq.reconcile_completed_refs(batch, ["rreconcile"], "author", reason="publish_succeeded")
    assert touched == ["rreconcile"]
    payload = read_json(oq._job_path(batch, job.job_id))
    assert payload["state"] == oq.STATE_SUCCEEDED
    assert payload["lease"] is None
    assert payload["lastIssue"] is None
    assert payload["timings"][-1]["reason"] == "publish_succeeded"


def test_purge_jobs_removes_matching_stage_entries():
    batch = _execution_id("test_batch_purge")
    oq.enqueue_ref_job(batch, "keep_download", "download")
    oq.enqueue_ref_job(batch, "drop_a", "author")
    oq.enqueue_ref_job(batch, "drop_b", "author")
    res = oqm.purge_jobs(batch, stage="author", refs=["drop_b", "drop_a"])
    assert res["removed"] == ["drop_a", "drop_b"]
    summary = oqm.queue_summary(batch)
    assert summary["byState"] == {"queued": ["keep_download"]}


def test_fail_sets_backoff_not_before():
    batch = _execution_id("test_batch_backoff")
    oq.enqueue_ref_job(batch, "rb", "author", max_attempts=3)
    j1 = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.fail_job(batch, j1.job_id, j1.lease.holder or "", issue=_queue_issue(j1, "boom"))
    payload = read_json(oq._job_path(batch, j1.job_id))
    assert payload["state"] == oq.STATE_FAILED
    assert payload["notBeforeEpoch"] > oq._now(), "failed job must back off before re-lease"
    # 退避未到期 → 不可重取
    assert oq.acquire_lease(batch, worker="w2", stage="author") is None


def test_startup_failure_can_skip_attempt_budget():
    batch = _execution_id("test_batch_startup_no_consume")
    oq.enqueue_ref_job(batch, "rsu", "author", max_attempts=2)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    res = oq.fail_job(
        batch,
        job.job_id,
        job.lease.holder or "",
        issue=_queue_issue(job, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res.state is oq.STATE_FAILED
    assert res.attempt == 1
    assert res.startup_failure_count == 1


def test_startup_failure_uses_independent_startup_budget():
    batch = _execution_id("test_batch_startup_budget")
    oq.enqueue_ref_job(batch, "rsub", "author", max_attempts=1, max_startup_failures=3)
    job1 = oq.acquire_lease(batch, worker="w1", stage="author")
    res1 = oq.fail_job(
        batch,
        job1.job_id,
        job1.lease.holder or "",
        issue=_queue_issue(job1, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res1.state is oq.STATE_FAILED
    payload = read_json(oq._job_path(batch, job1.job_id))
    payload["notBeforeEpoch"] = 0
    from core.io import write_json
    write_json(oq._job_path(batch, job1.job_id), payload)
    job2 = oq.acquire_lease(batch, worker="w2", stage="author")
    res2 = oq.fail_job(
        batch,
        job2.job_id,
        job2.lease.holder or "",
        issue=_queue_issue(job2, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res2.state is oq.STATE_FAILED
    payload = read_json(oq._job_path(batch, job2.job_id))
    payload["notBeforeEpoch"] = 0
    write_json(oq._job_path(batch, job2.job_id), payload)
    job3 = oq.acquire_lease(batch, worker="w3", stage="author")
    res3 = oq.fail_job(
        batch,
        job3.job_id,
        job3.lease.holder or "",
        issue=_queue_issue(job3, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=True,
        startup_failure=True,
    )
    assert res3.state is oq.STATE_DEAD
    assert res3.startup_failure_count == 3


def test_reaper_times_out_over_wall_clock():
    batch = _execution_id("test_batch_reaper_timeout")
    oq.enqueue_ref_job(batch, "rt", "author", max_attempts=1, max_wall_clock_seconds=1)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    # 模拟墙钟超时：deadline 已过
    path = oq._job_path(batch, job.job_id)
    payload = read_json(path)
    payload["deadlineEpoch"] = 1
    from core.io import write_json

    write_json(path, payload)
    res = oq.reap_jobs(batch)
    assert "rt" in res["timedOut"]
    after = read_json(path)
    assert after["state"] == oq.STATE_DEAD  # attempt 1 >= max 1
    assert after["lastIssue"]["code"] == "DATA.QUEUE.TIMEOUT"


def test_reaper_reclaims_expired_lease_within_deadline():
    batch = _execution_id("test_batch_reaper_reclaim")
    oq.enqueue_ref_job(batch, "rr", "author", max_wall_clock_seconds=99999)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    path = oq._job_path(batch, job.job_id)
    payload = read_json(path)
    payload["leaseExpiresEpoch"] = 1  # lease 过期但 deadline 未到
    from core.io import write_json

    write_json(path, payload)
    res = oq.reap_jobs(batch)
    assert "rr" in res["reclaimed"]
    after = read_json(path)
    assert after["state"] == oq.STATE_QUEUED



def test_revive_dead_startup_jobs_requeues_without_manual_edit():
    batch = _execution_id("test_batch_revive_startup")
    oq.enqueue_ref_job(batch, "rrevive", "author", max_attempts=1, max_startup_failures=1)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    oq.fail_job(
        batch,
        job.job_id,
        job.lease.holder or "",
        issue=_queue_issue(job, "Bridge request failed", kind=QueueFailureKind.STARTUP),
        same_run_retryable=False,
        startup_failure=True,
    )
    revived = oq.revive_dead_startup_jobs(batch, refs=["rrevive"], stage="author")
    assert revived["revived"] == ["rrevive"]
    payload = read_json(oq._job_path(batch, job.job_id))
    assert payload["state"] == oq.STATE_QUEUED
    assert payload["attempt"] == 1
    assert payload["startupFailureCount"] == 0


def test_lease_packet_carries_ralph_exit_contract():
    batch = _execution_id("test_batch_packet")
    oq.enqueue_ref_job(batch, "rp", "author")
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    packet = build_lease_packet(job)
    assert packet["ref"] == "rp" and packet["lease"] == job.lease.holder
    assert packet["deadlineEpoch"] > 0
    assert "ref_review_gate" in packet["ralphLoop"]
    assert packet["objectPacketRefs"]["draft"].endswith("draft.article.md")


def test_lease_packet_carries_execution_contract_five_elements():
    batch = _execution_id("test_batch_exec_contract")
    oq.enqueue_ref_job(batch, "rec", "author")
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    contract = build_lease_packet(job)["executionContract"]
    for key in ("inputs", "budget", "permissions", "completionConditions", "outputPaths"):
        assert contract.get(key), f"executionContract missing {key}"
    assert "read_ref_packet" in contract["permissions"]  # 最小工具集 allow-list
    assert contract["budget"]["maxWallClockSeconds"] == job.max_wall_clock_seconds
    assert any("ref_review_gate" in c for c in contract["completionConditions"])


def test_stuck_detection_forces_dead_before_max_attempts():
    batch = _execution_id("test_batch_stuck")
    # maxAttempts 高、stuckThreshold 低：同一 issues 指纹连续 3 次 → 直接 dead（不空耗 attempts）。
    oq.enqueue_ref_job(batch, "rstuck", "author", max_attempts=10, stuck_threshold=3)
    job_id = oq.stable_job_id(batch, "rstuck", "author")
    from core.io import write_json

    last = None
    for _ in range(3):
        payload = read_json(oq._job_path(batch, job_id))
        payload["notBeforeEpoch"] = 0
        write_json(oq._job_path(batch, job_id), payload)
        job = oq.acquire_lease(batch, worker="w1", stage="author")
        assert job is not None
        issue = _queue_issue(job, "same issue")
        last = oq.fail_job(
            batch,
            job.job_id,
            job.lease.holder or "",
            issue=issue,
            fingerprint=oq.issues_fingerprint((issue,)),
        )
    assert last is not None and last.state is oq.STATE_DEAD, "同一 issues 指纹连续 stuckThreshold 次必须判 stuck→dead"
    assert last.stuck_detected is True
    notes = list_notifications(batch)
    assert any(n.get("event") == "stuck" and n.get("ref") == "rstuck" for n in notes)


def test_usage_budget_exceeded_forces_dead():
    batch = _execution_id("test_batch_budget")
    oq.enqueue_ref_job(batch, "rbudget", "author", token_budget=1000)
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    mid = oq.record_usage(batch, job.job_id, job.lease.holder or "", tokens=400)
    assert mid.state is oq.STATE_LEASED  # 未超预算仍在跑
    res = oq.record_usage(batch, job.job_id, job.lease.holder or "", tokens=700)
    assert res.state is oq.STATE_DEAD
    assert res.last_issue is not None and res.last_issue.code.value == "DATA.QUEUE.BUDGET_EXCEEDED"
    assert res.token_ledger_document()[-1]["budgetExceeded"] is True
    notes = list_notifications(batch)
    assert any(n.get("event") == "budget_exceeded" for n in notes)


def _valid_envelope_for_job(
    batch: str,
    job: QueueJob,
    *,
    body: str = "# ok\n\n正文。",
    rel_path: str = "posts/article/demo.md",
) -> Path:
    root = store.execution_root(batch)
    draft = root / rel_path
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(body, encoding="utf-8")
    digest = pc.sha256_file(draft)
    envelope = pc.build_agent_result_envelope(
        job=job.to_document(),
        files=[{"path": rel_path, "sha256": digest, "role": "draft"}],
        gates=[pc.build_gate_verdict(gate_id="review", decision="passed", input_hash=digest, output_hash=digest)],
        agent_id="agent-test",
        run_id="run-test",
        provider="cursor_sdk",
        model="composer",
        prompt_sha256=pc.sha256_text("test prompt"),
    )
    path = root / "_shared" / f"{job.job_id}.envelope.json"
    write_json(path, envelope)
    return path


def test_complete_with_valid_envelope_succeeds():
    batch = _execution_id("test_batch_envelope_ok")
    oq.enqueue_ref_job(
        batch,
        "renv",
        "author",
        queue_backend="reliabletask",
        meta=_reliable_identity("renv"),
    )
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    envelope_path = _valid_envelope_for_job(batch, job)
    done = oq.complete_job_with_envelope(batch, job.job_id, job.lease.holder or "", envelope_path=envelope_path)
    assert done.state is oq.STATE_SUCCEEDED
    assert done.result_envelope_ref is not None and done.result_envelope_ref.endswith(".envelope.json")
    assert done.gate_verdicts_document()[0]["decision"] == "passed"


def test_complete_with_envelope_rejects_write_outside_assignment_roots():
    batch = _execution_id("test_batch_envelope_governance_root")
    assignment = _valid_assignment(
        batch,
        "renv_governed",
        allowed_write_roots=["posts/article/allowed"],
    )
    oq.enqueue_ref_job(
        batch,
        "renv_governed",
        "author",
        queue_backend="reliabletask",
        max_attempts=1,
        meta={
            "requireGovernance": True,
            "controllerRunId": assignment["controllerRunId"],
            "assignmentId": assignment["assignmentId"],
            "assignmentPath": assignment["assignmentPath"],
            "owner": assignment["role"],
            "allowedReadRoots": assignment["allowedReadRoots"],
            "allowedWriteRoots": assignment["allowedWriteRoots"],
            "assignment": assignment,
            **_reliable_identity("renv_governed"),
        },
    )
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    envelope_path = _valid_envelope_for_job(
        batch,
        job,
        rel_path="posts/article/outside/demo.md",
    )
    failed = oq.complete_job_with_envelope(batch, job.job_id, job.lease.holder or "", envelope_path=envelope_path)
    assert failed.state is oq.STATE_DEAD
    assert failed.last_issue is not None
    assert "outside assignment write roots" in failed.last_issue.message


def test_complete_with_envelope_rejects_hash_mismatch():
    batch = _execution_id("test_batch_envelope_hash")
    oq.enqueue_ref_job(
        batch,
        "renv_hash",
        "author",
        queue_backend="reliabletask",
        max_attempts=1,
        meta=_reliable_identity("renv_hash"),
    )
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    envelope_path = _valid_envelope_for_job(batch, job)
    envelope = read_json(envelope_path)
    envelope["files"][0]["sha256"] = "sha256:" + ("0" * 64)
    write_json(envelope_path, envelope)
    failed = oq.complete_job_with_envelope(batch, job.job_id, job.lease.holder or "", envelope_path=envelope_path)
    assert failed.state is oq.STATE_DEAD
    assert failed.last_issue is not None
    assert "hash mismatch" in failed.last_issue.message


def test_complete_with_envelope_rejects_non_passing_gate():
    batch = _execution_id("test_batch_envelope_gate")
    oq.enqueue_ref_job(
        batch,
        "renv_gate",
        "author",
        queue_backend="reliabletask",
        max_attempts=1,
        meta=_reliable_identity("renv_gate"),
    )
    job = oq.acquire_lease(batch, worker="w1", stage="author")
    envelope_path = _valid_envelope_for_job(batch, job)
    envelope = read_json(envelope_path)
    envelope["gates"][0]["decision"] = "failed"
    envelope["gates"][0]["issues"] = ["fact trace missing"]
    write_json(envelope_path, envelope)
    failed = oq.complete_job_with_envelope(batch, job.job_id, job.lease.holder or "", envelope_path=envelope_path)
    assert failed.state is oq.STATE_DEAD
    assert failed.last_issue is not None
    assert "must pass" in failed.last_issue.message


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"object_queue tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
