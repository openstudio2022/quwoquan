"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ContentType, ExecutionStage, PostStage, StageStatus
from content.execution.support import AUTO, Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, Sequence, StageResult, _active_spec, _is_homepage_only_execution, data_issue, data_issues, issue_messages, read_json
def _approved_review_refs(ctx: ExecutionContext, *, refs: set[str] | None = None) -> list[str]:
    from content.post import object_index as content_object
    approved: list[str] = []
    for ref in content_object.iter_content_refs(ctx.execution_id):
        if refs is not None and ref not in refs:
            continue
        try:
            gate_path = (
                content_object.content_object_dir(ctx.execution_id, ref)
                / "5.review"
                / "review_gate.json"
            )
        except KeyError:
            continue
        if not gate_path.is_file():
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is True:
            approved.append(ref)
    return approved

def _batch_reducer_payload(ctx: ExecutionContext, *, refs: set[str] | None = None) -> list[dict[str, str]]:
    from content.post import object_index as content_object
    from content.post.article.draft_io import read_draft_article, read_writing_pack
    payload: list[dict[str, str]] = []
    for ref in _approved_review_refs(ctx, refs=refs):
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        if coords.get("contentType") != "article":
            continue
        article = read_draft_article(ctx.execution_id, ref)
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        if not article:
            continue
        payload.append(
            {
                "ref": ref,
                "article": article,
                "writingIntent": str(pack.get("writingIntent") or ""),
                "baseSourceRef": str(pack.get("baseSourceRef") or ""),
                "baseSourceReusePolicy": str(pack.get("baseSourceReusePolicy") or ""),
            }
        )
    return payload

def _aggregate_review_fallback(
    ctx: ExecutionContext,
    *,
    refs: set[str] | None = None,
) -> ExecutionStage | None:
    """Aggregate typed review issues into the ReAct fallback stage.
    只有来源文件确实缺失/不可读时才回 download。事实表达、必含事实、
    文体或载体失败都属于单作品 compose 修复，不能让整批回退重抓来源。
    """
    from content.execution.stage_reports import iter_stage_envelopes
    saw_failure = False
    download_issue_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_UNREADABLE,
        DataIssueCode.SOURCE_PLAN_INVALID,
    }
    for _ref, rep in iter_stage_envelopes(ctx.execution_id, "post", "review_gate"):
        if refs is not None and _ref not in refs:
            continue
        payload = rep.get("payload") or rep
        if payload.get("passed") is True:
            continue
        issues = [
            DataIssue.from_dict(issue)
            for issue in payload.get("issues") or []
            if isinstance(issue, Mapping)
        ]
        if not issues:
            continue
        saw_failure = True
        if any(
            issue.code in download_issue_codes
            or issue.recovery is DataRecoveryAction.REWIND_DOWNLOAD
            for issue in issues
        ):
            return ExecutionStage.DOWNLOAD_PLAN
    return ExecutionStage.POST_COMPOSE if saw_failure else None

def _review_gate_is_stale(ctx: ExecutionContext, ref: str, gate_path: Path) -> bool:
    """Review depends on the latest compose contract and authored draft."""
    from content.post.article.draft_io import draft_article_path, prompt_path, writing_pack_path
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir
    from core.paths import STAGE_COMPOSE
    try:
        gate_mtime = gate_path.stat().st_mtime
    except OSError:
        return True
    candidates: list[Path] = [
        writing_pack_path(ctx.execution_id, ref),
        prompt_path(ctx.execution_id, ref),
        draft_article_path(ctx.execution_id, ref),
        content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE,
    ]
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_mtime > gate_mtime:
                return True
        except OSError:
            return True
    return False

def _content_ref_types(ctx: ExecutionContext, refs: list[str]) -> dict[str, list[str]]:
    from content.post import object_index as content_object
    from content.execution.identity import parse_execution_id

    execution_content_type = parse_execution_id(ctx.execution_id).content_type.value
    by_type: dict[str, list[str]] = {}
    for ref in refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        content_type = str(coords.get("contentType") or "").strip()
        if not content_type:
            raise ValueError(f"content object {ref!r} has no contentType")
        if content_type != execution_content_type:
            raise ValueError(
                f"content object {ref!r} type {content_type!r} conflicts with "
                f"execution type {execution_content_type!r}"
            )
        by_type.setdefault(content_type, []).append(ref)
    return {key: value for key, value in by_type.items() if value}

def _runtime_materialization_issues(ctx: ExecutionContext, refs: list[str]) -> list[str]:
    from content.execution.recovery.post_recovery import _content_type_for_carrier
    from content.post import object_index as content_object
    missing: list[str] = []
    issues: list[str] = []
    for ref in refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        expected_type = str(coords.get("contentType") or "article")
        try:
            obj_dir = content_object.content_object_dir(ctx.execution_id, ref)
        except KeyError:
            missing.append(ref)
            continue
        manifest_path = obj_dir / "manifest.json"
        if not manifest_path.is_file():
            missing.append(ref)
            continue
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError, TypeError):
            issues.append(f"{ref}: materialized manifest.json is unreadable")
            continue
        actual_type = _content_type_for_carrier(manifest.get("carrier") or manifest.get("contentType"))
        if actual_type != expected_type:
            issues.append(f"{ref}: runtime carrier {actual_type} != planned {expected_type}")
        if expected_type == "article" and not (obj_dir / "article.md").is_file():
            missing.append(ref)
    if missing:
        issues.insert(0, "release missing planned post ref(s): " + ", ".join(sorted(set(missing))[:20]))
    return issues

