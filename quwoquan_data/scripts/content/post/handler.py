"""Internal post-stage runner for compose, review, and materialization.

正文由创作 agent（Agent）创作，CLI 不再拼接任何句子：
  --stage compose-brief : 准备写作契约 writing_pack.json + prompt.md + 草稿包（posts/.../4.draft/）。
  文章/主页类由人/Agent 据 prompt.md 创作正文写回 4.draft/draft.article.md（generator=agent）；
  图片作品只使用结构化 sourceCollection/assets/caption，不生成正文草稿。
  --stage review        : 读 agent 草稿，过模板指纹/事实可回溯/出处三道门 + 质量门；--materialize 落地 approved。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from content.post.article.draft_io import (
    draft_package_dir,
    draft_article_path,
    draft_meta_path,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    write_annotated_agent_draft,
)
from content.review.annotation.entity_annotation import (
    annotate_inline,
    annotation_closure_issues,
    build_entity_dictionary,
)
from content.execution.writer_groups import writer_group_dir, partition_writer_groups, write_writer_group
from content.execution.runtime_state import write_execution_runtime_state
from content.post.object_index import content_type_from_brief, write_brief_object
from core.io import write_json
from core.paths import ensure_execution_command_layout, execution_command_root
from content.post.materialize_apply import materialize_posts
from content.post.article.entity_composition import (
    build_entity_writing_pack,
    iter_entity_briefs,
)
from content.post.article.entity_review import review_entity_draft
from content.post.article.route_analysis import analyze_route_ref
from content.post.article.route_compose import build_route_writing_pack
from content.post.article.route_core import iter_route_briefs
from content.post.article.route_review import review_route_draft
from core.control_types import ContentType, PostStage


CONTENT_TYPES = tuple(item.value for item in (ContentType.ARTICLE, ContentType.IMAGE, ContentType.VIDEO))
STAGES = tuple(item.value for item in PostStage)


@dataclass(frozen=True)
class PostStageRequest:
    """Typed internal request for one post stage in an execution work package."""

    execution_id: str
    content_type: ContentType
    stage: PostStage
    refs: tuple[str, ...] = ()
    writer_group_size: int = 1
    materialize: bool = False
    allow_partial: bool = False


def _is_image_carrier(brief) -> bool:
    return str(brief.get("carrier") or "").lower() == "image"


def _is_video_carrier(brief) -> bool:
    return str(brief.get("carrier") or "").lower() == "video"


def _collect_briefs(execution_id: str, refs):
    routes = iter_route_briefs(execution_id, refs)
    entities = iter_entity_briefs(execution_id, refs)
    return routes, entities


def _apply_writing_intent_override(brief, override):
    """把 content_plan_packet 的 writingIntent/baseSourceRef 注入 brief（任务层覆盖默认值）。"""
    if not override:
        return brief
    merged = dict(brief)
    for field in (
        "writingIntent",
        "baseSourceRef",
        "baseSourceReusePolicy",
        "carrier",
        "sourceCollectionId",
        "assetRefs",
        "sourceFrames",
        "sourceVideo",
        "sourceMode",
        "tagRefs",
        "authorId",
        "creatorProfileId",
        "creatorArchetype",
        "creatorProfileVersion",
        "creatorDisclosure",
        "experienceClaimMode",
        "authorQualitySignals",
        "creator",
    ):
        if field in override and override.get(field) not in (None, ""):
            merged[field] = override[field]
    if _is_image_carrier(merged) and not override.get("baseSourceRef"):
        merged.pop("baseSourceRef", None)
        merged.pop("_contentPlanBaseSourceLocked", None)
    if override.get("baseSourceRef"):
        merged["_contentPlanBaseSourceLocked"] = True
    return merged


def _assign_base_draft(execution_id: str, ref: str, brief):
    """认领唯一底稿（baseSourceRef 永远非空目标）；返回(brief, 缺底稿告警)。"""
    from content.post.article.base_draft import (
        assign_base_draft,
        load_base_draft_ledger,
        occupied_source_refs,
        save_base_draft_ledger,
    )

    declared = str(brief.get("baseSourceRef") or "").strip()
    if brief.get("_contentPlanBaseSourceLocked") and declared:
        ledger = load_base_draft_ledger(execution_id)
        taken = occupied_source_refs(ledger, exclude_post=ref)
        # 底稿中心 1:1：一源只能一篇，彻底取消 multi_intent_source_bundle 复用逃生口。
        if declared in taken:
            raise RuntimeError(
                f"{ref}: content_plan baseSourceRef already assigned to another ref: {declared}"
            )
        assignments = {
            source: post
            for source, post in dict(ledger.get("assignments") or {}).items()
            if post != ref
        }
        assignments[declared] = ref
        ledger["assignments"] = assignments
        save_base_draft_ledger(execution_id, ledger)
        return brief, None
    chosen = assign_base_draft(execution_id, ref, brief)
    if chosen and chosen != brief.get("baseSourceRef"):
        merged = dict(brief)
        merged["baseSourceRef"] = chosen
        return merged, None
    if not chosen and not brief.get("baseSourceRef"):
        return brief, f"{ref}: 无可用底稿（来源单元不足或均已被其它篇占用）"
    return brief, None


def _stage_compose_brief(execution_id: str, refs, *, writer_group_size: int = 1) -> int:
    from content.post.content_plan import load_writing_intent_overrides

    overrides = load_writing_intent_overrides(execution_id)
    routes, entities = _collect_briefs(execution_id, refs)
    prepared_refs: list[str] = []
    prepared_article_like = False
    blocked = 0
    base_draft_warnings: list[str] = []
    for ref, brief in routes:
        brief = _apply_writing_intent_override(brief, overrides.get(ref))
        if _is_video_carrier(brief):
            from content.post.video.authoring import prepare_video_brief

            prepare_video_brief(execution_id, ref)
            prepared_article_like = True
            prepared_refs.append(ref)
            continue
        warn = None
        if not _is_image_carrier(brief):
            brief, warn = _assign_base_draft(execution_id, ref, brief)
        write_brief_object(execution_id, ref, brief, content_type=content_type_from_brief(brief))
        if warn:
            base_draft_warnings.append(warn)
        quality = analyze_route_ref(execution_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[post] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_route_writing_pack(execution_id, ref, brief, quality)
        if not _is_image_carrier(brief):
            prepared_article_like = True
        prepared_refs.append(ref)
    for ref, brief in entities:
        brief = _apply_writing_intent_override(brief, overrides.get(ref))
        if _is_video_carrier(brief):
            from content.post.video.authoring import prepare_video_brief

            prepare_video_brief(execution_id, ref)
            prepared_article_like = True
            prepared_refs.append(ref)
            continue
        warn = None
        if not _is_image_carrier(brief):
            brief, warn = _assign_base_draft(execution_id, ref, brief)
        write_brief_object(execution_id, ref, brief, content_type=content_type_from_brief(brief))
        if warn:
            base_draft_warnings.append(warn)
        quality = analyze_route_ref(execution_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[post] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_entity_writing_pack(execution_id, ref, brief, quality)
        if not _is_image_carrier(brief):
            prepared_article_like = True
        prepared_refs.append(ref)
    for warn in base_draft_warnings:
        print(f"[post] BASE-DRAFT WARN {warn}", file=sys.stderr)
    out_dir = draft_package_dir(execution_id, prepared_refs[0]) if prepared_refs else None
    print(f"[post] compose prepared {len(prepared_refs)} writing pack(s); blocked={blocked}")
    if out_dir is not None:
        print(f"[post] Drafts dir: {out_dir.parent}")
    if writer_group_size > 1 and prepared_refs:
        groups = partition_writer_groups(prepared_refs, writer_group_size)
        for seq, group in enumerate(groups, start=1):
            write_writer_group(execution_id, seq, group)
        print(
            f"[post] single-session writer groups: {len(prepared_refs)} ref(s) → {len(groups)} prompt(s) "
            f"(size={writer_group_size}); see {writer_group_dir(execution_id)}"
        )
        if prepared_article_like:
            print("[post] Next: 创作 agent 阅读 _writer_groups/{seq}.writer_group_prompt.md；文章/主页类写回各 4.draft/draft.article.md，图片作品不生成正文草稿。")
        else:
            print("[post] Next: 图片作品已由结构化 sourceCollection/assets/caption 准备；不生成 4.draft/draft.article.md。")
    elif prepared_article_like:
        print("[post] Next: 创作 agent 阅读 4.draft/prompt.md 与 3.compose/writing_pack.json 创作正文，写回 4.draft/draft.article.md (generator=agent)。")
    else:
        print("[post] Next: 图片作品已由结构化 sourceCollection/assets/caption 准备；不生成 4.draft/draft.article.md。")
    print("[post] Next: task execute continues the execution through review and canonical promotion.")
    return len(prepared_refs)


def _stage_annotate_entities(execution_id: str, refs, *, allow_partial: bool) -> None:
    """实体标注环节：把 agent 正文里、库中有主页的实体首次出现处标成 inline 链接（确定性 grounding）。

    NER 由 compose 阶段会话 agent 完成（draft_meta.extractedEntities），本阶段只做词典 grounding +
    inline 机械标注 + ref 闭环强校验，并把被标注实体登记进 draft_meta.annotatedEntityRefs（compose 据此并入
    manifest.entityRefs，使标注→登记→主页闭环成立）。
    """
    routes, entities = _collect_briefs(execution_id, refs)
    total_links = 0
    refs_with_issues = 0
    for ref, brief in [*routes, *entities]:
        if _is_video_carrier(brief) or _is_image_carrier(brief):
            continue
        article = read_draft_article(execution_id, ref)
        if is_placeholder(article):
            print(f"[post] annotate-entities SKIP {ref}: draft 未由 agent 创作", file=sys.stderr)
            continue
        draft_meta = read_draft_meta(execution_id, ref) or {}
        dictionary, required = build_entity_dictionary(execution_id, brief, draft_meta)
        new_article, annotated = annotate_inline(article, dictionary)
        write_annotated_agent_draft(
            execution_id,
            ref,
            new_article,
            annotated_entity_refs=annotated,
        )
        total_links += len(annotated)
        issues = annotation_closure_issues(
            new_article,
            manifest_entity_refs=sorted(set(required) | annotated),
            dictionary=dictionary,
            required_refs=required,
            require_coverage=True,
        )
        if issues:
            refs_with_issues += 1
            print(f"[post] annotate-entities ISSUES {ref}: {issues}", file=sys.stderr)
    print(f"[post] annotate-entities annotated {total_links} link(s); {refs_with_issues} ref(s) with closure issues")
    print("[post] Next: task execute continues the execution through review and canonical promotion.")
    if refs_with_issues and not allow_partial:
        raise SystemExit(1)


def _stage_review(execution_id: str, refs, *, materialize: bool, allow_partial: bool) -> None:
    routes, entities = _collect_briefs(execution_id, refs)
    from content.source.media.gate import gate_media_check
    from content.source.media.check import check_images

    check_refs = [ref for ref, _ in [*routes, *entities]]
    media_statuses = check_images(execution_id, check_refs, allow_needs_review=True)
    media_issues = gate_media_check(execution_id, allow_needs_review=True, refs=check_refs)
    if media_statuses:
        passed = sum(1 for row in media_statuses if row["passed"])
        failed = len(media_statuses) - passed
        print(f"[post] media_check handled {len(media_statuses)} ref(s); passed={passed} failed={failed}")
    if media_issues:
        for issue in media_issues[:10]:
            print(f"[post] media_check FAIL {issue}", file=sys.stderr)
        if not allow_partial:
            raise SystemExit(1)

    statuses: list[dict] = []
    for ref, brief in routes:
        if _is_video_carrier(brief):
            from content.post.video.authoring import review_video_draft

            review = review_video_draft(execution_id, ref)
            statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})
            continue
        quality = analyze_route_ref(execution_id, ref, brief)
        review = review_route_draft(execution_id, ref, brief, quality)
        statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})
    for ref, brief in entities:
        if _is_video_carrier(brief):
            from content.post.video.authoring import review_video_draft

            review = review_video_draft(execution_id, ref)
            statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})
            continue
        quality = analyze_route_ref(execution_id, ref, brief)
        review = review_entity_draft(execution_id, ref, brief, quality)
        statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})

    failed = [row for row in statuses if row["decision"] != "approved"]
    approved = len(statuses) - len(failed)
    print(f"[post] review handled {len(statuses)} ref(s); approved={approved} failed={len(failed)}")
    if materialize and approved:
        paths = materialize_posts(execution_id, "article", refs=check_refs)
        paths += materialize_posts(execution_id, "image", refs=check_refs)
        paths += materialize_posts(execution_id, "video", refs=check_refs)
        print(f"[post] Materialized {len(paths)} approved post package(s).")
    if failed:
        for row in failed[:10]:
            print(f"[post] FAIL {row['ref']}: {row['issues']}", file=sys.stderr)
        if not allow_partial:
            raise SystemExit(1)


def handle_post(request: PostStageRequest) -> None:
    """Run one internal post stage for the sole execution work package."""
    execution_id = str(request.execution_id)
    content_type = request.content_type.value
    if not isinstance(request.stage, PostStage):
        raise TypeError("PostStageRequest.stage must be PostStage")
    stage = request.stage

    if content_type not in CONTENT_TYPES:
        print(f"[post] ERROR: content_type must be one of {CONTENT_TYPES}")
        return

    ensure_execution_command_layout(execution_id, "post")
    post_root = execution_command_root(execution_id, "post")
    write_execution_runtime_state(execution_id, command="post")
    refs = [item.strip() for item in request.refs if item.strip()] or None

    print(f"[post] Execution: {execution_id}, Type: {content_type}, Stage: {stage.value}")
    print(f"[post] Work dir: {post_root}")

    from content.post.object_index import has_briefs

    if not has_briefs(execution_id):
        return

    if stage is PostStage.COMPOSE_BRIEF:
        _stage_compose_brief(execution_id, refs, writer_group_size=request.writer_group_size)
    elif stage is PostStage.ANNOTATE_ENTITIES:
        _stage_annotate_entities(
            execution_id,
            refs,
            allow_partial=request.allow_partial,
        )
    elif stage is PostStage.REVIEW:
        _stage_review(
            execution_id,
            refs,
            materialize=request.materialize,
            allow_partial=request.allow_partial,
        )
    else:
        print(f"[post] ERROR: stage must be one of {STAGES}")
        raise SystemExit(2)
