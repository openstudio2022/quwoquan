"""Image and travelogue source discovery providers."""
from __future__ import annotations

import math
import re
import urllib.parse
from typing import Any

from download.research import runtime_bridge as time
from download.research.runtime_bridge import curl_json as _curl_json, wiki_api as _wiki_api
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
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Discover fetchable Qunar travelogue pages for article text evidence.

    RC4：去哪儿 UGC 游记是 text-only 文章底稿，配图必须同源；不再接受外部「授权图集」
    （已删除 authorized_images 死参），images 恒为空、imageEvidenceMode=""。
    """
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
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
                images: list[dict[str, Any]] = []
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
                    image_evidence_mode="",
                )
                source["title"] = title
                source["authorName"] = _strip_html(str(row.get("userName") or ""))
                source["routeDays"] = row.get("routeDays") or ""
                source["travelRoute"] = route[:20]
                source["viewCount"] = row.get("viewCount") or 0
                source["sourceUseMode"] = "factual_reference_only"
                source["publishMediaMode"] = "text_only"
                sources.append(source)
                if len(sources) >= limit:
                    return sources
            if not payload.get("more"):
                break
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
