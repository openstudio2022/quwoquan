"""Core route workflow contracts, routing decisions, and shared text helpers."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from content.post.article.draft_io import iter_draft_articles, PLACEHOLDER_MARKER
from core.control_types import ContentGenerator
from core.fact_coverage import fact_covered

from core.image_safety import assess_image, assess_asset_sources, is_near_duplicate, STATUS_UNSAFE
from content.execution.stage_reports import write_gate_report, write_repair_report, write_stage_result
from core.style_catalog import detect_opening_strategy, family_allowed_openings
from core.template_fingerprints import template_fingerprint_issues
from content.post.article.prompt_renderer import render_prompt_md
from content.post.article.writing_pack import build_writing_pack


ROUTE_TEMPLATE_IDS = {
    "线路_跟团攻略",
    "线路_环线攻略",
    "线路_自驾路书",
    "线路_枢纽到达",
    "线路_深度探险",
    "线路_周末短途",
    "线路_省钱攻略",
    "线路_银发慢游",
    "线路_补给避险",
}
PROVENANCE_TERMS = ("马蜂窝", "携程", "小红书", "知乎", "大众点评", "来源平台", "游记里还提到")
TRANSITION_TERMS = ("先", "再", "随后", "最后", "一路", "转场", "返程")
LIKE_FEELING_MARKERS = ("愿意", "放松", "松弛", "值得慢", "喜欢", "心动", "治愈", "踏实", "舍不得")
DISLIKE_FEELING_MARKERS = (
    "怕",
    "劝退",
    "累",
    "疲惫",
    "拖",
    "后悔",
    "别硬撑",
    "受不了",
    "难受",
    "硬撑",
    "不足",
    "遗憾",
    "不建议",
    "失望",
    "踩雷",
    "吐槽",
    "排队",
    "拥堵",
    "挤",
    "翻倍",
    "放弃硬排",
)


def _article_without_assets_allowed(brief: Mapping[str, Any]) -> bool:
    """无合格源图的优质文字底稿可发纯文字 article（publishMediaMode=text_only）。

    图片与文字同源底稿：底稿有合格图则配图，底稿无合格图则纯文字。这是来源
    形态决定的合法状态，不是去重降级——跨底稿引用相同图片是正常现象，不触发降级。
    """
    carrier = str(brief.get("carrier") or "").lower()
    if carrier == "image":
        return False
    return str(brief.get("publishMediaMode") or "").strip() == "text_only"


DECISION_MARKERS = ("我会", "我更愿意", "建议把", "如果你", "可以跟团", "宁可", "就该", "值不值得", "优先看", "我不会")
STANDALONE_TIPS_MARKERS = ("实用信息", "实用攻略信息", "来源平台", "信息卡", "小贴士：", "tips：", "贴士：")

# 软门集合单一真相源 = quality_gates.SOFT_QUALITY_GATES（review 与 publish-face verify 共用，
# 消除第二真相源）。新增/调整软门只改 quality_gates，禁止此处另起一套集合。
from core.quality_gates import SOFT_QUALITY_GATES as _SOFT_QUALITY_GATES
from core.quality_gates import (
    AUTHORING_DIAGNOSTIC_GATES as _AUTHORING_DIAGNOSTIC_GATES,
)

SOFT_CHECKS: set[str] = set(_SOFT_QUALITY_GATES)
AUTHORING_DIAGNOSTIC_CHECKS: set[str] = set(_AUTHORING_DIAGNOSTIC_GATES)
IMAGE_EVIDENCE_GENERATOR = ContentGenerator.IMAGE_EVIDENCE_PACK.value


def _compact_public_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def aggregate_checks(
    checks: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[str], int]:
    """聚合评审 checks：HARD 失败计入 blocking；SOFT 失败仅出建议+降分。

    返回 (blocking, suggestions, soft_failed_count)。
    """
    blocking: list[str] = []
    suggestions: list[str] = []
    soft_failed = 0
    for name, result in checks.items():
        if result.get("passed", True):
            continue
        issues = list(result.get("issues") or [])
        if name in SOFT_CHECKS or name in AUTHORING_DIAGNOSTIC_CHECKS:
            soft_failed += 1
            prefix = "诊断" if name in AUTHORING_DIAGNOSTIC_CHECKS else "建议"
            suggestions.extend(f"[{prefix}] {name}: {issue}" for issue in issues)
        else:
            blocking.extend(f"{name}: {issue}" for issue in issues)
        suggestions.extend(result.get("suggestions") or [])
    return blocking, suggestions, soft_failed


def is_route_brief(brief: Mapping[str, Any]) -> bool:
    subject = brief.get("subject") or {}
    return (
        isinstance(subject, Mapping)
        and subject.get("kind") == "topic"
        and subject.get("type") == "旅行/线路"
        and str(brief.get("templateId") or "") in ROUTE_TEMPLATE_IDS
    )


def load_compose_brief(execution_id: str, ref: str) -> dict[str, Any]:
    from content.post.object_index import read_brief_object

    brief = read_brief_object(execution_id, ref) or {}
    if not brief:
        return {}
    return brief


def iter_route_briefs(execution_id: str, refs: Sequence[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    from content.post.object_index import iter_content_refs

    wanted = {ref for ref in (refs or []) if ref}
    rows: list[tuple[str, dict[str, Any]]] = []
    for ref in iter_content_refs(execution_id):
        if wanted and ref not in wanted:
            continue
        brief = load_compose_brief(execution_id, ref)
        if brief and is_route_brief(brief):
            rows.append((ref, brief))
    return rows

def _route_section_intents(brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any]) -> list[str]:
    """章节意图：跟随底稿自身结构，仅给最小推进建议（不再下发固定骨架）。"""
    nodes = [str(n.get("entityName") or "") for n in (evidence_bundle.get("routeNodes") or []) if n.get("entityName")]
    order = "、".join(nodes) if nodes else "线路各节点"
    return [
        "结构跟随底稿：保留底稿自身的小标题与叙述顺序，只做轻量编辑（去语病/补证据/去平台痕迹）。",
        f"若底稿未按主线推进，可按 {order} 的真实顺序理顺，但不要套用固定模板小标题。",
    ]

# 底稿派生内容类目（publish 目录 angle = path bucket）：源即单位模型下不再用 templateId
# 模板映射，而是按载体 + 底稿派生的 writingIntent 标签确定性归类；标题取自底稿、保证目录唯一性。
_ANGLE_BY_INTENT = {
    "planning_consultation": "攻略",
    "decision_experience": "体验",
    "post_trip_journal": "游记",
}


def _publish_angle(brief: Mapping[str, Any]) -> str:
    """底稿派生内容类目（publish 目录 angle）。"""
    carrier = str(brief.get("carrier") or "").lower()
    if carrier == "image":
        return "画报"
    if carrier == "video":
        return "体验"
    if str(brief.get("articleCategory") or "").strip() == "photography":
        return "摄影"
    intent = str(brief.get("writingIntent") or "").strip()
    return _ANGLE_BY_INTENT.get(intent, "攻略")

GALLERY_MIN_IMAGES = 4
LOW_NARRATIVE_SIGNALS = 6


def _narrative_volume(evidence_bundle: Mapping[str, Any]) -> int:
    nodes = evidence_bundle.get("routeNodes") or []
    total = 0
    for node in nodes:
        total += len([x for x in (node.get("mainlineEvidence") or []) if x])
        emotion = node.get("emotionEvidence") or {}
        total += len(emotion.get("likes") or []) + len(emotion.get("painPoints") or [])
    return total


def resolve_carrier(brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any], assets: Sequence[Mapping[str, Any]]) -> str:
    """Route explicit image works separately from prose articles."""
    declared = str(brief.get("carrier") or "").lower()
    if declared == "image":
        # 显式声明的图片作品/画报优先：即使某张图文字偏多，也保持图片载体，
        # 由后续图片安全门逐张裁决，而非整体降级为 article。
        return "image"
    if any(asset.get("isTextHeavy") for asset in assets):
        return "article"
    if declared:
        return "article"
    policy = brief.get("imagePolicy") or {}
    min_images = int(policy.get("minImages") or GALLERY_MIN_IMAGES)
    safe_imgs = [a for a in assets if a.get("imageStatus", "safe") in ("safe", "text_heavy")]
    if len(safe_imgs) >= min_images and _narrative_volume(evidence_bundle) <= LOW_NARRATIVE_SIGNALS:
        return "image"
    return "article"


def _build_summary(article: str) -> str:
    compact = re.sub(r"\s+", " ", article).strip()
    return compact[:160]


def _image_caption_from_article(article: str) -> str:
    """Extract user-facing image caption text from an image draft.

    Image works store assets structurally.  The draft may include headings,
    figure blocks, or attribution notes for the authoring checkpoint, but those
    are not the public caption and must not be counted as caption prose.
    """
    text = re.sub(r"<!--[\s\S]*?-->", "", str(article or ""))
    text = re.sub(r":::figure[\s\S]*?:::", "", text)
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        if line.startswith("asset://"):
            continue
        if any(marker in line for marker in ("授权", "署名", "CC BY", "Creative Commons", "license")):
            continue
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _image_caption_from_brief(
    brief: Mapping[str, Any],
    pack: Mapping[str, Any],
    draft_meta: Mapping[str, Any] | None = None,
    article: str = "",
) -> str:
    meta = draft_meta or {}
    candidates: list[Any] = [
        meta.get("caption"),
        pack.get("caption"),
        brief.get("caption"),
        _image_caption_from_article(article),
    ]
    for asset in (pack.get("assets") or []):
        if isinstance(asset, Mapping):
            candidates.append(asset.get("caption"))
    for candidate in candidates:
        text = _compact_public_text(candidate, 300)
        if text:
            return text
    return ""


def _section_bodies(article: str) -> list[str]:
    parts = re.split(r"\n## ", article)
    bodies: list[str] = []
    for part in parts[1:]:
        lines = part.split("\n", 1)
        body = lines[1] if len(lines) > 1 else ""
        body = re.sub(r":::figure[\s\S]*?:::", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) > 40:
            bodies.append(body)
    return bodies


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _fact_in_article(article: str, fact: str) -> bool:
    if fact in article:
        return True
    return fact_covered(fact, article)


def _unique_strings(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

__all__ = [name for name in globals() if not name.startswith("__")]
