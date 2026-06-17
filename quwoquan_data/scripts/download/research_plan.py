"""Deterministic public-source research plan bootstrap.

This fills the source/research lane with auditable public sources before a
semantic Agent is needed. It is intentionally conservative: it writes only
empty lane plans unless --force is passed, and it leaves explicit gaps when a
source cannot be discovered from registered public endpoints.
"""
from __future__ import annotations

import argparse
import html
import json
import math
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
from _common.paths import STAGE_DOWNLOAD, batch_root
from _common.source_catalog import platform_category, vertical_from_task_id
from _common.source_unit import resolve_entity_object_dir
from download.prepare import prepare_source_plan

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
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", "2", "--retry-delay", "1", "--retry-all-errors",
            "--max-time", str(timeout),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout or "{}")
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


def _image_mentions_entity(
    image: dict[str, Any],
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    if not entity_id:
        return True
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
            if isinstance(page, dict) and str(page.get("extract") or "").strip():
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
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": entity_id,
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
        if any(_title_matches_entity(label, entity_id) for label in labels if label):
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
    if host.endswith("gov.cn") or host.endswith("mnr.gov.cn"):
        return "文旅局"
    if "dujiangyan.com.cn" in host or "yading" in host:
        return "景区官网"
    return "权威媒体"


def _license_allows_app_publish(license_name: str, license_url: str = "") -> bool:
    value = f"{license_name} {license_url}".lower()
    if not value.strip():
        return False
    if any(token in value for token in ("nc", "noncommercial", "nd", "noderivatives", "igo")):
        return False
    if re.search(r"\b1\.0\b", value) and (
        "creativecommons" in value
        or "cc by" in value
        or "by-sa" in value
        or "/by" in value
    ):
        return False
    return any(token in value for token in ("cc0", "publicdomain", "public domain", "pd", "by-sa", "by/sa", "by/", " by"))


def _evidence_reason(entity_id: str, lane: str, provider: str, category: str) -> str:
    lane_label = {"homepage": "实体主页", "article": "图文文章", "image": "图库作品"}.get(lane, lane)
    return f"{provider} 发现的 {entity_id} {lane_label}候选来源；类别={category or 'unknown'}"


def _source_category(platform: str, fallback: str = "") -> str:
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
        images = source.get("imageUrls") if isinstance(source.get("imageUrls"), list) else []
        if not images:
            issues.append("article base source must provide same-source or authorized image candidates")
        if str(source.get("imageEvidenceMode") or "") not in {
            "same_source",
            "same_authorized_collection",
        }:
            issues.append("article base source imageEvidenceMode must be same_source or same_authorized_collection")
    image_warnings: list[str] = []
    valid_images: list[dict[str, Any]] = []
    image_issues_block_source = lane != "article" or role == "base"
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
    if lane == "article" and role != "base" and "imageUrls" in source:
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


def _collection_gate(
    collection: dict[str, Any],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    issues: list[str] = []
    collection_id = str(collection.get("sourceCollectionId") or "").strip()
    if not collection_id:
        issues.append("sourceCollectionId missing")
    images = collection.get("images") if isinstance(collection.get("images"), list) else []
    if not images:
        issues.append("no rights-compatible images in collection")
    creators: set[str] = set()
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            issues.append(f"image[{index}] must be object")
            continue
        creator = str(image.get("creator") or image.get("credit") or collection.get("creator") or "").strip()
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
            if not str(image.get(field) or collection.get(field) or "").strip()
        ]
        if missing:
            issues.append(f"image[{index}] missing collection rights {missing}")
        if entity_id and not _image_mentions_entity(
            image,
            entity_id,
            entity_aliases=entity_aliases,
        ):
            issues.append(f"image[{index}] relevance does not strongly mention entity")
    if len(creators) > 1:
        issues.append("image work collection cannot mix multiple creators")
    return {"passed": not issues, "issues": issues}


def _commons_images(entity_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    data = _wiki_api(
        "commons.wikimedia.org",
        {
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": entity_id,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info = ((page.get("imageinfo") or [{}])[0] or {})
        url = str(info.get("url") or "")
        if not url or url in seen:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
            continue
        seen.add(url)
        meta = info.get("extmetadata") or {}
        license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
        license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
        if not license_url or not _license_allows_app_publish(license_name, license_url):
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 640 or height < 426 or max(width, height) < 800:
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


def _openverse_images(entity_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Discover rights-compatible image candidates via Openverse.

    Openverse is a discovery index, so the source proof remains the original
    landing page plus the license URL. We reject NC/ND and undersized images
    here before a candidate can enter any source plan.
    """
    params = urllib.parse.urlencode({"q": entity_id, "page_size": min(max(limit * 3, 5), 50)})
    data = _curl_json(f"{_OPENVERSE_API}?{params}", timeout=25)
    rows = data.get("results") if isinstance(data.get("results"), list) else []
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        landing = str(row.get("foreign_landing_url") or row.get("detail_url") or "").strip()
        license_slug = str(row.get("license") or "").strip()
        license_version = str(row.get("license_version") or "").strip()
        license_url = str(row.get("license_url") or "").strip()
        title = _strip_html(str(row.get("title") or ""))
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
        if not (_title_matches_entity(title, entity_id) or entity_id in str(row.get("attribution") or "")):
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
            break
    return images


def _qunar_travelogue_sources(
    entity_id: str,
    *,
    authorized_images: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Discover fetchable Qunar travelogue pages for article base evidence."""
    if not authorized_images:
        return []
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    image_index = 0
    for page in range(1, 5):
        encoded_q = urllib.parse.quote(entity_id)
        data: dict[str, Any] = {}
        for attempt in range(3):
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
            route_hit = any(_title_matches_entity(item, entity_id) for item in route)
            title_hit = _title_matches_entity(title, entity_id)
            if not (title_hit or route_hit):
                continue
            images = _image_window(authorized_images, image_index, count=1)
            if not images:
                continue
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
                    f"去哪儿攻略游记搜索命中 {entity_id}；"
                    f"title={title[:60]} route={','.join(route[:6])} city={city}"
                ),
                source_role="base",
                images=images,
                image_evidence_mode="same_authorized_collection",
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
        reserve = min(max(6, math.ceil(required * 1.5)), 12)
    return min(required + reserve, 24)


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
    return _source(
        source_id="article_qunar_review_support",
        platform="去哪儿景点点评",
        url=f"https://touch.travel.qunar.com/search?q={urllib.parse.quote(entity_id)}",
        category="review",
        discovery_provider="qunar_touch_search_page",
        match_confidence=0.86,
        evidence_reason=f"去哪儿搜索页提供 {entity_id} 景点标签、游记列表、热度与点评线索，仅作事实参考",
        source_role="supporting",
    )


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
    return f"{prefix}:{entity_id}:{raw}"


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


def _task_content_quotas(task_id: str) -> dict[str, int]:
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        spec = {}
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
    write_json(path, plan)
    return True


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
    }
    quotas = _task_content_quotas(task_id)
    required_article_bases = max(1, quotas["entityArticlesPerTarget"] or 1)
    required_image_works = max(1, quotas["imageWorksPerTarget"] or 1)
    for entity_id in entity_ids:
        obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
        dl = obj / STAGE_DOWNLOAD
        wiki_title = _wiki_title("zh.wikipedia.org", entity_id)
        related_wiki_titles = [
            title for title in _wiki_related_titles("zh.wikipedia.org", entity_id)
            if title and title != wiki_title
        ]
        voyage_title = _wiki_title("zh.wikivoyage.org", entity_id)
        wiki_url = _wiki_url("zh.wikipedia.org", wiki_title)
        voyage_url = _wiki_url("zh.wikivoyage.org", voyage_title)
        qid = _wikidata_item_for_zhwiki(wiki_title) or _wikidata_item_for_entity_search(entity_id)
        entity_aliases = _wikidata_entity_aliases(qid)
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
        commons = _commons_images(entity_id, limit=10)
        wikidata_commons = _wikidata_commons_images(
            qid,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            limit=10,
        )
        openverse = _openverse_images(entity_id, limit=12)
        wiki_page_images = _mediawiki_page_images(
            "zh.wikipedia.org", wiki_title, entity_id=entity_id, limit=6
        )
        voyage_page_images = _mediawiki_page_images(
            "zh.wikivoyage.org", voyage_title, entity_id=entity_id, limit=6
        )
        authorized_image_pool = openverse + commons + wikidata_commons + wiki_page_images + voyage_page_images
        homepage_image_pool = wiki_page_images or commons or wikidata_commons or openverse
        homepage_image_urls = {
            str(image.get("url") or "")
            for image in homepage_image_pool
            if str(image.get("url") or "").strip()
        }
        external_links = _trusted_external_links(wiki_title, limit=4)
        if not authorized_image_pool:
            issues.append(f"{entity_id}: no rights-compatible open-license images discovered")
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
            if official_url:
                accepted = _accept_source(
                    report,
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
                    ),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    homepage_sources.append(accepted)
            if wiki_url:
                accepted = _accept_source(
                    report,
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
                    ),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    homepage_sources.append(accepted)
            for support_index, support in enumerate(_known_homepage_support_websites(entity_id), start=1):
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_source(
                    report,
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
                    ),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    homepage_sources.append(accepted)
            accepted = _accept_source(
                report,
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
                ),
                entity_id=entity_id,
                lane="homepage",
                entity_aliases=entity_aliases,
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
                accepted = _accept_source(
                    report,
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
                    ),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    homepage_sources.append(accepted)
            if len(homepage_sources) < 2:
                accepted = _accept_source(
                    report,
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
                    ),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    homepage_sources.append(accepted)
            if _write_lane(
                dl / "homepage_source_plan.json",
                "homepage",
                {
                    "primaryEvidenceRef": (
                        _homepage_core_sources(homepage_sources)[0]["source_id"]
                        if homepage_sources
                        else ""
                    ),
                    "sources": _homepage_core_sources(homepage_sources),
                },
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "homepage",
                        "sources": len(_homepage_core_sources(homepage_sources)),
                    }
                )
            if len(homepage_sources) < 2:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason=f"homepage accepted sources {len(homepage_sources)} < 2",
                )
            if not homepage_image_pool:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason="homepage research needs >=1 rights-cleared source image",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )

        article_sources: list[dict[str, Any]] = []
        if "article" in selected_lanes:
            for source in _qunar_travelogue_sources(
                entity_id,
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
                platform = _external_platform(link)
                category = _source_category(platform, "authoritative_reference")
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=f"article_authoritative_support_{index}",
                        platform=platform,
                        url=link,
                        category=category,
                        discovery_provider="wikipedia_trusted_extlinks",
                        match_confidence=0.80,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Wikipedia trusted external links", category
                        ),
                        source_role="supporting",
                        images=_image_window(commons, 4 + index, count=3),
                        image_evidence_mode="same_authorized_collection" if commons else "",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
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
                    next_action="agent_repair_or_manual_fetchable_travelogue_provider",
                )
            if len(article_sources) < 4:
                issues.append(f"{entity_id}: article auto plan has {len(article_sources)} source(s), need >=4")
            article_categories = {
                str(source.get("category") or "")
                for source in article_sources
                if str(source.get("category") or "").strip()
            }
            if len(article_categories) < 3:
                issues.append(f"{entity_id}: article categories={len(article_categories)} need>=3")
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
                required_image_works,
                min(8, required_image_works + required_article_bases),
            )
            first_image = (
                _image_at(openverse, 0)
                or _image_at(commons, 0)
                or _image_at(wikidata_commons, 0)
                or _image_at(wiki_page_images, 0)
                or _image_at(voyage_page_images, 0)
            )
            if first_image:
                collection_candidates = openverse + commons + wikidata_commons + wiki_page_images + voyage_page_images
                collection_candidates = sorted(
                    collection_candidates,
                    key=lambda item: str(item.get("url") or "") in homepage_image_urls,
                )
                used_collection_ids: set[str] = set()
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
            if not collections:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no single-author/single-file rights-cleared image collection",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            elif len(collections) < required_image_works:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason=f"image collections={len(collections)} need>={required_image_works}",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            if _write_lane(
                dl / "image_source_plan.json",
                "image",
                {"collections": collections},
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

    ineligible: list[dict[str, Any]] = []
    ready: list[str] = []
    for entity_id in entity_ids:
        blockers = list(unavailable_by_entity.get(entity_id) or [])
        issues = issue_by_entity.get(entity_id) or []
        if blockers or issues:
            lanes = {
                str(item.get("lane") or "")
                for item in blockers
                if item.get("lane")
            }
            lanes.update(lane for lane in (_lane_for_issue(issue) for issue in issues) if lane)
            ineligible.append(
                {
                    "entityId": entity_id,
                    "lanes": sorted(lanes),
                    "issues": issues,
                    "issueReasons": sorted({_normalized_issue(issue) for issue in issues}),
                    "blockers": blockers,
                    "nextActions": sorted({str(item.get("nextAction") or "") for item in blockers if item.get("nextAction")}),
                }
            )
        else:
            ready.append(entity_id)
    return {
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
    }


def _write_auto_report_artifacts(task_id: str, batch_id: str, report: dict[str, Any]) -> None:
    shared_dir = batch_root(task_id, batch_id) / "_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    write_json(shared_dir / _AUTO_DISCOVERY_REPORT, report)
    availability = report.get("sourceAvailability") if isinstance(report.get("sourceAvailability"), dict) else {}
    write_json(shared_dir / "source_unavailable_targets.json", availability)


def _merge_auto_reports(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in ("updated", "issues", "candidates", "imageCollections", "sourceUnavailable"):
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
