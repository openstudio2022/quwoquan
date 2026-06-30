"""data produce — 两阶段内容生产（compose-brief → 创作 agent/结构化图片 → review）。

正文由创作 agent（Agent）创作，CLI 不再拼接任何句子：
  --stage compose-brief : 准备写作契约 writing_pack.json + prompt.md + 草稿包（posts/.../4.draft/）。
  文章/主页类由人/Agent 据 prompt.md 创作正文写回 4.draft/draft.article.md（generator=agent）；
  图片作品只使用结构化 sourceCollection/assets/caption，不生成正文草稿。
  --stage review        : 读 agent 草稿，过模板指纹/事实可回溯/出处三道门 + 质量门；--materialize 落地 approved。
"""
from __future__ import annotations

import argparse
import sys

from _common.draft_io import (
    draft_package_dir,
    draft_article_path,
    draft_meta_path,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
)
from _common.entity_annotation import (
    annotate_inline,
    annotation_closure_issues,
    build_entity_dictionary,
)
from _common.batch_orchestration import batch_dir, plan_batches, write_batch
from _common.batch_manifest import write_batch_manifest
from _common.content_object import content_type_from_brief, write_brief_object
from _common.io import write_json
from _common.paths import ensure_batch_layout, batch_command_root
from produce.materialize import materialize_posts
from produce.entity_workflow import (
    build_entity_writing_pack,
    iter_entity_briefs,
    review_entity_draft,
)
from produce.route_workflow import (
    analyze_route_ref,
    build_route_writing_pack,
    iter_route_briefs,
    review_route_draft,
)


CONTENT_TYPES = ("article", "image", "video")
STAGES = ("compose-brief", "annotate-entities", "review")


def _is_image_carrier(brief) -> bool:
    return str(brief.get("carrier") or "").lower() in ("image", "gallery")


def _collect_briefs(task_id: str, batch_id: str, refs):
    routes = iter_route_briefs(task_id, batch_id, refs)
    entities = iter_entity_briefs(task_id, batch_id, refs)
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


def _assign_base_draft(task_id: str, batch_id: str, ref: str, brief):
    """认领唯一底稿（baseSourceRef 永远非空目标）；返回(brief, 缺底稿告警)。"""
    from _common.base_draft import (
        assign_base_draft,
        load_base_draft_ledger,
        occupied_source_refs,
        save_base_draft_ledger,
    )

    declared = str(brief.get("baseSourceRef") or "").strip()
    if brief.get("_contentPlanBaseSourceLocked") and declared:
        ledger = load_base_draft_ledger(task_id, batch_id)
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
        save_base_draft_ledger(task_id, batch_id, ledger)
        return brief, None
    chosen = assign_base_draft(task_id, batch_id, ref, brief)
    if chosen and chosen != brief.get("baseSourceRef"):
        merged = dict(brief)
        merged["baseSourceRef"] = chosen
        return merged, None
    if not chosen and not brief.get("baseSourceRef"):
        return brief, f"{ref}: 无可用底稿（来源单元不足或均已被其它篇占用）"
    return brief, None