def _materialize_reviewed_refs(ctx: ExecutionContext, refs: list[str]) -> list[str]:
    from content.post.materialize_apply import materialize_posts
    from content.post.materialize_residue_cleanup import prune_unregistered_post_residue
    issues: list[str] = []
    by_type = _content_ref_types(ctx, refs)
    for content_type, typed_refs in sorted(by_type.items()):
        try:
            materialize_posts(ctx.execution_id, content_type, refs=typed_refs)
        except Exception as exc:  # noqa: BLE001 - gate turns materialization defects into stage issues.
            issues.append(f"{content_type} materialize failed: {exc}")
    # 物化后 content_object_index 已权威：清除 agent 用临时标题落地、最终改派坐标后
    # 遗留的死 provisional 残骸（未登记 + 无 manifest/无成品），否则目录证据链孤儿门
    # 会因旧坐标阶段残骸 BLOCK（放量时 agent 重组合/改标题会复现）。
    try:
        prune_unregistered_post_residue(ctx.execution_id)
    except Exception as exc:  # noqa: BLE001 - 剪枝失败降级为 stage issue，不静默吞。
        issues.append(f"prune unregistered post residue failed: {exc}")
    return issues

def _post_exit_issues(ctx: ExecutionContext, refs: list[str]) -> list[str]:
    from content.post.gate import gate_post
    issues: list[str] = []
    for content_type, typed_refs in sorted(_content_ref_types(ctx, refs).items()):
        issues.extend(gate_post(ctx.execution_id, content_type, refs=typed_refs))
    issues.extend(_runtime_materialization_issues(ctx, refs))
    # Keep repeated global/runtime findings readable across article+image gates.
    return list(dict.fromkeys(str(issue) for issue in issues))


def _run_post_review(ctx: ExecutionContext) -> StageResult:
    from content.execution.identity import parse_execution_id
    from content.execution.recovery.post_recovery import _content_plan_base_draft_shortfall_refs, _release_base_draft_shortfall_refs
    from content.post.handler import PostStageRequest, handle_post
    from content.post import object_index as content_object
    from content.post.article.base_draft import load_base_draft_ledger, save_base_draft_ledger
    from content.execution.handoff import build_execution_reducer_gate, write_execution_reducer_gate
    from content.execution.post_review_closure import (
        indexed_post_targets,
        resolve_post_review_closure,
        write_post_review_closure,
    )

    # 物化 batch 级 base_draft_ledger 落盘：纯图（image-only）批次不认领单一底稿、
    # assignments 合法为空，但 release_integrity 要求 ledger 文件存在且 schema 正确。
    # 幂等：文章批次的 assignments 已在底稿认领时写入，此处只保证文件落盘，不改内容。
    save_base_draft_ledger(
        ctx.execution_id, load_base_draft_ledger(ctx.execution_id)
    )
    if _is_homepage_only_execution(ctx):
        # homepage-only：无篇目对象；主页 review 证据在 build_validate 采纳门产出。
        # 与 image-only 空 payload 行为对齐，写空 batch reducer gate 供 release verify 消费。
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
            "homepage-only 批次无篇目，post_review 确定性跳过（主页发布门由 build_validate + release gate 承载）",
        )
    refs = content_object.iter_content_refs(ctx.execution_id)
    active_refs = list(refs)
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
    reviewable_refs = [
        ref for ref in active_refs if ref not in set(preflight_short_refs)
    ]
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
        # review gate 已绿时本分支跳过 handle_post 的 _stage_review，而 media_check
        # 正是在 _stage_review 内产出。纯图（image-only）内容对象的 review 在叶子阶段已
        # 通过，会直接走到此处，导致发布门因缺 media_check envelope 失败。这里幂等补跑
        # 图像安全体检（CV：人脸/水印/OCR/去重），保证发布门有真实 media_check 证据。
        from content.source.media.check import check_images

        check_images(ctx.execution_id, list(reviewable_refs), allow_needs_review=True)
    elif stale_review_refs:
        review_refs = sorted(set(stale_review_refs))
    if review_refs and not all_green:
        # 控制器路径必须拿到全部 per-ref review gate 再做对象级处置；
        # allow_partial=False 会在任一 ref 失败时 SystemExit，绕过 quota closure。
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

    for ref in reviewable_refs:
        add_issues(ref, _materialize_reviewed_refs(ctx, [ref]))
        add_issues(ref, _post_exit_issues(ctx, [ref]))
    independent_records = run_post_independent_reviews(ctx, reviewable_refs)
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

    # Reducer只消费仍 qualified 的 article，并把每个 reducer finding 归属到
    # affectedRefs。处置后重算，直到剩余 publishable closure 自身通过。
    article_refs = set(active_ref_types.get("article") or [])
    reducer_candidates = {
        ref for ref in article_refs if not object_issues[ref]
    }
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
    # Quota is a milestone, not a publish veto: any qualified objects may proceed.
    if closure.qualified_count > 0:
        milestone = "met" if closure.passed else "partial"
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.DONE,
            f"post_review quota {milestone} "
            f"(qualified={closure.qualified_count}/{closure.approved_quota}, "
            f"discarded={len(closure.discarded)})",
        )

    issue_records = list(independent_records)
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
    fallback = (
        ExecutionStage.CONTENT_PLAN
        if discarded_refs.intersection(preflight_short_refs)
        else _aggregate_review_fallback(ctx, refs=discarded_refs)
        or ExecutionStage.POST_COMPOSE
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
