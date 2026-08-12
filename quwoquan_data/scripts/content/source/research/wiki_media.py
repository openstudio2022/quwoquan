"""Image and travelogue source discovery providers."""
from __future__ import annotations

import re
from typing import Any

from core.runtime_policy import active_runtime_policy
from core.wiki_wikitext import parse_wikitext_placements

from content.source.mediawiki_page import fetch_mediawiki_page_bundle
from content.source.research import network_io
from content.source.research.image_search_providers import (
    _commons_category_images,
    _commons_images,
    _openverse_images,
    _wikidata_commons_images,
)
from content.source.research.reject_memory import _filter_rejected_images
from content.source.research.source_registry import _known_image_search_hints
from content.source.research.text_match import _expanded_entity_aliases
from content.source.research.wiki_common import _canonical_terms_url, _strip_html
from content.source.research.wiki_core import _wiki_url
from content.source.research.wiki_media_subjects import (
    wikimedia_subject_evidence_by_file,
)

_OPENVERSE_HTTP_TIMEOUT_SECONDS = active_runtime_policy().provider_timeouts.openverse_seconds


def _file_match_key(name: str) -> str:
    """统一 File 名匹配键：去命名空间前缀、下划线↔空格归一、大小写无关。

    placement.fileName 无前缀且空格转下划线；imageinfo 返回 title 带 `File:` 前缀且
    用空格。归一后两侧可对齐，把 wikitext 真实图位顺序映射回 imageinfo 结果。
    """
    raw = str(name or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    return raw.replace("_", " ").strip().casefold()

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
    bundle = fetch_mediawiki_page_bundle(host, title)
    if bundle is None or not bundle.wikitext or not bundle.rendered_text:
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
        if not re.search(r"\.(?:jpe?g|png|webp)$", raw_name, re.IGNORECASE):
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
    subject_evidence_by_key = wikimedia_subject_evidence_by_file(info_by_key)
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
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.IGNORECASE):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value") or "")
        raw_license_url = _strip_html(
            (meta.get("LicenseUrl") or {}).get("value") or ""
        )
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        seen_urls.add(url)
        credit = _strip_html(
            ((meta.get("Artist") or {}).get("value") or "")
            or ((meta.get("Credit") or {}).get("value") or "")
            or "Wikimedia contributor"
        )
        source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
        license_url = _canonical_terms_url(
            raw_license_url,
            license_name=license_name,
            source_url=source_url,
        )
        # caption 真相源优先取 wikitext 图位原图注；termsUrl 对无 LicenseUrl 的 PD 图
        # 回退到 Commons 文件描述页（记录 PD/许可与作者，可审计），避免合规真实图
        # 被 termsUrl 必填门误丢。
        placement_caption = _strip_html(str(placement.get("caption") or ""))
        commons_description = _strip_html(
            (meta.get("ImageDescription") or {}).get("value") or ""
        )
        commons_categories = _strip_html(
            (meta.get("Categories") or {}).get("value") or ""
        )
        description = (
            placement_caption
            or commons_description
            or str(row.get("title") or "")
        )
        visual_subject = " ".join(
            value
            for value in (commons_description, commons_categories)
            if value
        ) or description
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
                # 图位 caption 说明文章中的摆放语义；Commons 原图描述与
                # 分类说明画面主体。两者不得互相覆盖，后者作为 provider
                # 元数据冻结后供 article asset semantic admission 使用。
                "visualSubject": visual_subject[:500],
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
                "visualSubjectEvidence": list(subject_evidence_by_key.get(key, ())),
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
