"""Object queue runtime state machine, leases, failures, and snapshots."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

from core import ops_governance as og
from governance.creators.assignment import CREATOR_ASSIGNMENT_FIELDS, creator_from_payload
from core.io import read_json, write_json
from content.execution import production_contracts as pc
from content.execution import store
from content.execution.queue.core import (
    DEFAULT_LEASE_TTL_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_STARTUP_FAILURES,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    DEFAULT_STUCK_THRESHOLD,
    QUEUE_BACKEND_RELIABLETASK,
    STATE_BLOCKED,
    STATE_DEAD,
    STATE_FAILED,
    STATE_LEASED,
    STATE_QUEUED,
    STATE_SUCCEEDED,
    _active_mutex_keys,
    _backoff_seconds,
    _emit_notification,
    _envelope_governance_issues,
    _job_governance_issues,
    _job_path,
    _load_jobs,
    _now,
    _queue_lock,
    stable_job_id,
)
from content.execution.queue.jobs import enqueue_ref_job


def _clock_now() -> float:
    return _now()

def acquire_lease(
    execution_id: str,
    *,
    worker: str,
    stage: str | None = None,
    ref: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> dict[str, Any] | None:
    """取一个可执行 job 并加租约。尊重同源互斥与崩溃恢复（过期 lease 可重取）。

    ref 非空时只租该 ref（by-leaf / per-ref worker 精确寻址）。
    返回被租约的 job dict，或 None（无可执行 job）。
    """
    with _queue_lock(execution_id):
        now = _clock_now()
        jobs = _load_jobs(execution_id)
        active = _active_mutex_keys(jobs, now)
        for job in jobs:
            if stage and job.get("stage") != stage:
                continue
            if ref and job.get("ref") != ref:
                continue
            state = job.get("state")
            expired_lease = state == STATE_LEASED and float(job.get("leaseExpiresEpoch") or 0) <= now
            if state not in (STATE_QUEUED, STATE_FAILED) and not expired_lease:
                continue
            if float(job.get("notBeforeEpoch") or 0) > now:
                continue  # 失败退避中，未到可重取时刻
            governance_issues = _job_governance_issues(job)
            if governance_issues:
                job["state"] = STATE_BLOCKED
                job["lastError"] = "; ".join(governance_issues)
                job.setdefault("timings", []).append(
                    {"event": "blocked", "at": store.now_iso(), "reason": job["lastError"]}
                )
                job["updatedAt"] = store.now_iso()
                write_json(_job_path(execution_id, job["jobId"]), job)
                og.append_failure(
                    execution_id,
                    ref=str(job.get("ref") or ""),
                    stage=str(job.get("stage") or ""),
                    reason=job["lastError"],
                    category=og.FAILURE_GATE_BLOCK,
                    owner=str(job.get("owner") or ""),
                )
                continue
            mutex = str(job.get("mutexKey") or job.get("ref"))
            if mutex in active:
                continue  # 同源已有 job 在跑，互斥跳过
            wall_clock = int(job.get("maxWallClockSeconds") or DEFAULT_MAX_WALL_CLOCK_SECONDS)
            job["state"] = STATE_LEASED
            job["lease"] = f"{worker}:{int(now)}"
            job["leaseExpiresEpoch"] = now + ttl_seconds
            job["deadlineEpoch"] = now + wall_clock
            job["attempt"] = int(job.get("attempt") or 0) + 1
            job.setdefault("timings", []).append({"event": "leased", "at": store.now_iso(), "worker": worker})
            job["updatedAt"] = store.now_iso()
            write_json(_job_path(execution_id, job["jobId"]), job)
            return job
    return None

def _load_owned(execution_id: str, job_id: str, lease: str) -> dict[str, Any]:
    path = _job_path(execution_id, job_id)
    job = read_json(path)
    if job.get("lease") != lease:
        raise RuntimeError(f"lease mismatch for {job_id}: holder={job.get('lease')!r} caller={lease!r}")
    return job


def renew_lease(execution_id: str, job_id: str, lease: str, *, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> dict[str, Any]:
    job = _load_owned(execution_id, job_id, lease)
    job["leaseExpiresEpoch"] = _clock_now() + ttl_seconds
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(execution_id, job_id), job)
    return job

def _stamp_locked_creator(job: Mapping[str, Any], draft_meta: dict[str, Any], meta_path: Path) -> bool:
    """把 job 包里冻结的创作者锁定到 draft_meta（治理元数据系统所有，非 Agent 转写）。

    创作者分配在 content_plan 阶段已锁定并随 job 包下发，是唯一真相源；正文由 Agent 创作，
    但锁定创作者不应依赖 Agent 手工誊抄（漏写一字即整单 dead，放量必崩）。这里在完成校验前
    用 job 包的锁定值确定性回填 draft_meta，缺失或与锁定值不一致都以系统锁定值为准。
    返回是否发生回填（用于判断是否需要落盘）。
    """
    locked = creator_from_payload(job)
    if not locked:
        return False
    changed = False
    for field in CREATOR_ASSIGNMENT_FIELDS:
        value = locked.get(field)
        if value in (None, "", {}):
            continue
        # 只回填缺失字段（Agent 漏写）；若 Agent 写入与锁定值冲突的非空值，保留原值，
        # 交由下面的创作者校验暴露冲突，不静默覆盖以免掩盖真实的分配偏离。
        if draft_meta.get(field) in (None, "", {}):
            draft_meta[field] = value
            changed = True
    if changed:
        try:
            write_json(meta_path, draft_meta)
        except Exception:  # noqa: BLE001
            return False
    return changed


def _author_completion_issues(job: Mapping[str, Any]) -> list[str]:
    if str(job.get("stage") or "") != "author":
        return []
    if not bool(job.get("requireGovernance")):
        return []
    meta = job.get("meta") if isinstance(job.get("meta"), Mapping) else {}
    content_dir = str(meta.get("contentObjectDir") or "").strip().strip("/")
    if not content_dir or not content_dir.startswith("posts/article/"):
        return []
    try:
        from content.post.draft_io import is_placeholder
    except Exception as exc:  # noqa: BLE001
        return [f"author completion validator unavailable: {exc}"]
    execution_id = str(job.get("executionId") or "")
    root = store.execution_root(execution_id)
    draft_path = root / content_dir / "4.draft" / "draft.article.md"
    meta_path = root / content_dir / "4.draft" / "draft_meta.json"
    issues: list[str] = []
    article_ok = False
    if not draft_path.is_file():
        issues.append(f"author output missing: {draft_path.relative_to(root).as_posix()}")
    else:
        try:
            article = draft_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"author output unreadable: {exc}")
        else:
            if is_placeholder(article):
                issues.append("author output remains placeholder")
            else:
                article_ok = True
    try:
        draft_meta = read_json(meta_path)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"author draft_meta unreadable: {exc}")
        draft_meta = {}
    generator = str(draft_meta.get("generator") or "").strip()
    if generator != "agent":
        issues.append(f"draft_meta.generator is {generator or '<missing>'}, expected agent")
    # 治理元数据系统所有：仅对真正完成创作的草稿（正文非占位、generator=agent）确定性回填
    # 锁定创作者，避免 Agent 漏写冻结创作者导致整单 dead；占位/非 agent 草稿仍按上面硬失败。
    if article_ok and generator == "agent" and isinstance(draft_meta, dict):
        _stamp_locked_creator(job, draft_meta, meta_path)
    expected_creator = creator_from_payload(job)
    if expected_creator:
        actual_creator = creator_from_payload(draft_meta)
        for field in ("authorId", "creatorProfileId", "creatorArchetype", "creatorProfileVersion"):
            expected = str(expected_creator.get(field) or "").strip()
            actual = str(actual_creator.get(field) or "").strip()
            if expected and actual != expected:
                issues.append(
                    f"draft_meta.{field} is {actual or '<missing>'}, "
                    f"expected locked creator assignment {expected}"
                )
    return issues

def complete_job(execution_id: str, job_id: str, lease: str) -> dict[str, Any]:
    job = _load_owned(execution_id, job_id, lease)
    if bool(job.get("resultEnvelopeRequired")) and not job.get("resultEnvelopeRef"):
        raise RuntimeError(f"result envelope required before completing job {job_id}")
    completion_issues = _author_completion_issues(job)
    if completion_issues:
        return fail_job(
            execution_id,
            job_id,
            lease,
            error="; ".join(completion_issues),
            fingerprint=issues_fingerprint(completion_issues),
            same_run_retryable=True,
        )
    job["state"] = STATE_SUCCEEDED
    job["lease"] = None
    job["leaseExpiresEpoch"] = 0
    job["deadlineEpoch"] = 0
    job["notBeforeEpoch"] = 0
    job["sameRunRetryable"] = False
    job["lastError"] = None
    job["timings"].append({"event": "succeeded", "at": store.now_iso()})
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(execution_id, job_id), job)
    return job

def _stored_envelope_ref(envelope_path: Path, *, root: Path) -> str:
    try:
        return str(envelope_path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(envelope_path)

def complete_job_with_envelope(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    envelope_path: str | Path,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Complete a job only after validating an AgentResultEnvelope.

    This is the production admission path: files must exist, hashes must match,
    and every gate must have exactly one passing final verdict.
    """
    job = _load_owned(execution_id, job_id, lease)
    root = Path(workspace_root) if workspace_root is not None else store.execution_root(execution_id)
    path = Path(envelope_path)
    if not path.is_absolute():
        path = root / path
    try:
        envelope = read_json(path)
    except Exception as exc:  # noqa: BLE001
        issues = [f"result envelope unreadable: {exc}"]
        return fail_job(
            execution_id,
            job_id,
            lease,
            error="; ".join(issues),
            fingerprint=pc.stable_failure_fingerprint(issues),
            same_run_retryable=True,
        )
    issues = pc.validate_agent_result_envelope(envelope, workspace_root=root)
    issues.extend(pc.assert_envelope_matches_job(envelope, job))
    issues.extend(_envelope_governance_issues(job, envelope))
    if issues:
        return fail_job(
            execution_id,
            job_id,
            lease,
            error="; ".join(issues),
            fingerprint=pc.stable_failure_fingerprint(issues),
            same_run_retryable=True,
        )

    job["resultEnvelopeRef"] = _stored_envelope_ref(path, root=root)
    job["gateVerdicts"] = list(envelope.get("gates") or [])
    job.setdefault("timings", []).append({"event": "envelope_accepted", "at": store.now_iso(), "envelope": job["resultEnvelopeRef"]})
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(execution_id, job_id), job)
    return complete_job(execution_id, job_id, lease)


