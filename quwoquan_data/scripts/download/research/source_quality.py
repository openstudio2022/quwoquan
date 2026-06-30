"""Source and image quality gates for auto research plans."""
from __future__ import annotations

import os
import math
import re
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.source_catalog import platform_category
from vertical.license import validate_image_rights

from download.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _normalized_title,
    _text_mentions_entity,
    _title_matches_entity,
)

_ARTICLE_BASE_CATEGORIES = {
    "travelogue",
    "guidebook",
    "official_article",
    "vertical_professional",
    "ugc_longform",
    "community_post",
    "media_article",
    "platform_article",
    "forum_thread",
    "review_note",
}

_SUPPORTING_ONLY_CATEGORIES = {
    "authoritative_reference",
    "encyclopedia",
    "official",
    "map_geo",
    "weather",
    "review",
    "transport",
    "lodging",
}

_TRAVEL_SOURCE_REGISTRY = Path(__file__).resolve().parents[3] / "verticals" / "travel" / "sources" / "source_registry.yaml"

_HOMEPAGE_CORE_SOURCE_LIMIT = 5

_MAX_PUBLISHABLE_IMAGE_PIXELS = max(
    1_000_000,
    int(os.environ.get("QWQ_MAX_PUBLISHABLE_IMAGE_PIXELS", "80000000")),
)

def _image_pixel_issue(spec: Mapping[str, Any]) -> str:
    try:
        width = int(spec.get("width") or 0)
        height = int(spec.get("height") or 0)
    except (TypeError, ValueError):
        return ""
    if width <= 0 or height <= 0:
        return ""
    pixels = width * height
    if pixels > _MAX_PUBLISHABLE_IMAGE_PIXELS:
        return (
            f"imageRights pixelCount {pixels} exceeds "
            f"maxPublishablePixels {_MAX_PUBLISHABLE_IMAGE_PIXELS}"
        )
    return ""

