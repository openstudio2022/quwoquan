"""Build article and image candidates for one frozen coverage target."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.entity_focus import classify_entity_focus
from core.entity_focus import coverage_targets_mentioned
from core.quality_gates import derive_writing_intent

from content.execution import support
from content.execution.controller import content_plan_assets as plan_assets
from content.execution.controller.content_plan_article_anchor import (
    assess_article_entity_anchor,
)
from content.execution.controller.content_plan_asset_semantics import (
    admitted_article_asset_rows,
)
from content.execution.controller.content_plan_decisions import ContentPlanRejectLedger
from content.execution.controller.content_plan_prep import (
    _assess_content_plan_publish_image,
)
from content.post.article.base_draft import base_draft_readiness, load_base_draft_text
from content.post.article.base_draft_source import extract_source_title
from content.post.content_plan import ARTICLE_MIN_BASE_DRAFT_CHARS


def collect_target_candidates(
    *,
    ctx: support.ExecutionContext,
    root: Path,
    source_units: Sequence[Path],
    target: str,
    targets: Sequence[str],
    target_aliases: Mapping[str, Sequence[str]],
    rejects: ContentPlanRejectLedger,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Return source-bound candidates without selecting delivery quotas."""
    article_candidates: list[dict[str, Any]] = []
    image_candidates: list[dict[str, Any]] = []
    article_raw_count = 0
    image_raw_count = 0
    for source_dir in source_units:
        meta_path = source_dir / "meta.json"
        if not meta_path.is_file() or not (source_dir / "source.md").is_file():
            continue
        try:
            meta = support.read_json(meta_path)
        except (OSError, ValueError, TypeError):
            meta = {}
        source_id = str(meta.get("sourceId") or source_dir.name).strip()
        lane = str(meta.get("researchLane") or "").strip()
        rows = plan_assets.asset_rows(source_dir)
        if lane == "article":
            if str(meta.get("sourceRole") or "") != "base":
                continue
            if "support" in source_id.lower() or "support" in source_dir.name.lower():
                continue
            article_raw_count += 1
            if bool(meta.get("hasVideo")):
                # P3 文章判据：含视频则放弃——不把视频内容强行图文化为攻略文章。
                rejects.reject_article("contains_video", source_id, "来源含内联视频，文章类放弃")
                continue
            source_ref = plan_assets.source_ref(ctx, source_dir)
            base_body = load_base_draft_text(ctx.execution_id, source_ref)
            readiness = base_draft_readiness(
                base_body,
                publish_media_mode=str(meta.get("publishMediaMode") or ""),
            )
            text_len = int(readiness["effectiveChars"])
            if not readiness["ready"]:
                rejects.reject_article(
                    "text_too_short",
                    source_id,
                    f"{text_len}<{ARTICLE_MIN_BASE_DRAFT_CHARS}; "
                    f"figures={readiness['inlineFigureCount']} captions={readiness['captionChars']}",
                )
                continue
            focus_score, focus_verdict = classify_entity_focus(
                base_body,
                target,
                title=str(meta.get("title") or ""),
                sibling_names=targets,
            )
            from core.qunar_template import qunar_article_base_block_reason

            # 与 validate_content_plan 同口径：优先尊重 source unit meta
            # 中的实体锚点判定，避免 Qunar off_entity 游记进入 packet。
            qunar_focus_verdict = str(meta.get("entityFocusVerdict") or "").strip() or focus_verdict
            qunar_block = qunar_article_base_block_reason(meta, qunar_focus_verdict)
            if qunar_block:
                rejects.reject_article(qunar_block, source_id, "Qunar 模板底稿不可作为当前实体 article base")
                continue
            # 底稿中心 1:1：实体退化为多标签，文章不再因"未整体指代单一实体"弃稿
            # （多目的地游记照样按单一底稿成稿，实体作为标签集合）；focus 仅留作诊断信号。
            draft_title = extract_source_title(ctx.execution_id, source_ref)
            if not draft_title:
                # 标题取自底稿：文章源无法提取可用发布标题 → 上游诚实弃稿（不成稿）。
                rejects.reject_article("no_source_title", source_id, "底稿无法提取发布标题")
                continue
            entity_anchor = assess_article_entity_anchor(
                body=base_body,
                title=str(meta.get("title") or ""),
                target=target,
                aliases=target_aliases.get(target, ()),
            )
            if not entity_anchor.eligible:
                rejects.reject_article(
                    "entity_anchor_mismatch",
                    source_id,
                    entity_anchor.diagnostic(),
                )
                continue
            entity_tags = sorted(
                {
                    *coverage_targets_mentioned(
                        base_body,
                        str(meta.get("title") or ""),
                        targets,
                    ),
                    target,
                }
            )
            admitted_rows, semantic_issues = admitted_article_asset_rows(
                rows,
                entity_id=target,
                article_text=base_body,
                entity_aliases=target_aliases.get(target, ()),
            )
            for semantic_issue in semantic_issues:
                rejects.warn_article_image(
                    "asset_semantic_mismatch", source_id, semantic_issue
                )
            if not admitted_rows:
                rejects.warn_article_image("no_source_assets", source_id)
            article_candidates.append(
                {
                    "sourceDir": source_dir,
                    "sourceRef": source_ref,
                    "sourceId": source_id,
                    "title": str(meta.get("title") or source_id),
                    "draftTitle": draft_title,
                    "writingIntent": str(meta.get("writingIntent") or "")
                    or derive_writing_intent(base_body),
                    "articleCategory": str(meta.get("articleCategory") or ""),
                    "topicTagRefs": list(meta.get("topicTagRefs") or []),
                    "entityTags": entity_tags,
                    "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                    "sourceClass": str(meta.get("sourceClass") or meta.get("category") or ""),
                    "sourceQualityScore": float(
                        meta.get("sourceQualityScore")
                        or meta.get("qualityScore")
                        or meta.get("score")
                        or 0
                    ),
                    "textLen": text_len,
                    "entityFocusScore": focus_score,
                    "entityFocusVerdict": focus_verdict,
                    "sourceFreshnessTier": str(
                        meta.get("sourceFreshnessTier")
                        or (
                            (meta.get("siteTemplate") or {}).get("freshnessTier")
                            if isinstance(meta.get("siteTemplate"), Mapping)
                            else ""
                        )
                        or ""
                    ),
                    "rows": admitted_rows,
                    "targetEntity": target,
                    "targetAliases": list(target_aliases.get(target, ())),
                    "articleAnchorText": base_body,
                    **entity_anchor.candidate_fields(),
                }
            )
        elif lane == "image":
            for row in rows:
                image_raw_count += 1
                asset_ref = plan_assets.asset_ref(ctx, source_dir, row)
                collection_id = str(row.get("sourceCollectionId") or "").strip()
                if not asset_ref:
                    rejects.reject_image("missing_asset_ref", source_id)
                    continue
                if not collection_id:
                    rejects.reject_image("missing_source_collection_id", source_id, asset_ref)
                    continue
                asset_path = root / asset_ref
                if not asset_path.is_file():
                    rejects.reject_image("asset_file_missing", source_id, asset_ref)
                    continue
                canonical_issue = plan_assets._canonical_image_asset_issue(
                    source_dir, row
                )
                if canonical_issue:
                    rejects.reject_image(
                        "canonical_duplicate",
                        source_id,
                        canonical_issue,
                    )
                    continue
                verdict = _assess_content_plan_publish_image(asset_path, ctx)
                if verdict.blocks_image_publish:
                    rejects.reject_image(
                        "image_safety_blocked",
                        source_id,
                        f"{asset_ref}:{'/'.join(verdict.reasons) or verdict.status}",
                    )
                    continue
                image_candidates.append(
                    {
                        "sourceDir": source_dir,
                        "sourceRef": plan_assets.source_ref(ctx, source_dir),
                        "sourceId": source_id,
                        "assetRef": asset_ref,
                        "assetSha": plan_assets.asset_sha(row),
                        "receiptRef": str(
                            row.get("acquisitionReceiptRef") or ""
                        ).strip(),
                        "assetId": str(
                            row.get("professionalAssetId") or ""
                        ).strip(),
                        "contentSha256": str(
                            row.get("professionalContentSha256") or ""
                        ).strip(),
                        "collectionId": collection_id,
                        "caption": str(row.get("caption") or "").strip(),
                        "title": str(meta.get("title") or "").strip(),
                    }
                )
    return article_candidates, image_candidates, article_raw_count, image_raw_count
