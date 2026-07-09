"""Image and travelogue source discovery providers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import re
import urllib.parse
from typing import Any

from download.research import runtime_bridge as time
from download.research.runtime_bridge import curl_json as _curl_json, curl_text as _curl_text, wiki_api as _wiki_api
from download.research.plan_state import (
    _filter_rejected_images,
    _image_at,
    _image_window,
    _source,
)
from download.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _evidence_reason,
    _image_pixel_issue,
    _known_image_search_hints,
    _license_allows_app_publish,
)
from download.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _expanded_entity_aliases,
    _normalized_title,
    _text_mentions_entity,
    _title_matches_entity,
)
from download.research.wiki_common import (
    _BASE_DRAFT_IMAGE_CANDIDATES,
    _OPENVERSE_API,
    _QUNAR_SEARCH_API,
    _strip_html,
)
from download.research.wiki_core import (
    _claim_string_values,
    _wikidata_claims,
    _wiki_url,
)
from _common.wiki_wikitext import parse_wikitext_placements

_QUNAR_AUTHOR_BOOK_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']*(?:/youji|/travelbook/note)/(\d+)[^\"']*)[\"'][^>]*>(.*?)</a>",
    re.I | re.S,
)
_QUNAR_ANCHOR_TITLE_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*tit-text[^\"']*[\"'][^>]*>(.*?)</p>",
    re.I | re.S,
)
_QUNAR_ANCHOR_TIME_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*tit-time[^\"']*[\"'][^>]*>(.*?)</p>",
    re.I | re.S,
)
_QUNAR_RECENT_YEARS = 3
_QUNAR_ENTITY_SUFFIXES = (
    "长城",
    "攻略",
    "游记",
    "旅行",
    "旅游",
    "自由行",
    "一日游",
    "二日游",
    "三日游",
    "四日游",
    "五日游",
    "夜游",
    "复盘",
    "景区",
    "风景区",
    "风景名胜区",
    "旅游区",
    "文化旅游区",
    "古街",
    "古镇",
    "街区",
    "博物馆",
    "遗址",
    "基地",
    "公园",
)
_QUNAR_ENTITY_SPLIT_RE = re.compile(r"[—－–\-~～/／、,，|]+")
_QUNAR_ENTITY_SEARCH_SUFFIXES = (
    "风景名胜区",
    "文化旅游区",
    "旅游度假区",
    "旅游区",
    "风景区",
    "景区",
)
_QUNAR_FALSE_SUFFIXES = (
    "沟",
    "村",
    "镇",
    "乡",
    "县",
    "市",
    "区",
    "路",
    "站",
)


def _file_match_key(name: str) -> str:
    """统一 File 名匹配键：去命名空间前缀、下划线↔空格归一、大小写无关。

    placement.fileName 无前缀且空格转下划线；imageinfo 返回 title 带 `File:` 前缀且
    用空格。归一后两侧可对齐，把 wikitext 真实图位顺序映射回 imageinfo 结果。
    """
    raw = str(name or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    return raw.replace("_", " ").strip().casefold()

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
                    "modelReleaseStatus": "not_required",
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
                "modelReleaseStatus": "not_required",
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
                    "modelReleaseStatus": "not_required",
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

def _qunar_epoch_to_date(value: Any) -> str:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return ""
    if raw <= 0:
        return ""
    seconds = raw / 1000.0 if raw > 10_000_000_000 else raw
    try:
        return datetime.fromtimestamp(seconds, tz=timezone(timedelta(hours=8))).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return ""

def _qunar_row_published_at(row: dict[str, Any]) -> str:
    for key in ("startTime", "publishTime", "cTime", "uTime"):
        published = _qunar_epoch_to_date(row.get(key))
        if published:
            return published
    return ""

def _qunar_parse_date(value: Any) -> datetime.date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for pattern in (
        r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})",
        r"(?P<y>\d{4})/(?P<m>\d{1,2})/(?P<d>\d{1,2})",
        r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日?",
    ):
        match = re.search(pattern, raw)
        if not match:
            continue
        try:
            return datetime(
                int(match.group("y")),
                int(match.group("m")),
                int(match.group("d")),
                tzinfo=timezone(timedelta(hours=8)),
            ).date()
        except ValueError:
            return None
    return None

def _qunar_freshness_tier(published_at: str) -> str:
    parsed = _qunar_parse_date(published_at)
    if parsed is None:
        return "unknown"
    today = datetime.now(timezone(timedelta(hours=8))).date()
    cutoff = today.replace(year=today.year - _QUNAR_RECENT_YEARS)
    return "recent_3y" if parsed >= cutoff else "stale_over_3y"

def _qunar_entity_anchor(value: str, entity_id: str) -> bool:
    value_key = _normalized_title(value)
    entity_key = _normalized_title(entity_id)
    if not value_key or not entity_key:
        return False
    if value_key == entity_key:
        return True
    for index in [match.start() for match in re.finditer(re.escape(entity_key), value_key)]:
        before = value_key[:index]
        after = value_key[index + len(entity_key):]
        if not after:
            return True
        if any(after.startswith(_normalized_title(suffix)) for suffix in _QUNAR_ENTITY_SUFFIXES):
            return True
        if len(entity_key) <= 2 and any(after.startswith(_normalized_title(suffix)) for suffix in _QUNAR_FALSE_SUFFIXES):
            continue
        if before.endswith(("游", "逛", "到", "去", "看")) and any(
            marker in after for marker in ("攻略", "游记", "旅行", "旅游")
        ):
            return True
    return False

def _qunar_row_anchor_signals(
    row: dict[str, Any],
    *,
    entity_id: str,
    match_terms: list[str],
) -> tuple[bool, bool]:
    title = _strip_html(str(row.get("title") or ""))
    route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
    anchor_terms = _dedupe_terms([entity_id, *match_terms], limit=12)
    title_hit = any(_qunar_entity_anchor(title, term) for term in anchor_terms)
    route_hit = any(
        _qunar_entity_anchor(item, term)
        for item in route
        for term in anchor_terms
    )
    return title_hit, route_hit

def _qunar_source_from_row(
    *,
    row: dict[str, Any],
    entity_id: str,
    source_index: int,
    source_id_prefix: str,
    discovery_provider: str,
    match_confidence: float,
    evidence_reason: str,
) -> dict[str, Any]:
    raw_id = str(row.get("id") or "").strip()
    title = _strip_html(str(row.get("title") or ""))
    route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
    city = _strip_html(str(row.get("cityName") or ""))
    source = _source(
        source_id=f"{source_id_prefix}_{source_index}",
        platform="去哪儿攻略",
        url=f"https://touch.travel.qunar.com/youji/{raw_id}",
        category="travelogue",
        discovery_provider=discovery_provider,
        match_confidence=match_confidence,
        evidence_reason=evidence_reason,
        source_role="base",
        images=[],
        image_evidence_mode="",
    )
    source["title"] = title
    author_name = _strip_html(str(row.get("userName") or row.get("authorName") or ""))
    author_id = str(row.get("userId") or row.get("authorId") or row.get("uid") or "").strip()
    if author_name:
        source["authorName"] = author_name
        source["userName"] = author_name
    if author_id:
        source["authorId"] = author_id
        source["userId"] = author_id
        source["authorBooksUrl"] = f"https://touch.travel.qunar.com/{author_id}/books"
        source["userBooksUrl"] = source["authorBooksUrl"]
    published_at = str(row.get("publishedAt") or "").strip() or _qunar_row_published_at(row)
    if published_at:
        source["publishedAt"] = published_at
    source["sourceFreshnessTier"] = _qunar_freshness_tier(published_at)
    source["routeDays"] = row.get("routeDays") or ""
    source["travelRoute"] = route[:20]
    source["viewCount"] = row.get("viewCount") or 0
    source["sourceUseMode"] = "factual_reference_only"
    source["publishMediaMode"] = "text_only"
    if city:
        source["cityName"] = city
    return source

def _qunar_author_books_rows(
    *,
    author_id: str,
    author_name: str,
    entity_id: str,
    match_terms: list[str],
    seen_ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Read a Qunar author's books page and return additional detail-page rows.

    This is a conservative discovery frontier: it only emits same-author detail
    URLs whose title still anchors the current entity. Same creator context is
    useful, but it must not stitch an author's unrelated routes into this entity.
    """
    if not author_id or limit <= 0:
        return []
    books_url = f"https://touch.travel.qunar.com/{author_id}/books"
    html = _curl_text(books_url, timeout=20)
    if not html:
        return []
    rows: list[dict[str, Any]] = []
    for match in _QUNAR_AUTHOR_BOOK_ANCHOR_RE.finditer(html):
        raw_id = str(match.group(2) or "").strip()
        if not raw_id or raw_id in seen_ids:
            continue
        anchor_html = match.group(3) or ""
        title_match = _QUNAR_ANCHOR_TITLE_RE.search(anchor_html)
        title = _strip_html(title_match.group(1) if title_match else anchor_html)
        time_match = _QUNAR_ANCHOR_TIME_RE.search(anchor_html)
        time_text = _strip_html(time_match.group(1) if time_match else "")
        row = {
            "id": raw_id,
            "title": title,
            "userName": author_name,
            "userId": author_id,
            "publishedAt": time_text,
        }
        title_hit = any(
            _qunar_entity_anchor(title, term) or _title_matches_entity(title, term)
            for term in match_terms
            if term
        )
        if title_hit:
            rows.append(row)
    return rows[:limit]