def _known_image_reject_terms(entity_id: str) -> list[str]:
    """Curated cross-entity visual reject terms from the travel registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    terms: list[str] = []
    for row in data.get("knownImageRejectTerms") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        values = row.get("rejectTerms") if isinstance(row.get("rejectTerms"), list) else []
        terms.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe_terms(terms, limit=32)

def _image_conflicts_with_entity(image: Mapping[str, Any], entity_id: str) -> bool:
    reject_terms = _known_image_reject_terms(entity_id)
    if not reject_terms:
        return False
    fields = (
        "caption",
        "title",
        "relevance",
        "sourceUrl",
        "collectionPageUrl",
        "authorizationProof",
        "url",
    )
    text = " ".join(str(image.get(field) or "") for field in fields)
    text = urllib.parse.unquote(text)
    text = re.sub(r"[_/\\\-]+", " ", text).casefold()
    compact = _normalized_title(text).casefold()
    for term in reject_terms:
        raw = urllib.parse.unquote(str(term or "")).casefold()
        normalized = _normalized_title(raw).casefold()
        if (raw and raw in text) or (normalized and normalized in compact):
            return True
    return False

_HOMEPAGE_JSON_API_RE = re.compile(
    r'^\s*[\[{].{0,240}"(?:code|data|rows|result|success|message|msg|list|total)"',
    re.S,
)

_HOMEPAGE_REDIRECT_MARKERS = (
    "簡繁重定向",
    "简繁重定向",
    "本重定向",
    "重定向用来",
    "重定向用來",
    "redirect page",
)

_HOMEPAGE_DISAMBIG_MARKERS = (
    "可以指",
    "可指",
    "可能指",
    "指的是",
    "下列",
    "消歧义",
    "消歧義",
    "disambiguation",
)

_HOMEPAGE_FACT_MARKERS = (
    "位于",
    "位於",
    "坐落",
    "地处",
    "地處",
    "始建",
    "建于",
    "建於",
    "建成",
    "开放",
    "開放",
    "占地",
    "面積",
    "面积",
    "海拔",
    "全长",
    "全長",
    "长度",
    "长度",
    "宽度",
    "包括",
    "包含",
    "核心",
    "主要",
    "属于",
    "屬於",
    "国家级",
    "國家級",
    "AAAAA",
    "5A",
    "世界遗产",
    "世界遺產",
    "文化遗产",
    "自然遗产",
    "门票",
    "門票",
    "预约",
    "預約",
    "开放时间",
    "開放時間",
    "交通",
    "游览",
    "遊覽",
)

_HOMEPAGE_FACT_UNIT_RE = re.compile(
    r"(\d{3,4}年|\d+(?:\.\d+)?\s*(?:平方公里|公顷|亩|米|公里|千米|米|万平方米|万人次|亿元|级|A))"
)

_HOMEPAGE_DISAMBIG_LINE_RE = re.compile(
    r"^\s*(?:[-*#\d.、]+\s*)?[^。\n]{1,42}[：:][^。\n]{0,120}(?:位于|位於|位在|坐落|地处|地處)",
    re.M,
)

_HOMEPAGE_PAREN_LOCATION_LINE_RE = re.compile(
    r"[\(（][^)）]{1,16}[\)）][，,]?(?:位于|位於|位在|坐落|地处|地處)"
)

_HOMEPAGE_INSECT_CONTEXT_RE = re.compile(r"(学名|學名|胡蜂|黄蜂|黃蜂|昆虫|昆蟲|本属包括|本屬包括|下属物种|下屬物種)")

_HOMEPAGE_STATION_CONTEXT_RE = re.compile(r"(地铁|地鐵|车站|車站|站台|出入口|接驳交通)")

_HOMEPAGE_NAVIGATION_MARKERS = (
    "登录",
    "註冊",
    "注册",
    "上一页",
    "下一页",
    "扫一扫",
    "版权所有",
    "网站地图",
    "分享到",
    "返回首页",
)

def _homepage_entity_tokens(entity_id: str) -> list[str]:
    tokens = _dedupe_terms([entity_id, *_entity_name_variants(entity_id)], limit=16)
    out: list[str] = []
    for token in tokens:
        key = _normalized_title(token)
        if key and len(key) >= 2 and key not in out:
            out.append(key)
    return out

def _homepage_fact_signal_count(text: str, entity_id: str) -> int:
    tokens = _homepage_entity_tokens(entity_id)
    seen: set[str] = set()
    count = 0
    for raw in re.split(r"[。！？!?；;\n]+", str(text or "")):
        sentence = re.sub(r"\s+", " ", raw).strip()
        if len(sentence) < 8 or len(sentence) > 260:
            continue
        if any(marker in sentence for marker in _HOMEPAGE_NAVIGATION_MARKERS):
            continue
        key = _normalized_title(sentence)
        if key in seen:
            continue
        mentions_entity = any(token and token in key for token in tokens)
        has_signal = any(marker in sentence for marker in _HOMEPAGE_FACT_MARKERS) or bool(
            _HOMEPAGE_FACT_UNIT_RE.search(sentence)
        )
        if mentions_entity or has_signal:
            seen.add(key)
            count += 1
    return count

def _homepage_text_quality_issue(
    text: str,
    entity_id: str,
    *,
    require_fact_ready: bool,
) -> str:
    """Return a blocking reason when homepage text cannot support a base draft."""
    body = re.sub(r"\s+", " ", str(text or "")).strip()
    if not body:
        return "empty_homepage_text"
    if require_fact_ready and len(body) < 80:
        return "homepage_text_too_short"
    head = body[:1800]
    if _HOMEPAGE_JSON_API_RE.search(head):
        return "raw_json_api_homepage"
    if any(marker.lower() in head.lower() for marker in _HOMEPAGE_REDIRECT_MARKERS):
        return "redirect_homepage"
    disambig_hits = len(_HOMEPAGE_DISAMBIG_LINE_RE.findall(str(text or "")[:5000]))
    parenthesized_location_hits = len(_HOMEPAGE_PAREN_LOCATION_LINE_RE.findall(str(text or "")[:5000]))
    location_mentions = len(re.findall(r"(?:位于|位於|位在|坐落|地处|地處)", head))
    if disambig_hits >= 3 or (
        any(marker in head for marker in _HOMEPAGE_DISAMBIG_MARKERS)
        and (disambig_hits >= 1 or parenthesized_location_hits >= 2 or location_mentions >= 3)
    ):
        return "disambiguation_homepage"
    if require_fact_ready and _HOMEPAGE_INSECT_CONTEXT_RE.search(head) and "蜂" not in entity_id:
        return "wrong_entity_context"
    if require_fact_ready and _HOMEPAGE_STATION_CONTEXT_RE.search(head) and not entity_id.endswith("站"):
        return "wrong_entity_context"
    if require_fact_ready and _homepage_fact_signal_count(body[:5000], entity_id) < 4:
        return "insufficient_homepage_facts"
    return ""

def _image_mentions_entity(
    image: dict[str, Any],
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    if not entity_id:
        return True
    if _image_conflicts_with_entity(image, entity_id):
        return False
    for field in (
        "caption",
        "title",
        "sourceUrl",
        "collectionPageUrl",
        "authorizationProof",
        "url",
    ):
        if _text_mentions_entity(
            str(image.get(field) or ""),
            entity_id,
            entity_aliases=entity_aliases,
        ):
            return True
    return False

def _known_official_website(entity_id: str) -> str:
    """Curated official-site seed from the travel source registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return ""
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ""
    for row in data.get("knownOfficialSites") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""