def reconcile_completed_refs(
    execution_id: str,
    refs: Iterable[str],
    stage: str,
    *,
    reason: str = "artifact_completed",
) -> list[str]:
    """把已在对象产物/工作流侧确认完成的 ref 对齐为 succeeded。

    用于 fanout 历史残留清理：例如 author 曾 startup_failed/dead，但后续通过
    finalize/manual rerun 已产出 approved 成品。此时 object_queue 不应继续把计划
    聚合拖回 failed/dead。
    """
    touched: list[str] = []
    wanted = {str(ref).strip() for ref in refs if str(ref).strip()}
    if not wanted:
        return touched
    for ref in sorted(wanted):
        job_id = stable_job_id(execution_id, ref, stage)
        path = _job_path(execution_id, job_id)
        if not path.is_file():
            continue
        job = read_json(path)
        if str(job.get("stage") or "") != stage:
            continue
        if str(job.get("state") or "") == STATE_SUCCEEDED:
            continue
        job["state"] = STATE_SUCCEEDED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = False
        job["lastError"] = None
        job.setdefault("timings", []).append(
            {"event": "reconciled", "at": store.now_iso(), "reason": reason}
        )
        job["updatedAt"] = store.now_iso()
        write_json(path, job)
        touched.append(ref)
    return touched

