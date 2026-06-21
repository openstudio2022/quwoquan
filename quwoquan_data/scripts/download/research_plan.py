"""Deterministic public-source research plan bootstrap.

This fills the source/research lane with auditable public sources before a
semantic Agent is needed. It is intentionally conservative: it writes only
empty lane plans unless --force is passed, and it leaves explicit gaps when a
source cannot be discovered from registered public endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import subprocess
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from _common.io import read_json, write_json
from _common.image_asset_strategy import (
    image_count_is_hard_quota,
    image_count_policy,
    image_asset_strategy,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
)
from _common.paths import STAGE_DOWNLOAD, batch_root, relative_batch_ref
from _common.source_catalog import platform_category, vertical_from_task_id
from _common.source_plan_contract import source_plan_rule_signature
from _common.source_unit import resolve_entity_object_dir
from download.prepare import prepare_source_plan
from vertical.license import validate_image_rights

_USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
_AUTO_DISCOVERY_REPORT = "auto_research_plan.json"
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
_OPENVERSE_API = "https://api.openverse.org/v1/images/"
_QUNAR_SEARCH_API = "https://touch.travel.qunar.com/search"
_TRAVEL_SOURCE_REGISTRY = Path(__file__).resolve().parents[2] / "verticals" / "travel" / "sources" / "source_registry.yaml"
_HOMEPAGE_CORE_SOURCE_LIMIT = 5
_AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = max(
    3,
    int(os.environ.get("QWQ_AUTO_RESEARCH_CURL_TIMEOUT_SECONDS", "25")),
)
_AUTO_RESEARCH_CURL_RETRIES = max(
    1,
    int(os.environ.get("QWQ_AUTO_RESEARCH_CURL_RETRIES", "1")),
)
_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT = max(
    1,
    int(os.environ.get("QWQ_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT", "8")),
)
_VERIFIED_IMAGE_PLAN_SCAN_LIMIT = max(
    0,
    int(os.environ.get("QWQ_VERIFIED_IMAGE_PLAN_SCAN_LIMIT", "80")),
)
_MAX_PUBLISHABLE_IMAGE_PIXELS = max(
    1_000_000,
    int(os.environ.get("QWQ_MAX_PUBLISHABLE_IMAGE_PIXELS", "80000000")),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_auto_research_progress(
    task_id: str,
    batch_id: str,
    *,
    status: str,
    entity_count: int,
    completed_count: int = 0,
    entity_id: str = "",
    workers: int = 1,
    started_monotonic: float | None = None,
    message: str = "",
) -> dict[str, Any]:
    elapsed = max(time.monotonic() - started_monotonic, 0.001) if started_monotonic else 0.0
    progress = {
        "schemaVersion": "quwoquan.download.auto_research_progress",
        "updatedAt": _now_iso(),
        "status": status,
        "entityId": entity_id,
        "entityCount": entity_count,
        "completedCount": completed_count,
        "remainingCount": max(entity_count - completed_count, 0),
        "workers": workers,
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(completed_count / elapsed * 60.0, 3) if elapsed > 0 else 0.0,
        "message": message,
    }
    shared = batch_root(task_id, batch_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(shared / "auto_research_progress.json", progress)
    return progress


def _curl_json(url: str, *, timeout: int = 25) -> dict[str, Any]:
    effective_timeout = max(3, int(timeout or _AUTO_RESEARCH_CURL_TIMEOUT_SECONDS))
    effective_retries = max(1, int(_AUTO_RESEARCH_CURL_RETRIES))
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", str(effective_retries), "--retry-delay", "1", "--retry-all-errors",
            "--max-time", str(effective_timeout),
            url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    stdout = proc.stdout.decode("utf-8", errors="replace") if isinstance(proc.stdout, bytes) else str(proc.stdout or "")
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return _curl_json(f"https://{host}/w/api.php?{query}")


def _normalized_title(value: str) -> str:
    return re.sub(r"[\s_（）()《》〈〉·•,，。:：;；-]+", "", str(value or "")).lower()


def _dedupe_terms(values: list[str] | tuple[str, ...], *, limit: int = 12) -> list[str]:
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = _normalized_title(value)
        if not key or any(_normalized_title(existing) == key for existing in out):
            continue
        out.append(value)
        if len(out) >= limit:
            break
    return out


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


_EN_ALIAS_SUFFIX_RE = re.compile(
    r"\b(?:scenic\s+area|scenic\s+zone|tourist\s+area|tourist\s+zone|national\s+park|"
    r"national\s+geopark|geo\s+park|geopark|mountains?|park|area|reserve)\b.*$",
    re.I,
)


def _expanded_entity_aliases(values: list[str] | tuple[str, ...], *, limit: int = 24) -> list[str]:
    expanded: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        expanded.append(value)
        if re.search(r"[A-Za-z]", value):
            stripped = _EN_ALIAS_SUFFIX_RE.sub("", value).strip(" ,;:-()")
            if stripped and stripped != value and len(_normalized_title(stripped)) >= 4:
                expanded.append(stripped)
    return _dedupe_terms(expanded, limit=limit)


def _entity_name_variants(entity_id: str) -> list[str]:
    """Conservative aliases for official scenic-area names.

    National scenic-area names often carry administrative prefixes, suffixes,
    or multiple sub-sites. Discovery should search those names, while the later
    candidate and asset gates still enforce entity relevance and rights.
    """
    raw = str(entity_id or "").strip()
    if not raw:
        return []
    variants: list[str] = [raw]
    cleaned = re.sub(r"[（(].*?[）)]", "", raw).strip()
    if cleaned and cleaned != raw:
        variants.append(cleaned)
    suffixes = (
        "旅游度假区",
        "文化旅游区",
        "风景名胜区",
        "风景旅游区",
        "旅游景区",
        "风景区",
        "景区",
        "公园",
        "旅游区",
    )
    for base in list(variants):
        for suffix in suffixes:
            if base.endswith(suffix) and len(base) > len(suffix) + 1:
                stripped = base[: -len(suffix)].strip(" -—－·")
                if stripped:
                    variants.append(stripped)
    split_pattern = r"[—－–\-、,，/]|及周围|及|·"
    for base in list(variants):
        for part in re.split(split_pattern, base):
            part = part.strip(" -—－·")
            if len(_normalized_title(part)) >= 3:
                variants.append(part)
    admin_prefix = re.match(r"^([\u4e00-\u9fa5]{2,8}(?:市|区|县|旗|州|盟))(.{3,})$", cleaned)
    if admin_prefix:
        variants.append(admin_prefix.group(2).strip())
    return _expanded_entity_aliases(variants, limit=12)


def _title_matches_entity(title: str, entity_id: str) -> bool:
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    if title_key == entity_key:
        return True
    if entity_key in title_key:
        return True
    return title_key in entity_key and len(title_key) >= max(3, round(len(entity_key) * 0.75))


_WIKI_TITLE_ALLOWED_SUFFIXES = (
    "旅游景区",
    "景区",
    "风景区",
    "风景名胜区",
    "国家级风景名胜区",
    "国家公园",
    "自然保护区",
    "保护区",
    "森林公园",
    "地质公园",
    "公园",
    "古城",
    "古镇",
)
_WIKI_TITLE_BLOCKED_SUBSTITUTES = (
    "机场",
    "车站",
    "火车站",
    "高铁站",
    "客运站",
    "镇",
    "乡",
    "村",
    "街道",
    "县",
    "市",
    "区",
    "学校",
    "大学",
    "公司",
)
_WIKI_TITLE_ALLOWED_ALIAS_EXACT_2CHAR = {
    "太湖",
    "西湖",
    "泰山",
    "华山",
    "黄山",
    "嵩山",
    "衡山",
    "恒山",
    "庐山",
    "崂山",
}


def _wiki_title_matches_entity(title: str, entity_id: str) -> bool:
    """百科页标题必须是实体本身或景区类同义扩展，不能是机场/镇/城市替代页。"""
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    if title_key == entity_key:
        return True
    if title_key.startswith(entity_key):
        suffix = title_key[len(entity_key):]
        allowed = {_normalized_title(item) for item in _WIKI_TITLE_ALLOWED_SUFFIXES}
        if suffix in allowed:
            return True
        if any(marker in suffix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES):
            return False
        return False
    if title_key.endswith(entity_key):
        prefix = title_key[: -len(entity_key)]
        return 0 < len(prefix) <= 4 and not any(
            marker in prefix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES
        )
    return False


def _wiki_resolved_title_matches_entity(
    title: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    """Validate a resolved wiki title against the canonical entity.

    Short aliases are useful for discovery, but homepage resolution must not let
    generic aliases drift to another object, for example 北京奥林匹克公园 -> 悉尼奥林匹克公园.
    """
    if _wiki_title_matches_entity(title, entity_id):
        return True
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    allowed_suffixes = {_normalized_title(item) for item in _WIKI_TITLE_ALLOWED_SUFFIXES}
    allowed_suffixes.update({"遗址", "遺址", "故里", "古镇", "古鎮", "湿地", "濕地"})
    for alias in entity_aliases:
        alias_key = _normalized_title(alias)
        if not alias_key or alias_key == entity_key or alias_key not in entity_key:
            continue
        if len(alias_key) < 3 and alias_key not in _WIKI_TITLE_ALLOWED_ALIAS_EXACT_2CHAR:
            continue
        if title_key == alias_key:
            return True
        if title_key.startswith(alias_key):
            suffix = title_key[len(alias_key):]
            if suffix in allowed_suffixes:
                return True
            if any(marker in suffix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES):
                return False
    return False


def _text_mentions_entity(
    value: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    text = urllib.parse.unquote(str(value or ""))
    text = re.sub(r"[_/\\\-]+", " ", text)
    if _title_matches_entity(text, entity_id):
        return True
    text_key = _normalized_title(text)
    for alias in entity_aliases:
        alias_key = _normalized_title(alias)
        if alias_key and (alias_key in text_key or _title_matches_entity(text, alias)):
            return True
    return False


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


def _wiki_title(host: str, entity_id: str) -> str:
    def _usable_title(title: str) -> str:
        if not title or not _wiki_title_matches_entity(title, entity_id):
            return ""
        extract = _wiki_api(
            host,
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": "1",
                "format": "json",
            },
        )
        pages = (extract.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            extract_text = str(page.get("extract") or "").strip()
            if extract_text and not _homepage_text_quality_issue(
                extract_text,
                entity_id,
                require_fact_ready=False,
            ):
                return str(page.get("title") or title)
        return ""

    exact = _wiki_api(host, {"action": "query", "titles": entity_id, "format": "json"})
    pages = (exact.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict) and int(page.get("pageid") or -1) > 0:
            title = str(page.get("title") or entity_id)
            usable = _usable_title(title)
            if usable:
                return usable
    search = _wiki_api(
        host,
        {
            "action": "query",
            "list": "search",
            "srsearch": entity_id,
            "srlimit": 5,
            "format": "json",
        },
    )
    rows = ((search.get("query") or {}).get("search") or [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        usable = _usable_title(title)
        if usable:
            return usable
    return ""


def _wiki_title_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 10,
) -> str:
    """Resolve an entity wiki title through canonical name, short names and aliases."""
    terms = _dedupe_terms(
        [*_entity_name_variants(entity_id), *entity_aliases],
        limit=limit,
    )
    validation_aliases = _dedupe_terms([*terms, *entity_aliases], limit=limit + len(entity_aliases))
    for term in terms:
        title = _wiki_title(host, term)
        if not title:
            continue
        if _wiki_resolved_title_matches_entity(
            title,
            entity_id,
            entity_aliases=validation_aliases,
        ):
            return title
    return ""


def _wiki_related_titles_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 3,
) -> list[str]:
    """Resolve related wiki pages through aliases while preserving entity grounding."""
    found: list[str] = []
    seen: set[str] = set()
    terms = _dedupe_terms(
        [*_entity_name_variants(entity_id), *entity_aliases],
        limit=max(limit * 2, 8),
    )
    for term in terms:
        for title in _wiki_related_titles(host, term, limit=limit):
            key = _normalized_title(title)
            if not key or key in seen:
                continue
            if not (
                _text_mentions_entity(title, entity_id, entity_aliases=entity_aliases)
                or _text_mentions_entity(title, term, entity_aliases=entity_aliases)
            ):
                continue
            seen.add(key)
            found.append(title)
            if len(found) >= limit:
                return found
    return found


_RELATED_WIKI_SUFFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("博物馆", ("遗址", "文化遗址", "")),
    ("纪念馆", ("故居", "旧址", "")),
)


def _wiki_related_titles(host: str, entity_id: str, *, limit: int = 3) -> list[str]:
    """Find tightly related wiki pages for supporting evidence only.

    Some visitor-facing entities (for example a museum built around an
    archaeological site) have no exact wiki page while the underlying cultural
    object has one. These pages are useful for factual context, but must never
    replace the entity homepage or become article base drafts.
    """
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return []
    stems: list[str] = []
    for suffix, related_suffixes in _RELATED_WIKI_SUFFIXES:
        if entity_id.endswith(suffix) and len(entity_id) > len(suffix):
            stem = entity_id[: -len(suffix)]
            stems.extend(stem + item for item in related_suffixes)
    if not stems:
        return []
    data = _wiki_api(
        host,
        {
            "action": "query",
            "list": "search",
            "srsearch": entity_id,
            "srlimit": 10,
            "format": "json",
        },
    )
    rows = ((data.get("query") or {}).get("search") or [])
    wanted = {_normalized_title(item) for item in stems if item.strip()}
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        title_key = _normalized_title(title)
        if not title or title_key in seen:
            continue
        if title_key not in wanted:
            continue
        extract = _wiki_api(
            host,
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": "1",
                "format": "json",
            },
        )
        pages = (extract.get("query") or {}).get("pages") or {}
        if not any(
            isinstance(page, dict) and str(page.get("extract") or "").strip()
            for page in pages.values()
        ):
            continue
        seen.add(title_key)
        found.append(title)
        if len(found) >= limit:
            break
    return found


def _wiki_url(host: str, title: str) -> str:
    if not title:
        return ""
    return f"https://{host}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _wikidata_item_for_zhwiki(title: str) -> str:
    data = _wiki_api("zh.wikipedia.org", {
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "format": "json",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict):
            qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
            if qid:
                return qid
    return ""


def _wikidata_item_for_entity_search(entity_id: str) -> str:
    """Return a strongly matching Wikidata QID without relying on zhwiki.

    Some Chinese scenic areas do not have a zhwiki page but do have a Wikidata
    item with Commons media. We only accept exact/strong label or alias matches;
    weak city/province substitutes stay out of the plan.
    """
    if not entity_id:
        return ""
    for term in _dedupe_terms(_entity_name_variants(entity_id), limit=5):
        data = _curl_json(
            "https://www.wikidata.org/w/api.php?"
            + urllib.parse.urlencode(
                {
                    "action": "wbsearchentities",
                    "search": term,
                    "language": "zh",
                    "uselang": "zh",
                    "limit": 5,
                    "format": "json",
                }
            ),
            timeout=20,
        )
        rows = data.get("search") if isinstance(data.get("search"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            labels = [str(row.get("label") or ""), str(row.get("match", {}).get("text") or "")]
            aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
            labels.extend(str(item) for item in aliases)
            if any(
                _title_matches_entity(label, entity_id)
                or _title_matches_entity(label, term)
                for label in labels
                if label
            ):
                qid = str(row.get("id") or "")
                if qid.startswith("Q"):
                    return qid
    return ""


def _wikidata_claims(qid: str) -> dict[str, Any]:
    if not qid:
        return {}
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            }
        ),
        timeout=20,
    )
    entity = ((data.get("entities") or {}).get(qid) or {})
    claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
    return claims if isinstance(claims, dict) else {}


def _wikidata_entity_aliases(qid: str) -> list[str]:
    if not qid:
        return []
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|aliases",
                "languages": "zh|zh-hans|zh-hant|en",
                "format": "json",
            }
        ),
        timeout=20,
    )
    entity = ((data.get("entities") or {}).get(qid) or {})
    values: list[str] = []
    for bucket_name in ("labels", "aliases"):
        bucket = entity.get(bucket_name) if isinstance(entity.get(bucket_name), dict) else {}
        for rows in bucket.values():
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    value = str(row.get("value") or "").strip()
                    if value and value not in values:
                        values.append(value)
    return values


def _claim_string_values(claims: dict[str, Any], pid: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(pid) or []:
        if not isinstance(claim, dict):
            continue
        shutdown_wait = True
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _official_website(qid: str) -> str:
    if not qid:
        return ""
    for value in _claim_string_values(_wikidata_claims(qid), "P856"):
        if value.startswith(("http://", "https://")):
            return value
    return ""


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


_TRUSTED_EXTERNAL_DOMAINS: tuple[str, ...] = (
    "gov.cn",
    "people.com.cn",
    "news.cn",
    "xinhuanet.com",
    "chinanews.com",
    "cctv.com",
    "gmw.cn",
    "scol.com.cn",
    "newssc.org",
    "whc.unesco.org",
    "mnr.gov.cn",
    "dujiangyan.com.cn",
    "yading.cn",
    "yadingtour.com",
    "sxd.cn",
    "ctrip.com",
    "trip.com",
    "mafengwo.cn",
    "mafengwo.com",
    "qyer.com",
    "tripadvisor.cn",
    "tripadvisor.com",
    "lonelyplanet.com",
    "nationalgeographic.com",
)


def _trusted_external_links(title: str, *, limit: int = 4) -> list[str]:
    if not title:
        return []
    data = _wiki_api(
        "zh.wikipedia.org",
        {
            "action": "query",
            "titles": title,
            "prop": "extlinks",
            "ellimit": 50,
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    links: list[str] = []
    seen: set[str] = set()
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        for row in page.get("extlinks") or []:
            raw = str(row.get("*") or row.get("url") or "").strip()
            if not raw or raw in seen:
                continue
            parsed = urllib.parse.urlparse(raw)
            host = (parsed.hostname or "").lower()
            if not parsed.scheme.startswith("http"):
                continue
            if "web.archive.org" in host or "google." in host or "toolforge.org" in host:
                continue
            if any(host == domain or host.endswith(f".{domain}") for domain in _TRUSTED_EXTERNAL_DOMAINS):
                seen.add(raw)
                links.append(raw)
            if len(links) >= limit:
                return links
    return links


def _external_platform(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if "ctrip.com" in host or "trip.com" in host:
        return "携程攻略"
    if "mafengwo." in host:
        return "马蜂窝"
    if "qyer.com" in host:
        return "穷游"
    if "tripadvisor." in host:
        return "Tripadvisor"
    if "lonelyplanet.com" in host:
        return "Lonely Planet"
    if "nationalgeographic.com" in host:
        return "National Geographic"
    if "people.com.cn" in host:
        return "人民网"
    if "news.cn" in host or "xinhuanet.com" in host:
        return "新华网"
    if "chinanews.com" in host:
        return "中国新闻网"
    if "cctv.com" in host:
        return "央视网"
    if "gmw.cn" in host:
        return "光明网"
    if "whc.unesco.org" in host:
        return "UNESCO"
    if host.endswith("gov.cn") or host.endswith("mnr.gov.cn"):
        return "文旅局"
    if "dujiangyan.com.cn" in host or "yading" in host:
        return "景区官网"
    return "权威媒体"


def _url_looks_like_article(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "").lower()
    if not path or path in {"/", ""}:
        return False
    basename = path.rsplit("/", 1)[-1]
    if basename in {"index.html", "index.htm", "default.html", "default.htm"}:
        return False
    article_patterns = (
        r"/n\d+/\d{4}/\d{4}/",
        r"/\d{4}/\d{2}/\d{2}/",
        r"/\d{4}-\d{2}/\d{2}/",
        r"/c_\d+",
        r"/arti[a-z0-9]+",
        r"userobject\d+ai\d+",
    )
    if any(re.search(pattern, path) for pattern in article_patterns):
        return True
    return bool(re.search(r"\.(shtml|html|htm)$", path) and re.search(r"\d{4,}", path))


def _external_article_category(url: str, platform: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    platform_text = platform.casefold()
    if any(marker in host for marker in ("ctrip.com", "trip.com", "mafengwo.", "qyer.com", "tripadvisor.")):
        return "travelogue"
    if "lonelyplanet.com" in host or "nationalgeographic.com" in host or "whc.unesco.org" in host:
        return "vertical_professional"
    if host.endswith("gov.cn") or host.endswith("mnr.gov.cn") or platform in {"文旅局", "景区官网"}:
        return "official_article" if _url_looks_like_article(url) else "official"
    if any(marker in host for marker in ("people.com.cn", "news.cn", "xinhuanet.com", "chinanews.com", "cctv.com", "gmw.cn")):
        return "media_article" if _url_looks_like_article(url) else "authoritative_reference"
    if any(marker in platform_text for marker in ("人民网", "新华", "中国新闻网", "央视", "光明", "media")):
        return "media_article" if _url_looks_like_article(url) else "authoritative_reference"
    return "authoritative_reference"


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


_HOMEPAGE_PRIMARY_SOURCE_MARKERS = (
    "维基百科",
    "wikipedia",
    "百度百科",
    "搜狗百科",
    "字节百科",
    "百科",
    "景区官网",
    "官网",
    "官方",
)
_HOMEPAGE_SUPPORT_ONLY_SOURCE_MARKERS = ("政府", "文旅", "政务", "gov.cn", "权威媒体", "媒体")
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
    if category in {"encyclopedia", "official_site"}:
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


def _image_search_terms(
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    *,
    limit: int = 4,
) -> list[str]:
    return _dedupe_terms([*_entity_name_variants(entity_id), *entity_aliases], limit=limit)


def _commons_images(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in _image_search_terms(entity_id, entity_aliases, limit=4):
        data = _wiki_api(
            "commons.wikimedia.org",
            {
                "action": "query",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": term,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "format": "json",
            },
        )
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            info = ((page.get("imageinfo") or [{}])[0] or {})
            url = str(info.get("url") or "")
            if not url or url in seen:
                continue
            if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
                continue
            meta = info.get("extmetadata") or {}
            license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
            license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
            if not license_url or not _license_allows_app_publish(license_name, license_url):
                continue
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            if width < 640 or height < 426 or max(width, height) < 800:
                continue
            if _image_pixel_issue({"width": width, "height": height}):
                continue
            credit = _strip_html(
                ((meta.get("Artist") or {}).get("value") or "")
                or ((meta.get("Credit") or {}).get("value") or "")
                or "Wikimedia Commons contributor"
            )
            description = _strip_html(
                ((meta.get("ImageDescription") or {}).get("value") or "")
                or str(page.get("title") or "")
            )
            source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
            if entity_id and not _text_mentions_entity(
                f"{description} {page.get('title') or ''} {source_url}",
                entity_id,
                entity_aliases=entity_aliases,
            ):
                continue
            seen.add(url)
            images.append(
                {
                    "url": url,
                    "platform": "Wikimedia Commons",
                    "license": license_name,
                    "credit": credit,
                    "sourceUrl": source_url,
                    "termsUrl": license_url,
                    "licenseSnapshot": f"{license_name} recorded on Wikimedia Commons file page",
                    "authorizationProof": source_url,
                    "usageScope": "app_publish",
                    "width": width,
                    "height": height,
                    "caption": description[:120] or f"{entity_id} Wikimedia Commons image",
                    "relevance": description[:120] or source_url,
                    "creator": credit,
                    "collectionPageUrl": source_url,
                }
            )
            if len(images) >= limit:
                return images
    return images


def _commons_images_for_titles(
    titles: list[str],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
    collection_page_url: str = "",
) -> list[dict[str, Any]]:
    normalized: list[str] = []
    seen_titles: set[str] = set()
    for title in titles:
        name = str(title or "").strip()
        if not name:
            continue
        if not name.startswith(("File:", "文件:")):
            name = f"File:{name}"
        if name in seen_titles:
            continue
        seen_titles.add(name)
        normalized.append(name)
        if len(normalized) >= 50:
            break
    if not normalized:
        return []
    data = _wiki_api(
        "commons.wikimedia.org",
        {
            "action": "query",
            "titles": "|".join(normalized),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info = ((page.get("imageinfo") or [{}])[0] or {})
        url = str(info.get("url") or "")
        if not url or url in seen_urls:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
        license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
        if not _license_allows_app_publish(license_name, license_url):
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 640 or height < 426 or max(width, height) < 800:
            continue
        if _image_pixel_issue({"width": width, "height": height}):
            continue
        description = _strip_html(
            ((meta.get("ImageDescription") or {}).get("value") or "")
            or str(page.get("title") or "")
        )
        if entity_id and not _text_mentions_entity(
            description,
            entity_id,
            entity_aliases=entity_aliases,
        ):
            # Category/P18 hits can be generic locator maps or logos; keep only
            # strongly entity-related image metadata for production lanes.
            continue
        seen_urls.add(url)
        credit = _strip_html(
            ((meta.get("Artist") or {}).get("value") or "")
            or ((meta.get("Credit") or {}).get("value") or "")
            or "Wikimedia Commons contributor"
        )
        source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
        images.append(
            {
                "url": url,
                "platform": "Wikimedia Commons",
                "license": license_name,
                "credit": credit,
                "sourceUrl": source_url,
                "termsUrl": license_url,
                "licenseSnapshot": f"{license_name} recorded on Wikimedia Commons file page",
                "authorizationProof": source_url,
                "usageScope": "app_publish",
                "width": width,
                "height": height,
                "caption": description[:120] or f"{entity_id} Wikimedia Commons image",
                "relevance": description[:120] or source_url,
                "creator": credit,
                "collectionPageUrl": collection_page_url or source_url,
            }
        )
        if len(images) >= limit:
            break
    return images


def _commons_category_images(
    category: str,
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> list[dict[str, Any]]:
    category = str(category or "").strip()
    if not category:
        return []
    title = category if category.startswith("Category:") else f"Category:{category}"
    data = _wiki_api(
        "commons.wikimedia.org",
        {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": title,
            "cmnamespace": 6,
            "cmtype": "file",
            "cmlimit": min(max(limit * 4, 8), 50),
            "format": "json",
        },
    )
    rows = ((data.get("query") or {}).get("categorymembers") or [])
    titles = [str(row.get("title") or "") for row in rows if isinstance(row, dict)]
    page_url = f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    return _commons_images_for_titles(
        titles,
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        limit=limit,
        collection_page_url=page_url,
    )


def _wikidata_commons_images(
    qid: str,
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> list[dict[str, Any]]:
    claims = _wikidata_claims(qid)
    titles = _claim_string_values(claims, "P18")
    images = _commons_images_for_titles(
        titles,
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        limit=limit,
    )
    if len(images) >= limit:
        return images[:limit]
    for category in _claim_string_values(claims, "P373"):
        for image in _commons_category_images(
            category,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            limit=limit,
        ):
            if all(str(image.get("url") or "") != str(existing.get("url") or "") for existing in images):
                images.append(image)
            if len(images) >= limit:
                return images[:limit]
    return images[:limit]


def _openverse_images(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Discover rights-compatible image candidates via Openverse.

    Openverse is a discovery index, so the source proof remains the original
    landing page plus the license URL. We reject NC/ND and undersized images
    here before a candidate can enter any source plan.
    """
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in _image_search_terms(entity_id, entity_aliases, limit=4):
        params = urllib.parse.urlencode({"q": term, "page_size": min(max(limit * 3, 5), 50)})
        data = _curl_json(f"{_OPENVERSE_API}?{params}", timeout=25)
        rows = data.get("results") if isinstance(data.get("results"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            landing = str(row.get("foreign_landing_url") or row.get("detail_url") or "").strip()
            license_slug = str(row.get("license") or "").strip()
            license_version = str(row.get("license_version") or "").strip()
            license_url = str(row.get("license_url") or "").strip()
            title = _strip_html(str(row.get("title") or ""))
            attribution = str(row.get("attribution") or "")
            if not url or url in seen or not landing:
                continue
            if not _license_allows_app_publish(license_slug, license_url):
                continue
            if bool(row.get("mature")):
                continue
            width = int(row.get("width") or 0)
            height = int(row.get("height") or 0)
            if width < 640 or height < 426 or max(width, height) < 800:
                continue
            if _image_pixel_issue({"width": width, "height": height}):
                continue
            if not _text_mentions_entity(
                f"{title} {attribution} {landing}",
                entity_id,
                entity_aliases=entity_aliases,
            ):
                continue
            creator = _strip_html(str(row.get("creator") or "")) or f"{row.get('provider') or 'Openverse'} contributor"
            provider = _strip_html(str(row.get("provider") or row.get("source") or "openverse"))
            license_name = f"CC {license_slug.upper()} {license_version}".strip()
            collection_id = f"openverse:{provider}:{row.get('id') or _normalized_title(url)[:24]}"
            seen.add(url)
            images.append(
                {
                    "url": url,
                    "platform": "Openverse",
                    "license": license_name,
                    "credit": creator,
                    "sourceUrl": landing,
                    "termsUrl": license_url,
                    "licenseSnapshot": (
                        f"{license_name} indexed by Openverse; verify on original landing page before publish"
                    ),
                    "authorizationProof": landing,
                    "usageScope": "app_publish",
                    "width": width,
                    "height": height,
                    "caption": title[:120] or f"{entity_id} Openverse image",
                    "relevance": title[:120] or landing,
                    "creator": creator,
                    "collectionPageUrl": landing,
                    "sourceCollectionId": collection_id,
                    "openverseId": str(row.get("id") or ""),
                    "openverseProvider": provider,
                }
            )
            if len(images) >= limit:
                return images
    return images


def _qunar_travelogue_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    authorized_images: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Discover fetchable Qunar travelogue pages for article text evidence."""
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    image_index = 0
    # Composite scenic areas often have official operation names while UGC uses
    # sub-site or short destination names. Keep enough alias budget to reach
    # curated registry aliases without lowering the downstream entity gate.
    search_terms = _dedupe_terms([*_entity_name_variants(entity_id), *entity_aliases], limit=8)
    match_terms = _dedupe_terms([entity_id, *search_terms, *entity_aliases], limit=12)
    for term in search_terms:
        for page in range(1, 3):
            encoded_q = urllib.parse.quote(term)
            data: dict[str, Any] = {}
            for attempt in range(2):
                for url in (
                    f"{_QUNAR_SEARCH_API}?_json&q={encoded_q}&page={page}",
                    f"{_QUNAR_SEARCH_API}?_json=&q={encoded_q}&page={page}",
                ):
                    data = _curl_json(url, timeout=20)
                    if data.get("ret") is True:
                        break
                if data.get("ret") is True:
                    break
                time.sleep(0.35 * (attempt + 1))
            payload = data.get("data") if isinstance(data.get("data"), dict) else {}
            rows = payload.get("bookList") if isinstance(payload.get("bookList"), list) else []
            if not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw_id = str(row.get("id") or "").strip()
                if not raw_id or raw_id in seen_ids:
                    continue
                title = _strip_html(str(row.get("title") or ""))
                route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
                city = _strip_html(str(row.get("cityName") or ""))
                route_hit = any(
                    _title_matches_entity(item, match_term)
                    for item in route
                    for match_term in match_terms
                )
                title_hit = any(_title_matches_entity(title, match_term) for match_term in match_terms)
                if not (title_hit or route_hit):
                    continue
                images = _image_window(authorized_images, image_index, count=1)
                if images:
                    image_index += 1
                seen_ids.add(raw_id)
                source = _source(
                    source_id=f"article_qunar_base_{len(sources) + 1}",
                    platform="去哪儿攻略",
                    url=f"https://touch.travel.qunar.com/youji/{raw_id}",
                    category="travelogue",
                    discovery_provider="qunar_touch_search_json",
                    match_confidence=0.94 if title_hit else 0.86,
                    evidence_reason=(
                        f"去哪儿攻略游记搜索命中 {entity_id}；query={term}; "
                        f"title={title[:60]} route={','.join(route[:6])} city={city}"
                    ),
                    source_role="base",
                    images=images,
                    image_evidence_mode="same_authorized_collection" if images else "",
                )
                source["title"] = title
                source["authorName"] = _strip_html(str(row.get("userName") or ""))
                source["routeDays"] = row.get("routeDays") or ""
                source["travelRoute"] = route[:20]
                source["viewCount"] = row.get("viewCount") or 0
                source["sourceUseMode"] = "factual_reference_only"
                sources.append(source)
                if len(sources) >= limit:
                    return sources
            if not payload.get("more"):
                break
    return sources


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


def _qunar_review_support_source(entity_id: str) -> dict[str, Any]:
    source = _source(
        source_id="article_qunar_review_support",
        platform="去哪儿景点点评",
        url=f"https://touch.travel.qunar.com/search?q={urllib.parse.quote(entity_id)}",
        category="review_note",
        discovery_provider="qunar_touch_search_page",
        match_confidence=0.86,
        evidence_reason=f"去哪儿搜索页提供 {entity_id} 景点标签、游记列表、热度与点评线索，可作多意图事实参考底稿",
        source_role="base",
    )
    source["category"] = "review_note"
    return source


def _mediawiki_page_images(
    host: str,
    title: str,
    *,
    entity_id: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return rights-compatible images transcluded by one exact MediaWiki page."""
    if not title:
        return []
    page_url = _wiki_url(host, title)
    page = _wiki_api(
        host,
        {
            "action": "query",
            "titles": title,
            "prop": "images",
            "imlimit": 40,
            "format": "json",
        },
    )
    pages = (page.get("query") or {}).get("pages") or {}
    filenames: list[str] = []
    for row in pages.values():
        if not isinstance(row, dict):
            continue
        for image in row.get("images") or []:
            name = str(image.get("title") or "")
            if name.startswith("File:") or name.startswith("文件:"):
                filenames.append(name)
            if len(filenames) >= limit * 3:
                break
    if not filenames:
        return []
    data = _wiki_api(
        host,
        {
            "action": "query",
            "titles": "|".join(filenames[:50]),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        },
    )
    info_pages = (data.get("query") or {}).get("pages") or {}
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in info_pages.values():
        if not isinstance(row, dict):
            continue
        info = ((row.get("imageinfo") or [{}])[0] or {})
        url = str(info.get("url") or "")
        if not url or url in seen:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
        license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
        if not license_name or not re.search(r"CC|Public domain|PD|自由|公有", license_name, re.I):
            continue
        if "igo" in license_name.lower() or not license_url:
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 640 or height < 426 or max(width, height) < 800:
            continue
        seen.add(url)
        credit = _strip_html(
            ((meta.get("Artist") or {}).get("value") or "")
            or ((meta.get("Credit") or {}).get("value") or "")
            or "Wikimedia contributor"
        )
        description = _strip_html(
            ((meta.get("ImageDescription") or {}).get("value") or "")
            or str(row.get("title") or "")
        )
        source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
        images.append(
            {
                "url": url,
                "platform": "维基导游" if "wikivoyage" in host else "维基百科",
                "license": license_name,
                "credit": credit,
                "sourceUrl": source_url,
                "termsUrl": license_url,
                "licenseSnapshot": f"{license_name} recorded on {host} file metadata",
                "authorizationProof": source_url,
                "usageScope": "app_publish",
                "width": width,
                "height": height,
                "caption": description[:120] or f"{entity_id} page image",
                "relevance": description[:120] or page_url,
                "creator": credit,
                "collectionPageUrl": page_url,
            }
        )
        if len(images) >= limit:
            break
    return images


def _safe_collection_id(prefix: str, entity_id: str, ref: str) -> str:
    raw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(ref or "").lower())[:60]
    raw = raw or _normalized_title(entity_id) or "source"
    digest = hashlib.sha1(str(ref or raw).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{entity_id}:{raw}:{digest}"


def _image_at(images: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    if not images:
        return None
    return dict(images[index % len(images)])


def _image_window(
    images: list[dict[str, Any]],
    index: int,
    *,
    count: int = 3,
) -> list[dict[str, Any]]:
    """Return a small deterministic candidate window for one source unit.

    A source image is part of an article/homepage draft. Giving the downloader
    multiple rights-cleared candidates keeps the lane resilient to a broken CDN
    object without mixing in unvetted or unrelated assets.
    """
    if not images or count <= 0:
        return []
    window: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset in range(min(count, len(images))):
        image = _image_at(images, index + offset)
        if not image:
            continue
        url = str(image.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        window.append(image)
    return window


def _source(
    *,
    source_id: str,
    platform: str,
    url: str,
    image: dict[str, Any] | None = None,
    images: list[dict[str, Any]] | None = None,
    category: str = "",
    discovery_provider: str = "",
    match_confidence: float = 0.0,
    evidence_reason: str = "",
    source_role: str = "supporting",
    image_evidence_mode: str = "",
    fetchable_override: bool | None = None,
) -> dict[str, Any]:
    source_category = _source_category(platform, category)
    row: dict[str, Any] = {
        "source_id": source_id,
        "platform": platform,
        "url": url,
        "sourceUseMode": "factual_reference_only",
        "category": source_category,
        "discoveryProvider": discovery_provider,
        "matchConfidence": round(float(match_confidence or 0.0), 3),
        "evidenceReason": evidence_reason,
        "sourceRole": source_role,
        "imageEvidenceMode": image_evidence_mode,
        "entityMatch": "strong" if match_confidence >= 0.72 else "weak",
    }
    if fetchable_override is True:
        row["fetchable"] = True
        row["fetchableOverride"] = True
    candidates: list[dict[str, Any]] = []
    if images:
        candidates.extend(dict(item) for item in images if isinstance(item, dict))
    if image:
        candidates.append(dict(image))
    if candidates:
        seen: set[str] = set()
        row["imageUrls"] = []
        for item in candidates:
            image_url = str(item.get("url") or "")
            if not image_url or image_url in seen:
                continue
            seen.add(image_url)
            row["imageUrls"].append(item)
    return row


def _accept_source(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any] | None:
    verdict = _candidate_gate(
        source,
        entity_id=entity_id,
        lane=lane,
        entity_aliases=entity_aliases,
    )
    source["candidateGate"] = verdict
    report.setdefault("candidates", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "source_id": source.get("source_id") or "",
            "platform": source.get("platform") or "",
            "url": source.get("url") or "",
            "category": verdict.get("category") or "",
            "discoveryProvider": source.get("discoveryProvider") or "",
            "matchConfidence": verdict.get("matchConfidence"),
            "evidenceReason": source.get("evidenceReason") or "",
            "passed": bool(verdict.get("passed")),
            "issues": list(verdict.get("issues") or []),
            "warnings": list(verdict.get("warnings") or []),
        }
    )
    return source if verdict["passed"] else None


def _reject_source_candidate(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    reason: str,
) -> None:
    verdict = {
        "passed": False,
        "issues": [reason],
        "warnings": [],
        "category": source.get("category") or "",
        "matchConfidence": source.get("matchConfidence") or 0,
        "role": source.get("sourceRole") or "supporting",
    }
    source["candidateGate"] = verdict
    report.setdefault("candidates", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "source_id": source.get("source_id") or "",
            "platform": source.get("platform") or "",
            "url": source.get("url") or "",
            "category": verdict.get("category") or "",
            "discoveryProvider": source.get("discoveryProvider") or "",
            "matchConfidence": verdict.get("matchConfidence"),
            "evidenceReason": source.get("evidenceReason") or "",
            "passed": False,
            "issues": [reason],
            "warnings": [],
        }
    )


def _accept_source_with_reject_memory(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_source_urls: set[str] | None = None,
) -> dict[str, Any] | None:
    url = str(source.get("url") or "").strip()
    if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
        if lane == "homepage" and _travel_registry_url_fetchable(url):
            return _accept_source(
                report,
                source,
                entity_id=entity_id,
                lane=lane,
                entity_aliases=entity_aliases,
            )
        _reject_source_candidate(
            report,
            source,
            entity_id=entity_id,
            lane=lane,
            reason="source URL previously rejected by download/source_screen gate",
        )
        return None
    return _accept_source(
        report,
        source,
        entity_id=entity_id,
        lane=lane,
        entity_aliases=entity_aliases,
    )


def _record_unavailable(
    report: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    reason: str,
    next_action: str = "manual_research_or_target_replacement",
) -> None:
    report.setdefault("sourceUnavailable", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "reason": reason,
            "nextAction": next_action,
        }
    )


def _source_unavailable_for_entity(
    report: Mapping[str, Any],
    *,
    entity_id: str,
    lane: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("entityId") or "") != entity_id:
            continue
        item_lane = str(item.get("lane") or "")
        if item_lane not in {lane, "all"}:
            continue
        rows.append(dict(item))
    return rows


def _task_spec(task_id: str) -> dict[str, Any]:
    try:
        from task import store

        return store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return {}


def _task_content_quotas(task_id: str) -> dict[str, int]:
    spec = _task_spec(task_id)
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    return {
        "entityArticlesPerTarget": max(0, int(quotas.get("entityArticlesPerTarget") or 0)),
        "imageWorksPerTarget": max(0, int(quotas.get("imageWorksPerTarget") or 0)),
        "entityHomepagesPerTarget": max(0, int(quotas.get("entityHomepagesPerTarget") or 0)),
    }


def _plan_has_payload(plan: dict[str, Any], lane: str) -> bool:
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    if lane == "image":
        return bool(payload.get("collections") or plan.get("collections"))
    return bool(payload.get("sources") or plan.get("sources"))


def _write_lane(path: Path, lane: str, payload_update: dict[str, Any], *, force: bool) -> bool:
    plan = read_json(path) if path.is_file() else {}
    if not force and _plan_has_payload(plan, lane):
        return False
    payload = dict(plan.get("payload") or {})
    payload.update(payload_update)
    plan["payload"] = payload
    task_id = str(plan.get("taskId") or "")
    entity_id = str(plan.get("ref") or payload.get("entityId") or "").strip()
    if task_id and entity_id:
        plan["sourceRuleSignature"] = source_plan_rule_signature(
            vertical_from_task_id(task_id),
            entity_id,
        )
    write_json(path, plan)
    return True


def _collections_from_image_plan(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        plan = read_json(path)
    except Exception:  # noqa: BLE001
        return []
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    rows = payload.get("collections") or plan.get("collections") or []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _url_memory_keys(url: str) -> set[str]:
    raw = str(url or "").strip()
    if not raw:
        return set()
    keys = {raw}
    try:
        unquoted = urllib.parse.unquote(raw)
    except Exception:  # noqa: BLE001
        unquoted = raw
    if unquoted:
        keys.add(unquoted)
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        normalized = urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                "",
                parsed.query,
                "",
            )
        )
        keys.add(normalized)
        try:
            keys.add(urllib.parse.unquote(normalized))
        except Exception:  # noqa: BLE001
            pass
    return {key for key in keys if key}