def _known_homepage_support_websites(entity_id: str) -> list[dict[str, str]]:
    """Curated same-lane official/government detail pages for sparse homepages."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    rows: list[dict[str, str]] = []
    for index, row in enumerate(data.get("knownHomepageSupportSites") or [], start=1):
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        rows.append(
            {
                "source_id": str(row.get("sourceId") or f"home_official_support_{index}").strip(),
                "platform": str(row.get("platform") or "景区官网").strip(),
                "url": url,
                "category": str(row.get("category") or "official").strip(),
            }
        )
    return rows

def _travel_registry_url_fetchable(url: str) -> bool:
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return False
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return False
    for site in data.get("sites") or []:
        if not isinstance(site, dict):
            continue
        domains = [str(item).lower() for item in (site.get("domains") or []) if str(item).strip()]
        if not domains:
            continue
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return bool(site.get("fetchable"))
    return False

def _known_article_sources(entity_id: str) -> list[dict[str, str]]:
    """Curated article-lane seed sources from the travel source registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    rows: list[dict[str, str]] = []
    for index, row in enumerate(data.get("knownArticleSources") or [], start=1):
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        explicit_fetchable = row.get("fetchable")
        if explicit_fetchable is not None:
            if not bool(explicit_fetchable):
                continue
        elif not _travel_registry_url_fetchable(url):
            continue
        rows.append(
            {
                "source_id": str(row.get("sourceId") or f"article_registry_base_{index}").strip(),
                "platform": str(row.get("platform") or "垂类专业站").strip(),
                "url": url,
                "category": str(row.get("category") or "travelogue").strip(),
                "title": str(row.get("title") or "").strip(),
                "fetchable": bool(row.get("fetchable")),
            }
        )
    return rows

