"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Iterable, Mapping, Sequence, StageResult, data_issues, execution_root, issue_messages, load_execution_state, read_json, save_execution_state, shutil, store
from core.io import write_json

def _content_issue_matchers(
    ctx: ExecutionContext,
) -> dict[str, set[str]]:
    from content.post import object_index as content_object
    matchers: dict[str, set[str]] = {}
    for ref in content_object.iter_content_refs(ctx.execution_id):
        tokens = {ref}
        try:
            rel = content_object.content_object_rel(ctx.execution_id, ref)
        except KeyError:
            matchers[ref] = tokens
            continue
        tokens.add(rel)
        if rel.startswith("posts/"):
            tokens.add(rel[len("posts/"):])
        matchers[ref] = {token for token in tokens if token}
    return matchers

def _post_review_retry_refs(
    ctx: ExecutionContext,
    issue_records: Sequence[DataIssue],
) -> tuple[list[str], dict[str, list[str]]]:
    """Map review failures to refs without invalidating current green objects."""
    from content.post import object_index as content_object
    matchers = _content_issue_matchers(ctx)
    affected: set[str] = set()
    issue_map: dict[str, list[str]] = {}
    saw_object_gate = False
    for ref in content_object.iter_content_refs(ctx.execution_id):
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
        saw_object_gate = True
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is False:
            affected.add(ref)
            issue_map[ref] = [str(item) for item in (payload.get("issues") or [])]
    # Object gates are the latest and most precise verdict. Batch/release issues
    # often mention every object path and must not widen a two-ref repair to all.
    if saw_object_gate and affected:
        return sorted(affected), issue_map
    if saw_object_gate:
        reducer_path = execution_root(ctx.execution_id) / "_shared" / "execution_reducer_gate.json"
        if reducer_path.is_file():
            reducer = read_json(reducer_path)
            reducer_refs = [
                str(ref)
                for ref in (reducer.get("affectedRefs") or [])
                if str(ref) in matchers
            ]
            if reducer_refs:
                reducer_issues = [str(item) for item in (reducer.get("issues") or issue_messages(issue_records))]
                return sorted(set(reducer_refs)), {
                    ref: list(reducer_issues) for ref in reducer_refs
                }
        if not issue_records:
            return [], {}
    unmatched: list[DataIssue] = []
    for issue in issue_records:
        if not issue.ref or issue.ref not in matchers:
            unmatched.append(issue)
            continue
        affected.add(issue.ref)
        issue_map.setdefault(issue.ref, []).append(str(issue))
    if not affected and not saw_object_gate:
        affected = set(content_object.iter_content_refs(ctx.execution_id))
    if not affected:
        return [], {}
    refs = sorted(affected)
    for ref in refs:
        issue_map.setdefault(ref, [])
    if unmatched:
        for ref in refs:
            issue_map[ref].extend(issue_messages(unmatched))
    return refs, issue_map

def _issues_directly_reference_ref(
    *,
    ref: str,
    issue_records: Sequence[DataIssue],
) -> bool:
    return any(issue.ref == ref for issue in issue_records)

def _release_base_draft_shortfall_refs(
    ctx: ExecutionContext,
    *,
    active_refs: Iterable[str],
) -> list[str]:
    """Find content-plan objects that fail the article base-draft floor."""
    return _content_plan_base_draft_shortfall_refs(ctx, active_refs)

def _content_plan_base_draft_shortfall_refs(ctx: ExecutionContext, active_refs: Iterable[str]) -> list[str]:
    """Lightweight preflight for article source sufficiency before expensive gates.
    字数门形态自适应（唯一真相源 base_draft_readiness）：长文需正文≥600；图文混排
    底稿正文≥200 且有足量内联图/图注即可。禁止在此另起固定 600 raw 门误杀图多文少
    的真·图文底稿。
    """
    from content.post import object_index as content_object
    from content.post.article.base_draft import base_draft_readiness
    from content.post.article.draft_io import read_writing_pack
    short_refs: list[str] = []
    for ref in active_refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        if str(coords.get("contentType") or "article") != "article":
            continue
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        base_text = str(pack.get("baseDraftText") or "")
        readiness = base_draft_readiness(
            base_text,
            publish_media_mode=str(pack.get("publishMediaMode") or ""),
        )
        if not readiness["ready"]:
            short_refs.append(str(ref))
    return short_refs

def _content_type_for_carrier(carrier: object) -> str:
    normalized = str(carrier or "").strip()
    return normalized if normalized in {"article", "image", "video"} else "article"