def _stage_compose_brief(task_id: str, batch_id: str, refs, *, batch_size: int = 1) -> int:
    from _common.content_plan import load_writing_intent_overrides

    overrides = load_writing_intent_overrides(task_id, batch_id)
    routes, entities = _collect_briefs(task_id, batch_id, refs)
    prepared_refs: list[str] = []
    prepared_article_like = False
    blocked = 0
    base_draft_warnings: list[str] = []
    for ref, brief in routes:
        brief = _apply_writing_intent_override(brief, overrides.get(ref))
        warn = None
        if not _is_image_carrier(brief):
            brief, warn = _assign_base_draft(task_id, batch_id, ref, brief)
        write_brief_object(task_id, batch_id, ref, brief, content_type=content_type_from_brief(brief))
        if warn:
            base_draft_warnings.append(warn)
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[produce] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_route_writing_pack(task_id, batch_id, ref, brief, quality)
        if not _is_image_carrier(brief):
            prepared_article_like = True
        prepared_refs.append(ref)
    for ref, brief in entities:
        brief = _apply_writing_intent_override(brief, overrides.get(ref))
        warn = None
        if not _is_image_carrier(brief):
            brief, warn = _assign_base_draft(task_id, batch_id, ref, brief)
        write_brief_object(task_id, batch_id, ref, brief, content_type=content_type_from_brief(brief))
        if warn:
            base_draft_warnings.append(warn)
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[produce] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_entity_writing_pack(task_id, batch_id, ref, brief, quality)
        if not _is_image_carrier(brief):
            prepared_article_like = True
        prepared_refs.append(ref)
    for warn in base_draft_warnings:
        print(f"[produce] BASE-DRAFT WARN {warn}", file=sys.stderr)
    out_dir = draft_package_dir(task_id, batch_id, prepared_refs[0]) if prepared_refs else None
    print(f"[produce] compose-brief prepared {len(prepared_refs)} writing pack(s); blocked={blocked}")
    if out_dir is not None:
        print(f"[produce] Drafts dir: {out_dir.parent}")
    if batch_size > 1 and prepared_refs:
        groups = plan_batches(prepared_refs, batch_size)
        for seq, group in enumerate(groups, start=1):
            write_batch(task_id, batch_id, seq, group)
        print(
            f"[produce] single-session batches: {len(prepared_refs)} ref(s) → {len(groups)} batch prompt(s) "
            f"(size={batch_size}); see {batch_dir(task_id, batch_id)}"
        )
        if prepared_article_like:
            print("[produce] Next: 创作 agent阅读 _batch/{seq}.batch_prompt.md；文章/主页类写回各 4.draft/draft.article.md，图片作品不生成正文草稿。")
        else:
            print("[produce] Next: 图片作品已由结构化 sourceCollection/assets/caption 准备；不生成 4.draft/draft.article.md。")
    elif prepared_article_like:
        print("[produce] Next: 创作 agent阅读 4.draft/prompt.md 与 3.compose/writing_pack.json 创作正文，写回 4.draft/draft.article.md (generator=agent)。")
    else:
        print("[produce] Next: 图片作品已由结构化 sourceCollection/assets/caption 准备；不生成 4.draft/draft.article.md。")
    print("[produce] 然后运行: qwq-data data produce --task <T> --batch <B> --type article --stage review --materialize")
    return len(prepared_refs)


def _stage_annotate_entities(task_id: str, batch_id: str, refs, *, allow_partial: bool) -> None:
    """实体标注环节：把 agent 正文里、库中有主页的实体首次出现处标成 inline 链接（确定性 grounding）。

    NER 由 compose 阶段会话 agent 完成（draft_meta.extractedEntities），本阶段只做词典 grounding +
    inline 机械标注 + ref 闭环强校验，并把被标注实体登记进 draft_meta.annotatedEntityRefs（compose 据此并入
    manifest.entityRefs，使标注→登记→主页闭环成立）。
    """
    routes, entities = _collect_briefs(task_id, batch_id, refs)
    total_links = 0
    refs_with_issues = 0
    for ref, brief in [*routes, *entities]:
        article = read_draft_article(task_id, batch_id, ref)
        if is_placeholder(article):
            print(f"[produce] annotate-entities SKIP {ref}: draft 未由 agent 创作", file=sys.stderr)
            continue
        draft_meta = read_draft_meta(task_id, batch_id, ref) or {}
        dictionary, required = build_entity_dictionary(task_id, batch_id, brief, draft_meta)
        new_article, annotated = annotate_inline(article, dictionary)
        if new_article != article:
            draft_article_path(task_id, batch_id, ref).write_text(new_article, encoding="utf-8")
        draft_meta["annotatedEntityRefs"] = sorted(annotated)
        write_json(draft_meta_path(task_id, batch_id, ref), draft_meta)
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
            print(f"[produce] annotate-entities ISSUES {ref}: {issues}", file=sys.stderr)
    print(f"[produce] annotate-entities annotated {total_links} link(s); {refs_with_issues} ref(s) with closure issues")
    print("[produce] Next: qwq-data data produce --task <T> --batch <B> --type article --stage review --materialize")
    if refs_with_issues and not allow_partial:
        raise SystemExit(1)