def _known_entity_aliases(entity_id: str) -> list[str]:
    """Curated entity aliases that are valid across source discovery lanes."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    aliases: list[str] = []
    for row in data.get("knownEntityAliases") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        values = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        aliases.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe_terms(aliases, limit=16)

def _known_image_search_hints(entity_id: str) -> dict[str, list[str]]:
    """Curated visual-discovery hints from the travel source registry.

    These are discovery inputs only. They do not bypass asset-level license,
    entity-relevance, creator, watermark, or collection gates.
    """
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return {"aliases": [], "commonsCategories": []}
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"aliases": [], "commonsCategories": []}
    aliases: list[str] = []
    categories: list[str] = []
    for row in data.get("knownImageSearchHints") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        raw_aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        raw_categories = (
            row.get("commonsCategories") if isinstance(row.get("commonsCategories"), list) else []
        )
        aliases.extend(str(value).strip() for value in raw_aliases if str(value).strip())
        categories.extend(str(value).strip() for value in raw_categories if str(value).strip())
    return {
        "aliases": _dedupe_terms(aliases, limit=16),
        "commonsCategories": _dedupe_terms(categories, limit=12),
    }

def _license_allows_app_publish(license_name: str, license_url: str = "") -> bool:
    value = f"{license_name} {license_url}".lower()
    if not value.strip():
        return False
    if any(token in value for token in ("nc", "noncommercial", "nd", "noderivatives", "igo")):
        return False
    if any(token in value for token in ("cc0", "publicdomain", "public domain")):
        return True
    if re.search(r"\b1\.0\b", value) and (
        "creativecommons" in value
        or "cc by" in value
        or "by-sa" in value
        or "/by" in value
    ):
        return False
    return any(token in value for token in ("pd", "by-sa", "by/sa", "by/", " by"))

def _evidence_reason(entity_id: str, lane: str, provider: str, category: str) -> str:
    lane_label = {"homepage": "实体主页", "article": "图文文章", "image": "图库作品"}.get(lane, lane)
    return f"{provider} 发现的 {entity_id} {lane_label}候选来源；类别={category or 'unknown'}"

def _source_category(platform: str, fallback: str = "") -> str:
    if fallback in _ARTICLE_BASE_CATEGORIES:
        return fallback
    return platform_category(platform) or fallback

def _homepage_plan_sort_key(source: Mapping[str, Any]) -> tuple[int, int, str]:
    text = " ".join(
        str(source.get(field) or "")
        for field in ("platform", "category", "source_id", "discoveryProvider", "url")
    ).casefold()
    category = str(source.get("category") or "").casefold()
    platform = str(source.get("platform") or "")
    if category == "encyclopedia" or any(marker in text for marker in ("wikipedia", "维基百科", "百度百科", "搜狗百科", "头条百科", "字节百科", "britannica")):
        bucket = 0
    elif "wikidata" in text or "knowledge graph" in text:
        bucket = 1
    elif any(marker in text for marker in ("官网", "official", "官方网站")):
        bucket = 2
    elif any(marker in text for marker in ("政府", "文旅", "政务", "gov.cn")):
        bucket = 4
    else:
        bucket = 3
    confidence = int(float(source.get("matchConfidence") or 0) * -1000)
    return (bucket, confidence, platform)

def _homepage_core_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Homepage core evidence: encyclopedia/knowledge/official first, capped."""
    return sorted(sources, key=_homepage_plan_sort_key)[:_HOMEPAGE_CORE_SOURCE_LIMIT]

# P3 三类解耦：可作实体主页 base draft 的主源【只限百科】。官网/官方降为 supporting。
_HOMEPAGE_PRIMARY_SOURCE_MARKERS = (
    "维基百科",
    "wikipedia",
    "百度百科",
    "搜狗百科",
    "字节百科",
    "百科",
)

_HOMEPAGE_SUPPORT_ONLY_SOURCE_MARKERS = (
    "政府",
    "文旅",
    "政务",
    "gov.cn",
    "权威媒体",
    "媒体",
    "景区官网",
    "官网",
    "官方",
    "official",
)

_HOMEPAGE_NON_HOMEPAGE_SOURCE_MARKERS = ("攻略", "游记", "评论", "点评", "小红书", "摄影")

_HOMEPAGE_TEXT_EVIDENCE_REQUIRED_DOMAINS = (
    "baike.baidu.com",
    "baike.sogou.com",
)

def _homepage_can_seed_base_draft(source: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(source.get(field) or "")
        for field in ("platform", "category", "source_id", "discoveryProvider", "url")
    ).strip()
    lowered = text.casefold()
    if any(marker.casefold() in lowered for marker in _HOMEPAGE_NON_HOMEPAGE_SOURCE_MARKERS):
        return False
    if any(marker.casefold() in lowered for marker in _HOMEPAGE_SUPPORT_ONLY_SOURCE_MARKERS):
        return False
    category = str(source.get("category") or "").casefold()
    # 只有百科类目可作主页 base draft 主源；official_site 已在 support-only markers 归为补充源。
    if category == "encyclopedia":
        return True
    return any(marker.casefold() in lowered for marker in _HOMEPAGE_PRIMARY_SOURCE_MARKERS)

