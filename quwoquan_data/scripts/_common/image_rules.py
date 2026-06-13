"""下载阶段图片门禁规则：相关性必填(非模板)、每实体最少数量、最小像素尺寸。

与对象证据链规格一致：每张图必须能说清「与检索对象的真实相关性」，禁止通用模板串
（如 "{实体} 实景主图"）。数量与像素门保证内容页不会出现单图/糊图。
真相源：docs/pipeline_directory_layout_spec.md + 用户图片下载要求。
"""
from __future__ import annotations

import re

# 每个实体最少要下到的合格图片数（封面 + 至少一张细节）。
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
    re.compile(r"支撑.{0,20}(?:环线|组合产品|组合一日游|区位段落|交通段落)"),
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
    if is_indirect_target_relevance(relevance):
        return (
            f"imageRelevance: {asset_id} 仅为『{entity_id}』邻近景点/环线/县域语境，"
            f"不能冒充目标实体图片（当前: {relevance!r}）"
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


def min_count_issue(downloaded: int, *, entity_id: str) -> str | None:
    """实体图片数量门：少于 MIN_ENTITY_IMAGES 返回问题串。"""
    if int(downloaded) < MIN_ENTITY_IMAGES:
        return (
            f"imageCount: {entity_id} 仅下到 {downloaded} 张合格图"
            f"（要求 ≥{MIN_ENTITY_IMAGES}：封面+细节）"
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
    "pixel_size_issue",
    "min_count_issue",
    "asset_index_relevance_issues",
]
