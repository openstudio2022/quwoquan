"""data produce — 两阶段内容生产（compose-brief → 会话模型创作 → review）。

正文由会话模型（Agent）创作，CLI 不再拼接任何句子：
  --stage compose-brief : 准备写作契约 writing_pack.json + prompt.md + 占位草稿（produce/drafts/）。
  （人/Agent 据 prompt.md 创作正文写回 drafts/{ref}/article.md，generator=agent）
  --stage review        : 读 agent 草稿，过模板指纹/事实可回溯/出处三道门 + 质量门；--materialize 落地 approved。
"""
from __future__ import annotations

import argparse
import sys

from _common.draft_io import (
    drafts_dir,
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
from _common.io import write_json
from _common.paths import batch_inputs_dir, ensure_batch_layout, batch_command_root
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


def _collect_briefs(task_id: str, batch_id: str, refs):
    routes = iter_route_briefs(task_id, batch_id, refs)
    entities = iter_entity_briefs(task_id, batch_id, refs)
    return routes, entities


def _stage_compose_brief(task_id: str, batch_id: str, refs, *, batch_size: int = 1) -> int:
    routes, entities = _collect_briefs(task_id, batch_id, refs)
    prepared_refs: list[str] = []
    blocked = 0
    for ref, brief in routes:
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[produce] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_route_writing_pack(task_id, batch_id, ref, brief, quality)
        prepared_refs.append(ref)
    for ref, brief in entities:
        quality = analyze_route_ref(task_id, batch_id, ref, brief)
        if quality.get("recommendation") == "skip":
            blocked += 1
            print(f"[produce] SKIP {ref}: evidence too weak (recommendation=skip)", file=sys.stderr)
            continue
        build_entity_writing_pack(task_id, batch_id, ref, brief, quality)
        prepared_refs.append(ref)
    out_dir = drafts_dir(task_id, batch_id)
    print(f"[produce] compose-brief prepared {len(prepared_refs)} writing pack(s); blocked={blocked}")
    print(f"[produce] Drafts dir: {out_dir}")
    if batch_size > 1 and prepared_refs:
        groups = plan_batches(prepared_refs, batch_size)
        for seq, group in enumerate(groups, start=1):
            write_batch(task_id, batch_id, seq, group)
        print(
            f"[produce] single-session batches: {len(prepared_refs)} ref(s) → {len(groups)} batch prompt(s) "
            f"(size={batch_size}); see {batch_dir(task_id, batch_id)}"
        )
        print("[produce] Next: 会话模型阅读 _batch/{seq}.batch_prompt.md，一会话产 N 篇分别写回各 {ref}/article.md。")
    else:
        print("[produce] Next: 会话模型阅读 {ref}/prompt.md 与 {ref}/writing_pack.json 创作正文，写回 {ref}/article.md (generator=agent)。")
    print("[produce] 然后运行: qwq-data produce --task <T> --batch <B> --type article --stage review --materialize")
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
        dictionary, required = build_entity_dictionary(task_id, brief, draft_meta)
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
    print("[produce] Next: qwq-data produce --task <T> --batch <B> --type article --stage review --materialize")
    if refs_with_issues and not allow_partial:
        raise SystemExit(1)


def _stage_review(task_id: str, batch_id: str, refs, *, materialize: bool, allow_partial: bool) -> None:
    routes, entities = _collect_briefs(task_id, batch_id, refs)
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
        paths = materialize_posts(task_id, batch_id, "article")
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
    refs = [item.strip() for item in (getattr(args, "refs", "") or "").split(",") if item.strip()] or None

    print(f"[produce] Task: {task_id}, Batch: {batch_id}, Type: {content_type}, Stage: {stage}")
    print(f"[produce] Work dir: {produce_root}")

    compose_inputs_dir = batch_inputs_dir(task_id, batch_id, "produce", "compose")
    if content_type != "article" or not compose_inputs_dir.exists():
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
        help="(review stage) Materialize approved review results into produce/posts/",
    )
    p.set_defaults(handler=handle_produce)
