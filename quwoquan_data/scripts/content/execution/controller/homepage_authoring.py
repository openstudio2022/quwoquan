"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, _IMAGE_SOURCE_TEXT_NOISE_PATTERNS, _IMAGE_SOURCE_TEXT_NOISE_TOKENS, _active_spec, _is_homepage_only_execution, data_issue, execution_root, load_execution_state, os, re, read_json, require_domain_etype, save_execution_state, shutil, store, write_json
from content.execution.controller.homepage_author_evidence import (
    _finalize_existing_managed_author_outputs,
    _managed_image_author_meta_issues,
)
from content.execution.controller.homepage_author_finalization import (
    _finalize_existing_object_queue_author_outputs,
)

def _homepages_done(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from content.homepage.homepage import homepage_runtime_spec
    from content.homepage.homepage_release_validation import validate_entity_pages
    runtime_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    issues = validate_entity_pages(ctx.execution_id, runtime_spec)
    for target in ((runtime_spec.get("scope") or {}).get("coverageTargets") or []):
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(target.get("entityType"), context=name)
        issues.extend(_homepage_independent_review_issues(ctx, domain, etype, name))
    return (not issues), issues

def _homepage_independent_review_issues(
    ctx: ExecutionContext,
    domain: str,
    etype: str,
    name: str,
) -> list[str]:
    review_path = (
        execution_root(ctx.execution_id)
        / "entities"
        / domain
        / etype
        / name
        / "5.review/review.json"
    )
    if not review_path.is_file():
        return []
    review = read_json(review_path)
    reviewer = (
        review.get("independentReviewer")
        if isinstance(review.get("independentReviewer"), Mapping)
        else {}
    )
    reviewer_status = str((reviewer or {}).get("status") or "pending")
    if reviewer_status == "pending":
        return []
    if reviewer_status != "passed":
        recorded = [str(item) for item in review.get("issues") or [] if str(item).strip()]
        return recorded or [f"{name}: independent reviewer not passed ({reviewer_status})"]
    from content.homepage.commercial_gate import independent_review_issues

    draft_meta_path = (
        execution_root(ctx.execution_id)
        / "entities"
        / domain
        / etype
        / name
        / "4.draft/draft_meta.json"
    )
    draft_meta = read_json(draft_meta_path) if draft_meta_path.is_file() else {}
    from content.execution.model_contract import execution_model_pair_for_execution

    author_model = execution_model_pair_for_execution(ctx.execution_id).author
    author = {
        "runId": str(draft_meta.get("agentRunId") or ""),
        "modelFamily": author_model.family.value,
    }
    return independent_review_issues(reviewer, author, label=name)

def _homepage_pending_entities(ctx: ExecutionContext) -> list[str]:
    """Return only active homepage objects that still fail per-entity validate.
    Managed retries must not re-run already accepted homepage triplets; otherwise
    a single slow/failed Cursor job can multiply token cost and overwrite stable
    evidence. The validator remains the source of truth, not Agent self-report.
    """
    from content.homepage.homepage_release_validation import validate_entity_page
    pending: list[str] = []
    for target in ((_active_spec(ctx).get("scope") or {}).get("coverageTargets") or []):
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        issues = validate_entity_page(
            ctx.execution_id,
            domain,
            etype,
            name,
        )
        issues.extend(_homepage_independent_review_issues(ctx, domain, etype, name))
        if issues:
            pending.append(name)
    return pending

def _content_plan_done(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """content_plan checkpoint：篇目包+注册+brief 是否就绪。"""
    from content.execution.controller.content_plan_prep import _clean_content_plan_outputs
    from content.post.content_plan_validation import validate_content_plan
    if _is_homepage_only_execution(ctx):
        # homepage-only：无篇目合同，content_plan 确定性完成；清掉任何篇目残留，
        # 防止历史 agent 误写的 packet/briefs 把 post 车道当文章推进。
        _clean_content_plan_outputs(ctx)
        return True, []
    _prune_content_plan_extra_briefs(ctx)
    issues = validate_content_plan(ctx.execution_id, _active_spec(ctx))
    return (not issues), issues

def _prune_content_plan_extra_briefs(ctx: ExecutionContext) -> list[str]:
    """Remove filesystem brief objects that are no longer registered.
    Agent repairs may rewrite content_plan_packet/index while leaving old
    posts/**/3.compose/brief.json trees behind. Downstream post must consume
    only the packet/index truth source, so stale object trees are pruned before
    validating the checkpoint.
    """
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir, load_index
    from core.paths import STAGE_COMPOSE
    root = execution_root(ctx.execution_id)
    posts_root = root / "posts"
    if not posts_root.is_dir():
        return []
    index = load_index(ctx.execution_id)
    expected: set[Path] = set()
    for ref in index:
        try:
            expected.add((content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    actual = {
        path.resolve()
        for path in posts_root.glob(f"*/*/*/*/{STAGE_COMPOSE}/{BRIEF_FILE}")
        if path.is_file()
    }
    removed: list[str] = []
    for brief_path in sorted(actual - expected):
        object_dir = brief_path.parents[1]
        rel = object_dir.relative_to(root).as_posix() if object_dir.is_relative_to(root) else object_dir.as_posix()
        shutil.rmtree(object_dir)
        removed.append(rel)
    if removed:
        print(
            "[task execute] Pruned stale content_plan brief object(s): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )
    return removed

def _drafts_authored(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """post_author checkpoint：compose 后的所有 carrier drafts 是否被 Agent 创作."""
    from content.execution.recovery.post_recovery import _content_plan_base_draft_shortfall_refs
    from content.post import object_index as content_object
    from content.post.content_review import generator_provenance_issues
    from content.post.article.draft_io import draft_article_path, is_placeholder, read_draft_meta, read_writing_pack
    from core.paths import STAGE_REVIEW
    state = load_execution_state(ctx.execution_id)
    finalized_count = _finalize_existing_managed_author_outputs(ctx, state)
    if finalized_count:
        state = load_execution_state(ctx.execution_id)
        state.heartbeat_at = store.now_iso()
        state.last_author_finalize_count = finalized_count
        save_execution_state(state)
    content_refs = content_object.iter_content_refs(ctx.execution_id)
    active_refs = list(content_refs)
    if not content_refs:
        return False, ["(no content objects; run compose-brief first)"]
    preflight_short_refs = _content_plan_base_draft_shortfall_refs(ctx, active_refs)
    if preflight_short_refs:
        return False, [
            f"{ref}: baseDraftText effective length below authoring gate"
            for ref in preflight_short_refs
        ]
    object_queue_finalized = _finalize_existing_object_queue_author_outputs(ctx, active_refs)
    if object_queue_finalized:
        state = load_execution_state(ctx.execution_id)
        state.heartbeat_at = store.now_iso()
        state.last_object_queue_author_finalize_count = object_queue_finalized
        save_execution_state(state)
    pending: list[str] = []
    for ref in active_refs:
        try:
            pack = read_writing_pack(ctx.execution_id, ref) or {}
        except KeyError:
            pack = {}
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        is_image_carrier = (
            str(pack.get("carrier") or "") == "image"
            or str(coords.get("contentType") or "") == "image"
        )
        is_video_carrier = (
            str(pack.get("carrier") or "") == "video"
            or str(coords.get("contentType") or "") == "video"
        )
        if is_video_carrier:
            from content.post.video.authoring import video_author_issues

            if video_author_issues(
                ctx.execution_id,
                ref,
                require_agent_run=ctx.managed,
            ):
                pending.append(ref)
            continue
        if is_image_carrier:
            if ctx.managed and _managed_image_author_meta_issues(
                read_draft_meta(ctx.execution_id, ref),
                writing_pack=pack,
                require_agent_run=True,
            ):
                pending.append(ref)
            continue
        try:
            art = draft_article_path(ctx.execution_id, ref)
        except KeyError:
            pending.append(ref)
            continue
        if not art.is_file():
            pending.append(ref)
            continue
        try:
            article_text = art.read_text(encoding="utf-8")
        except OSError:
            pending.append(ref)
            continue
        draft_needs_agent = False
        try:
            review_dir = content_object.content_object_stage_dir(
                ctx.execution_id, ref, STAGE_REVIEW
            )
        except KeyError:
            review_dir = None
        repair_is_newer = False
        if review_dir is not None:
            repair_report = review_dir / "repair_report.json"
            if repair_report.is_file():
                try:
                    repair_is_newer = repair_report.stat().st_mtime >= art.stat().st_mtime
                except OSError:
                    repair_is_newer = True
        if is_placeholder(article_text):
            draft_needs_agent = True
        elif generator_provenance_issues(read_draft_meta(ctx.execution_id, ref)):
            draft_needs_agent = True
        elif repair_is_newer:
            draft_needs_agent = True
        if draft_needs_agent:
            pending.append(ref)
    return (not pending), pending
