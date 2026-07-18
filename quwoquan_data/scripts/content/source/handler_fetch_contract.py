"""Typed source-fetch identity, rights, and media-count helpers."""
from __future__ import annotations

import re
from typing import Any, Mapping

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def resolved_source_title_matches_entity(
    source: Mapping[str, Any],
    *,
    resolved_title: str,
    entity_id: str,
) -> bool:
    """Validate a resolved wiki title against the frozen candidate identity."""
    from content.source.research.text_match import _wiki_resolved_title_matches_entity

    candidate_title = str(source.get("sourceTitle") or "").strip()
    return _wiki_resolved_title_matches_entity(
        resolved_title,
        entity_id,
    ) or bool(
        candidate_title
        and _wiki_resolved_title_matches_entity(resolved_title, candidate_title)
    )


def source_fetch_failure_issue(
    source: Mapping[str, Any],
    *,
    entity_id: str,
    error: Exception,
) -> DataIssue:
    raw_lane = str(source.get("researchLane") or DataIssueLane.ALL.value)
    try:
        lane = DataIssueLane(raw_lane)
    except ValueError:
        lane = DataIssueLane.ALL
    return data_issue(
        DataIssueCode.SOURCE_UNREADABLE,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=entity_id,
        lane=lane,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="source adapter failed to return a readable payload",
        attributes={
            "sourceId": str(source.get("source_id") or ""),
            "errorType": type(error).__name__,
            "detail": str(error)[:240],
        },
    )


def canonicalize_source_url(url: str) -> str:
    """Normalize a source URL into the per-entity deduplication key."""
    text = str(url or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"^https?://", "", text)
    text = text.split("#", 1)[0].split("?", 1)[0]
    return text.rstrip("/")


def is_non_open_baike_source(source: Mapping[str, Any]) -> bool:
    """Resolve rights mode from explicit sourceKind, never from host guessing."""
    from core.baike_source_contract import SOURCE_USE_MODES

    source_kind = str(source.get("sourceKind") or "")
    return SOURCE_USE_MODES.get(source_kind) == "factual_reference_only"


def requires_factual_compression(source: Mapping[str, Any]) -> bool:
    """Resolve encyclopedia compression from the registry source-use mode."""
    return is_non_open_baike_source(source)


def publishable_homepage_source_image_count(images: list[dict[str, Any]]) -> int:
    """Count same-source images that may enter the homepage visual surface."""
    count = 0
    for image in images:
        if bool(image.get("isMapLike")):
            continue
        if str(image.get("placementType") or "") == "locatorMap":
            continue
        try:
            if int(image.get("coverCandidateRank") or 0) < 0:
                continue
        except (TypeError, ValueError):
            continue
        count += 1
    return count


__all__ = [
    "canonicalize_source_url",
    "is_non_open_baike_source",
    "publishable_homepage_source_image_count",
    "requires_factual_compression",
    "resolved_source_title_matches_entity",
    "source_fetch_failure_issue",
]