def _homepage_requires_text_snapshot(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in _HOMEPAGE_TEXT_EVIDENCE_REQUIRED_DOMAINS)

def _source_has_text_snapshot(source: Mapping[str, Any]) -> bool:
    for key in ("body", "text", "extractText", "sourceText", "textSnapshot"):
        if str(source.get(key) or "").strip():
            return True
    return False

def _homepage_candidate_has_fetch_evidence(source: Mapping[str, Any], url: str) -> bool:
    """Homepage source plans must prove the source can become text evidence.

    A bare search/item URL is not enough for production: download_fetch can
    reject anti-crawled encyclopedia pages after minutes of media work. Accept
    sources from verified/reusable providers, registry fetchable sites, or rows
    that carry a text snapshot for deterministic materialization. A bare
    encyclopedia URL still needs a snapshot unless the registry says it is
    fetchable.
    """
    provider = str(source.get("discoveryProvider") or "")
    if provider.startswith("mediawiki_"):
        return True
    if provider in {
        "verified_homepage_source_unit_reuse",
        "Chinese Wikipedia",
        "English Wikipedia",
        "Wikivoyage",
    }:
        return True
    if provider.startswith("verified_homepage_source_unit"):
        return True
    if _source_has_text_snapshot(source):
        return True
    if bool(source.get("fetchable")):
        return True
    if _travel_registry_url_fetchable(url):
        return True
    if _homepage_requires_text_snapshot(url):
        return False
    return False

