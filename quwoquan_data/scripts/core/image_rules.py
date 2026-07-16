"""下载阶段图片门禁规则：相关性必填(非模板)、最小像素尺寸。

与对象证据链规格一致：每张图必须能说清「与检索对象的真实相关性」，禁止通用模板串
（如 "{实体} 实景主图"）。像素门保证内容页不会出现糊图；数量门由当前
ContentSupplyTask 的载体配额决定，图片作品允许单张高质量图。
真相源：docs/pipeline_directory_layout_spec.md + 用户图片下载要求。
"""
from __future__ import annotations

import re
import urllib.parse
from functools import lru_cache
from pathlib import Path

import yaml

# 旧任务的默认实体图数量；新 separated research 按任务配额动态计算。
MIN_ENTITY_IMAGES = 2

# 最小像素尺寸门：长边 >= 800，且宽高均 >= 设定下限，避免缩略糊图进内容页。
MIN_IMAGE_WIDTH = 640
MIN_IMAGE_HEIGHT = 426
MIN_IMAGE_LONG_EDGE = 800

# 通用/模板化相关性串：空、或仅由实体名 + 通用词拼成，视为「无真实相关性」。
_GENERIC_RELEVANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*$"),
    re.compile(r"^实?景?主?图$"),
    re.compile(r"^封面图?$"),
    re.compile(r"^配图$"),
    re.compile(r"^示意图$"),
    re.compile(r"^图片?$"),
    re.compile(r"实景主图$"),
    re.compile(r"^覆盖该?对象的基础事实"),
)

_INDIRECT_TARGET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:距|距离).{0,18}(?:公里|千米)"),
    re.compile(r"(?:互补|同日|组合).{0,12}(?:游线|环线|一日游)"),
    re.compile(r"(?:邻近|周边).{0,12}(?:景点|景区|文化|游线)"),
    re.compile(r"(?:所属县域|县城景观|藏居客厅|民居内景)"),
    re.compile(r"支撑.{0,20}(?:环线|组合产品|组合一日游|交通段落)"),
)

_LOW_QUALITY_CAPTION_MARKERS = (
    "500px provided description",
)

_TRAVEL_SOURCE_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "verticals"
    / "travel"
    / "sources"
    / "source_registry.yaml"
)


def is_generic_relevance(relevance: str, *, entity_id: str = "") -> bool:
    """判断相关性是否为空或通用模板串（去掉实体名后若只剩通用词，也算通用）。"""
    text = str(relevance or "").strip()
    if not text:
        return True
    for pat in _GENERIC_RELEVANCE_PATTERNS:
        if pat.search(text):
            return True
    # 去掉实体名后若塌缩成通用词（"<实体> 实景主图" → "实景主图"），同样判通用。
    if entity_id:
        stripped = text.replace(str(entity_id), "").strip(" 　-—·:：")
        if stripped and stripped != text:
            for pat in _GENERIC_RELEVANCE_PATTERNS:
                if pat.search(stripped):
                    return True
    return False


def is_indirect_target_relevance(relevance: str) -> bool:
    """识别明确把邻近景点、环线或县域素材当作目标实体配图的说明。"""
    text = str(relevance or "").strip()
    return any(pattern.search(text) for pattern in _INDIRECT_TARGET_PATTERNS)


def relevance_issue(relevance: str, *, entity_id: str, asset_id: str) -> str | None:
    """单图相关性门：缺失/通用返回问题串，否则 None。"""
    if is_generic_relevance(relevance, entity_id=entity_id):
        return (
            f"imageRelevance: {asset_id} 缺少与『{entity_id}』的真实相关性说明"
            f"（当前: {relevance!r}，禁止通用模板串）"
        )
    text = str(relevance or "").strip()
    if (
        entity_id
        and entity_id in text
        and any(marker in text for marker in ("直接呈现", "摄于", "目标景区", "核心景区"))
    ):
        return None
    if is_indirect_target_relevance(relevance):
        return (
            f"imageRelevance: {asset_id} 仅为『{entity_id}』邻近景点/环线/县域语境，"
            f"不能冒充目标实体图片（当前: {relevance!r}）"
        )
    return None


def image_caption_quality_issue(caption: str, *, entity_id: str = "", asset_id: str = "") -> str | None:
    """Block unreadable source captions before they become publish titles."""
    text = re.sub(r"\s+", " ", str(caption or "")).strip()
    if not text:
        return None
    lower = text.casefold()
    label = asset_id or "?"
    if any(marker in lower for marker in _LOW_QUALITY_CAPTION_MARKERS):
        question_count = text.count("?") + text.count("？")
        if question_count >= 3 or "#??" in text or "[]" in text:
            return (
                f"imageCaption: {label} 图片说明疑似乱码/平台模板"
                f"（当前: {text!r}）"
            )
    question_count = text.count("?") + text.count("？")
    if len(text) >= 12 and question_count / max(1, len(text)) >= 0.25:
        return (
            f"imageCaption: {label} 图片说明疑似乱码"
            f"（当前: {text!r}）"
        )
    return None


