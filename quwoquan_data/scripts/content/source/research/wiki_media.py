"""Image and travelogue source discovery providers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
import urllib.parse
from typing import Any

from core.runtime_policy import active_runtime_policy
from content.source.research import network_io
from content.source.research.plan_state import (
    _filter_rejected_images,
    _image_at,
    _image_window,
)
from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _evidence_reason,
    _image_pixel_issue,
    _license_allows_app_publish,
)
from content.source.research.source_registry import _known_image_search_hints
from content.source.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _expanded_entity_aliases,
    _normalized_title,
    _text_mentions_entity,
)
from content.source.research.wiki_common import (
    _BASE_DRAFT_IMAGE_CANDIDATES,
    _OPENVERSE_API,
    _strip_html,
)
from content.source.research.wiki_core import (
    _claim_string_values,
    _wikidata_claims,
    _wiki_url,
)
from core.wiki_wikitext import parse_wikitext_placements

_OPENVERSE_HTTP_TIMEOUT_SECONDS = active_runtime_policy().provider_timeouts.openverse_seconds


@dataclass(frozen=True, slots=True)
class MediaWikiPageBundle:
    requested_title: str
    resolved_title: str
    page_id: int
    revision_id: int
    content_sha256: str
    rendered_html: str
    wikitext: str
    rendered_image_titles: tuple[str, ...]


def _mediawiki_page_bundle(host: str, title: str) -> MediaWikiPageBundle | None:
    payload = network_io.wiki_api(
        host,
        {
            "action": "parse",
            "page": title,
            "prop": "text|wikitext|images",
            "redirects": 1,
            "format": "json",
        },
    )
    parse_block = payload.get("parse") if isinstance(payload, dict) else None
    if not isinstance(parse_block, dict):
        return None

    def _star_value(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("*") or "")
        return str(value or "")

    rendered_titles = tuple(
        str(value).strip()
        for value in (parse_block.get("images") or [])
        if str(value).strip()
    )
    wikitext = _star_value(parse_block.get("wikitext"))
    rendered_html = _star_value(parse_block.get("text"))
    return MediaWikiPageBundle(
        requested_title=title,
        resolved_title=str(parse_block.get("title") or title),
        page_id=int(parse_block.get("pageid") or 0),
        revision_id=int(parse_block.get("revid") or 0),
        content_sha256=hashlib.sha256(wikitext.encode("utf-8")).hexdigest(),
        rendered_html=rendered_html,
        wikitext=wikitext,
        rendered_image_titles=rendered_titles,
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
        data = network_io.wiki_api(
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
    data = network_io.wiki_api(
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
    data = network_io.wiki_api(
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
    here before a candidate can enter any source content.execution.planning.
    """
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in _image_search_terms(entity_id, entity_aliases, limit=4):
        params = urllib.parse.urlencode({"q": term, "page_size": min(max(limit * 3, 5), 50)})
        data = network_io.curl_json(
            f"{_OPENVERSE_API}?{params}",
            timeout=_OPENVERSE_HTTP_TIMEOUT_SECONDS,
        )
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

def _mediawiki_page_images(
    host: str,
    title: str,
    *,
    entity_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """实体百科底稿图候选：单次页面 bundle + 强类型 placement。

    同一次 ``action=parse`` 取得 rendered HTML、wikitext、页面身份与 rendered image
    titles；wikitext 负责段落锚点和原图注，rendered titles 负责确认模板展开后的图片确实
    出现在页面。imageinfo 只补原图字节、许可与 Commons 描述，不再形成第二条枚举路径。
    """
    if not title:
        return []
    page_url = _wiki_url(host, title)
    bundle = _mediawiki_page_bundle(host, title)
    if bundle is None or not bundle.wikitext.strip() or not bundle.rendered_html.strip():
        return []
    _, placements = parse_wikitext_placements(bundle.wikitext)
    if not placements:
        return []
    # 按 wikitext 真实展示顺序保留 File（dedupe + 跳过视频/音频/动图/矢量/文档），
    # 仅放行可内联展示的位图（与下游 imageinfo url 扩展名门一致）。
    ordered_titles: list[str] = []
    placement_by_key: dict[str, dict[str, Any]] = {}
    rendered_keys = {_file_match_key(value) for value in bundle.rendered_image_titles}
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
        if rendered_keys and key not in rendered_keys:
            continue
        seen_keys.add(key)
        ordered_titles.append(file_title)
        placement_by_key[key] = dict(placement)
    if not ordered_titles:
        return []
    info_by_key: dict[str, dict[str, Any]] = {}
    requested_titles = ordered_titles if limit is None else ordered_titles[: max(0, int(limit))]
    for start in range(0, len(requested_titles), 50):
        data = network_io.wiki_api(
            host,
            {
                "action": "query",
                "titles": "|".join(requested_titles[start : start + 50]),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "format": "json",
            },
        )
        info_pages = (data.get("query") or {}).get("pages") or {}
        for row in info_pages.values():
            if not isinstance(row, dict):
                continue
            info_by_key[_file_match_key(str(row.get("title") or ""))] = row
    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    # 页面自有图片必须全部归因；外部调用只有显式 limit 时才截取支持来源。
    for file_title in requested_titles:
        key = _file_match_key(file_title)
        row = info_by_key.get(key)
        if not isinstance(row, dict):
            continue
        placement = placement_by_key.get(key, {})
        group_id = str(placement.get("groupId") or "")
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
        # 回退到 Commons 文件描述页（记录 PD/许可与作者，可审计），避免合规真实图
        # 被 termsUrl 必填门误丢。
        placement_caption = _strip_html(str(placement.get("caption") or ""))
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
                "pageResolvedTitle": bundle.resolved_title,
                "pageId": bundle.page_id,
                "pageRevisionId": bundle.revision_id,
                "pageContentSha256": bundle.content_sha256,
                "renderedImageCount": len(bundle.rendered_image_titles),
                "sourceOrder": source_order,
                "fileTitle": file_title,
                # 布局/封面候选语义透传（source.layout.json figure 同源口径）；
                # placeholderId 与 render_source_markdown 的原位占位同一编号。
                "placeholderId": f"source-inline-{source_order + 1:03d}",
                "placementType": str(placement.get("placementType") or "inline"),
                "groupId": group_id,
                "sectionSlug": str(placement.get("sectionSlug") or ""),
                "coverCandidateRank": int(placement.get("coverCandidateRank") or 0),
                "subjectKey": str(placement.get("subjectKey") or ""),
                "isMapLike": bool(placement.get("isMapLike")),
            }
        )
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
    page_limit: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Discover publishable open-license image candidates from primary pools."""

    image_hints = _known_image_search_hints(entity_id)
    image_aliases = _expanded_entity_aliases(
        [*entity_aliases, *image_hints["aliases"]],
        limit=max(24, len(entity_aliases) + len(image_hints["aliases"])),
    )
    commons = _filter_rejected_images(
        _commons_images(
            entity_id,
            entity_aliases=image_aliases,
            limit=commons_limit,
        ),
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
        _openverse_images(
            entity_id,
            entity_aliases=image_aliases,
            limit=openverse_limit,
        ),
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
