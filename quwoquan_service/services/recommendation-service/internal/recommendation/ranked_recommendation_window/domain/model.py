from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping


WINDOW_TTL = timedelta(minutes=10)
MAX_WINDOW_ITEMS = 300
MAX_WINDOW_OBJECT_CARDS = 20


@dataclass(frozen=True, slots=True)
class RankedRecommendationItem:
    ordinal: int
    content_id: str
    score: float
    feature_snapshot_digest: str
    item_feature_snapshot: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    content_id: str
    score: float
    feature_snapshot_digest: str
    item_feature_snapshot: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RecommendationObjectCard:
    object_kind: str
    object_id: str
    title: str
    subtitle: str | None
    cover_url: str | None
    tag_refs: tuple[str, ...]
    reason_key: str
    recall_path: str


@dataclass(frozen=True, slots=True)
class RankingResult:
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    feature_snapshot_at: datetime
    ranking_snapshot_digest: str
    user_feature_snapshot: Mapping[str, Any]
    candidates: tuple[RankedCandidate, ...]
    object_cards: tuple[RecommendationObjectCard, ...] = ()


@dataclass(frozen=True, slots=True)
class RankedRecommendationWindow:
    window_id: str
    subject_id: str
    scenario: str
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    request_digest: str
    ranking_snapshot_digest: str
    feature_snapshot_at: datetime
    user_feature_snapshot: Mapping[str, Any]
    items: tuple[RankedRecommendationItem, ...]
    created_at: datetime
    expires_at: datetime
    object_cards: tuple[RecommendationObjectCard, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        window_id: str,
        subject_id: str,
        scenario: str,
        request_digest: str,
        ranking: RankingResult,
        now: datetime | None = None,
    ) -> "RankedRecommendationWindow":
        created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        normalized_subject = subject_id.strip()
        normalized_scenario = scenario.strip()
        if not all(
            value.strip()
            for value in (
                window_id,
                normalized_subject,
                normalized_scenario,
                ranking.experiment_bucket,
                request_digest,
                ranking.model_bucket,
                ranking.policy_digest,
                ranking.ranking_snapshot_digest,
            )
        ):
            raise ValueError(
                "windowId, subjectId, scenario and ranking snapshot digests are required"
            )
        if ranking.feature_snapshot_at.tzinfo is None:
            raise ValueError("featureSnapshotAt must be timezone-aware")
        if ranking.feature_snapshot_at.astimezone(timezone.utc) > created_at:
            raise ValueError("featureSnapshotAt cannot be later than window creation")
        normalized_bucket = ranking.model_bucket.strip()
        normalized_experiment_bucket = ranking.experiment_bucket.strip()
        if normalized_experiment_bucket not in {"model", "rule"}:
            raise ValueError("experimentBucket must be model or rule")
        if normalized_bucket not in {"model", "rule"}:
            raise ValueError("modelBucket must be model or rule")
        if normalized_bucket == "model" and (
            not ranking.model_channel or not ranking.model_release_id
        ):
            raise ValueError("model ranking requires modelChannel and modelReleaseId")
        if normalized_bucket == "rule" and (
            ranking.model_channel is not None or ranking.model_release_id is not None
        ):
            raise ValueError("rule ranking cannot claim a model channel or release")
        if len(ranking.candidates) > MAX_WINDOW_ITEMS:
            raise ValueError("ranked window must contain at most 300 items")
        if len(ranking.object_cards) > MAX_WINDOW_OBJECT_CARDS:
            raise ValueError("ranked window must contain at most 20 object cards")
        seen: set[str] = set()
        items: list[RankedRecommendationItem] = []
        for ordinal, candidate in enumerate(ranking.candidates):
            normalized_content_id = candidate.content_id.strip()
            if (
                not normalized_content_id
                or normalized_content_id in seen
                or not math.isfinite(float(candidate.score))
                or not candidate.feature_snapshot_digest.strip()
            ):
                raise ValueError("ranked window candidate snapshot is invalid")
            seen.add(normalized_content_id)
            items.append(
                RankedRecommendationItem(
                    ordinal=ordinal,
                    content_id=normalized_content_id,
                    score=float(candidate.score),
                    feature_snapshot_digest=candidate.feature_snapshot_digest.strip(),
                    item_feature_snapshot=dict(candidate.item_feature_snapshot),
                )
            )
        return cls(
            window_id=window_id.strip(),
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            experiment_bucket=normalized_experiment_bucket,
            model_bucket=normalized_bucket,
            model_channel=ranking.model_channel.strip() if ranking.model_channel else None,
            model_release_id=(
                ranking.model_release_id.strip() if ranking.model_release_id else None
            ),
            policy_digest=ranking.policy_digest.strip(),
            request_digest=request_digest.strip(),
            ranking_snapshot_digest=ranking.ranking_snapshot_digest.strip(),
            feature_snapshot_at=ranking.feature_snapshot_at.astimezone(timezone.utc),
            user_feature_snapshot=dict(ranking.user_feature_snapshot),
            items=tuple(items),
            created_at=created_at,
            expires_at=created_at + WINDOW_TTL,
            object_cards=cls._validate_object_cards(ranking.object_cards),
        )

    @staticmethod
    def _validate_object_cards(
        cards: tuple[RecommendationObjectCard, ...],
    ) -> tuple[RecommendationObjectCard, ...]:
        normalized: list[RecommendationObjectCard] = []
        seen: set[tuple[str, str]] = set()
        for card in cards:
            object_kind = card.object_kind.strip()
            object_id = card.object_id.strip()
            title = card.title.strip()
            reason_key = card.reason_key.strip()
            recall_path = card.recall_path.strip()
            identity = (object_kind, object_id)
            if (
                object_kind not in {"entity_homepage", "gathering"}
                or not object_id
                or identity in seen
                or not title
                or not reason_key
                or not recall_path
                or any(not tag.strip() for tag in card.tag_refs)
                or len(set(card.tag_refs)) != len(card.tag_refs)
            ):
                raise ValueError("ranked window object card snapshot is invalid")
            seen.add(identity)
            normalized.append(
                RecommendationObjectCard(
                    object_kind=object_kind,
                    object_id=object_id,
                    title=title,
                    subtitle=(card.subtitle.strip() if card.subtitle else None),
                    cover_url=(card.cover_url.strip() if card.cover_url else None),
                    tag_refs=tuple(tag.strip() for tag in card.tag_refs),
                    reason_key=reason_key,
                    recall_path=recall_path,
                )
            )
        return tuple(normalized)

    def page(self, *, from_ordinal: int, limit: int) -> tuple[tuple[RankedRecommendationItem, ...], int | None]:
        if from_ordinal < 0 or limit <= 0 or limit > 100:
            raise ValueError("fromOrdinal and limit are outside the accepted range")
        page_items = self.items[from_ordinal : from_ordinal + limit]
        next_ordinal = from_ordinal + len(page_items)
        if next_ordinal >= len(self.items):
            next_ordinal = None
        return page_items, next_ordinal
