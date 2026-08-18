"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.support import Any, ExecutionContext, ExecutionStateStatus, MANAGED_AGENT_FUTURE_GRACE_SECONDS, MANAGED_AGENT_TIMEOUT_SECONDS, MANAGED_LANE_LIMITS, MAX_MANAGED_INFRA_RETRIES, MAX_REACT_REWINDS, Mapping, Path, ThreadPoolExecutor, _is_homepage_only_execution, _normalize_managed_agent_provider, defaultdict, execution_root, load_execution_state, os, release_root, save_execution_state, store, time, wait
from content.execution.agent.managed_checkpoint import (
    _managed_yield_after_ref_slice,
    _run_managed_checkpoint,
)

_AGENT_FUTURE_POLL_TIMEOUT_SECONDS = active_runtime_policy().agent_future_poll_timeout_seconds





def _reconcile_completed_publish_state(ctx: ExecutionContext) -> bool:
    """Close canonical publish evidence when an object Agent finished first."""
    from content.execution.controller.publish import _publishable_homepage_refs
    state = load_execution_state(ctx.execution_id)
    if "publish" not in set(state.completed or []):
        return True
    if _is_homepage_only_execution(ctx):
        from content.execution.qualification import finalize_execution_qualification

        from content.execution.controller.publish import _publishable_homepage_names

        try:
            qualification = finalize_execution_qualification(
                ctx.execution_id,
                publishable_names=_publishable_homepage_names(ctx),
            )
        except (OSError, TypeError, ValueError) as exc:
            qualification_issues = [str(exc)]
        else:
            qualification_issues = [str(issue) for issue in qualification.issues]
        if qualification_issues:
            state.completed = [
                stage for stage in (state.completed or []) if stage != "publish"
            ]
            state.status = ExecutionStateStatus.RUNNING
            state.failed_objects = qualification_issues
            state.next_action = "repair execution source qualification before publish"
            save_execution_state(state)
            return False
        from core.paths import PUBLISH_ROOT
        from content.execution.workspace import execution_root, write_publish_ref
        from content.release.canonical.object_transaction_audit import (
            validate_canonical_publish,
        )
        from content.release.canonical.object_transaction_contract import (
            refresh_canonical_tag_snapshots,
        )

        refresh_canonical_tag_snapshots(PUBLISH_ROOT)
        closure = validate_canonical_publish(PUBLISH_ROOT)
        if closure["status"] != "passed":
            state.completed = [stage for stage in (state.completed or []) if stage != "publish"]
            state.status = ExecutionStateStatus.RUNNING
            state.failed_objects = [str(issue) for issue in closure["issues"]]
            state.next_action = "repair canonical publish closure before publish"
            save_execution_state(state)
            return False
        homepage_refs = _publishable_homepage_refs(ctx)
        write_publish_ref(
            ctx.execution_id,
            entity_refs=[ref.removeprefix("/entity/") for ref in homepage_refs],
        )
        save_execution_state(state)
        return True
    # posts execution：canonical publish 是唯一发布真相源；promotion 幂等地
    # 复验 object transaction、closure 并回写 publish_ref。
    from content.release.canonical.post_promotion import promote_execution_posts

    try:
        promote_execution_posts(ctx.execution_id)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        state.completed = [
            stage for stage in (state.completed or []) if stage != "publish"
        ]
        state.status = ExecutionStateStatus.RUNNING
        state.failed_objects = [str(exc)]
        state.next_action = "repair canonical post promotion before publish"
        save_execution_state(state)
        return False
    save_execution_state(state)
    return True

def _managed_checkpoint_repair_budget_exhausted(used_attempts: int) -> bool:
    """Return whether a checkpoint spent its initial pass and all ReAct repairs."""
    return used_attempts > MAX_REACT_REWINDS