def _url_in_memory(url: str, memory: set[str]) -> bool:
    if not memory:
        return False
    return bool(_url_memory_keys(url) & memory)


def _add_url_memory(memory: set[str], url: str) -> None:
    memory.update(_url_memory_keys(url))


def _urls_from_issue_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://[^)\]\s\"']+", str(text or "")):
        url = match.group(0).rstrip("。；;,，")
        if url:
            urls.append(url)
    return urls


def _entity_download_dirs_for_history(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> list[Path]:
    root = batch_root(task_id, batch_id)
    task_batches_dir = root.parent
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    dirs: list[Path] = [
        root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD,
    ]
    if task_batches_dir.is_dir():
        batches = sorted(
            [path for path in task_batches_dir.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for batch_dir in batches[:_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT]:
            dl = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD
            if dl not in dirs:
                dirs.append(dl)
    return dirs


def _download_reject_memory(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> dict[str, set[str]]:
    """Return source/image URLs proven bad by prior fetch and screen gates.

    Source planning can reuse known-good pools, but it must also remember known
    bad URLs. Otherwise a repair loop keeps selecting pages/images that the
    deterministic fetch and source_screen stages have already rejected.
    """

    source_urls: set[str] = set()
    image_urls: set[str] = set()
    root = batch_root(task_id, batch_id)
    for dl in _entity_download_dirs_for_history(
        task_id,
        batch_id,
        entity_id,
        entity_type=entity_type,
    ):
        rejected_root = dl / "rejected_sources"
        if rejected_root.is_dir():
            for quality_path in sorted(rejected_root.glob("*/source.quality.json")):
                try:
                    quality = read_json(quality_path)
                except Exception:  # noqa: BLE001
                    continue
                try:
                    meta = read_json(quality_path.parent / "meta.json")
                except Exception:  # noqa: BLE001
                    meta = {}
                homepage_fetch_retry_blocked = (
                    str(meta.get("researchLane") or "") == "homepage"
                    and str(meta.get("platform") or "") in {"百度百科", "搜狗百科"}
                    and not bool(quality.get("fetchSucceeded"))
                    and int(quality.get("statusCode") or 0) == 0
                    and not _travel_registry_url_fetchable(str(quality.get("url") or ""))
                )
                if not (_source_reject_should_enter_memory(quality) or homepage_fetch_retry_blocked):
                    continue
                _add_url_memory(source_urls, str(quality.get("url") or ""))

    task_batches_dir = root.parent
    batch_dirs = [root]
    if task_batches_dir.is_dir():
        batch_dirs.extend(
            path for path in sorted(
                [p for p in task_batches_dir.iterdir() if p.is_dir()],
                key=lambda path: path.stat().st_mtime if path.exists() else 0,
                reverse=True,
            )[:_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT]
            if path != root
        )
    for batch_dir in batch_dirs:
        gate_path = (
            batch_dir
            / "task_download"
            / "results"
            / "image_fetch_gate"
            / f"{entity_id}.json"
        )
        if not gate_path.is_file():
            continue
        try:
            gate = read_json(gate_path)
        except Exception:  # noqa: BLE001
            continue
        payload = gate.get("payload") if isinstance(gate.get("payload"), dict) else gate
        evidence = payload.get("evidenceSummary") or payload.get("evidence_summary") or {}
        for item in evidence.get("rejectedForQuality") or []:
            text = str(item or "")
            hard_reject = any(
                marker in text
                for marker in (
                    "imageSafety",
                    "watermark",
                    "imagePixels",
                    "imageRelevance",
                    "unsupported license",
                    "missing image rights",
                    "rights",
                )
            )
            if not hard_reject:
                continue
            for url in _urls_from_issue_text(str(item)):
                _add_url_memory(image_urls, url)
    return {"sourceUrls": source_urls, "imageUrls": image_urls}


def _source_reject_should_enter_memory(quality: dict[str, Any]) -> bool:
    """Only hard source rejects enter planning memory.

    A network/policy soft failure has no page body and no quality reasons. If a
    registry policy or fetch strategy is fixed later, planning must be able to
    retry that URL instead of carrying a stale "bad source" forever.
    """

    if bool(quality.get("fetchSucceeded")):
        return True
    try:
        status_code = int(quality.get("statusCode") or 0)
    except (TypeError, ValueError):
        status_code = 0
    if status_code >= 400:
        return True
    reasons = quality.get("reasons") if isinstance(quality.get("reasons"), list) else []
    try:
        score = int(quality.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return bool(reasons) or score > 0


def _filter_rejected_images(
    images: list[dict[str, Any]],
    rejected_image_urls: set[str],
) -> list[dict[str, Any]]:
    if not rejected_image_urls:
        return images
    filtered: list[dict[str, Any]] = []
    for image in images:
        url = str(image.get("url") or "").strip()
        source_url = str(image.get("sourceUrl") or "").strip()
        proof = str(image.get("authorizationProof") or "").strip()
        if (
            _url_in_memory(url, rejected_image_urls)
            or _url_in_memory(source_url, rejected_image_urls)
            or _url_in_memory(proof, rejected_image_urls)
        ):
            continue
        filtered.append(image)
    return filtered


def _discover_open_license_image_pools(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...],
    qid: str,
    wiki_title: str,
    voyage_title: str,
    rejected_image_urls: set[str],
    commons_limit: int = 14,
    wikidata_limit: int = 14,
    openverse_limit: int = 16,
    page_limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Discover publishable open-license image candidates from primary pools."""

    image_hints = _known_image_search_hints(entity_id)
    image_aliases = _expanded_entity_aliases(
        [*entity_aliases, *image_hints["aliases"]],
        limit=max(24, len(entity_aliases) + len(image_hints["aliases"])),
    )
    commons = _filter_rejected_images(
        _commons_images(entity_id, entity_aliases=image_aliases, limit=commons_limit),
        rejected_image_urls,
    )
    wikidata_commons = _filter_rejected_images(
        _wikidata_commons_images(
            qid,
            entity_id=entity_id,
            entity_aliases=image_aliases,
            limit=wikidata_limit,
        ),
        rejected_image_urls,
    )
    openverse = _filter_rejected_images(
        _openverse_images(entity_id, entity_aliases=image_aliases, limit=openverse_limit),
        rejected_image_urls,
    )
    wiki_page_images = _filter_rejected_images(
        _mediawiki_page_images(
            "zh.wikipedia.org", wiki_title, entity_id=entity_id, limit=page_limit
        ),
        rejected_image_urls,
    )
    voyage_page_images = _filter_rejected_images(
        _mediawiki_page_images(
            "zh.wikivoyage.org", voyage_title, entity_id=entity_id, limit=page_limit
        ),
        rejected_image_urls,
    )
    hint_commons: list[dict[str, Any]] = []
    seen_hint_urls: set[str] = set()
    for category in image_hints["commonsCategories"]:
        for image in _commons_category_images(
            category,
            entity_id=entity_id,
            entity_aliases=image_aliases,
            limit=commons_limit,
        ):
            url = str(image.get("url") or "").strip()
            if not url or url in seen_hint_urls:
                continue
            seen_hint_urls.add(url)
            hint_commons.append(image)
            if len(hint_commons) >= commons_limit:
                break
        if len(hint_commons) >= commons_limit:
            break
    hint_commons = _filter_rejected_images(hint_commons, rejected_image_urls)
    return {
        "commons": commons,
        "hint_commons": hint_commons,
        "wikidata_commons": wikidata_commons,
        "openverse": openverse,
        "wiki_page_images": wiki_page_images,
        "voyage_page_images": voyage_page_images,
    }


def _normalize_collection_for_reuse(collection: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(collection)
    collection_id = str(normalized.get("sourceCollectionId") or "").strip()
    normalized_images: list[dict[str, Any]] = []
    for image in normalized.get("images") or []:
        if not isinstance(image, dict):
            continue
        item = dict(image)
        if collection_id and not item.get("sourceCollectionId"):
            item["sourceCollectionId"] = collection_id
        if normalized.get("creator") and not item.get("creator"):
            item["creator"] = normalized.get("creator")
        if normalized.get("collectionPageUrl") and not item.get("collectionPageUrl"):
            item["collectionPageUrl"] = normalized.get("collectionPageUrl")
        for field in ("license", "termsUrl", "authorizationProof", "licenseSnapshot", "usageScope"):
            if normalized.get(field) and not item.get(field):
                item[field] = normalized.get(field)
        normalized_images.append(item)
    normalized["images"] = normalized_images
    normalized["discoveryProvider"] = "verified_source_pool_reuse"
    return normalized


def _verified_image_collections_from_prior_plans(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_image_urls: set[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Reuse already verified image collections from the current task.

    External visual discovery is intentionally broad but can be unstable across
    retries. Reusing previous source plans keeps retries deterministic while
    still re-running the asset-level collection gate before publishability.
    """
    root = batch_root(task_id, batch_id)
    task_batches_dir = root.parent
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
    candidate_paths: list[Path] = [current]
    if task_batches_dir.is_dir():
        batches = sorted(
            [path for path in task_batches_dir.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for batch_dir in batches:
            plan = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
            if plan != current:
                candidate_paths.append(plan)
    tasks_root = next((parent for parent in root.parents if parent.name == "tasks"), None)
    if tasks_root and _VERIFIED_IMAGE_PLAN_SCAN_LIMIT:
        cross_task_plans = [
            path
            for path in tasks_root.glob(
                f"**/batches/*/entities/地点/{etype}/{entity_id}/{STAGE_DOWNLOAD}/image_source_plan.json"
            )
            if path != current and path not in candidate_paths
        ]
        cross_task_plans.sort(
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        candidate_paths.extend(cross_task_plans[:_VERIFIED_IMAGE_PLAN_SCAN_LIMIT])
    collections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidate_paths:
        for raw_collection in _collections_from_image_plan(path):
            collection = _normalize_collection_for_reuse(raw_collection)
            if rejected_image_urls:
                collection["images"] = _filter_rejected_images(
                    list(collection.get("images") or []),
                    rejected_image_urls,
                )
            collection_id = str(collection.get("sourceCollectionId") or "").strip()
            if not collection_id or collection_id in seen:
                continue
            verdict = _collection_gate(
                collection,
                entity_id=entity_id,
                entity_aliases=entity_aliases,
                allow_verified_collection_id_match=False,
            )
            if not verdict["passed"]:
                continue
            try:
                reuse_ref = path.relative_to(task_batches_dir.parent).as_posix()
            except ValueError:
                if tasks_root:
                    try:
                        reuse_ref = path.relative_to(tasks_root).as_posix()
                    except ValueError:
                        reuse_ref = path.as_posix()
                else:
                    reuse_ref = path.as_posix()
            collection["reuseSourcePlan"] = reuse_ref
            collections.append(collection)
            seen.add(collection_id)
            if len(collections) >= limit:
                return collections
    return collections


def _images_from_collections(collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        collection_id = str(collection.get("sourceCollectionId") or "").strip()
        for image in collection.get("images") or []:
            if not isinstance(image, dict):
                continue
            item = dict(image)
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if collection_id and not item.get("sourceCollectionId"):
                item["sourceCollectionId"] = collection_id
            seen.add(url)
            images.append(item)
    return images


def _sources_from_article_plan(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        plan = read_json(path)
    except Exception:  # noqa: BLE001
        return []
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    rows = payload.get("sources") or plan.get("sources") or []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _homepage_urls_from_current_plan(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> set[str]:
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    path = (
        batch_root(task_id, batch_id)
        / "entities"
        / "地点"
        / etype
        / entity_id
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    return {
        str(source.get("url") or "").strip()
        for source in _sources_from_article_plan(path)
        if str(source.get("url") or "").strip()
    }


def _verified_homepage_sources_from_source_units(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    rejected_source_urls: set[str] | None = None,
    limit: int = _HOMEPAGE_CORE_SOURCE_LIMIT,
) -> list[dict[str, Any]]:
    """Reuse homepage source units that already passed source_screen.

    Source repair should not discard a working wiki/official source while
    retrying a failed Baidu/Sogou candidate. This keeps the repair loop
    monotonic and prevents the planner from cycling over known-bad URLs.
    """
    from _common.source_unit import iter_source_units

    obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for unit in iter_source_units(obj):
        meta_path = unit / "meta.json"
        quality_path = unit / "source.quality.json"
        if not meta_path.is_file() or not quality_path.is_file():
            continue
        try:
            meta = read_json(meta_path)
            quality = read_json(quality_path)
        except Exception:  # noqa: BLE001
            continue
        if str(meta.get("researchLane") or "") != "homepage":
            continue
        if str(quality.get("quality") or "") == "Reject":
            continue
        text_path = unit / "source.clean.md"
        if not text_path.is_file():
            text_path = unit / "source.md"
        if not text_path.is_file():
            continue
        try:
            source_text = text_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        issue = _homepage_text_quality_issue(
            source_text,
            entity_id,
            require_fact_ready=True,
        )
        if issue:
            continue
        url = str(meta.get("url") or quality.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
            continue
        source_id = str(meta.get("sourceId") or unit.name.split(".", 1)[-1] or "home_verified").strip()
        platform = str(meta.get("platform") or meta.get("sourceKind") or "百科").strip()
        category = str(meta.get("category") or meta.get("sourceKind") or "").strip()
        sources.append(
            {
                "source_id": source_id,
                "platform": platform,
                "url": url,
                "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                "category": _source_category(platform, category),
                "discoveryProvider": "verified_homepage_source_unit_reuse",
                "matchConfidence": 0.97,
                "evidenceReason": f"reuse retained homepage source unit {unit.name}",
                "sourceRole": "primary" if not sources else "supporting",
                "imageEvidenceMode": "",
                "entityMatch": "strong",
                "reuseSourceUnit": relative_batch_ref(unit / "source.md", task_id, batch_id),
            }
        )
        seen_urls.add(url)
        if len(sources) >= limit:
            break
    return sources


def _verified_article_sources_from_prior_plans(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    rejected_source_urls: set[str] | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    root = batch_root(task_id, batch_id)
    task_batches_dir = root.parent
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
    candidate_paths: list[Path] = [current]
    if task_batches_dir.is_dir():
        batches = sorted(
            [path for path in task_batches_dir.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for batch_dir in batches:
            plan = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
            if plan != current:
                candidate_paths.append(plan)
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for path in candidate_paths:
        for raw_source in _sources_from_article_plan(path):
            url = str(raw_source.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
                continue
            gate = raw_source.get("candidateGate") if isinstance(raw_source.get("candidateGate"), dict) else {}
            if gate and gate.get("passed") is False:
                continue
            category = str(raw_source.get("category") or "").strip()
            source = dict(raw_source)
            original_id = str(source.get("source_id") or "article_source").strip()
            source["originalSourceId"] = original_id
            source["source_id"] = f"article_reused_{len(sources) + 1}_{_normalized_title(original_id)[:24]}"
            source["discoveryProvider"] = "verified_source_pool_reuse"
            source["reuseSourcePlan"] = str(path.relative_to(task_batches_dir.parent))
            if category in _ARTICLE_BASE_CATEGORIES and not source.get("sourceRole"):
                source["sourceRole"] = "base"
            if not source.get("matchConfidence"):
                source["matchConfidence"] = (gate.get("matchConfidence") if gate else 0.86) or 0.86
            sources.append(source)
            seen_urls.add(url)
            if len(sources) >= limit:
                return sources
    return sources


def _write_auto_research_plans_impl(
    task_id: str,
    batch_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    write_shared_report: bool = True,
) -> dict[str, Any]:
    selected_lanes = lanes or {"homepage", "article", "image"}
    vertical = vertical_from_task_id(task_id)
    entities = [
        {"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type}
        for entity_id in entity_ids
    ]
    prepare_source_plan(task_id, batch_id, entities)
    updated: list[dict[str, Any]] = []
    issues: list[str] = []
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": updated,
        "issues": issues,
        "candidates": [],
        "imageCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }
    quotas = _task_content_quotas(task_id)
    strategy_spec = _task_spec(task_id)
    image_strategy = image_asset_strategy(strategy_spec)
    image_policy = image_count_policy(strategy_spec)
    requires_publishable_images = image_strategy_requires_publishable_images(strategy_spec)
    report["imageAssetStrategy"] = image_strategy
    report["imageCountPolicy"] = image_policy
    report["imagePublishableAssetsRequired"] = requires_publishable_images
    required_article_bases = max(1, quotas["entityArticlesPerTarget"] or 1)
    desired_image_works = max(0, quotas["imageWorksPerTarget"] or 0)
    image_bonus_saturation_count = max(1, desired_image_works)
    hard_image_works = (
        image_bonus_saturation_count
        if image_count_is_hard_quota(strategy_spec)
        else minimum_publishable_images_per_target(strategy_spec)
    )
    try:
        from download.gate import download_requirements

        required_publishable_images = max(
            hard_image_works,
            int(download_requirements(task_id).get("minImages") or 0),
        )
    except Exception:  # noqa: BLE001
        required_publishable_images = hard_image_works
    report["scoringPolicy"] = {
        "imageCountPolicy": image_policy,
        "imageBonusSaturationCount": image_bonus_saturation_count,
        "minimumPublishableImagesPerTarget": hard_image_works,
        "articleLengthPassChars": 600,
    }
    for entity_id in entity_ids:
        obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
        dl = obj / STAGE_DOWNLOAD
        initial_aliases = _entity_name_variants(entity_id)
        wiki_title = _wiki_title_for_entity(
            "zh.wikipedia.org",
            entity_id,
            entity_aliases=initial_aliases,
        )
        qid = _wikidata_item_for_zhwiki(wiki_title) or _wikidata_item_for_entity_search(entity_id)
        entity_aliases = _expanded_entity_aliases(
            [
                *_entity_name_variants(entity_id),
                *_known_entity_aliases(entity_id),
                wiki_title,
                *_wikidata_entity_aliases(qid),
            ],
            limit=24,
        )
        if not wiki_title:
            wiki_title = _wiki_title_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
        related_wiki_titles = [
            title for title in _wiki_related_titles_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if title and title != wiki_title
        ]
        needs_visual_pool = bool(selected_lanes & {"article", "image"})
        voyage_title = (
            _wiki_title_for_entity(
                "zh.wikivoyage.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if needs_visual_pool
            else ""
        )
        wiki_url = _wiki_url("zh.wikipedia.org", wiki_title)
        voyage_url = _wiki_url("zh.wikivoyage.org", voyage_title)
        registry_official_url = _known_official_website(entity_id)
        official_url = registry_official_url or _official_website(qid)
        official_provider = (
            "travel_source_registry"
            if registry_official_url
            else "wikidata_official_website"
        )
        official_reason_provider = (
            "Travel source registry official website"
            if registry_official_url
            else "Wikidata official website"
        )
        reject_memory = _download_reject_memory(
            task_id,
            batch_id,
            entity_id,
            entity_type=entity_type,
        )
        rejected_source_urls = reject_memory["sourceUrls"]
        rejected_image_urls = reject_memory["imageUrls"]
        prior_image_collections = (
            _verified_image_collections_from_prior_plans(
                task_id,
                batch_id,
                entity_id,
                entity_type=entity_type,
                entity_aliases=entity_aliases,
                rejected_image_urls=rejected_image_urls,
                limit=max(image_bonus_saturation_count, 8),
            )
            if needs_visual_pool
            else []
        )
        prior_image_pool = _images_from_collections(prior_image_collections)
        prior_article_sources = (
            _verified_article_sources_from_prior_plans(
                task_id,
                batch_id,
                entity_id,
                entity_type=entity_type,
                rejected_source_urls=rejected_source_urls,
                limit=_article_base_candidate_limit(required_article_bases),
            )
            if "article" in selected_lanes
            else []
        )
        prior_homepage_sources = (
            _verified_homepage_sources_from_source_units(
                task_id,
                batch_id,
                entity_id,
                entity_type=entity_type,
                rejected_source_urls=rejected_source_urls,
            )
            if "homepage" in selected_lanes
            else []
        )
        image_pools = (
            _discover_open_license_image_pools(
                entity_id,
                entity_aliases=entity_aliases,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
                rejected_image_urls=rejected_image_urls,
            )
            if needs_visual_pool
            else {
                "commons": [],
                "hint_commons": [],
                "wikidata_commons": [],
                "openverse": [],
                "wiki_page_images": [],
                "voyage_page_images": [],
            }
        )
        commons = image_pools["commons"]
        hint_commons = image_pools.get("hint_commons") or []
        wikidata_commons = image_pools["wikidata_commons"]
        openverse = image_pools["openverse"]
        wiki_page_images = image_pools["wiki_page_images"]
        voyage_page_images = image_pools["voyage_page_images"]
        authorized_image_pool = (
            prior_image_pool
            + openverse
            + commons
            + hint_commons
            + wikidata_commons
            + wiki_page_images
            + voyage_page_images
        )
        if needs_visual_pool and not authorized_image_pool:
            rescue_pools = _discover_open_license_image_pools(
                entity_id,
                entity_aliases=entity_aliases,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
                rejected_image_urls=rejected_image_urls,
                commons_limit=20,
                wikidata_limit=20,
                openverse_limit=24,
                page_limit=14,
            )
            rescue_pool = (
                rescue_pools["openverse"]
                + rescue_pools["commons"]
                + (rescue_pools.get("hint_commons") or [])
                + rescue_pools["wikidata_commons"]
                + rescue_pools["wiki_page_images"]
                + rescue_pools["voyage_page_images"]
            )
            if rescue_pool:
                commons = rescue_pools["commons"]
                hint_commons = rescue_pools.get("hint_commons") or []
                wikidata_commons = rescue_pools["wikidata_commons"]
                openverse = rescue_pools["openverse"]
                wiki_page_images = rescue_pools["wiki_page_images"]
                voyage_page_images = rescue_pools["voyage_page_images"]
                authorized_image_pool = prior_image_pool + rescue_pool
                report.setdefault("rescueEvents", []).append(
                    {
                        "entityId": entity_id,
                        "lane": "image",
                        "reason": "open_license_image_discovery_empty_on_first_pass",
                        "images": len(rescue_pool),
                    }
                )
        homepage_image_pool = wiki_page_images or commons or hint_commons or wikidata_commons or openverse
        homepage_image_urls = {
            str(image.get("url") or "")
            for image in homepage_image_pool
            if str(image.get("url") or "").strip()
        }
        external_links = (
            _trusted_external_links(
                wiki_title,
                limit=max(4, min(12, required_article_bases * 2)),
            )
            if "article" in selected_lanes
            else []
        )
        if needs_visual_pool and requires_publishable_images and not authorized_image_pool:
            issues.append(f"{entity_id}: no rights-compatible open-license images discovered")
            if "image" in selected_lanes:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no rights-compatible Openverse/Wikimedia images discovered",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )

        homepage_sources: list[dict[str, Any]] = []
        baidu_url = f"https://baike.baidu.com/item/{urllib.parse.quote(entity_id)}"
        if "homepage" in selected_lanes:
            def _accept_homepage_source(source: dict[str, Any]) -> dict[str, Any] | None:
                return _accept_source_with_reject_memory(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                    rejected_source_urls=rejected_source_urls,
                )

            for prior_source in prior_homepage_sources:
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_homepage_source(dict(prior_source))
                if accepted:
                    homepage_sources.append(accepted)
            if official_url:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_official",
                        platform="景区官网",
                        url=official_url,
                        category="official",
                        discovery_provider=official_provider,
                        match_confidence=0.94,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", official_reason_provider, "official"
                        ),
                        source_role="primary",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            if wiki_url:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_wikipedia",
                        platform="维基百科",
                        url=wiki_url,
                        category="encyclopedia",
                        discovery_provider="mediawiki_exact_title",
                        match_confidence=0.99,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Chinese Wikipedia", "encyclopedia"
                        ),
                        source_role="primary" if not homepage_sources else "supporting",
                        images=_image_window(homepage_image_pool, 0, count=3),
                        image_evidence_mode="same_source" if wiki_page_images else "same_authorized_collection",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            for support_index, support in enumerate(_known_homepage_support_websites(entity_id), start=1):
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_homepage_source(
                    _source(
                        source_id=support["source_id"] or f"home_official_support_{support_index}",
                        platform=support["platform"] or "景区官网",
                        url=support["url"],
                        category=support["category"] or "official",
                        discovery_provider="travel_source_registry",
                        match_confidence=0.90,
                        evidence_reason=_evidence_reason(
                            entity_id,
                            "homepage",
                            "Travel source registry official detail page",
                            support["category"] or "official",
                        ),
                        source_role="supporting",
                        images=_image_window(homepage_image_pool, 1 + support_index, count=2),
                        image_evidence_mode="same_authorized_collection" if homepage_image_pool else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            accepted = _accept_homepage_source(
                _source(
                    source_id="home_baidu_baike",
                    platform="百度百科",
                    url=baidu_url,
                    category="encyclopedia",
                    discovery_provider="baidu_baike_exact_item_url",
                    match_confidence=0.86,
                    evidence_reason=_evidence_reason(
                        entity_id, "homepage", "Baidu Baike item URL", "encyclopedia"
                    ),
                    source_role="supporting",
                    images=_image_window(homepage_image_pool, 0, count=3),
                    image_evidence_mode="same_authorized_collection" if homepage_image_pool else "",
                )
            )
            if accepted:
                homepage_sources.append(accepted)
            for related_index, related_title in enumerate(related_wiki_titles[:2], start=1):
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                related_url = _wiki_url("zh.wikipedia.org", related_title)
                if not related_url:
                    continue
                related_images = _mediawiki_page_images(
                    "zh.wikipedia.org",
                    related_title,
                    entity_id=entity_id,
                    limit=3,
                )
                related_pool = related_images or authorized_image_pool
                accepted = _accept_homepage_source(
                    _source(
                        source_id=f"home_related_encyclopedia_support_{related_index}",
                        platform="维基百科",
                        url=related_url,
                        category="encyclopedia",
                        discovery_provider="mediawiki_related_title",
                        match_confidence=0.82,
                        evidence_reason=(
                            f"Chinese Wikipedia related page {related_title} provides "
                            f"entity context and rights-compatible media for {entity_id}"
                        ),
                        source_role="supporting",
                        images=_image_window(related_pool, 0, count=3),
                        image_evidence_mode=(
                            "same_source" if related_images else "same_authorized_collection"
                        ) if related_pool else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            if len(homepage_sources) < 2:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_sogou_baike",
                        platform="搜狗百科",
                        url=f"https://baike.sogou.com/v?query={urllib.parse.quote(entity_id)}",
                        category="encyclopedia",
                        discovery_provider="sogou_baike_exact_query_url",
                        match_confidence=0.78,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Sogou Baike query URL", "encyclopedia"
                        ),
                        source_role="supporting",
                        images=_image_window(homepage_image_pool, 1, count=3),
                        image_evidence_mode="same_authorized_collection" if homepage_image_pool else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            homepage_core_sources = _homepage_core_sources(homepage_sources)
            if _write_lane(
                dl / "homepage_source_plan.json",
                "homepage",
                {
                    "primaryEvidenceRef": (
                        homepage_core_sources[0]["source_id"]
                        if homepage_core_sources
                        else ""
                    ),
                    "sources": homepage_core_sources,
                },
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "homepage",
                        "sources": len(homepage_core_sources),
                    }
                )
            homepage_seed_sources = [
                source for source in homepage_core_sources if _homepage_can_seed_base_draft(source)
            ]
            if not homepage_seed_sources:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason="homepage has no encyclopedia/official seed source for baseDraft",
                    next_action="manual_homepage_seed_source_or_target_replacement",
                )

        article_sources: list[dict[str, Any]] = []
        if "article" in selected_lanes:
            for source in _qunar_travelogue_sources(
                entity_id,
                entity_aliases=entity_aliases,
                authorized_images=authorized_image_pool,
                limit=_article_base_candidate_limit(required_article_bases),
            ):
                accepted = _accept_source(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            accepted = _accept_source(
                report,
                _qunar_review_support_source(entity_id),
                entity_id=entity_id,
                lane="article",
                entity_aliases=entity_aliases,
            )
            if accepted:
                article_sources.append(accepted)
            for related_index, related_title in enumerate(related_wiki_titles, start=1):
                related_url = _wiki_url("zh.wikipedia.org", related_title)
                if not related_url:
                    continue
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=f"article_related_encyclopedia_support_{related_index}",
                        platform="维基百科",
                        url=related_url,
                        category="encyclopedia",
                        discovery_provider="mediawiki_related_title",
                        match_confidence=0.82,
                        evidence_reason=(
                            f"Chinese Wikipedia related page {related_title} provides factual "
                            f"context for {entity_id}; supporting only, not an article base"
                        ),
                        source_role="supporting",
                        images=_image_window(wiki_page_images or authorized_image_pool, 1 + related_index, count=2),
                        image_evidence_mode=(
                            "same_authorized_collection" if (wiki_page_images or authorized_image_pool) else ""
                        ),
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            if voyage_url:
                voyage_images = voyage_page_images or authorized_image_pool
                accepted = _accept_source(
                    report,
                    _source(
                        source_id="article_wikivoyage_base",
                        platform="维基导游",
                        url=voyage_url,
                        category="travelogue",
                        discovery_provider="wikivoyage_exact_title",
                        match_confidence=0.99,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Chinese Wikivoyage", "travelogue"
                        ),
                        source_role="base",
                        images=_image_window(voyage_images, 0, count=3),
                        image_evidence_mode=(
                            "same_source" if voyage_page_images else "same_authorized_collection"
                        ) if voyage_images else "",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            for index, link in enumerate(external_links, start=1):
                if _url_in_memory(link, rejected_source_urls):
                    continue
                platform = _external_platform(link)
                category = _external_article_category(link, platform)
                source_role = "base" if category in _ARTICLE_BASE_CATEGORIES else "supporting"
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=(
                            f"article_external_base_{index}"
                            if source_role == "base"
                            else f"article_authoritative_support_{index}"
                        ),
                        platform=platform,
                        url=link,
                        category=category,
                        discovery_provider="wikipedia_trusted_extlinks",
                        match_confidence=0.80,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Wikipedia trusted external links", category
                        ),
                        source_role=source_role,
                        images=_image_window(commons, 4 + index, count=3),
                        image_evidence_mode="same_authorized_collection" if commons else "",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            for index, known in enumerate(_known_article_sources(entity_id), start=1):
                if _url_in_memory(str(known.get("url") or ""), rejected_source_urls):
                    continue
                category = str(known.get("category") or "travelogue").strip()
                source_role = "base" if category in _ARTICLE_BASE_CATEGORIES else "supporting"
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=known["source_id"] or f"article_registry_base_{index}",
                        platform=known["platform"] or "垂类专业站",
                        url=known["url"],
                        category=category,
                        discovery_provider="travel_source_registry",
                        match_confidence=0.88,
                        evidence_reason=_evidence_reason(
                            entity_id,
                            "article",
                            "Travel source registry known article source",
                            category,
                        ),
                        source_role=source_role,
                        images=_image_window(authorized_image_pool, 2 + index, count=3),
                        image_evidence_mode="same_authorized_collection" if authorized_image_pool else "",
                        fetchable_override=bool(known.get("fetchable")),
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    if known.get("title"):
                        accepted["title"] = known["title"]
                    article_sources.append(accepted)
            commons_visual = _image_at(commons, 5)
            open_visual = _image_at(openverse, 0)
            if commons_visual or open_visual:
                visual = commons_visual or open_visual or {}
                accepted = _accept_source(
                    report,
                    _source(
                        source_id="article_open_visual_support",
                        platform=str(visual.get("platform") or "Openverse"),
                        url=str(visual.get("sourceUrl") or visual.get("url") or ""),
                        category="open_license",
                        discovery_provider="open_license_image_search",
                        match_confidence=0.82,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Open license image search", "open_license"
                        ),
                        source_role="supporting",
                        images=_image_window(authorized_image_pool, 5, count=3),
                        image_evidence_mode="same_authorized_collection",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            seen_article_urls = {
                str(source.get("url") or "").strip()
                for source in article_sources
                if str(source.get("url") or "").strip()
            }
            homepage_urls = {
                str(source.get("url") or "").strip()
                for source in homepage_sources
                if str(source.get("url") or "").strip()
            }
            homepage_urls.update(
                _homepage_urls_from_current_plan(
                    task_id,
                    batch_id,
                    entity_id,
                    entity_type=entity_type,
                )
            )
            for source in prior_article_sources:
                url = str(source.get("url") or "").strip()
                if not url or url in seen_article_urls or url in homepage_urls:
                    continue
                if _url_in_memory(url, rejected_source_urls):
                    continue
                accepted = _accept_source(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
                    seen_article_urls.add(url)
            base_count = sum(1 for source in article_sources if source.get("sourceRole") == "base")
            if base_count < required_article_bases:
                issues.append(
                    f"{entity_id}: article base sources={base_count} need>={required_article_bases}"
                )
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="article",
                    reason=f"article base sources={base_count} need>={required_article_bases}",
                    next_action="agent_repair_or_manual_fetchable_article_provider",
                )
            if len(article_sources) < required_article_bases:
                issues.append(
                    f"{entity_id}: article auto plan has {len(article_sources)} "
                    f"source(s), need >={required_article_bases}"
                )
            article_plan_sources = _select_article_plan_sources(
                article_sources,
                required_article_bases=required_article_bases,
            )
            if _write_lane(
                dl / "article_source_plan.json",
                "article",
                {"sources": article_plan_sources},
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "article",
                        "sources": len(article_plan_sources),
                    }
                )

        if "image" in selected_lanes:
            collections: list[dict[str, Any]] = []
            desired_image_collections = max(
                required_publishable_images + 3,
                min(12, required_publishable_images + required_article_bases + 3),
            )
            used_collection_ids: set[str] = set()
            for collection in prior_image_collections:
                collection_id = str(collection.get("sourceCollectionId") or "").strip()
                if not collection_id or collection_id in used_collection_ids:
                    continue
                collection_verdict = _collection_gate(
                    collection,
                    entity_id=entity_id,
                    entity_aliases=entity_aliases,
                    vertical=vertical,
                )
                report.setdefault("imageCollections", []).append(
                    {
                        "entityId": entity_id,
                        "sourceCollectionId": collection_id,
                        "platform": collection.get("platform") or "",
                        "imageCount": len(collection.get("images") or []),
                        "passed": bool(collection_verdict.get("passed")),
                        "issues": list(collection_verdict.get("issues") or []),
                        "discoveryProvider": "verified_source_pool_reuse",
                    }
                )
                if not collection_verdict["passed"]:
                    continue
                used_collection_ids.add(collection_id)
                collections.append(collection)
                if len(collections) >= desired_image_collections:
                    break
            first_image = (
                _image_at(prior_image_pool, 0)
                or _image_at(openverse, 0)
                or _image_at(commons, 0)
                or _image_at(wikidata_commons, 0)
                or _image_at(wiki_page_images, 0)
                or _image_at(voyage_page_images, 0)
            )
            if first_image and len(collections) < desired_image_collections:
                collection_candidates = (
                    openverse
                    + commons
                    + hint_commons
                    + wikidata_commons
                    + wiki_page_images
                    + voyage_page_images
                )
                collection_candidates = sorted(
                    collection_candidates,
                    key=lambda item: str(item.get("url") or "") in homepage_image_urls,
                )
                for raw_item in collection_candidates:
                    item = dict(raw_item)
                    collection_id = _safe_collection_id(
                        "open_license_file",
                        entity_id,
                        str(item.get("sourceCollectionId") or item.get("sourceUrl") or item.get("url") or ""),
                    )
                    if collection_id in used_collection_ids:
                        continue
                    used_collection_ids.add(collection_id)
                    item["sourceCollectionId"] = collection_id
                    item["creator"] = item.get("creator") or item.get("credit") or "Wikimedia Commons contributor"
                    item["collectionPageUrl"] = item.get("collectionPageUrl") or item.get("sourceUrl") or item.get("url") or ""
                    item["researchLane"] = "image"
                    collection = {
                        "sourceCollectionId": collection_id,
                        "creator": item["creator"],
                        "credit": item.get("credit") or item["creator"],
                        "collectionPageUrl": item["collectionPageUrl"],
                        "platform": item.get("platform") or "Openverse",
                        "license": item.get("license") or "",
                        "termsUrl": item.get("termsUrl") or "",
                        "licenseSnapshot": item.get("licenseSnapshot") or "",
                        "authorizationProof": item.get("authorizationProof") or item["collectionPageUrl"],
                        "usageScope": "app_publish",
                        "discoveryProvider": "open_license_image_search",
                        "evidenceReason": _evidence_reason(
                            entity_id, "image", "Open license image search", "open_license"
                        ),
                        "images": [item],
                    }
                    collection_verdict = _collection_gate(
                        collection,
                        entity_id=entity_id,
                        entity_aliases=entity_aliases,
                        vertical=vertical,
                    )
                    report.setdefault("imageCollections", []).append(
                        {
                            "entityId": entity_id,
                            "sourceCollectionId": collection_id,
                            "platform": collection.get("platform") or "",
                            "imageCount": len(collection.get("images") or []),
                            "passed": bool(collection_verdict.get("passed")),
                            "issues": list(collection_verdict.get("issues") or []),
                        }
                    )
                    if collection_verdict["passed"]:
                        collections.append(collection)
                    if len(collections) >= desired_image_collections:
                        break
            if not requires_publishable_images:
                report.setdefault("imageCollections", []).append(
                    {
                        "entityId": entity_id,
                        "sourceCollectionId": "",
                        "platform": "",
                        "imageCount": len(authorized_image_pool),
                        "passed": True,
                        "issues": [],
                        "discoveryProvider": "reference_only_image_strategy",
                        "imageAssetStrategy": image_strategy,
                    }
                )
            elif hard_image_works and not collections:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no single-author/single-file rights-cleared image collection",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            elif hard_image_works and len(collections) < hard_image_works:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason=f"image collections={len(collections)} need>={hard_image_works}",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            else:
                unique_publishable_images = len(
                    _collection_publishable_image_urls(
                        collections,
                        entity_id=entity_id,
                        entity_aliases=entity_aliases,
                        vertical=vertical,
                    )
                )
                if required_publishable_images and unique_publishable_images < required_publishable_images:
                    _record_unavailable(
                        report,
                        entity_id=entity_id,
                        lane="image",
                        reason=(
                            f"unique publishable images={unique_publishable_images} "
                            f"need>={required_publishable_images}"
                        ),
                        next_action="manual_authorized_gallery_or_target_replacement",
                    )
            if _write_lane(
                dl / "image_source_plan.json",
                "image",
                {
                    "collections": collections,
                    "imageDiscoveryDiagnostics": {
                        "imageAssetStrategy": image_strategy,
                        "imageCountPolicy": image_policy,
                        "requiresPublishableImages": requires_publishable_images,
                        "desiredImageWorks": desired_image_works,
                        "imageBonusSaturationCount": image_bonus_saturation_count,
                        "requiredImageWorks": hard_image_works,
                        "requiredPublishableImages": required_publishable_images,
                        "qid": qid,
                        "wikiTitle": wiki_title,
                        "voyageTitle": voyage_title,
                        "entityAliases": entity_aliases[:24],
                        "poolCounts": {
                            "priorImageCollections": len(prior_image_collections),
                            "priorImagePool": len(prior_image_pool),
                            "commons": len(commons),
                            "hintCommons": len(hint_commons),
                            "wikidataCommons": len(wikidata_commons),
                            "openverse": len(openverse),
                            "wikiPageImages": len(wiki_page_images),
                            "voyagePageImages": len(voyage_page_images),
                            "authorizedImagePool": len(authorized_image_pool),
                            "acceptedCollections": len(collections),
                        },
                        "sourceUnavailable": _source_unavailable_for_entity(
                            report,
                            entity_id=entity_id,
                            lane="image",
                        ),
                    },
                    "sourceUnavailable": _source_unavailable_for_entity(
                        report,
                        entity_id=entity_id,
                        lane="image",
                    ),
                },
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "image",
                        "collections": len(collections),
                        "images": sum(len(c.get("images") or []) for c in collections),
                    }
                )
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    if write_shared_report:
        _write_auto_report_artifacts(task_id, batch_id, report)
    return report


def _source_availability_summary(report: dict[str, Any], entity_ids: list[str]) -> dict[str, Any]:
    unavailable_by_entity: dict[str, list[dict[str, Any]]] = {}
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if entity_id:
            unavailable_by_entity.setdefault(entity_id, []).append(item)
    issue_by_entity: dict[str, list[str]] = {}
    for issue in report.get("issues") or []:
        text = str(issue or "")
        entity = text.split(":", 1)[0].strip() if ":" in text else ""
        if entity:
            issue_by_entity.setdefault(entity, []).append(text)
    passed_lanes_by_entity: dict[str, set[str]] = {}
    for item in report.get("candidates") or []:
        if not isinstance(item, dict) or not bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        lane = str(item.get("lane") or "").strip()
        if entity_id and lane:
            passed_lanes_by_entity.setdefault(entity_id, set()).add(lane)
    for item in report.get("candidates") or []:
        if not isinstance(item, dict) or bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if not entity_id:
            continue
        lane = str(item.get("lane") or "").strip()
        if lane and lane in passed_lanes_by_entity.get(entity_id, set()):
            # Rejected discovery candidates are diagnostics. They must not
            # mark the whole lane unavailable after another candidate already
            # passed and became eligible for the consumable source plan.
            continue
        source_id = str(item.get("source_id") or "").strip()
        issues = [str(issue) for issue in (item.get("issues") or []) if str(issue).strip()]
        if not issues:
            issues = ["source candidate gate failed"]
        prefix = f"{entity_id}: {lane} candidate {source_id}".strip()
        issue_by_entity.setdefault(entity_id, []).extend(f"{prefix}: {issue}" for issue in issues)

    def _lane_for_issue(issue: str) -> str:
        lower = issue.lower()
        if "article" in lower or "travelogue" in lower or "guidebook" in lower:
            return "article"
        if "image" in lower or "open-license images" in lower or "rights-compatible" in lower:
            return "image"
        if "homepage" in lower:
            return "homepage"
        if "source discovery infrastructure" in lower:
            return "all"
        return ""

    def _normalized_issue(issue: str) -> str:
        text = issue.split(":", 1)[1].strip() if ":" in issue else issue
        text = re.sub(r"=\d+", "=N", text)
        text = re.sub(r"\d+", "N", text)
        return text

    scoring_policy = report.get("scoringPolicy") if isinstance(report.get("scoringPolicy"), dict) else {}
    image_saturation = int(scoring_policy.get("imageBonusSaturationCount") or 1)
    image_counts_by_entity: dict[str, int] = {}
    for item in report.get("imageCollections") or []:
        if not isinstance(item, dict) or not bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if not entity_id:
            continue
        image_counts_by_entity[entity_id] = image_counts_by_entity.get(entity_id, 0) + 1

    def _image_count_score(entity_id: str) -> float:
        if image_saturation <= 0:
            return 1.0
        return round(min(image_counts_by_entity.get(entity_id, 0) / image_saturation, 1.0), 4)

    ineligible: list[dict[str, Any]] = []
    scored_targets: list[dict[str, Any]] = []
    image_soft_warnings: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        blockers = list(unavailable_by_entity.get(entity_id) or [])
        issues = issue_by_entity.get(entity_id) or []
        lanes = {
            str(item.get("lane") or "")
            for item in blockers
            if item.get("lane")
        }
        lanes.update(lane for lane in (_lane_for_issue(issue) for issue in issues) if lane)
        fatal_blockers = [item for item in blockers if str(item.get("lane") or "") != "image"]
        fatal_issues = [issue for issue in issues if _lane_for_issue(issue) != "image"]
        soft_blockers = [item for item in blockers if str(item.get("lane") or "") == "image"]
        soft_issues = [issue for issue in issues if _lane_for_issue(issue) == "image"]
        image_score = _image_count_score(entity_id)
        eligible = not fatal_blockers and not fatal_issues
        composite_score = round((80.0 if eligible else 0.0) + (20.0 * image_score if eligible else 0.0), 2)
        scored_row = {
            "entityId": entity_id,
            "eligible": eligible,
            "compositeScore": composite_score,
            "minimumQualityScore": 80.0 if eligible else 0.0,
            "imageBonusScore": round(20.0 * image_score if eligible else 0.0, 2),
            "imageCountScore": image_score,
            "publishableImageCollectionCount": image_counts_by_entity.get(entity_id, 0),
            "imageBonusSaturationCount": image_saturation,
        }
        scored_targets.append(scored_row)
        if soft_blockers or soft_issues:
            image_soft_warnings.append(
                {
                    "entityId": entity_id,
                    "lanes": ["image"],
                    "issues": soft_issues,
                    "issueReasons": sorted({_normalized_issue(issue) for issue in soft_issues}),
                    "blockers": soft_blockers,
                    "nextActions": sorted({str(item.get("nextAction") or "") for item in soft_blockers if item.get("nextAction")}),
                    "scoreImpact": {
                        "imageCountScore": image_score,
                        "imageBonusScore": scored_row["imageBonusScore"],
                    },
                }
            )
        if not eligible:
            ineligible.append(
                {
                    "entityId": entity_id,
                    "lanes": sorted(lanes),
                    "issues": fatal_issues,
                    "issueReasons": sorted({_normalized_issue(issue) for issue in fatal_issues}),
                    "blockers": fatal_blockers,
                    "softImageWarnings": {
                        "issues": soft_issues,
                        "blockers": soft_blockers,
                    },
                    "nextActions": sorted({str(item.get("nextAction") or "") for item in fatal_blockers if item.get("nextAction")}),
                }
            )
    ranked_targets = sorted(
        scored_targets,
        key=lambda row: (-float(row.get("compositeScore") or 0.0), str(row.get("entityId") or "")),
    )
    ready = [str(row["entityId"]) for row in ranked_targets if bool(row.get("eligible"))]
    return {
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
        "rankedTargets": ranked_targets,
        "imageSoftWarnings": image_soft_warnings,
        "scoringPolicy": scoring_policy,
    }


def _write_auto_report_artifacts(task_id: str, batch_id: str, report: dict[str, Any]) -> None:
    shared_dir = batch_root(task_id, batch_id) / "_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    write_json(shared_dir / _AUTO_DISCOVERY_REPORT, report)
    availability = report.get("sourceAvailability") if isinstance(report.get("sourceAvailability"), dict) else {}
    write_json(shared_dir / "source_unavailable_targets.json", availability)


def _merge_auto_reports(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in ("updated", "issues", "candidates", "imageCollections", "sourceUnavailable", "rescueEvents"):
        rows = incoming.get(key) if isinstance(incoming.get(key), list) else []
        base.setdefault(key, []).extend(rows)


def write_auto_research_plans(
    task_id: str,
    batch_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    max_workers: int = 1,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Discover separated source plans, optionally parallelized per entity."""
    selected_lanes = lanes or {"homepage", "article", "image"}
    vertical = vertical_from_task_id(task_id)
    started = time.monotonic()
    workers = max(1, int(max_workers or 1))

    def emit_progress(
        status: str,
        *,
        completed_count: int = 0,
        entity_id: str = "",
        message: str = "",
    ) -> None:
        progress = _write_auto_research_progress(
            task_id,
            batch_id,
            status=status,
            entity_count=len(entity_ids),
            completed_count=completed_count,
            entity_id=entity_id,
            workers=workers,
            started_monotonic=started,
            message=message,
        )
        if progress_callback is not None:
            progress_callback(progress)

    emit_progress("running", message="auto research started")
    if workers <= 1 or len(entity_ids) <= 1:
        report = _write_auto_research_plans_impl(
            task_id,
            batch_id,
            entity_ids,
            entity_type=entity_type,
            force=force,
            lanes=selected_lanes,
            write_shared_report=False,
        )
        emit_progress(
            "running",
            completed_count=len(entity_ids),
            message="auto research completed for all entities",
        )
    else:
        entities = [
            {"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type}
            for entity_id in entity_ids
        ]
        prepare_source_plan(task_id, batch_id, entities)
        report = {
            "schemaVersion": "quwoquan.download.auto_research_plan",
            "taskId": task_id,
            "batchId": batch_id,
            "vertical": vertical,
            "selectedLanes": sorted(selected_lanes),
            "updated": [],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [],
        }
        results: dict[str, dict[str, Any]] = {}
        executor = ThreadPoolExecutor(max_workers=min(workers, len(entity_ids)))
        futures = {}
        shutdown_wait = True
        try:
            futures = {
                executor.submit(
                    _write_auto_research_plans_impl,
                    task_id,
                    batch_id,
                    [entity_id],
                    entity_type=entity_type,
                    force=force,
                    lanes=selected_lanes,
                    write_shared_report=False,
                ): entity_id
                for entity_id in entity_ids
            }
            completed_count = 0
            for future in as_completed(futures):
                entity_id = futures[future]
                try:
                    results[entity_id] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results[entity_id] = {
                        "updated": [],
                        "issues": [f"{entity_id}: source discovery infrastructure failure: {type(exc).__name__}: {exc}"],
                        "candidates": [],
                        "imageCollections": [],
                        "sourceUnavailable": [
                            {
                                "entityId": entity_id,
                                "lane": "all",
                                "reason": f"source discovery infrastructure failure: {type(exc).__name__}: {exc}",
                                "nextAction": "retry_source_discovery",
                            }
                        ],
                    }
                completed_count += 1
                emit_progress(
                    "running",
                    completed_count=completed_count,
                    entity_id=entity_id,
                    message=f"auto research completed {completed_count}/{len(entity_ids)}",
                )
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            emit_progress(
                "interrupted",
                completed_count=len(results),
                message="auto research interrupted; queued futures cancelled",
            )
            shutdown_wait = False
            raise
        finally:
            executor.shutdown(wait=shutdown_wait, cancel_futures=not shutdown_wait)
        for entity_id in entity_ids:
            _merge_auto_reports(report, results.get(entity_id) or {})
    elapsed = max(time.monotonic() - started, 0.001)
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    report["throughput"] = {
        "maxWorkers": workers,
        "entityCount": len(entity_ids),
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(len(entity_ids) / elapsed * 60.0, 3),
    }
    _write_auto_report_artifacts(task_id, batch_id, report)
    emit_progress(
        "succeeded",
        completed_count=len(entity_ids),
        message="auto research report written",
    )
    return report


def handle_research_plan(args: argparse.Namespace) -> None:
    lane_arg = str(getattr(args, "lane", "all") or "all")
    lanes = None if lane_arg == "all" else {lane_arg}
    report = write_auto_research_plans(
        str(args.task),
        str(args.batch),
        [item.strip() for item in str(args.entity_ids or "").split(",") if item.strip()],
        entity_type=str(args.entity_type or ""),
        force=bool(getattr(args, "force", False)),
        lanes=lanes,
        max_workers=int(getattr(args, "max_workers", 1) or 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("issues") and getattr(args, "strict", False):
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    def _add_common(name: str, help_text: str) -> argparse.ArgumentParser:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("--task", required=True)
        p.add_argument("--batch", required=True)
        p.add_argument("--entity-ids", required=True)
        p.add_argument("--entity-type", default="")
        p.add_argument("--lane", choices=("all", "homepage", "article", "image"), default="all")
        p.add_argument("--max-workers", type=int, default=1, help="Entity-level source discovery concurrency")
        p.add_argument("--force", action="store_true", help="Overwrite non-empty lane plans")
        p.add_argument("--strict", action="store_true", help="Exit non-zero when public-source discovery has gaps")
        p.set_defaults(handler=handle_research_plan)
        return p

    _add_common(
        "research-plan",
        "Bootstrap separated homepage/article/image source plans from registered public sources",
    )
    _add_common(
        "source-discover",
        "Discover and gate source candidates for one or more separated research lanes",
    )