def _is_stuck(job: dict[str, Any], fingerprint: str | None) -> bool:
    """断路器：同一失败指纹连续 stuckThreshold 次不变 → 卡死（同 issues 反复修不动）。"""
    if not fingerprint:
        return False
    threshold = int(job.get("stuckThreshold") or DEFAULT_STUCK_THRESHOLD)
    prints = list(job.get("failureFingerprints") or [])
    prints.append(fingerprint)
    job["failureFingerprints"] = prints[-threshold:]
    recent = job["failureFingerprints"]
    return len(recent) >= threshold and len(set(recent)) == 1


def _apply_failure(
    job: dict[str, Any],
    error: str,
    *,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> dict[str, Any]:
    """失败状态机（fail_job 与 reaper 共用）：

    - 同一失败指纹连续 stuckThreshold 次不变 → 直接 dead（stuck，不再空耗 attempts）；
    - 未超 maxAttempts → failed + 指数退避；超出 → dead。
    """
    now = _clock_now()
    attempt = int(job.get("attempt") or 0)
    startup_failure_count = int(job.get("startupFailureCount") or 0)
    if startup_failure:
        startup_failure_count += 1
        job["startupFailureCount"] = startup_failure_count
    job["lastError"] = error
    job["lease"] = None
    job["sameRunRetryable"] = bool(same_run_retryable)
    job.setdefault("timings", []).append({"event": "failed", "at": store.now_iso(), "error": error})
    stuck = _is_stuck(job, fingerprint)
    exhausted = (
        startup_failure_count >= int(job.get("maxStartupFailures") or DEFAULT_MAX_STARTUP_FAILURES)
        if startup_failure
        else attempt >= int(job.get("maxAttempts") or 1)
    )
    if stuck or exhausted:
        job["state"] = STATE_DEAD
        job["notBeforeEpoch"] = 0
        if stuck:
            job["stuckDetected"] = True
            _emit_notification(
                job.get("executionId", ""),
                {
                    "event": "stuck",
                    "ref": job.get("ref"),
                    "jobId": job.get("jobId"),
                    "fingerprint": fingerprint,
                    "stuckThreshold": job.get("stuckThreshold"),
                    "lastError": error,
                },
            )
    else:
        job["state"] = STATE_FAILED
        job["notBeforeEpoch"] = now + _backoff_seconds(
            startup_failure_count if startup_failure else attempt
        )
    job["updatedAt"] = store.now_iso()
    return job


def fail_job(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    error: str,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> dict[str, Any]:
    """失败处理：未超 maxAttempts → 退回 failed(退避后可重取)；超出 / 卡死 → dead(转人工)。

    fingerprint：本轮失败的 issues 指纹（如 review_gate.issues 排序后 sha1），
    用于断路器识别"同 issues 反复修不动"。
    same_run_retryable=False：仅写 failed+backoff 留待下一次 fanout 运行，不要求当前进程继续等待。
    startup_failure=True：用于 startup failure 等“未真正执行”的场景，单独累计 startupFailureCount，
    不消耗内容质量重试预算 attempt。
    """
    job = _load_owned(execution_id, job_id, lease)
    _apply_failure(
        job,
        error,
        fingerprint=fingerprint,
        same_run_retryable=same_run_retryable,
        startup_failure=startup_failure,
    )
    og.append_failure(
        execution_id,
        ref=str(job.get("ref") or ""),
        stage=str(job.get("stage") or ""),
        reason=error,
        category=og.classify_failure(error),
        owner=str(job.get("owner") or ""),
    )
    write_json(_job_path(execution_id, job_id), job)
    return job


def revive_dead_startup_jobs(
    execution_id: str,
    *,
    refs: Iterable[str] | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """把仅因 startup failure 卡住的 job 恢复为 queued，继续同一批次主线。

    兼容两种真实现场：
    - 已耗尽 startup budget，落到 `dead`
    - 非 retryable startup 失败，暂留在 `failed`

    两者在“当前 draft 仍是占位稿、需要重新 author”这一语义上等价，都应允许
    后续 `sync_content_author_jobs()` 把 job 拉回 `queued`。
    """
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    revived: list[str] = []
    for job in _load_jobs(execution_id):
        if job.get("state") not in (STATE_DEAD, STATE_FAILED):
            continue
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        last_error = str(job.get("lastError") or "")
        if not last_error.startswith("startup:"):
            continue
        job["state"] = STATE_QUEUED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = True
        job["startupFailureCount"] = 0
        job["lastError"] = None
        job["failureFingerprints"] = []
        job.pop("stuckDetected", None)
        job.setdefault("timings", []).append({"event": "revived", "at": store.now_iso(), "reason": "startup_failure_retry"})
        job["updatedAt"] = store.now_iso()
        write_json(_job_path(execution_id, str(job["jobId"])), job)
        revived.append(ref)
    return {"revived": sorted(revived), "summary": queue_summary(execution_id)}


def issues_fingerprint(issues: Iterable[str]) -> str:
    """把一组 review issues 归一化为稳定指纹（供断路器比对"同 issues 反复修不动"）。"""
    norm = sorted({str(i).strip() for i in issues if str(i).strip()})
    return hashlib.sha1("\u0000".join(norm).encode("utf-8")).hexdigest()[:16]

def record_usage(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    tokens: int = 0,
    cost_usd: float = 0.0,
) -> dict[str, Any]:
    """累计 token/cost 用量；超 tokenBudget/costBudgetUsd（>0 时）→ 强制 dead（budget_exceeded）。"""
    job = _load_owned(execution_id, job_id, lease)
    usage = dict(job.get("usage") or {"tokens": 0, "costUsd": 0.0})
    usage["tokens"] = int(usage.get("tokens", 0)) + int(tokens)
    usage["costUsd"] = float(usage.get("costUsd", 0.0)) + float(cost_usd)
    job["usage"] = usage
    job.setdefault("tokenLedger", []).append(
        pc.build_token_ledger_entry(
            execution_id=str(job.get("executionId") or execution_id),
            job_id=job_id,
            # run 关联（P4 补强）：优先 agent runId；无 runId 时 lease 是本次执行实例
            # 的唯一持有标识，作为 run 关联兜底。
            run_id=str(job.get("agentRunId") or lease or job_id),
            creator_profile_id=str(job.get("creatorProfileId") or (job.get("meta") or {}).get("creatorProfileId") or "unknown"),
            content_type=str(job.get("contentType") or (job.get("meta") or {}).get("contentType") or job.get("stage") or "unknown"),
            budget_tokens=int(job.get("tokenBudget") or 0),
            used_tokens=int(usage.get("tokens") or 0),
            cost_usd=float(usage.get("costUsd") or 0.0),
            provider=str((job.get("meta") or {}).get("agentProvider") or ""),
            model=str((job.get("meta") or {}).get("model") or ""),
        )
    )
    token_budget = int(job.get("tokenBudget") or 0)
    cost_budget = float(job.get("costBudgetUsd") or 0.0)
    over_token = token_budget > 0 and usage["tokens"] > token_budget
    over_cost = cost_budget > 0 and usage["costUsd"] > cost_budget
    if over_token or over_cost:
        reason = (
            f"budget_exceeded: tokens={usage['tokens']}/{token_budget} costUsd={usage['costUsd']}/{cost_budget}"
        )
        # 预算耗尽是硬停（不重试）：强制 dead + notify。
        job["attempt"] = int(job.get("maxAttempts") or 1)
        _apply_failure(job, reason)
        _emit_notification(
            execution_id,
            {"event": "budget_exceeded", "ref": job.get("ref"), "jobId": job_id, "usage": usage},
        )
    else:
        job["updatedAt"] = store.now_iso()
    write_json(_job_path(execution_id, job_id), job)
    return job


def reap_jobs(execution_id: str) -> dict[str, Any]:
    """主动 reaper（业界 stuck-job recovery）：
    - 超 deadlineEpoch（墙钟硬上限）的 leased job → 强制 fail（timeout），按 maxAttempts 升级 dead；
    - lease 过期但未超 deadline（崩溃/无心跳）的 leased job → 回收为 queued，可被重取。
    """
    now = _clock_now()
    timed_out: list[str] = []
    reclaimed: list[str] = []
    for job in _load_jobs(execution_id):
        if job.get("state") != STATE_LEASED:
            continue
        deadline = float(job.get("deadlineEpoch") or 0)
        lease_exp = float(job.get("leaseExpiresEpoch") or 0)
        if deadline and now > deadline:
            _apply_failure(job, f"timeout: exceeded maxWallClock ({job.get('maxWallClockSeconds')}s)")
            job["deadlineEpoch"] = 0
            write_json(_job_path(execution_id, job["jobId"]), job)
            timed_out.append(str(job.get("ref")))
        elif lease_exp and now > lease_exp:
            job["state"] = STATE_QUEUED
            job["lease"] = None
            job["leaseExpiresEpoch"] = 0
            job["deadlineEpoch"] = 0
            job.setdefault("timings", []).append({"event": "reclaimed", "at": store.now_iso(), "reason": "lease_expired"})
            job["updatedAt"] = store.now_iso()
            write_json(_job_path(execution_id, job["jobId"]), job)
            reclaimed.append(str(job.get("ref")))
    return {"timedOut": sorted(timed_out), "reclaimed": sorted(reclaimed)}


def dead_jobs(execution_id: str) -> list[dict[str, Any]]:
    """列出 dead job（转人工修复队列），含最后错误与尝试数。"""
    out: list[dict[str, Any]] = []
    for job in _load_jobs(execution_id):
        if job.get("state") != STATE_DEAD:
            continue
        out.append(
            {
                "jobId": job.get("jobId"),
                "ref": job.get("ref"),
                "stage": job.get("stage"),
                "attempt": job.get("attempt"),
                "lastError": job.get("lastError"),
            }
        )
    return out


def block_job(execution_id: str, job_id: str, *, reason: str) -> dict[str, Any]:
    path = _job_path(execution_id, job_id)
    job = read_json(path)
    job["state"] = STATE_BLOCKED
    job["lease"] = None
    job["lastError"] = reason
    job["updatedAt"] = store.now_iso()
    write_json(path, job)
    return job


def requeue_refs(
    execution_id: str,
    refs: Iterable[str],
    stage: str,
    *,
    reason: str = "reducer_fail",
) -> list[str]:
    """把指定 ref 重新入队为 queued（同批重跑，不新建 repair batch）。

    适用于：
    - reducer 跨篇门失败后，只回退受影响 ref；
    - 人工/Agent 已修复对象产物后，把 dead/failed ref 拉回当前批次继续跑。
    """
    touched: list[str] = []
    for ref in refs:
        job_id = stable_job_id(execution_id, ref, stage)
        path = _job_path(execution_id, job_id)
        if not path.is_file():
            continue
        job = read_json(path)
        job["state"] = STATE_QUEUED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = True
        job["startupFailureCount"] = 0
        job["lastError"] = None
        job["failureFingerprints"] = []
        job.pop("stuckDetected", None)
        job["timings"].append({"event": "requeued", "at": store.now_iso(), "reason": reason})
        job["updatedAt"] = store.now_iso()
        write_json(path, job)
        touched.append(ref)
    return touched

def purge_jobs(
    execution_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """硬清理匹配 job（reset_state / 上游回退后丢弃过期 stage 队列）。

    object_queue 是 workflow 下游派生物，不是发布契约真相源；当 workflow 明确回到
    download/content_plan/compose 之前时，旧 author job 已经失效，必须整体丢弃。
    """
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    removed: list[str] = []
    for job in _load_jobs(execution_id):
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        path = _job_path(execution_id, str(job.get("jobId") or ""))
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(ref)
    return {"removed": sorted(removed), "summary": queue_summary(execution_id)}


def queue_summary(execution_id: str) -> dict[str, Any]:
    jobs = _load_jobs(execution_id)
    by_state: dict[str, list[str]] = {}
    by_backend: dict[str, int] = {}
    for job in jobs:
        by_state.setdefault(str(job.get("state")), []).append(str(job.get("ref")))
        backend = str(job.get("queueBackend") or QUEUE_BACKEND_LOCAL)
        by_backend[backend] = by_backend.get(backend, 0) + 1
    return {
        "total": len(jobs),
        "byState": {k: sorted(v) for k, v in sorted(by_state.items())},
        "byBackend": dict(sorted(by_backend.items())),
    }


def queue_runtime_snapshot(
    execution_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """调度期快照：给 runner 判断“当前真无活”还是“只是退避/互斥空窗”。

    refs=None 表示不过滤；refs 非空时只统计 assignment 负责的 ref 范围。
    sameRunRetryable=False 的 failed job（例如 startup 失败）保留给下一次 run，不要求当前进程继续等待。
    """
    current = _clock_now() if now is None else float(now)
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    by_state: dict[str, int] = {}
    waitable_live = 0
    leaseable_now = 0
    failed_backoff_same_run = 0
    next_retry_epoch: float | None = None
    next_lease_expiry_epoch: float | None = None
    next_deadline_epoch: float | None = None
    for job in _load_jobs(execution_id):
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        state = str(job.get("state") or "")
        by_state[state] = by_state.get(state, 0) + 1
        if state == STATE_QUEUED:
            waitable_live += 1
            leaseable_now += 1
            continue
        if state == STATE_LEASED:
            waitable_live += 1
            lease_exp = float(job.get("leaseExpiresEpoch") or 0)
            if lease_exp and lease_exp <= current:
                leaseable_now += 1
            elif lease_exp:
                next_lease_expiry_epoch = (
                    lease_exp if next_lease_expiry_epoch is None else min(next_lease_expiry_epoch, lease_exp)
                )
            deadline = float(job.get("deadlineEpoch") or 0)
            if deadline:
                next_deadline_epoch = deadline if next_deadline_epoch is None else min(next_deadline_epoch, deadline)
            continue
        if state != STATE_FAILED:
            continue
        if not bool(job.get("sameRunRetryable", True)):
            continue
        waitable_live += 1
        not_before = float(job.get("notBeforeEpoch") or 0)
        if not_before <= current:
            leaseable_now += 1
        else:
            failed_backoff_same_run += 1
            next_retry_epoch = not_before if next_retry_epoch is None else min(next_retry_epoch, not_before)
    return {
        "total": sum(by_state.values()),
        "byState": dict(sorted(by_state.items())),
        "waitableLive": waitable_live,
        "leaseableNow": leaseable_now,
        "failedBackoffSameRun": failed_backoff_same_run,
        "nextRetryEpoch": next_retry_epoch,
        "nextLeaseExpiryEpoch": next_lease_expiry_epoch,
        "nextDeadlineEpoch": next_deadline_epoch,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