def run_managed_controller(ctx: ExecutionContext) -> int:
    """父进程消费全部 Agent checkpoint，直到 release verify 通过或转人工。"""
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done, _handle_managed_infra_budget_exhausted, _managed_author_failure_refs, _managed_consecutive_no_start_infra_failures
    from content.execution.agent.history import last_managed_agent_run
    from content.execution.recovery.download_unresolved import _download_plan_unresolved_entities, _write_download_availability
    from content.execution.controller.control import _recover_stale_controller_yield
    from content.execution.controller.orchestrator import run_controller
    reconcile_failures = 0
    while True:
        code = run_controller(ctx)
        if code == 0:
            if _reconcile_completed_publish_state(ctx):
                return 0
            # promote/closure repair stripped publish; allow one repair pass only.
            # Infinite continue previously burned disk when create-once / identity
            # conflicts kept failing after a successful publish stage.
            reconcile_failures += 1
            if reconcile_failures > 1:
                state = load_execution_state(ctx.execution_id)
                state.status = ExecutionStateStatus.MANUAL_REQUIRED
                state.next_action = (
                    "canonical publish reconcile failed after publish; "
                    "see failedObjects for promote/closure evidence"
                )
                state.heartbeat_at = store.now_iso()
                if not state.failed_objects:
                    state.failed_objects = [
                        "canonical publish reconcile failed after publish"
                    ]
                save_execution_state(state)
                return 1
            continue
        if code != 10:
            return code
        state = load_execution_state(ctx.execution_id)
        stage = str(state.waiting_checkpoint or "")
        try:
            from core.control_types import ExecutionStage, ReliableTaskDispatchStatus

            typed_stage = ExecutionStage(stage)
        except ValueError:
            typed_stage = None
        if typed_stage is not None:
            from content.execution.agent.reliabletask_dispatch import (
                dispatch_reliabletask_checkpoint,
            )

            dispatch = dispatch_reliabletask_checkpoint(ctx, typed_stage)
            if dispatch is not None:
                state = load_execution_state(ctx.execution_id)
                state.owner = f"managed-{ctx.runtime.value}:reliabletask:{stage}"
                state.heartbeat_at = store.now_iso()
                state.failed_issue_records = [
                    issue.as_dict() for issue in dispatch.issues
                ]
                state.failed_objects = [str(issue) for issue in dispatch.issues]
                state.next_action = (
                    f"ReliableTask {dispatch.queue_stage.value}: "
                    f"attempted={dispatch.attempted_count}, "
                    f"completed={dispatch.completed_count}, "
                    f"discarded={len(dispatch.discarded)}, "
                    f"status={dispatch.status.value}"
                )
                if dispatch.status is ReliableTaskDispatchStatus.COMPLETED:
                    state.status = ExecutionStateStatus.RUNNING
                    save_execution_state(state)
                    continue
                state.status = (
                    ExecutionStateStatus.MANUAL_REQUIRED
                    if dispatch.status is ReliableTaskDispatchStatus.BLOCKED
                    else ExecutionStateStatus.WAITING_AGENT
                )
                save_execution_state(state)
                return (
                    1
                    if dispatch.status is ReliableTaskDispatchStatus.BLOCKED
                    else 10
                )
        if isinstance(state.controller_yield, Mapping):
            if _recover_stale_controller_yield(ctx, state):
                continue
            print(f"[task execute] controller yield at checkpoint '{stage}'; resume later")
            return 10
        retries = state.retry_counts
        used = int(retries.get(stage, 0))
        retry_blocked_author_progress = (
            stage == "post_author"
            and used >= MAX_REACT_REWINDS
            and (last_run := last_managed_agent_run(state)) is not None
            and last_run.stage.value == stage
            and last_run.finished_count > 0
        )
        if retry_blocked_author_progress:
            failed_refs = _managed_author_failure_refs(
                last_run.outcomes
            )
            retries.pop(stage, None)
            state.retry_counts = retries
            state.status = ExecutionStateStatus.REPAIRING
            state.failed_objects = failed_refs or list(_checkpoint_is_done(ctx, stage)[1])
            state.next_action = (
                f"retry remaining {stage} refs after partial author progress; "
                f"finished={last_run.finished_count}, "
                f"remaining={len(state.failed_objects)}"
            )
            state.heartbeat_at = store.now_iso()
            save_execution_state(state)
            used = 0
        # ``MAX_REACT_REWINDS`` is the number of corrective ReAct passes, not
        # the total number of Agent attempts.  A checkpoint therefore gets its
        # initial authoring pass plus the configured repair passes.  Stopping
        # at ``used >=`` consumed the final repair before it could receive the
        # validation failure produced by the preceding pass.
        if _managed_checkpoint_repair_budget_exhausted(used):
            _ok, issues = _checkpoint_is_done(ctx, stage)
            state.status = ExecutionStateStatus.MANUAL_REQUIRED
            state.failed_objects = list(issues)
            state.next_action = (
                f"{stage} failed validation after {used} managed attempts"
                + (f"; unresolved={len(issues)}" if issues else "")
            )
            save_execution_state(state)
            return 1
        consecutive_no_start_failures = _managed_consecutive_no_start_infra_failures(
            state,
            stage=stage,
        )
        if consecutive_no_start_failures >= MAX_MANAGED_INFRA_RETRIES:
            last_run = last_managed_agent_run(state)
            infrastructure_failures = last_run.infrastructure_failures if last_run else 0
            result = _handle_managed_infra_budget_exhausted(
                ctx,
                state,
                stage=stage,
                infra_used=consecutive_no_start_failures,
                infrastructure_failures=infrastructure_failures,
            )
            if result:
                return result
            continue
        state.status = (
            ExecutionStateStatus.REPAIRING
            if used
            else ExecutionStateStatus.WAITING_AGENT
        )
        save_execution_state(state)
        if _run_managed_checkpoint(ctx, stage):
            state = load_execution_state(ctx.execution_id)
            infra = state.infrastructure_retry_counts
            infra.pop(stage, None)
            state.infrastructure_retry_counts = infra
            save_execution_state(state)
            if isinstance(state.controller_yield, Mapping):
                print(f"[task execute] controller yield after managed slice at checkpoint '{stage}'")
                return 10
            continue
        state = load_execution_state(ctx.execution_id)
        last_run = last_managed_agent_run(state)
        finished_count = last_run.finished_count if last_run else 0
        if stage == "post_author" and finished_count > 0:
            retries = state.retry_counts
            retries.pop(stage, None)
            state.retry_counts = retries
            infra = state.infrastructure_retry_counts
            infra.pop(stage, None)
            state.infrastructure_retry_counts = infra
            failed_refs = _managed_author_failure_refs(
                last_run.outcomes if last_run else ()
            )
            state.status = ExecutionStateStatus.REPAIRING
            state.failed_objects = failed_refs or list(_checkpoint_is_done(ctx, stage)[1])
            state.next_action = (
                f"retry remaining {stage} refs after partial author progress: "
                f"finished={finished_count}, remaining={len(state.failed_objects)}"
            )
            state.heartbeat_at = store.now_iso()
            if _managed_yield_after_ref_slice():
                state.controller_yield = {
                    "stage": stage,
                    "reason": "managed ref slice partially completed",
                    "hint": state.next_action,
                    "yieldedAt": state.heartbeat_at,
                }
                save_execution_state(state)
                print(f"[task execute] controller yield after partial managed slice at checkpoint '{stage}'")
                return 10
            state.controller_yield = None
            save_execution_state(state)
            time.sleep(2)
            continue
        infrastructure_failures = last_run.infrastructure_failures if last_run else 0
        if infrastructure_failures:
            infra = state.infrastructure_retry_counts
            if stage == "post_author" and finished_count > 0:
                # Cursor bridge failures are infrastructure noise, not content
                # failures.  Large author waves may still make real progress
                # while a subset of jobs fails to start; count only consecutive
                # no-progress waves against the infra retry budget.
                infra.pop(stage, None)
                state.infrastructure_retry_counts = infra
                failed_refs = _managed_author_failure_refs(
                    last_run.outcomes if last_run else ()
                )
                state.status = ExecutionStateStatus.REPAIRING
                state.failed_objects = failed_refs
                state.next_action = (
                    f"retry remaining {stage} refs after partial progress: "
                    f"finished={finished_count}, infraFailures={infrastructure_failures}, "
                    f"remaining={len(failed_refs)}"
                )
                state.heartbeat_at = store.now_iso()
                save_execution_state(state)
                time.sleep(10)
                continue
            consecutive_no_start_failures = _managed_consecutive_no_start_infra_failures(
                state,
                stage=stage,
            )
            infra_used = max(int(infra.get(stage, 0)) + 1, consecutive_no_start_failures)
            infra[stage] = infra_used
            state.infrastructure_retry_counts = infra
            if infra_used >= MAX_MANAGED_INFRA_RETRIES:
                ok_after_failures, issues_after_failures = _checkpoint_is_done(ctx, stage)
                if ok_after_failures:
                    result = _handle_managed_infra_budget_exhausted(
                        ctx,
                        state,
                        stage=stage,
                        infra_used=infra_used,
                        infrastructure_failures=infrastructure_failures,
                        checkpoint_issues=issues_after_failures,
                    )
                    if result:
                        return result
                    continue
                if stage == "download_plan":
                    unresolved = _download_plan_unresolved_entities(ctx)
                    _write_download_availability(ctx, unresolved, source="managed_infra_retry")
                result = _handle_managed_infra_budget_exhausted(
                    ctx,
                    state,
                    stage=stage,
                    infra_used=infra_used,
                    infrastructure_failures=infrastructure_failures,
                    checkpoint_issues=issues_after_failures,
                )
                if result:
                    return result
                if ok_after_failures:
                    continue
                return 1
            state.next_action = (
                f"retry {stage} infrastructure: attempt "
                f"{infra_used + 1}/{MAX_MANAGED_INFRA_RETRIES}"
            )
            save_execution_state(state)
            time.sleep(min(30, 5 * infra_used))
            continue
        retries = state.retry_counts
        retries[stage] = used + 1
        state.retry_counts = retries
        save_execution_state(state)
        time.sleep(min(2 ** used, 5))