def _qunar_search_terms(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> list[str]:
    split_terms: list[str] = []
    for part in _QUNAR_ENTITY_SPLIT_RE.split(str(entity_id or "")):
        value = part.strip()
        if len(_normalized_title(value)) < 2:
            continue
        split_terms.append(value)
        for suffix in _QUNAR_ENTITY_SEARCH_SUFFIXES:
            if value.endswith(suffix):
                short = value[: -len(suffix)].strip()
                if len(_normalized_title(short)) >= 2:
                    split_terms.append(short)
                break
    base_terms = _dedupe_terms([*_entity_name_variants(entity_id), *split_terms, *entity_aliases], limit=8)
    primary = str(base_terms[0] if base_terms else entity_id or "").strip()
    primary_intents = [f"{primary}攻略", f"{primary}游记"] if primary else []
    primary_context = [f"{primary}旅游", f"{primary}景区"] if primary else []
    return _dedupe_terms([*primary_intents, *base_terms, *primary_context], limit=limit)

def _qunar_travelogue_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Discover fetchable Qunar travelogue pages for article text evidence.

    RC4：去哪儿 UGC 游记是 text-only 文章底稿，配图必须同源；不再接受外部「授权图集」
    （已删除 authorized_images 死参），images 恒为空、imageEvidenceMode=""。
    """
    sources: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    # Composite scenic areas often have official operation names while UGC uses
    # sub-site or short destination names. Keep enough alias budget to reach
    # curated registry aliases without lowering the downstream entity gate.
    search_terms = _qunar_search_terms(entity_id, entity_aliases=entity_aliases, limit=8)
    match_terms = _dedupe_terms([*_entity_name_variants(entity_id), *entity_aliases, *search_terms], limit=16)
    source_index = 0
    expanded_author_ids: set[str] = set()
    for term in search_terms:
        for page in (1, 2):
            page_candidate_count_before = len(candidates)
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
                title_hit, route_hit = _qunar_row_anchor_signals(
                    row,
                    entity_id=entity_id,
                    match_terms=match_terms,
                )
                if not (title_hit or route_hit):
                    continue
                seen_ids.add(raw_id)
                published_at = str(row.get("publishedAt") or "").strip() or _qunar_row_published_at(row)
                freshness = _qunar_freshness_tier(published_at)
                match_confidence = 0.96 if title_hit else 0.88
                if freshness == "stale_over_3y":
                    match_confidence = min(match_confidence, 0.74)
                candidates.append(
                    {
                        "row": row,
                        "term": term,
                        "title": title,
                        "route": route,
                        "city": city,
                        "titleHit": title_hit,
                        "routeHit": route_hit,
                        "freshness": freshness,
                        "matchConfidence": match_confidence,
                    }
                )
                author_name = _strip_html(str(row.get("userName") or ""))
                author_id = str(row.get("userId") or row.get("authorId") or row.get("uid") or "").strip()
                if author_id and author_id not in expanded_author_ids:
                    expanded_author_ids.add(author_id)
                    expansion_budget = 2
                    for author_row in _qunar_author_books_rows(
                        author_id=author_id,
                        author_name=author_name,
                        entity_id=entity_id,
                        match_terms=match_terms,
                        seen_ids=seen_ids,
                        limit=expansion_budget,
                    ):
                        author_raw_id = str(author_row.get("id") or "").strip()
                        if not author_raw_id or author_raw_id in seen_ids:
                            continue
                        seen_ids.add(author_raw_id)
                        author_title = _strip_html(str(author_row.get("title") or ""))
                        author_title_hit, author_route_hit = _qunar_row_anchor_signals(
                            author_row,
                            entity_id=entity_id,
                            match_terms=match_terms,
                        )
                        if not (author_title_hit or author_route_hit):
                            continue
                        author_freshness = _qunar_freshness_tier(
                            str(author_row.get("publishedAt") or "")
                        )
                        candidates.append(
                            {
                                "row": author_row,
                                "term": f"author:{author_name or author_id}",
                                "title": author_title,
                                "route": [],
                                "city": "",
                                "titleHit": author_title_hit,
                                "routeHit": author_route_hit,
                                "freshness": author_freshness,
                                "matchConfidence": 0.86 if author_freshness != "stale_over_3y" else 0.74,
                                "authorExpansion": True,
                                "authorLabel": author_name or author_id,
                        }
                    )
            if not payload.get("more"):
                break
            if len(candidates) >= limit:
                break
            if len(candidates) == page_candidate_count_before:
                break
    def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
        freshness_rank = {
            "recent_3y": 0,
            "unknown": 1,
            "stale_over_3y": 2,
        }.get(str(item.get("freshness") or ""), 1)
        anchor_rank = 0 if item.get("titleHit") else 1
        route_len = len(item.get("route") or [])
        try:
            views = int(item.get("row", {}).get("viewCount") or 0)
        except (TypeError, ValueError):
            views = 0
        return (
            freshness_rank,
            anchor_rank,
            min(route_len, 20),
            -int(float(item.get("matchConfidence") or 0.0) * 1000),
            -views,
        )

    for item in sorted(candidates, key=_candidate_sort_key):
        if len(sources) >= limit:
            break
        source_index += 1
        row = item["row"]
        provider = (
            "qunar_author_books_page"
            if item.get("authorExpansion")
            else "qunar_touch_search_json"
        )
        reason_prefix = (
            f"去哪儿攻略同作者作品集补源 {entity_id}；author={item.get('authorLabel')};"
            if item.get("authorExpansion")
            else f"去哪儿攻略游记搜索命中 {entity_id}；query={item.get('term')};"
        )
        source = _qunar_source_from_row(
            row=row,
            entity_id=entity_id,
            source_index=source_index,
            source_id_prefix="article_qunar_base",
            discovery_provider=provider,
            match_confidence=float(item.get("matchConfidence") or 0.0),
            evidence_reason=(
                f"{reason_prefix} title={str(item.get('title') or '')[:60]} "
                f"route={','.join((item.get('route') or [])[:6])} city={item.get('city') or ''}; "
                f"freshness={item.get('freshness')}"
            ),
        )
        source["sourceFreshnessTier"] = item.get("freshness") or source.get("sourceFreshnessTier") or "unknown"
        sources.append(source)
    return sources

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
    """实体百科底稿图候选：唯一真相源 = 页面 wikitext `[[File:...]]` 真实图位。

    用 `action=parse&prop=wikitext` 取正文 → `parse_wikitext_placements` 提取真实展示
    File（保留 sourceOrder 与 caption）→ 仅对这些 File 取 imageinfo。跳过视频/音频等
    非图片 transclude。不再用 `prop=images` 全量 transclude（信息框/gallery/导航模板里的
    页面外图会混入），确保 plan 阶段 `wiki_page_images` 的 File 集合 == download 阶段
    `meta.imagePlacements`（同一 `parse_wikitext_placements` 口径），消除「封面/插图不来自
    底稿原文」的真相源分裂。
    """
    if not title:
        return []
    page_url = _wiki_url(host, title)
    parsed = _wiki_api(
        host,
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": 1,
            "format": "json",
        },
    )
    parse_block = parsed.get("parse") if isinstance(parsed, dict) else {}
    wikitext = ""
    if isinstance(parse_block, dict):
        raw_wikitext = parse_block.get("wikitext")
        if isinstance(raw_wikitext, dict):
            wikitext = str(raw_wikitext.get("*") or "")
        else:
            wikitext = str(raw_wikitext or "")
    if not wikitext.strip():
        return []
    _, placements = parse_wikitext_placements(wikitext)
    if not placements:
        return []
    # 按 wikitext 真实展示顺序保留 File（dedupe + 跳过视频/音频/动图/矢量/文档），
    # 仅放行可内联展示的位图（与下游 imageinfo url 扩展名门一致）。
    ordered_titles: list[str] = []
    placement_by_key: dict[str, dict[str, Any]] = {}
    seen_keys: set[str] = set()
    for placement in sorted(placements, key=lambda row: int(row.get("sourceOrder") or 0)):
        raw_name = str(placement.get("fileName") or "").strip()
        if not raw_name:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)$", raw_name, re.I):
            continue  # 跳过 .webm/.ogv/.ogg/.gif/.svg/.pdf 等非位图展示文件
        file_title = raw_name if raw_name.startswith(("File:", "文件:")) else f"File:{raw_name}"
        key = _file_match_key(file_title)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_titles.append(file_title)
        placement_by_key[key] = dict(placement)
    if not ordered_titles:
        return []
    data = _wiki_api(
        host,
        {
            "action": "query",
            "titles": "|".join(ordered_titles[:50]),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        },
    )
    info_pages = (data.get("query") or {}).get("pages") or {}
    info_by_key: dict[str, dict[str, Any]] = {}
    for row in info_pages.values():
        if not isinstance(row, dict):
            continue
        info_by_key[_file_match_key(str(row.get("title") or ""))] = row
    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    # 组感知配额：宫格/表格行图（groupId 非空）成组保完整，不占散图 limit；
    # 散图按 limit 截断；总保险丝防病态页面无限拉图。
    loose_kept = 0
    total_ceiling = max(int(limit) * 6, 48)
    for file_title in ordered_titles:
        key = _file_match_key(file_title)
        row = info_by_key.get(key)
        if not isinstance(row, dict):
            continue
        placement = placement_by_key.get(key, {})
        group_id = str(placement.get("groupId") or "")
        if len(images) >= total_ceiling:
            break
        if not group_id and loose_kept >= limit:
            continue
        info = ((row.get("imageinfo") or [{}])[0] or {})
        url = str(info.get("url") or "")
        if not url or url in seen_urls:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
        license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
        # 许可可发布性以 _license_allows_app_publish 为唯一真相源：公有领域(PD/CC0)即便
        # extmetadata 无 LicenseUrl 也合规可发布，不再用 `not license_url` 误丢真实底稿图。
        if not _license_allows_app_publish(license_name, license_url):
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 640 or height < 426 or max(width, height) < 800:
            continue
        seen_urls.add(url)
        credit = _strip_html(
            ((meta.get("Artist") or {}).get("value") or "")
            or ((meta.get("Credit") or {}).get("value") or "")
            or "Wikimedia contributor"
        )
        source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
        # caption 真相源优先取 wikitext 图位原图注；termsUrl 对无 LicenseUrl 的 PD 图
        # 回退到 Commons 文件描述页（记录 PD/许可与作者，可审计），与 download 阶段
        # `_wikipedia_api_image_assets` 一致，避免合规真实图被 termsUrl 必填门误丢。
        placement_caption = str(placement.get("caption") or "").strip()
        description = placement_caption or _strip_html(
            ((meta.get("ImageDescription") or {}).get("value") or "")
            or str(row.get("title") or "")
        )
        source_order = int(placement.get("sourceOrder") or 0)
        images.append(
            {
                "url": url,
                "platform": "维基导游" if "wikivoyage" in host else "维基百科",
                "license": license_name,
                "credit": credit,
                "sourceUrl": source_url,
                "termsUrl": license_url or source_url,
                "licenseSnapshot": f"{license_name} recorded on {host} file metadata",
                "authorizationProof": source_url,
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
                "width": width,
                "height": height,
                "caption": description[:120] or f"{entity_id} page image",
                "relevance": description[:120] or page_url,
                "creator": credit,
                "collectionPageUrl": page_url,
                "sourceOrder": source_order,
                "fileTitle": file_title,
                # 布局/封面候选语义透传（source.layout.json figure 同源口径）；
                # placeholderId 与 render_source_markdown 的原位占位同一编号。
                "placeholderId": f"source-inline-{source_order + 1:03d}",
                "placementType": str(placement.get("placementType") or "inline"),
                "groupId": group_id,
                "sectionSlug": str(placement.get("sectionSlug") or ""),
                "coverCandidateRank": int(placement.get("coverCandidateRank") or 0),
                "isMapLike": bool(placement.get("isMapLike")),
            }
        )
        if not group_id:
            loose_kept += 1
    return images

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
        time.call(
            "_commons_images",
            _commons_images,
            entity_id,
            entity_aliases=image_aliases,
            limit=commons_limit,
        ),
        rejected_image_urls,
    )
    wikidata_commons = _filter_rejected_images(
        time.call(
            "_wikidata_commons_images",
            _wikidata_commons_images,
            qid,
            entity_id=entity_id,
            entity_aliases=image_aliases,
            limit=wikidata_limit,
        ),
        rejected_image_urls,
    )
    openverse = _filter_rejected_images(
        time.call(
            "_openverse_images",
            _openverse_images,
            entity_id,
            entity_aliases=image_aliases,
            limit=openverse_limit,
        ),
        rejected_image_urls,
    )
    wiki_page_images = _filter_rejected_images(
        time.call(
            "_mediawiki_page_images",
            _mediawiki_page_images,
            "zh.wikipedia.org", wiki_title, entity_id=entity_id, limit=page_limit
        ),
        rejected_image_urls,
    )
    voyage_page_images = _filter_rejected_images(
        time.call(
            "_mediawiki_page_images",
            _mediawiki_page_images,
            "zh.wikivoyage.org", voyage_title, entity_id=entity_id, limit=page_limit
        ),
        rejected_image_urls,
    )
    hint_commons: list[dict[str, Any]] = []
    seen_hint_urls: set[str] = set()
    for category in image_hints["commonsCategories"]:
        for image in time.call(
            "_commons_category_images",
            _commons_category_images,
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