def _candidate_gate(
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Gate one source candidate before it can enter a lane source plan.

    The gate is deliberately conservative. Discovery can record rejected rows in
    the diagnostic report, but only passed rows are written into consumable lane
    plans. This prevents weak wiki/search matches and city-level substitute pages
    from becoming article base evidence.
    """
    issues: list[str] = []
    url = str(source.get("url") or "").strip()
    platform = str(source.get("platform") or "").strip()
    category = str(source.get("category") or _source_category(platform) or "").strip()
    role = str(source.get("sourceRole") or "supporting").strip()
    confidence = float(source.get("matchConfidence") or 0.0)
    if not url.startswith(("http://", "https://")):
        issues.append("url must be http(s)")
    if not platform:
        issues.append("platform missing")
    if not category:
        issues.append(f"platform {platform!r} is not registered in source catalog")
    if confidence < 0.72:
        issues.append(f"matchConfidence {confidence:.2f} < 0.72")
    if str(source.get("entityMatch") or "") == "weak":
        issues.append("weak entity match is not allowed")
    if lane == "article" and role == "base":
        if category not in _ARTICLE_BASE_CATEGORIES:
            issues.append(
                f"article base source category must be an article-quality source class, got {category or 'unknown'}"
            )
        if category in _SUPPORTING_ONLY_CATEGORIES:
            issues.append(f"{category} can only be supportingEvidence for article lane")
    if lane == "article":
        # RC4 红线：文章配图必须同源（来自文章底稿自身图片）。same_authorized_collection
        # 表示用"另一授权图集"的图当文章配图＝跨源替代，是九寨沟问题的根因之一，显式拒绝。
        # （图片作品 image lane 的图库一源一作品才允许 same_authorized_collection。）
        if str(source.get("imageEvidenceMode") or "").strip() == "same_authorized_collection":
            issues.append(
                "article lane must not use same_authorized_collection image evidence "
                "(article images must be same-source from the article's own base draft)"
            )
    if lane == "homepage" and category in {
        "encyclopedia",
        "overview_baike",
        "official",
        "official_site",
        "government",
    }:
        if not _homepage_candidate_has_fetch_evidence(source, url):
            issues.append(
                "homepage source must be registry-fetchable, verified retained source, "
                "or carry a text snapshot before entering source plan"
            )
    image_warnings: list[str] = []
    valid_images: list[dict[str, Any]] = []
    image_issues_block_source = lane == "image"
    for index, image in enumerate(source.get("imageUrls") or [], start=1):
        image_issues: list[str] = []
        if not isinstance(image, dict):
            image_issues.append(f"image[{index}] must be object")
            if image_issues_block_source:
                issues.extend(image_issues)
            else:
                image_warnings.extend(image_issues)
            continue
        missing = [
            field
            for field in ("url", "license", "termsUrl", "authorizationProof")
            if not str(image.get(field) or "").strip()
        ]
        if missing:
            image_issues.append(f"image[{index}] missing rights fields {missing}")
        elif not _license_allows_app_publish(
            str(image.get("license") or ""),
            str(image.get("termsUrl") or ""),
        ):
            image_issues.append(f"image[{index}]: imageRights unsupported license {image.get('license')}")
        if entity_id and not _image_mentions_entity(
            image,
            entity_id,
            entity_aliases=entity_aliases,
        ):
            image_issues.append(f"image[{index}] metadata does not strongly mention entity")
        if image_issues:
            if image_issues_block_source:
                issues.extend(image_issues)
            else:
                image_warnings.extend(image_issues)
        else:
            valid_images.append(image)
    if lane != "image" and "imageUrls" in source:
        if valid_images:
            source["imageUrls"] = valid_images
        else:
            source.pop("imageUrls", None)
            source["imageEvidenceMode"] = ""
    return {
        "passed": not issues,
        "issues": issues,
        "warnings": image_warnings,
        "category": category,
        "matchConfidence": confidence,
        "role": role,
    }

def _collection_image_spec(collection: Mapping[str, Any], image: Mapping[str, Any]) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for field in (
        "sourceCollectionId",
        "creator",
        "credit",
        "collectionPageUrl",
        "platform",
        "license",
        "termsUrl",
        "licenseSnapshot",
        "authorizationProof",
        "usageScope",
        "sourceUrl",
    ):
        value = image.get(field) or collection.get(field)
        if value not in ("", None):
            spec[field] = value
    for field in (
        "url",
        "caption",
        "relevance",
        "title",
        "width",
        "height",
        "modelReleaseRequired",
        "modelReleaseStatus",
        "generationModel",
        "generationPromptHash",
        "generatedAt",
        "syntheticDisclosure",
    ):
        value = image.get(field)
        if value not in ("", None):
            spec[field] = value
    if not spec.get("sourceUrl"):
        spec["sourceUrl"] = (
            spec.get("collectionPageUrl")
            or spec.get("authorizationProof")
            or spec.get("url")
            or ""
        )
    if not spec.get("credit") and spec.get("creator"):
        spec["credit"] = spec["creator"]
    if not spec.get("creator") and spec.get("credit"):
        spec["creator"] = spec["credit"]
    return spec

def _collection_publishable_image_urls(
    collections: list[dict[str, Any]],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    vertical: str = "travel",
) -> set[str]:
    urls: set[str] = set()
    for collection in collections:
        if not isinstance(collection, dict):
            continue
        verdict = _collection_gate(
            collection,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            vertical=vertical,
        )
        if not verdict["passed"]:
            continue
        for image in collection.get("images") or []:
            if not isinstance(image, dict):
                continue
            spec = _collection_image_spec(collection, image)
            url = str(spec.get("url") or "").strip()
            if not url:
                continue
            if validate_image_rights(spec, vertical=vertical):
                continue
            if not _license_allows_app_publish(
                str(spec.get("license") or ""),
                str(spec.get("termsUrl") or ""),
            ):
                continue
            if not _image_mentions_entity(spec, entity_id, entity_aliases=entity_aliases):
                continue
            urls.add(url)
    return urls

def _collection_gate(
    collection: dict[str, Any],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    allow_verified_collection_id_match: bool = False,
    vertical: str = "travel",
) -> dict[str, Any]:
    issues: list[str] = []
    collection_id = str(collection.get("sourceCollectionId") or "").strip()
    if not collection_id:
        issues.append("sourceCollectionId missing")
    verified_collection_entity_match = (
        allow_verified_collection_id_match
        and collection_id
        and _text_mentions_entity(collection_id, entity_id, entity_aliases=entity_aliases)
    )
    images = collection.get("images") if isinstance(collection.get("images"), list) else []
    if not images:
        issues.append("no rights-compatible images in collection")
    creators: set[str] = set()
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            issues.append(f"image[{index}] must be object")
            continue
        spec = _collection_image_spec(collection, image)
        creator = str(spec.get("creator") or spec.get("credit") or "").strip()
        if creator:
            creators.add(creator)
        missing = [
            field
            for field in (
                "url",
                "sourceCollectionId",
                "creator",
                "collectionPageUrl",
                "license",
                "termsUrl",
                "authorizationProof",
            )
            if not str(spec.get(field) or "").strip()
        ]
        if missing:
            issues.append(f"image[{index}] missing collection rights {missing}")
        rights_issues = validate_image_rights(spec, vertical=vertical)
        if rights_issues:
            issues.extend(f"image[{index}]: {issue}" for issue in rights_issues)
        elif not _license_allows_app_publish(
            str(spec.get("license") or ""),
            str(spec.get("termsUrl") or ""),
        ):
            issues.append(f"image[{index}]: imageRights unsupported license {spec.get('license')}")
        pixel_issue = _image_pixel_issue(spec)
        if pixel_issue:
            issues.append(f"image[{index}]: {pixel_issue}")
        if (
            entity_id
            and not verified_collection_entity_match
            and not _image_mentions_entity(
                spec,
                entity_id,
                entity_aliases=entity_aliases,
            )
        ):
            issues.append(f"image[{index}] relevance does not strongly mention entity")
    if len(creators) > 1:
        issues.append("image work collection cannot mix multiple creators")
    return {"passed": not issues, "issues": issues}

def _article_base_candidate_limit(required_article_bases: int) -> int:
    """Fetch quota plus enough buffer for text/image/rights/dedupe attrition.

    Four article objects usually need substantially more than four discovered
    candidates because short travel notes, missing source assets and one-asset
    one-use rules are filtered later by download/content gates.
    """
    required = max(1, int(required_article_bases or 1))
    if required <= 2:
        reserve = max(2, required)
    else:
        reserve = min(max(12, math.ceil(required * 2.5)), 24)
    return min(required + reserve, 32)

def _select_article_plan_sources(
    sources: list[dict[str, Any]],
    *,
    required_article_bases: int,
    max_sources: int = 0,
) -> list[dict[str, Any]]:
    """Keep base-source redundancy without crowding out supporting categories."""
    required = max(1, int(required_article_bases or 1))
    bases = [source for source in sources if source.get("sourceRole") == "base"]
    supporting = [source for source in sources if source.get("sourceRole") != "base"]
    base_keep = min(len(bases), _article_base_candidate_limit(required))
    max_rows = max(base_keep + 3, required + 4)
    if int(max_sources or 0) > 0:
        max_rows = max(required + 3, min(max_rows, int(max_sources)))
        base_keep = min(base_keep, max(required, max_rows - 3))
    selected: list[dict[str, Any]] = list(bases[:base_keep])
    seen_ids = {str(source.get("source_id") or "") for source in selected}
    categories = {str(source.get("category") or "") for source in selected if source.get("category")}

    for source in supporting:
        category = str(source.get("category") or "")
        source_id = str(source.get("source_id") or "")
        if source_id in seen_ids:
            continue
        if category and category not in categories:
            selected.append(source)
            seen_ids.add(source_id)
            categories.add(category)
        if len(categories) >= 3:
            break

    for source in [*supporting, *bases[base_keep:]]:
        source_id = str(source.get("source_id") or "")
        if source_id in seen_ids:
            continue
        selected.append(source)
        seen_ids.add(source_id)
        if len(selected) >= max_rows:
            break
    return selected[:max_rows]
