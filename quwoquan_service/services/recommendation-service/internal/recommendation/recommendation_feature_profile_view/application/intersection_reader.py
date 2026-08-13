from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol


ALLOWED_INTERSECTION_CLASSES = frozenset({"fact", "affinity"})
ALLOWED_SOCIAL_PROOF_ANCHORS = frozenset({"organizer", "entity", "content", "creator"})
ALLOWED_SUPPLY_KEYS = frozenset(
    {"entity_page_view", "entity_wishlist", "circle_membership", "post_declared_visit"}
)
MAX_INTERSECTION_REASONS = 200


@dataclass(frozen=True, slots=True)
class SubjectIntersectionSnapshot:
    subject_id: str
    intersection_class: str
    channel: str
    reasons: tuple[Mapping[str, Any], ...]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectIntersectionSnapshot:
    subject_id: str
    object_type: str
    object_id: str
    reasons: tuple[Mapping[str, Any], ...]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class IntersectionSupplySnapshot:
    supply_key: str
    distinct_object_count: int
    computed_at: datetime


class IntersectionProjectionStore(Protocol):
    def read_subject_intersections(
        self,
        subject_id: str,
        intersection_class: str,
        channel: str,
    ) -> SubjectIntersectionSnapshot: ...

    def read_object_intersections(
        self,
        subject_id: str,
        object_type: str,
        object_id: str,
    ) -> ObjectIntersectionSnapshot: ...

    def read_intersection_supply(self, supply_key: str) -> IntersectionSupplySnapshot: ...

    def subject_intersection_evidence_digest(self, subject_id: str) -> str: ...

    def object_intersection_evidence_digest(
        self, subject_id: str, object_type: str, object_id: str
    ) -> str: ...

    def intersection_supply_evidence_digest(self) -> str: ...


class SubjectClosureReader(Protocol):
    def exists(self, subject_id: str) -> bool: ...


class SubjectClosedError(RuntimeError):
    """Terminal privacy fence: a closed subject must never be rematerialized."""


class Reader:
    def __init__(
        self,
        store: IntersectionProjectionStore,
        materializer=None,
        subject_closures: SubjectClosureReader | None = None,
    ) -> None:
        if store is None or materializer is None or subject_closures is None:
            raise ValueError("RecommendationFeatureProfileView intersection store is required")
        self._store = store
        self._materializer = materializer
        self._subject_closures = subject_closures

    def _require_open_subject(self, subject_id: str) -> None:
        if self._subject_closures.exists(subject_id):
            raise SubjectClosedError(
                "closed subjects cannot rebuild recommendation intersections"
            )

    def list_subject_intersections(
        self,
        *,
        subject_id: str,
        intersection_class: str,
        channel: str | None,
    ) -> SubjectIntersectionSnapshot:
        normalized_subject = subject_id.strip()
        normalized_class = intersection_class.strip()
        normalized_channel = (channel or "").strip()
        if (
            not normalized_subject
            or normalized_class not in ALLOWED_INTERSECTION_CLASSES
            or len(normalized_channel) > 64
        ):
            raise ValueError("subject intersection query is invalid")
        self._require_open_subject(normalized_subject)
        digest = self._store.subject_intersection_evidence_digest(normalized_subject)
        self._materializer.rebuild_subject(
            source_event_id=f"intersection-subject-evidence:{digest}",
            source_event_digest=digest,
            subject_id=normalized_subject,
            channel=None,
        )
        snapshot = self._store.read_subject_intersections(
            normalized_subject,
            normalized_class,
            normalized_channel,
        )
        self._validate_snapshot(snapshot.reasons, snapshot.generated_at)
        return snapshot

    def list_object_intersections(
        self,
        *,
        subject_id: str,
        object_type: str,
        object_id: str,
    ) -> ObjectIntersectionSnapshot:
        normalized_subject = subject_id.strip()
        normalized_type = object_type.strip()
        normalized_object = object_id.strip()
        if (
            not normalized_subject
            or not normalized_type
            or len(normalized_type) > 64
            or not normalized_object
        ):
            raise ValueError("object intersection query is invalid")
        self._require_open_subject(normalized_subject)
        digest = self._store.object_intersection_evidence_digest(
            normalized_subject,
            normalized_type,
            normalized_object,
        )
        self._materializer.rebuild_object(
            source_event_id=f"intersection-object-evidence:{digest}",
            source_event_digest=digest,
            subject_id=normalized_subject,
            object_type=normalized_type,
            object_id=normalized_object,
        )
        snapshot = self._store.read_object_intersections(
            normalized_subject,
            normalized_type,
            normalized_object,
        )
        self._validate_snapshot(snapshot.reasons, snapshot.generated_at)
        return snapshot

    def get_gathering_social_proof(
        self,
        *,
        anchor_kind: str,
        object_id: str,
    ) -> dict[str, int]:
        """四锚点两级诚实社会证明计数（读时聚合，不落计数缓存）。

        anchorKind 闭集 organizer/entity/content/creator；计数只从发起证据、
        active Participation 与公开回顾事实派生，无内容的行动永远不进经历级。
        """
        anchor = anchor_kind.strip()
        normalized_object = object_id.strip()
        if anchor not in ALLOWED_SOCIAL_PROOF_ANCHORS or not normalized_object:
            raise ValueError("gathering social proof query is invalid")
        return self._store.read_gathering_social_proof(
            anchor_kind=anchor,
            object_id=normalized_object,
        )

    def get_flywheel_funnel(
        self,
        *,
        window_from,
        window_to,
        source_object_kind: str = "",
        source_object_id: str = "",
        capacity_tier: str = "",
        tag_ref: str = "",
    ) -> dict[str, object]:
        """北极星漏斗多维诚实快照（分子分母只从域事实投影派生）。"""
        tier = capacity_tier.strip()
        if tier and tier not in {"duo", "group"}:
            raise ValueError("flywheel funnel capacityTier is invalid")
        return self._store.read_flywheel_funnel(
            window_from=window_from,
            window_to=window_to,
            source_object_kind=source_object_kind.strip(),
            source_object_id=source_object_id.strip(),
            capacity_tier=tier,
            tag_ref=tag_ref.strip(),
        )

    def get_supply(self, *, supply_key: str) -> IntersectionSupplySnapshot:
        normalized_key = supply_key.strip()
        if normalized_key not in ALLOWED_SUPPLY_KEYS:
            raise ValueError("intersection supply key is not canonical")
        digest = self._store.intersection_supply_evidence_digest()
        self._materializer.rebuild_supplies(
            source_event_id=f"intersection-supply-evidence:{digest}",
            source_event_digest=digest,
        )
        snapshot = self._store.read_intersection_supply(normalized_key)
        if snapshot.distinct_object_count < 0 or snapshot.computed_at.tzinfo is None:
            raise RuntimeError("intersection supply projection is invalid")
        return snapshot

    @staticmethod
    def _validate_snapshot(
        reasons: tuple[Mapping[str, Any], ...],
        generated_at: datetime,
    ) -> None:
        if len(reasons) > MAX_INTERSECTION_REASONS or generated_at.tzinfo is None:
            raise RuntimeError("intersection projection is outside the canonical bound")
        if any(not isinstance(reason, Mapping) for reason in reasons):
            raise RuntimeError("intersection projection contains a non-object reason")
