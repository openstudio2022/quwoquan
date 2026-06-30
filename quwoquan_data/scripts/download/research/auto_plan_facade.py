"""Compatibility seam for legacy ``download.research_plan`` monkeypatches."""
from __future__ import annotations

from typing import Any

from download.research import runtime_bridge
from download.research.plan_state import _task_content_quotas as _impl_task_content_quotas
from download.research.source_quality import (
    _known_article_sources as _impl_known_article_sources,
    _known_entity_aliases as _impl_known_entity_aliases,
    _known_homepage_support_websites as _impl_known_homepage_support_websites,
    _known_official_website as _impl_known_official_website,
)
from download.research.wiki_discovery import (
    _discover_open_license_image_pools as _impl_discover_open_license_image_pools,
    _external_article_category as _impl_external_article_category,
    _external_platform as _impl_external_platform,
    _mediawiki_page_images as _impl_mediawiki_page_images,
    _official_website as _impl_official_website,
    _qunar_review_support_source as _impl_qunar_review_support_source,
    _qunar_travelogue_sources as _impl_qunar_travelogue_sources,
    _trusted_external_links as _impl_trusted_external_links,
    _wikidata_entity_aliases as _impl_wikidata_entity_aliases,
    _wikidata_item_for_entity_search as _impl_wikidata_item_for_entity_search,
    _wikidata_item_for_zhwiki as _impl_wikidata_item_for_zhwiki,
    _wiki_related_titles_for_entity as _impl_wiki_related_titles_for_entity,
    _wiki_title_for_entity as _impl_wiki_title_for_entity,
)

def _task_content_quotas(task_id: str) -> dict[str, int]:
    return runtime_bridge.call("_task_content_quotas", _impl_task_content_quotas, task_id)


def _known_article_sources(entity_id: str) -> list[dict[str, str]]:
    return runtime_bridge.call("_known_article_sources", _impl_known_article_sources, entity_id)


def _known_homepage_support_websites(entity_id: str) -> list[dict[str, str]]:
    return runtime_bridge.call(
        "_known_homepage_support_websites",
        _impl_known_homepage_support_websites,
        entity_id,
    )


def _known_entity_aliases(entity_id: str) -> list[str]:
    return runtime_bridge.call("_known_entity_aliases", _impl_known_entity_aliases, entity_id)


def _known_official_website(entity_id: str) -> str:
    return runtime_bridge.call("_known_official_website", _impl_known_official_website, entity_id)


def _wiki_title_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> str:
    return runtime_bridge.call(
        "_wiki_title_for_entity",
        _impl_wiki_title_for_entity,
        host,
        entity_id,
        entity_aliases=entity_aliases,
    )


def _wiki_related_titles_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> list[str]:
    return runtime_bridge.call(
        "_wiki_related_titles_for_entity",
        _impl_wiki_related_titles_for_entity,
        host,
        entity_id,
        entity_aliases=entity_aliases,
    )


def _wikidata_item_for_zhwiki(title: str) -> str:
    return runtime_bridge.call("_wikidata_item_for_zhwiki", _impl_wikidata_item_for_zhwiki, title)


def _wikidata_item_for_entity_search(entity_id: str) -> str:
    return runtime_bridge.call(
        "_wikidata_item_for_entity_search",
        _impl_wikidata_item_for_entity_search,
        entity_id,
    )


def _wikidata_entity_aliases(qid: str) -> list[str]:
    return runtime_bridge.call("_wikidata_entity_aliases", _impl_wikidata_entity_aliases, qid)


def _official_website(qid: str) -> str:
    return runtime_bridge.call("_official_website", _impl_official_website, qid)


def _trusted_external_links(title: str, *, limit: int = 4) -> list[str]:
    return runtime_bridge.call("_trusted_external_links", _impl_trusted_external_links, title, limit=limit)


def _mediawiki_page_images(
    host: str,
    title: str,
    *,
    entity_id: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    return runtime_bridge.call(
        "_mediawiki_page_images",
        _impl_mediawiki_page_images,
        host,
        title,
        entity_id=entity_id,
        limit=limit,
    )


def _qunar_travelogue_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 4,
) -> list[dict[str, Any]]:
    return runtime_bridge.call(
        "_qunar_travelogue_sources",
        _impl_qunar_travelogue_sources,
        entity_id,
        entity_aliases=entity_aliases,
        limit=limit,
    )


def _qunar_review_support_source(entity_id: str) -> dict[str, Any]:
    return runtime_bridge.call(
        "_qunar_review_support_source",
        _impl_qunar_review_support_source,
        entity_id,
    )


def _external_platform(url: str) -> str:
    return runtime_bridge.call("_external_platform", _impl_external_platform, url)


def _external_article_category(url: str, platform: str) -> str:
    return runtime_bridge.call(
        "_external_article_category",
        _impl_external_article_category,
        url,
        platform,
    )


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
    return runtime_bridge.call(
        "_discover_open_license_image_pools",
        _impl_discover_open_license_image_pools,
        entity_id,
        entity_aliases=entity_aliases,
        qid=qid,
        wiki_title=wiki_title,
        voyage_title=voyage_title,
        rejected_image_urls=rejected_image_urls,
        commons_limit=commons_limit,
        wikidata_limit=wikidata_limit,
        openverse_limit=openverse_limit,
        page_limit=page_limit,
    )