def _stage_review(task_id: str, batch_id: str, refs, *, materialize: bool, allow_partial: bool) -> None:
    routes, entities = _collect_briefs(task_id, batch_id, refs)
    from media.gate import gate_media_check
    from media.handler import check_images

    check_refs = [ref for ref, _ in [*routes, *entities]]
    media_statuses = check_images(task_id, batch_id, check_refs, allow_needs_review=True)
    media_issues = gate_media_check(task_id, batch_id, allow_needs_review=True, refs=check_refs)
    if media_statuses:
        passed = sum(1 for row in media_statuses if row["passed"])
        failed = len(media_statuses) - passed
        print(f"[produce] media_check handled {len(media_statuses)} ref(s); passed={passed} failed={failed}")
    if media_issues:
        for issue in media_issues[:10]:
            print(f"[produce] media_check FAIL {issue}", file=sys.stderr)
        if not allow_partial:
            raise SystemExit(1)

    statuses: list[dict] = []
    for ref, brief in routes:
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        review = review_route_draft(task_id, batch_id, ref, brief, quality)
        statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})
    for ref, brief in entities:
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        review = review_entity_draft(task_id, batch_id, ref, brief, quality)
        statuses.append({"ref": ref, "decision": review.get("decision"), "issues": review.get("issues") or []})

    failed = [row for row in statuses if row["decision"] != "approved"]
    approved = len(statuses) - len(failed)
    print(f"[produce] review handled {len(statuses)} ref(s); approved={approved} failed={len(failed)}")
    if materialize and approved:
        paths = materialize_posts(task_id, batch_id, "article", refs=check_refs)
        paths += materialize_posts(task_id, batch_id, "image", refs=check_refs)
        print(f"[produce] Materialized {len(paths)} approved post package(s).")
    if failed:
        for row in failed[:10]:
            print(f"[produce] FAIL {row['ref']}: {row['issues']}", file=sys.stderr)
        if not allow_partial:
            raise SystemExit(1)


def handle_produce(args: argparse.Namespace) -> None:
    task_id = args.task
    batch_id = args.batch
    content_type = args.type
    stage = getattr(args, "stage", "compose-brief")

    if content_type not in CONTENT_TYPES:
        print(f"[produce] ERROR: --type must be one of {CONTENT_TYPES}")
        return

    ensure_batch_layout(task_id, batch_id, "produce")
    produce_root = batch_command_root(task_id, batch_id, "produce")
    write_batch_manifest(task_id, batch_id, command=f"produce:{stage}")
    refs = [item.strip() for item in (getattr(args, "refs", "") or "").split(",") if item.strip()] or None

    print(f"[produce] Task: {task_id}, Batch: {batch_id}, Type: {content_type}, Stage: {stage}")
    print(f"[produce] Work dir: {produce_root}")

    from _common.content_object import has_briefs

    if content_type != "article" or not has_briefs(task_id, batch_id):
        if getattr(args, "materialize", False):
            paths = materialize_posts(task_id, batch_id, content_type)
            print(f"[produce] Materialized {len(paths)} approved post package(s).")
        return

    if stage == "compose-brief":
        _stage_compose_brief(task_id, batch_id, refs, batch_size=getattr(args, "batch_size", 1))
    elif stage == "annotate-entities":
        _stage_annotate_entities(
            task_id,
            batch_id,
            refs,
            allow_partial=getattr(args, "allow_partial", False),
        )
    elif stage == "review":
        _stage_review(
            task_id,
            batch_id,
            refs,
            materialize=getattr(args, "materialize", False),
            allow_partial=getattr(args, "allow_partial", False),
        )
    else:
        print(f"[produce] ERROR: --stage must be one of {STAGES}")
        raise SystemExit(2)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("produce", help="Produce content (article/image/video) — two-stage agent composition")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--type", required=True, choices=CONTENT_TYPES, help="Content type")
    p.add_argument(
        "--stage",
        choices=STAGES,
        default="compose-brief",
        help="compose-brief (prepare) | annotate-entities (实体 inline 标注) | review (gate+materialize)",
    )
    p.add_argument("--refs", help="Optional comma-separated refs to process")
    p.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="(compose-brief) 把 N 个实体聚合成单会话 batch prompt，一会话产多篇（默认 1=逐篇）",
    )
    p.add_argument(
        "--allow-partial",
        action="store_true",
        help="Do not fail the command when some refs remain blocked by review gates",
    )
    p.add_argument(
        "--materialize",
        action="store_true",
        help="(review stage) Materialize approved review results into batch/posts/",
    )
    p.set_defaults(handler=handle_produce)