def _invalidate_ref_for_retry(ctx: ExecutionContext, ref: str, *, preserve_draft: bool = False) -> bool:
    """清理旧草稿/旧成品，让 rewound execution 真正回到待重写状态。
    ``preserve_draft=True`` 时保留 ``4.draft`` 已写正文与 draft_meta（不 wipe 成
    placeholder / 不下调 generator），只清理已物化成品面与陈旧 review 侧车。配合
    `_write_retry_reports_for_refs` 写入更新的 ``5.review/repair_report.json``，让
    `_drafts_authored` 通过 ``repair_is_newer`` 把该 ref 标为待重写——agent 在已写正文
    基础上**就地修订**，而不是从占位从零重写（进度持久化，失败不销毁）。用于 post_review
    单点失败回退；显式 retry-stage / 写包契约变更仍用默认销毁语义。
    """
    from content.post import object_index as content_object
    from content.post.article.draft_io import draft_package_dir, read_writing_pack, write_image_evidence_draft, write_placeholder_draft
    try:
        obj_dir = content_object.content_object_dir(ctx.execution_id, ref)
        draft_dir = draft_package_dir(ctx.execution_id, ref)
    except KeyError:
        return False
    coords = content_object.content_coords(ctx.execution_id, ref) or {}
    pack = read_writing_pack(ctx.execution_id, ref) or {}
    content_type = _content_type_for_carrier(
        coords.get("contentType") or pack.get("carrier")
    )
    if not preserve_draft:
        if content_type == "image":
            write_image_evidence_draft(
                ctx.execution_id,
                ref,
                selected_asset_ids=[
                    str(asset.get("assetId") or "")
                    for asset in (pack.get("assets") or [])
                    if isinstance(asset, Mapping) and asset.get("assetId")
                ],
                cited_source_paths=[str(path) for path in (pack.get("sourcePaths") or []) if path],
            )
        elif content_type == "video":
            from content.post.video.authoring import video_script_path

            script_path = video_script_path(ctx.execution_id, ref)
            if script_path.is_file():
                script_path.unlink()
            write_json(
                draft_dir / "draft_meta.json",
                {
                    "ref": ref,
                    "generator": "pending",
                    "status": "pending_agent",
                    "citedSourcePaths": list(pack.get("sourcePaths") or []),
                },
            )
        else:
            write_placeholder_draft(
                ctx.execution_id,
                ref,
                allow_agent_downgrade=True,
                downgrade_reason="explicit execution retry invalidated upstream compose/author evidence",
            )
    author_self_check = draft_dir / "author_self_check.json"
    if author_self_check.is_file():
        author_self_check.unlink()
    review_dir = obj_dir / "5.review"
    for name in ("ref_review_gate.json", "provenance.json", "review_ledger.json", "review_entities.json"):
        path = review_dir / name
        if path.is_file():
            path.unlink()
    for name in ("article.md", "gallery.md", "manifest.json", "_object.json"):
        path = obj_dir / name
        if path.is_file():
            path.unlink()
    assets_dir = obj_dir / "assets"
    if assets_dir.is_dir():
        shutil.rmtree(assets_dir)
    content_object.write_content_object_index(ctx.execution_id, ref)
    return True

