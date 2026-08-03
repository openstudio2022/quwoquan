from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RecommendationObjectCardCandidate:
    homepage_id: str
    canonical_entity_id: str
    title: str
    subtitle: str | None
    cover_url: str | None
    tag_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateLifecycleSnapshot:
    scenario: str
    content_id: str
    content_type: str
    author_id: str
    tag_refs: tuple[str, ...]
    entity_refs: tuple[str, ...]
    published_at: datetime
    content_vertical: str | None
    entity_tag_ids: tuple[str, ...]
    source_sequence: int
    updated_at: datetime
    object_card: RecommendationObjectCardCandidate | None = None


@dataclass(frozen=True, slots=True)
class PremiumAdmissionSnapshot:
    content_id: str
    status: str
    scope: str
    quality_admission: str
    quality_score: float
    supply_source: str | None
    source_task_id: str | None
    audit_id: str
    rollback_token: str
    featured_at: datetime
    expires_at: datetime
    takedown_ejected: bool
    updated_at: datetime

    def eligible_at(self, now: datetime) -> bool:
        return (
            self.status == "active"
            and self.scope == "global"
            and self.quality_admission == "approved"
            and self.quality_score >= 0.75
            and not self.takedown_ejected
            and self.expires_at > now
        )


class CandidateIndexStore(Protocol):
    def remove_if_newer(self, *, scenario: str, content_id: str, source_sequence: int) -> bool: ...

    def upsert_lifecycle_if_newer(self, snapshot: CandidateLifecycleSnapshot) -> bool: ...

    def apply_premium_source_event(
        self,
        *,
        event_id: str,
        snapshot: PremiumAdmissionSnapshot,
    ) -> bool: ...


class Projector:
    def __init__(self, store: CandidateIndexStore) -> None:
        self._store = store

    def project_lifecycle(self, snapshot: CandidateLifecycleSnapshot) -> bool:
        if not all(
            value.strip()
            for value in (
                snapshot.scenario,
                snapshot.content_id,
                snapshot.content_type,
                snapshot.author_id,
            )
        ):
            raise ValueError("candidate lifecycle identity and author are required")
        if (
            snapshot.published_at.tzinfo is None
            or snapshot.updated_at.tzinfo is None
            or snapshot.source_sequence <= 0
        ):
            raise ValueError("candidate lifecycle time and sourceSequence are required")
        for values in (snapshot.tag_refs, snapshot.entity_refs, snapshot.entity_tag_ids):
            if any(not value.strip() for value in values) or len(set(values)) != len(values):
                raise ValueError("candidate lifecycle references must be non-empty and unique")
        if snapshot.object_card is not None:
            card = snapshot.object_card
            if not all(
                value.strip()
                for value in (card.homepage_id, card.canonical_entity_id, card.title)
            ):
                raise ValueError("recommendation object card candidate is incomplete")
            if any(not value.strip() for value in card.tag_refs) or len(
                set(card.tag_refs)
            ) != len(card.tag_refs):
                raise ValueError("recommendation object card tags must be unique")
        return self._store.upsert_lifecycle_if_newer(snapshot)

    def remove(self, *, scenario: str, content_id: str, source_sequence: int) -> bool:
        if not scenario.strip() or not content_id.strip() or source_sequence <= 0:
            raise ValueError("candidate removal identity and sourceSequence are required")
        return self._store.remove_if_newer(
            scenario=scenario,
            content_id=content_id,
            source_sequence=source_sequence,
        )

    def apply_premium_source_event(
        self,
        *,
        event_id: str,
        snapshot: PremiumAdmissionSnapshot,
    ) -> bool:
        if not event_id.strip() or not all(
            value.strip()
            for value in (
                snapshot.content_id,
                snapshot.status,
                snapshot.scope,
                snapshot.quality_admission,
                snapshot.audit_id,
                snapshot.rollback_token,
            )
        ):
            raise ValueError("premium admission identity and audit fields are required")
        if snapshot.status not in {"active", "rolled_back", "takedown_ejected"}:
            raise ValueError("premium admission status is invalid")
        if snapshot.scope != "global" or snapshot.quality_admission != "approved":
            raise ValueError("premium admission scope and quality decision are invalid")
        if not math.isfinite(snapshot.quality_score) or snapshot.quality_score < 0:
            raise ValueError("premium admission qualityScore must be finite and non-negative")
        if any(
            value.tzinfo is None
            for value in (snapshot.featured_at, snapshot.expires_at, snapshot.updated_at)
        ):
            raise ValueError("premium admission timestamps must be timezone-aware")
        if snapshot.expires_at <= snapshot.featured_at:
            raise ValueError("premium admission expiresAt must follow featuredAt")
        if snapshot.status == "active" and snapshot.takedown_ejected:
            raise ValueError("active premium admission cannot be takedown-ejected")
        if snapshot.status == "takedown_ejected" and not snapshot.takedown_ejected:
            raise ValueError("takedown premium admission must carry takedownEjected")
        return self._store.apply_premium_source_event(
            event_id=event_id,
            snapshot=snapshot,
        )