def _normalized_known_term_text(value: str) -> str:
    text = urllib.parse.unquote(str(value or "")).casefold()
    text = re.sub(r"[_/\\\-·|:：,，.。()（）\\[\\]【】]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def _known_image_reject_registry() -> dict[str, tuple[str, ...]]:
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return {}
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for row in data.get("knownImageRejectTerms") or []:
        if not isinstance(row, dict):
            continue
        entity = str(row.get("entity") or "").strip()
        values = row.get("rejectTerms") if isinstance(row.get("rejectTerms"), list) else []
        seen: set[str] = set()
        terms: list[str] = []
        for value in values:
            term = str(value or "").strip()
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
        if entity and terms:
            out[entity] = tuple(terms)
    return out


def known_image_reject_terms(entity_id: str) -> tuple[str, ...]:
    """Curated cross-entity visual reject terms from the travel source registry."""
    entity = str(entity_id or "").strip()
    if not entity:
        return ()
    return _known_image_reject_registry().get(entity, ())


def image_known_reject_issue(
    text: str,
    *,
    entity_id: str,
    asset_id: str = "",
) -> str | None:
    """Block curated same-name/wrong-place image matches before release."""
    entity = str(entity_id or "").strip()
    if not entity:
        return None
    haystack_raw = urllib.parse.unquote(str(text or "")).casefold()
    haystack_normalized = _normalized_known_term_text(haystack_raw)
    for term in known_image_reject_terms(entity):
        raw = urllib.parse.unquote(str(term or "")).casefold()
        normalized = _normalized_known_term_text(raw)
        if (raw and raw in haystack_raw) or (
            normalized and normalized in haystack_normalized
        ):
            label = asset_id or "?"
            return (
                f"imageCaption: {label} 命中『{entity}』已知错位图片词"
                f"（term={term!r}）"
            )
    return None


def pixel_size_issue(width: int | None, height: int | None, *, asset_id: str) -> str | None:
    """单图像素门：尺寸缺失或低于阈值返回问题串，否则 None。"""
    if not width or not height:
        return f"imagePixels: {asset_id} 缺少像素尺寸（无法判定清晰度）"
    if int(width) < MIN_IMAGE_WIDTH or int(height) < MIN_IMAGE_HEIGHT:
        return (
            f"imagePixels: {asset_id} 尺寸过小 {width}x{height}"
            f"（要求 ≥{MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}）"
        )
    if max(int(width), int(height)) < MIN_IMAGE_LONG_EDGE:
        return (
            f"imagePixels: {asset_id} 长边过短 {max(int(width), int(height))}"
            f"（要求 ≥{MIN_IMAGE_LONG_EDGE}）"
        )
    return None


def min_count_issue(downloaded: int, *, entity_id: str, required: int | None = None) -> str | None:
    """实体图片数量门：少于 required 返回问题串。

    required 为空时仅用于旧任务默认门；新工作流应传入由任务配额计算出的数量。
    """
    min_required = MIN_ENTITY_IMAGES if required is None else max(0, int(required))
    if int(downloaded) < min_required:
        return (
            f"imageCount: {entity_id} 仅下到 {downloaded} 张合格图"
            f"（要求 ≥{min_required}）"
        )
    return None


def asset_index_relevance_issues(assets: list[dict], *, entity_id: str = "") -> list[str]:
    """扫描 assets.index 条目的相关性，返回所有通用/缺失问题（供静态门复用）。"""
    issues: list[str] = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("sourceAssetId") or asset.get("fileName") or "?")
        issue = relevance_issue(
            str(asset.get("relevance") or ""), entity_id=entity_id, asset_id=aid
        )
        if issue:
            issues.append(issue)
    return issues


__all__ = [
    "MIN_ENTITY_IMAGES",
    "MIN_IMAGE_WIDTH",
    "MIN_IMAGE_HEIGHT",
    "MIN_IMAGE_LONG_EDGE",
    "is_generic_relevance",
    "relevance_issue",
    "image_caption_quality_issue",
    "known_image_reject_terms",
    "image_known_reject_issue",
    "pixel_size_issue",
    "min_count_issue",
    "asset_index_relevance_issues",
]
