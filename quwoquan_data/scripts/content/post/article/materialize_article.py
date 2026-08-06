"""Approved article finalization for post materialization."""
from __future__ import annotations

import re
from typing import Any

from content.post.article.article_media_contract import materialize_article_media
from content.post.article.draft_io import is_placeholder, read_draft_article
from content.post.materialize_contract import _annotate_manifest_entities


def _resolve_materialized_article(
    execution_id: str,
    ref: str,
    *,
    compose_payload: dict[str, Any],
    entity_refs: list[str],
) -> tuple[str, list[str]]:
    draft_article = read_draft_article(execution_id, ref)
    if is_placeholder(draft_article):
        raise RuntimeError(
            f"{ref}: approved materialization requires a real 4.draft/draft.article.md; "
            "compose snapshot fallback is blocked to avoid expanding multi-body drift"
        )
    article_md = str(draft_article or "")
    actions: list[str] = []
    # P2 连续图组回填：创作 agent 原样带回的 :::figuregroup 占位，在发布物化处展开为 N 个同源
    # 单图块（下游 article.md / 资产解析 / text_only 剥离统一消费单图形态，连续图不丢、顺序不乱）。
    from core.figure_groups import expand_figure_groups

    expanded_article = expand_figure_groups(article_md)
    if expanded_article != article_md:
        actions.append("figure_groups_expanded")
        article_md = expanded_article
    if isinstance(entity_refs, list):
        annotated = _annotate_manifest_entities(article_md, entity_refs)
        if annotated != article_md:
            actions.append("entity_annotations_injected")
            article_md = annotated
    if str(compose_payload.get("publishMediaMode") or "").strip() == "text_only":
        stripped = _strip_text_only_asset_markup(article_md)
        if stripped != article_md:
            actions.append("text_only_asset_markup_removed")
            article_md = stripped
    article_md, media_actions = materialize_article_media(
        execution_id,
        ref,
        article_md,
        compose_payload,
    )
    actions.extend(media_actions)
    return article_md, actions


def _strip_text_only_asset_markup(article_md: str) -> str:
    """Remove draft image markup when release downgraded an article to text-only."""
    text = str(article_md or "")
    text = re.sub(r"(?ms)^:::figure(?:group)?\b.*?^:::\s*", "", text)
    text = re.sub(r"(?m)^coverImage:\s*asset://[^\n]+\n?", "", text)
    text = re.sub(r"(?m)^!\[[^\]]*\]\(asset://[^)]+\)\s*$\n?", "", text)
    text = re.sub(r"(?m)^asset://[^\s]+\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + ("\n" if text.strip() else "")
