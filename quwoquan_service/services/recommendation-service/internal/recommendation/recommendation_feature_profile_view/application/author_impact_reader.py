from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuthorImpactItem:
    impact_id: str
    help_type: str
    action: str
    intersection_dimension: str
    tag_ref: str
    source: str
    count: int
    updated_at: datetime
    representative_content_id: str


@dataclass(frozen=True, slots=True)
class AuthorImpactSummary:
    author_id: str
    total: int
    items: tuple[AuthorImpactItem, ...]


@dataclass(frozen=True, slots=True)
class AuthorImpactEvidence:
    evidence_id: str
    impact_id: str
    content_id: str
    content_type: str
    help_type: str
    action: str
    intersection_dimension: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorImpactEvidencePage:
    impact_id: str
    total_count: int
    items: tuple[AuthorImpactEvidence, ...]
    next_cursor: str | None
    has_more: bool


class AuthorImpactProjectionStore(Protocol):
    def read_author_impact(self, author_id: str, limit: int) -> AuthorImpactSummary: ...

    def read_author_impact_evidence(
        self,
        author_id: str,
        impact_id: str,
        cursor: str | None,
        limit: int,
    ) -> AuthorImpactEvidencePage: ...


class Reader:
    def __init__(self, store: AuthorImpactProjectionStore) -> None:
        if store is None:
            raise ValueError("RecommendationFeatureProfileView store is required")
        self._store = store

    def get_author_impact(self, *, author_id: str, limit: int = 12) -> AuthorImpactSummary:
        normalized_author = author_id.strip()
        if not normalized_author or limit < 1 or limit > 50:
            raise ValueError("author impact query is invalid")
        return self._store.read_author_impact(normalized_author, limit)

    def list_author_impact_evidence(
        self,
        *,
        author_id: str,
        impact_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> AuthorImpactEvidencePage:
        normalized_author = author_id.strip()
        normalized_impact = impact_id.strip()
        normalized_cursor = (cursor or "").strip() or None
        if (
            not normalized_author
            or not normalized_impact
            or limit < 1
            or limit > 50
            or (normalized_cursor is not None and len(normalized_cursor) > 2048)
        ):
            raise ValueError("author impact evidence query is invalid")
        return self._store.read_author_impact_evidence(
            normalized_author,
            normalized_impact,
            normalized_cursor,
            limit,
        )
