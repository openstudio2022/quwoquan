"""证据驱动篇目规划包（content_plan_packet）校验。

真相源：tasks/{executionId}/_shared/content_plan_packet.json
见 object-homepage-coverage-scaling/design.md。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from core.article_commercial_policy import article_commercial_closure_enabled
from content.post.article.base_draft import ARTICLE_MIN_BASE_DRAFT_CHARS, base_draft_readiness, load_base_draft_text
from core import ops_governance as og
from content.post.object_index import BRIEF_FILE, content_object_stage_dir, load_index
from governance.creators.assignment import creator_assignment_issues, creator_assignment_required
from core.image_rules import image_caption_quality_issue
from core.io import read_json
from core.image_safety import assess_image_publish_prefilter
from core.paths import (
    STAGE_COMPOSE,
    execution_content_plan_packet_path,
    execution_results_dir,
    execution_root,
    relative_execution_ref,
)
from core.quality_gates import WRITING_INTENTS, writing_intent_issues
from core.qunar_template import qunar_article_base_block_reason
from content.post.content_plan_state import (
    load_content_plan_packet,
    packet_items as _items,
    reject_source_ids,
)

CONTENT_PLAN_SCHEMA = "quwoquan_data.content_plan_packet"
ARTICLE_BASE_SOURCE_ROLES = {"base"}
ARTICLE_BASE_SOURCE_CATEGORIES = {
    "travelogue",
    "guidebook",
    "travel_guide",
    "wikivoyage",
    "official_article",
    "vertical_professional",
    "ugc_longform",
    "community_post",
    "media_article",
    "platform_article",
    "forum_thread",
    "review_note",
}
ARTICLE_SUPPORTING_ONLY_CATEGORIES = {
    "authoritative_reference",
    "official",
    "government",
    "media",
    "open_license",
    "image_collection",
    "overview_baike",
    "encyclopedia",
}


def _source_asset_rows(root: Path, source_ref: str) -> list[dict[str, Any]]:
    if not source_ref:
        return []
    source_path = root / source_ref
    index_path = source_path.parent / "assets" / "index.json"
    if not index_path.is_file():
        return []
    try:
        rows = read_json(index_path).get("assets") or []
    except (OSError, ValueError, TypeError):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _source_meta(root: Path, source_ref: str) -> dict[str, Any]:
    if not source_ref:
        return {}
    meta_path = (root / source_ref).parent / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        data = read_json(meta_path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _article_source_category(meta: Mapping[str, Any]) -> str:
    return str(
        meta.get("category")
        or meta.get("sourceCategory")
        or meta.get("sourceKind")
        or ""
    ).strip()


def _source_asset_ref(
    execution_id: str, root: Path, source_ref: str, row: Mapping[str, Any]
) -> str:
    file_name = str(row.get("fileName") or "").strip()
    if not source_ref or not file_name:
        return ""
    return relative_execution_ref((root / source_ref).parent / "assets" / file_name, execution_id)




def content_plan_quotas_required(spec: Mapping[str, Any]) -> bool:
    """content_plan packet 承载 article/image/video/route 篇目合同。

    实体主页（entityHomepagesPerTarget）不是篇目：主页三件套的唯一真相源在
    build_homepage/build_validate 车道（`_homepages_done` + review sidecars），
    发布走 entities 实体面。把主页配额算进"需要 packet"会制造
    clean→auto-skip→等 Agent 的确定性死循环（agent 写的 packet 每轮被
    `_clean_content_plan_outputs` 删除），因此这里刻意不计入主页配额。
    """
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    return bool(
        int(quotas.get("entityArticles") or 0)
        or int(quotas.get("routeArticles") or 0)
        or int(quotas.get("entityArticlesPerTarget") or 0)
        or int(quotas.get("imageWorksPerTarget") or 0)
        or int(quotas.get("videoWorksPerTarget") or 0)
    )


def load_writing_intent_overrides(execution_id: str) -> dict[str, dict[str, Any]]:
    """从 content_plan_packet 读取每篇 writingIntent / baseSourceRef，供 compose 注入 brief。

    返回 {ref: {"writingIntent": ..., "baseSourceRef": ...}}（仅含已声明的字段）。
    这是 content_plan(任务层) → brief(写作契约) 的单一贯通点，保证即使 Agent 没把
    writingIntent 写进 brief.json，writing_pack/prompt 仍有正确主线。
    """
    packet = load_content_plan_packet(execution_id) or {}
    overrides: dict[str, dict[str, Any]] = {}
    for item in _items(packet):
        ref = str(item.get("ref") or "").strip()
        if not ref:
            continue
        row: dict[str, Any] = {}
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
            "creatorProfileDigest",
            "creatorDisclosure",
            "experienceClaimMode",
            "authorQualitySignals",
            "creator",
        ):
            if item.get(field) not in (None, ""):
                row[field] = item.get(field)
        if row:
            overrides[ref] = row
    return overrides
