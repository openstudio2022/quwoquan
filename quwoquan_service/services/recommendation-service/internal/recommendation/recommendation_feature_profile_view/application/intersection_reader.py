from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol


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
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if store is None or materializer is None or subject_closures is None:
            raise ValueError("RecommendationFeatureProfileView intersection store is required")
        self._store = store
        self._materializer = materializer
        self._subject_closures = subject_closures
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _expiry_refresh_marker(self, reasons: tuple[Mapping[str, Any], ...]) -> str:
        """过期触发重算（REQ-004 / SIT-004.t2）的 receipt 标记。

        物化收据按 (source_event_id, digest) create-once：evidence 不变时快照不会重写，
        过期的 expiresAt 会一直留在快照里。这里在当前快照存在任一 `expiresAt <= now` 的
        reason 时，把最早过期的 expiresAt 拼进 source_event_id，使 projector 产生新的
        收据并真正重物化；同一份过期快照在重物化前得到同一个标记（幂等，不会重复写），
        重物化后 expiresAt 前移、标记为空，回到纯 evidence digest 的 create-once 路径。
        """
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expired: list[str] = []
        for reason in reasons:
            if not isinstance(reason, Mapping):
                continue
            raw = str(reason.get("expiresAt") or "").strip()
            if not raw:
                continue
            try:
                expires_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                expired.append(raw)
        if not expired:
            return ""
        return f":refresh:{min(expired)}"

    def _current_reasons(self, read) -> tuple[Mapping[str, Any], ...]:
        """重物化前窥视当前快照；投影尚未物化（首读）时没有可过期的 reason。"""
        try:
            return tuple(read().reasons)
        except RuntimeError:
            return ()

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
        refresh = self._expiry_refresh_marker(
            self._current_reasons(
                lambda: self._store.read_subject_intersections(
                    normalized_subject,
                    normalized_class,
                    normalized_channel,
                )
            )
        )
        self._materializer.rebuild_subject(
            source_event_id=f"intersection-subject-evidence:{digest}{refresh}",
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
        refresh = self._expiry_refresh_marker(
            self._current_reasons(
                lambda: self._store.read_object_intersections(
                    normalized_subject,
                    normalized_type,
                    normalized_object,
                )
            )
        )
        self._materializer.rebuild_object(
            source_event_id=f"intersection-object-evidence:{digest}{refresh}",
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
