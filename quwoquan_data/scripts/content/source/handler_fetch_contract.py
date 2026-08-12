"""Typed source-fetch identity, rights, and media-count helpers."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.control_types import ContentType
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)

from content.source.contracts import SourceCandidate


@dataclass(frozen=True, slots=True)
class HomepageBaseDraftAdmission:
    """Typed homepage base-draft verdict shared by fetch and source gates."""

    accepted: bool
    fact_count: int
    issue_code: DataIssueCode | None


def homepage_base_draft_admission(
    source: Mapping[str, Any],
    *,
    source_text: str,
    entity_id: str,
    resolved_title: str,
    minimum_body_chars: int,
    minimum_fact_count: int,
    minimum_fact_chars: int,
) -> HomepageBaseDraftAdmission:
    """Apply the sole homepage base-draft admission contract after fetch."""
    from content.homepage.homepage_text import homepage_base_draft_readiness

    source_meta = dict(source)
    if resolved_title:
        source_meta["resolvedTitle"] = resolved_title
    authority_title = str(
        source_meta.get("qualifiedAuthorityTitle")
        or source_meta.get("sourceTitle")
        or ""
    ).strip()
    readiness = homepage_base_draft_readiness(
        source_meta,
        source_text,
        entity_name=entity_id,
        aliases=(authority_title,) if authority_title else (),
        minimum_body_chars=minimum_body_chars,
        minimum_fact_count=minimum_fact_count,
        minimum_fact_chars=minimum_fact_chars,
    )
    fact_count = int(readiness.get("factCount") or 0)
    if bool(readiness.get("ready")):
        return HomepageBaseDraftAdmission(
            accepted=True,
            fact_count=fact_count,
            issue_code=None,
        )
    return HomepageBaseDraftAdmission(
        accepted=False,
        fact_count=fact_count,
        issue_code=DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
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


def source_content_fidelity_issue(
    source: Mapping[str, Any],
    *,
    entity_id: str,
    rendered_text: str,
    candidate_text: str,
) -> DataIssue | None:
    """Return an object-level rejection without aborting later source candidates."""
    from core.source_fidelity import assess_source_content_fidelity

    fidelity = assess_source_content_fidelity(rendered_text, candidate_text)
    if fidelity.complete:
        return None
    entity_token = re.sub(r"\s+", "", str(entity_id or "")).casefold()
    candidate_token = re.sub(r"\s+", "", str(candidate_text or "")).casefold()
    if (
        entity_token
        and entity_token in candidate_token
        and all(
            entity_token
            not in re.sub(r"\s+", "", paragraph).casefold()
            for paragraph in fidelity.missing_paragraphs
        )
    ):
        # Broad registry-admitted pages can contain unrelated city/province
        # sections that the wikitext renderer intentionally drops.  They are
        # not part of this execution's target evidence.  Preserve the strict
        # gate whenever target-owned prose is absent.
        return None
    raw_lane = str(source.get("researchLane") or DataIssueLane.ALL.value)
    try:
        lane = DataIssueLane(raw_lane)
    except ValueError:
        lane = DataIssueLane.ALL
    return data_issue(
        DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=entity_id,
        lane=lane,
        recovery=DataRecoveryAction.REPLACE_SOURCE,
        message="MediaWiki rendered prose was not preserved in source.clean.md",
        attributes={
            "sourceId": str(source.get("source_id") or ""),
            "authoritativeParagraphCount": fidelity.authoritative_paragraph_count,
            "matchedParagraphCount": fidelity.matched_paragraph_count,
            "missingPreview": fidelity.missing_paragraphs[0][:240],
        },
    )


def require_source_candidate_admission(
    source: Mapping[str, Any],
    *,
    require_commercial_article_binding: bool = False,
) -> SourceCandidate:
    """Decode a planned candidate and refuse a rejected match before fetch."""

    candidate = SourceCandidate.from_mapping(source)
    candidate.require_accepted()
    if require_commercial_article_binding and candidate.lane is ContentType.ARTICLE:
        from content.source.research.article_frontier_profile import (
            resolve_article_source_binding,
        )

        if str(source.get("articleCommercialAdmission") or "") != "commercial_release":
            raise ValueError(
                "commercial article source is not registry-admitted for release"
            )
        resolve_article_source_binding(
            candidate.url,
            site_id=str(source.get("articleSiteId") or ""),
            profile_digest=str(source.get("sourceDiscoveryProfileDigest") or ""),
        )
    return candidate


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
    "homepage_base_draft_admission",
    "is_non_open_baike_source",
    "publishable_homepage_source_image_count",
    "require_source_candidate_admission",
    "requires_factual_compression",
    "source_content_fidelity_issue",
    "source_fetch_failure_issue",
]
