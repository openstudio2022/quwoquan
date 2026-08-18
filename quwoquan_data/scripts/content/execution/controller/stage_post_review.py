"""Execute the object-level post review stage and its publishable closure."""

from __future__ import annotations

from core.control_types import ContentType, ExecutionStage, PostStage, StageStatus

from content.execution.controller.failure_isolation import run_isolated_batch
from content.execution.controller.post_review_support import (
    aggregate_review_fallback as _aggregate_review_fallback,
)
from content.execution.controller.post_review_support import (
    batch_reducer_payload as _batch_reducer_payload,
)
from content.execution.controller.post_review_support import (
    content_ref_types as _content_ref_types,
)
from content.execution.controller.post_review_support import (
    materialize_reviewed_refs as _materialize_reviewed_refs,
)
from content.execution.controller.post_review_support import (
    post_exit_issues as _post_exit_issues,
)
from content.execution.controller.post_review_support import (
    review_gate_is_stale as _review_gate_is_stale,
)
from content.execution.support import (
    AUTO,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    Sequence,
    StageResult,
    _is_homepage_only_execution,
    data_issue,
    data_issues,
    read_json,
)


def _run_post_review(ctx: ExecutionContext) -> StageResult:
    from content.execution.closure.post_review import (
        indexed_post_targets,
        resolve_post_review_closure,
        write_post_review_closure,
    )
    from content.execution.controller.execute.handoff import (
        build_execution_reducer_gate,
        write_execution_reducer_gate,
    )
    from content.execution.identity import parse_execution_id
    from content.execution.recovery.post_recovery import (
        _content_plan_base_draft_shortfall_refs,
        _release_base_draft_shortfall_refs,
    )
    from content.post import object_index as content_object
    from content.post.article.base_draft import (
        load_base_draft_ledger,
        save_base_draft_ledger,
    )
    from content.post.handler import PostStageRequest, handle_post

    save_base_draft_ledger(
        ctx.execution_id,
        load_base_draft_ledger(ctx.execution_id),
    )
    if _is_homepage_only_execution(ctx):
        write_execution_reducer_gate(
            ctx.execution_id,
            {
                "schema": "quwoquan_data.execution_reducer_gate",
                "passed": True,
                "issues": [],
                "affectedRefs": [],
                "sourceReuse": {},
                "intentDistribution": {},
                "imageCoverage": {},
            },
        )
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.DONE,
            "homepage-only 批次无篇目，post_review 确定性跳过"
            "（主页发布门由 build_validate + release gate 承载）",
        )

    refs = content_object.iter_content_refs(ctx.execution_id)
    active_refs = list(refs)
    from content.execution.agent.checkpoint_exclusion import (
        current_semantic_checkpoint_exclusions,
    )

    author_exclusions = current_semantic_checkpoint_exclusions(
        ctx.execution_id,
        stage=ExecutionStage.POST_AUTHOR,
        object_refs=active_refs,
    )
    object_targets = indexed_post_targets(ctx.execution_id)
    object_issues: dict[str, list[str]] = {ref: [] for ref in active_refs}

    def add_issues(ref: str, messages: Sequence[object]) -> None:
        bucket = object_issues[ref]
        for raw in messages:
            message = str(raw).strip()
            if message and message not in bucket:
                bucket.append(message)

    try:
        active_ref_types = _content_ref_types(ctx, active_refs)
    except ValueError as exc:
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.FAILED,
            f"post_review content object contract invalid: {exc}",
            fallback_stage=ExecutionStage.POST_COMPOSE,
            issue_records=data_issues(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.POST_REVIEW,
                messages=[str(exc)],
                recovery=DataRecoveryAction.STOP,
            ),
        )
    carrier = next(
        iter(active_ref_types),
        parse_execution_id(ctx.execution_id).content_type.value,
    )
    preflight_short_refs = _content_plan_base_draft_shortfall_refs(ctx, active_refs)
    for ref in preflight_short_refs:
        add_issues(ref, ["baseDraftText effective length below content_plan gate"])

    from content.execution.controller.stage_post_compose import (
        compose_brief_absorbed_path,
    )

    compose_absorbed_refs = [
        ref
        for ref in active_refs
        if compose_brief_absorbed_path(ctx.execution_id, ref).is_file()
    ]
    for ref in compose_absorbed_refs:
        try:
            absorbed = read_json(compose_brief_absorbed_path(ctx.execution_id, ref))
        except (OSError, ValueError, TypeError):
            absorbed = {}
        reason = str(absorbed.get("reason") or "compose-brief gate failed; absorbed")
        add_issues(ref, [reason])

    for ref, exclusion in author_exclusions.items():
        terminal = exclusion.get("terminalOutcome")
        terminal = terminal if isinstance(terminal, dict) else {}
        message = str(terminal.get("error") or "semantic author shortfall").strip()
        disposition = str(exclusion.get("disposition") or "excluded")
        repair_action = str(exclusion.get("repairAction") or "human_decision")
        add_issues(
            ref,
            [
                f"semantic author {disposition}: {message}; "
                f"repairAction={repair_action}"
            ],
        )

    excluded_refs = (
        set(preflight_short_refs)
        | set(compose_absorbed_refs)
        | set(author_exclusions)
    )
    reviewable_refs = [ref for ref in active_refs if ref not in excluded_refs]
    all_green = bool(reviewable_refs)
    stale_review_refs: list[str] = []
    for ref in reviewable_refs:
        gate_path = (
            content_object.content_object_dir(ctx.execution_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            all_green = False
            stale_review_refs.append(ref)
            continue
        envelope = read_json(gate_path)
        if (envelope.get("payload") or envelope).get("passed") is not True:
            all_green = False
            stale_review_refs.append(ref)
            continue
        if _review_gate_is_stale(ctx, ref, gate_path):
            all_green = False
            stale_review_refs.append(ref)

    review_refs = reviewable_refs
    if all_green:
        from content.source.media.check import check_images

        check_images(
            ctx.execution_id,
            list(reviewable_refs),
            allow_needs_review=True,
        )
    elif stale_review_refs:
        review_refs = sorted(set(stale_review_refs))
    if review_refs and not all_green:
        handle_post(
            PostStageRequest(
                execution_id=ctx.execution_id,
                content_type=ContentType(
                    next(iter(_content_ref_types(ctx, review_refs)))
                ),
                stage=PostStage.REVIEW,
                refs=tuple(review_refs),
                allow_partial=True,
                materialize=True,
            )
        )

    from content.execution.controller.post_independent_review import (
        run_post_independent_reviews,
    )
    from content.execution.controller.professional_asset_independent_review import (
        run_professional_asset_independent_reviews,
    )

    def _review_object(ref: str) -> list[object]:
        return [
            *_materialize_reviewed_refs(ctx, [ref]),
            *_post_exit_issues(ctx, [ref]),
        ]

    # 逐对象隔离：单个对象的 typed 失败只应让它自己在 closure 里被丢弃，不能连带
    # 作废整批已完成的评审。治理阻断与未归类失败仍然升级为 stage 失败。
    isolated = run_isolated_batch(reviewable_refs, _review_object)
    for ref, messages in isolated.succeeded:
        add_issues(ref, messages)
    for row in isolated.failed:
        add_issues(row.object_ref, row.issues)
    independent_records = run_post_independent_reviews(ctx, reviewable_refs)
    independent_records.extend(
        run_professional_asset_independent_reviews(ctx, reviewable_refs)
    )
    for issue in independent_records:
        if issue.ref and issue.ref in object_issues:
            add_issues(issue.ref, [issue])
        else:
            for ref in reviewable_refs:
                add_issues(ref, [issue])

    release_short_refs = _release_base_draft_shortfall_refs(
        ctx,
        active_refs=reviewable_refs,
    )
    for ref in release_short_refs:
        add_issues(ref, ["baseDraftText below release gate"])
    for ref in reviewable_refs:
        gate_path = (
            content_object.content_object_dir(ctx.execution_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            add_issues(ref, ["review_gate.json missing"])
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is not True:
            ref_issues = [str(item) for item in (payload.get("issues") or [])]
            add_issues(
                ref,
                [
                    "review_gate failed"
                    + (": " + "; ".join(ref_issues[:5]) if ref_issues else "")
                ],
            )

    article_refs = set(active_ref_types.get("article") or [])
    reducer_candidates = {ref for ref in article_refs if not object_issues[ref]}
    execution_gate = build_execution_reducer_gate(
        _batch_reducer_payload(ctx, refs=reducer_candidates)
    )
    while execution_gate.get("passed") is False and reducer_candidates:
        affected = {
            str(ref)
            for ref in execution_gate.get("affectedRefs") or []
            if str(ref) in reducer_candidates
        }
        if not affected:
            affected = set(reducer_candidates)
        reducer_messages = [
            str(issue) for issue in execution_gate.get("issues") or []
        ] or ["batch reducer failed without an issue"]
        for ref in affected:
            add_issues(ref, reducer_messages)
        reducer_candidates.difference_update(affected)
        execution_gate = build_execution_reducer_gate(
            _batch_reducer_payload(ctx, refs=reducer_candidates)
        )
    write_execution_reducer_gate(ctx.execution_id, execution_gate)

    closure = resolve_post_review_closure(
        ctx.execution_id,
        carrier=carrier,
        object_targets=object_targets,
        object_issues=object_issues,
    )
    write_post_review_closure(closure)
    if closure.qualified_count > 0:
        milestone = "met" if closure.passed else "partial"
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.DONE,
            f"post_review quota {milestone} "
            f"(qualified={closure.qualified_count}/{closure.approved_quota}, "
            f"discarded={len(closure.discarded)}, "
            f"isolated={isolated.report()['failedCount']})",
        )

    issue_records = list(independent_records)
    # 已归类的 issue 会以 str(issue) 进入 closure；再包一层 QUALITY_FAILED 会把
    # reviewer 技术性失败升级成内容质量失败，触发多余的 author 回退并吃掉 author
    # 自己的 attempt 预算。这里只补充尚未归类的 closure issue。
    classified = {
        (issue.ref, str(issue).strip()) for issue in independent_records if issue.ref
    }
    for row in closure.discarded:
        issue_records.extend(
            data_issue(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.POST_REVIEW,
                ref=row.object_ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message=message,
            )
            for message in row.issues
            if (row.object_ref, message) not in classified
        )
    if not issue_records:
        issue_records.append(
            data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.POST_REVIEW,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="post_review has no qualified content objects",
            )
        )
    discarded_refs = {row.object_ref for row in closure.discarded}
    # 每条 issue 已经携带 typed recovery。当全部 discarded 都只是 reviewer 侧的
    # RETRY_AGENT（内容本身通过了 deterministic gate），回到 post_compose 会重写
    # 一篇合格正文，并让 author 白白耗掉自己的 attempt 预算。这种情况下只该重跑
    # review 本身。
    retry_review_only = bool(issue_records) and all(
        issue.recovery is DataRecoveryAction.RETRY_AGENT
        for issue in issue_records
        if issue.ref in discarded_refs or not issue.ref
    )
    fallback = (
        ExecutionStage.CONTENT_PLAN
        if discarded_refs.intersection(preflight_short_refs)
        else _aggregate_review_fallback(ctx, refs=discarded_refs)
        or (
            ExecutionStage.POST_REVIEW
            if retry_review_only
            else ExecutionStage.POST_COMPOSE
        )
    )
    return StageResult(
        ExecutionStage.POST_REVIEW,
        AUTO,
        StageStatus.FAILED,
        "post_review has zero qualified objects "
        f"(qualified={closure.qualified_count}/{closure.approved_quota}, "
        f"discarded={len(closure.discarded)})",
        fallback_stage=fallback,
        issue_records=issue_records,
    )


__all__ = ["_run_post_review"]
