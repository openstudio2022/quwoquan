"""Homepage base-draft source admission policy."""
from __future__ import annotations

import urllib.parse
from typing import Any, Mapping

from core.content_source_registry import (
    homepage_primary_authority_rank,
    homepage_source_can_seed_base_draft,
)
from content.source.research.source_registry import _travel_registry_url_fetchable

_HOMEPAGE_CORE_SOURCE_LIMIT = 5

def _homepage_plan_sort_key(source: Mapping[str, Any]) -> tuple[int, int, str]:
    platform = str(source.get("platform") or "")
    source_kind = str(source.get("sourceKind") or "")
    bucket = (
        homepage_primary_authority_rank(source_kind)
        if homepage_source_can_seed_base_draft(source)
        else 100
    )
    confidence = int(float(source.get("matchConfidence") or 0) * -1000)
    return (bucket, confidence, platform)

def _homepage_core_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """主页正文来源必须先经过 registry 四百科闭集准入。"""
    admitted = [source for source in sources if homepage_source_can_seed_base_draft(source)]
    return sorted(admitted, key=_homepage_plan_sort_key)[:_HOMEPAGE_CORE_SOURCE_LIMIT]

_HOMEPAGE_SUPPORT_ONLY_SOURCE_MARKERS = (
    "权威媒体",
    "媒体",
)

_HOMEPAGE_NON_HOMEPAGE_SOURCE_MARKERS = ("攻略", "游记", "评论", "点评", "小红书", "摄影")

_HOMEPAGE_TEXT_EVIDENCE_REQUIRED_DOMAINS = (
    "baike.baidu.com",
    "baike.sogou.com",
    "baike.com",
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
    return homepage_source_can_seed_base_draft(source)

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