def _purge_stale_author_queue(
    ctx: ExecutionContext,
    *,
    refs: list[str] | None = None,
    reason: str,
) -> None:
    from content.execution.queue.management import purge_jobs
    result = purge_jobs(ctx.execution_id, stage="author", refs=refs)
    removed = result.get("removed") or []
    if removed:
        print(
            f"[task execute] 已清理过期 author queue ({reason}): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )

def _write_retry_reports_for_refs(
    ctx: ExecutionContext,
    *,
    refs: list[str],
    issue_map: dict[str, list[str]],
    target_stage: str,
) -> None:
    from content.execution.stage_reports import write_repair_report
    fallback_stage = "download" if target_stage == "download_plan" else "agent_compose"
    rerun_chain = (
        ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        if fallback_stage == "download"
        else ["agent_compose", "review", "materialize"]
    )
    for ref in refs:
        messages = issue_map.get(ref) or ["post_review gate failed; inspect current batch issues"]
        write_repair_report(
            execution_id=ctx.execution_id,
            command="post",
            ref=ref,
            failed_stage=DataIssueStage.REVIEW,
            failed_gate="post_verify",
            issues=data_issues(
                DataIssueCode.SOURCE_MISSING if fallback_stage == "download" else DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.REVIEW,
                ref=ref,
                messages=messages,
                recovery=(
                    DataRecoveryAction.REWIND_DOWNLOAD
                    if fallback_stage == "download"
                    else DataRecoveryAction.REWIND_COMPOSE
                ),
            ),
            fallback_stage=fallback_stage,
            rerun_chain=rerun_chain,
        )

def _record_post_review_retry_history(
    ctx: ExecutionContext,
    *,
    refs: list[str],
    issue_map: dict[str, list[str]],
    target_stage: str,
) -> None:
    if not refs:
        return
    state = load_execution_state(ctx.execution_id)
    rows = [
        dict(row)
        for row in (state.produce_review_retry_history or [])
        if isinstance(row, Mapping)
    ]
    rows.append(
        {
            "stage": "post_review",
            "targetStage": target_stage,
            "refs": list(refs),
            "issueMap": {ref: list(issue_map.get(ref) or []) for ref in refs},
            "recordedAt": store.now_iso(),
        }
    )
    state.produce_review_retry_history = rows[-50:]
    save_execution_state(state)

def _prepare_post_review_retry(ctx: ExecutionContext, result: StageResult, target_stage: str) -> bool:
    from content.execution.controller.stage_post_review import _approved_review_refs
    from content.execution.queue.jobs import enqueue_ref_job
    from content.execution.queue.management import requeue_refs
    from content.post.article.draft_io import read_writing_pack
    refs, issue_map = _post_review_retry_refs(ctx, result.issue_records)
    # 单点失败隔离（防塌方）：已通过对象级 review gate 的稿件（含已写正文）一律不动，
    # 除非批级发布门直接点名该 ref/path；失败对象的回退绝不波及无关绿对象的已写正文。
    approved_refs = set(_approved_review_refs(ctx))
    refs = [
        ref for ref in refs
        if ref not in approved_refs
        or _issues_directly_reference_ref(ref=ref, issue_records=result.issue_records)
    ]
    if not refs:
        return False
    _record_post_review_retry_history(
        ctx,
        refs=refs,
        issue_map=issue_map,
        target_stage=target_stage,
    )
    if target_stage == "download_plan":
        _write_retry_reports_for_refs(ctx, refs=refs, issue_map=issue_map, target_stage=target_stage)
        _purge_stale_author_queue(ctx, reason="post_review->download_plan")
        return True
    # 底稿中心快速失败：不再用 20% bulk-repair 闸门（QWQ_POST_REVIEW_ALLOW_BULK_REPAIR）
    # 阻塞整批等待人工诊断。失败 ref 一律按有界 ReAct 预算（MAX_REACT_REWINDS）重写；
    # 预算耗尽后保持失败并转人工，不删除冻结对象。
    # 进度持久化（失败不销毁）：保留失败对象已写正文 + draft_meta，靠 repair_report 触发就地修订，
    # 只清理已物化成品面与陈旧 review 侧车，agent 在原稿基础上改而非从占位从零重写。
    _write_retry_reports_for_refs(ctx, refs=refs, issue_map=issue_map, target_stage=target_stage)
    _purge_stale_author_queue(ctx, refs=refs, reason="post_review->post_compose")
    reset = [ref for ref in refs if _invalidate_ref_for_retry(ctx, ref, preserve_draft=True)]
    requeued = requeue_refs(
        ctx.execution_id,
        reset,
        "author",
        reason="post_review_retry",
    ) if reset else []
    missing = [ref for ref in reset if ref not in set(requeued)]
    if missing:
        from content.post import object_index as content_object
        from governance.creators.assignment import creator_assignment_issues, creator_from_payload
        for ref in missing:
            pack = read_writing_pack(ctx.execution_id, ref) or {}
            brief = content_object.read_brief_object(ctx.execution_id, ref) or {}
            carrier = str(pack.get("carrier") or "article")
            # 复用 author 入队的同一 creator 解析链（pack -> brief），不重造（R24/R25）。
            creator = creator_from_payload(pack) or creator_from_payload(brief)
            meta: dict[str, Any] = {"baseSourceRef": pack.get("baseSourceRef") or ref}
            # 仅当有完整 registry creator 装配时才声明 contentType（触发 enqueue 严格 creator 门）。
            # managed 模式全程无 creator 装配：省略 contentType/carrier，对齐 enqueue_partition_leaves，
            # 让 author 执行阶段按 pack/brief/plan 默认解析 creator，避免 fanout 专用门在重试路径误崩。
            if creator and not creator_assignment_issues(
                creator,
                carrier=carrier,
            ):
                meta["contentType"] = carrier
                meta.update(creator)
            enqueue_ref_job(
                ctx.execution_id,
                ref,
                "author",
                mutex_key=str(pack.get("baseSourceRef") or ref),
                meta=meta,
            )
    if reset:
        print(
            "[task execute] 已为 post_review 回退重置待重写 ref: "
            + ", ".join(reset[:12])
            + (" ..." if len(reset) > 12 else "")
        )
    return bool(reset)
