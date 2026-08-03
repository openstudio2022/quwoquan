from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping, Protocol

from generated.recommendation.recommendation_feature_profile_view.models.request_response import (
    IntersectionReason,
)

from .intersection_reader import (
    ALLOWED_INTERSECTION_CLASSES,
    ALLOWED_SUPPLY_KEYS,
    MAX_INTERSECTION_REASONS,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SubjectIntersectionMaterialization:
    source_event_id: str
    source_event_digest: str
    subject_id: str
    intersection_class: str
    channel: str
    reasons: tuple[Mapping[str, Any], ...]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectIntersectionMaterialization:
    source_event_id: str
    source_event_digest: str
    subject_id: str
    object_type: str
    object_id: str
    reasons: tuple[Mapping[str, Any], ...]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class IntersectionSupplyMaterialization:
    source_event_id: str
    source_event_digest: str
    supply_key: str
    distinct_object_count: int
    computed_at: datetime


class IntersectionProjectionWriter(Protocol):
    def replace_subject_intersections_if_absent(
        self, mutation: SubjectIntersectionMaterialization
    ) -> bool: ...

    def replace_object_intersections_if_absent(
        self, mutation: ObjectIntersectionMaterialization
    ) -> bool: ...

    def replace_intersection_supply_if_absent(
        self, mutation: IntersectionSupplyMaterialization
    ) -> bool: ...


class Projector:
    """Materializes complete snapshots; partial patches are deliberately unsupported."""

    def __init__(self, store: IntersectionProjectionWriter) -> None:
        if store is None:
            raise ValueError("Recommendation intersection projection store is required")
        self._store = store

    def replace_subject_snapshot(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        subject_id: str,
        intersection_class: str,
        channel: str | None,
        reasons: tuple[Mapping[str, Any], ...],
        generated_at: datetime,
    ) -> bool:
        event_id, digest = _source_identity(source_event_id, source_event_digest)
        normalized_subject = subject_id.strip()
        normalized_class = intersection_class.strip()
        normalized_channel = (channel or "").strip()
        if (
            not normalized_subject
            or normalized_class not in ALLOWED_INTERSECTION_CLASSES
            or len(normalized_channel) > 64
        ):
            raise ValueError("subject intersection materialization identity is invalid")
        normalized_reasons = _validate_reasons(
            reasons,
            expected_subject=normalized_subject,
            expected_class=normalized_class,
        )
        _aware(generated_at, "generatedAt")
        return self._store.replace_subject_intersections_if_absent(
            SubjectIntersectionMaterialization(
                source_event_id=event_id,
                source_event_digest=digest,
                subject_id=normalized_subject,
                intersection_class=normalized_class,
                channel=normalized_channel,
                reasons=normalized_reasons,
                generated_at=generated_at,
            )
        )

    def replace_object_snapshot(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        subject_id: str,
        object_type: str,
        object_id: str,
        reasons: tuple[Mapping[str, Any], ...],
        generated_at: datetime,
    ) -> bool:
        event_id, digest = _source_identity(source_event_id, source_event_digest)
        normalized_subject = subject_id.strip()
        normalized_type = object_type.strip()
        normalized_object = object_id.strip()
        if (
            not normalized_subject
            or not normalized_type
            or len(normalized_type) > 64
            or not normalized_object
        ):
            raise ValueError("object intersection materialization identity is invalid")
        normalized_reasons = _validate_reasons(
            reasons,
            expected_subject=normalized_subject,
            expected_class=None,
        )
        _aware(generated_at, "generatedAt")
        return self._store.replace_object_intersections_if_absent(
            ObjectIntersectionMaterialization(
                source_event_id=event_id,
                source_event_digest=digest,
                subject_id=normalized_subject,
                object_type=normalized_type,
                object_id=normalized_object,
                reasons=normalized_reasons,
                generated_at=generated_at,
            )
        )

    def replace_supply_snapshot(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        supply_key: str,
        distinct_object_count: int,
        computed_at: datetime,
    ) -> bool:
        event_id, digest = _source_identity(source_event_id, source_event_digest)
        normalized_key = supply_key.strip()
        if normalized_key not in ALLOWED_SUPPLY_KEYS or distinct_object_count < 0:
            raise ValueError("intersection supply materialization is invalid")
        _aware(computed_at, "computedAt")
        return self._store.replace_intersection_supply_if_absent(
            IntersectionSupplyMaterialization(
                source_event_id=event_id,
                source_event_digest=digest,
                supply_key=normalized_key,
                distinct_object_count=distinct_object_count,
                computed_at=computed_at,
            )
        )


def _source_identity(source_event_id: str, source_event_digest: str) -> tuple[str, str]:
    event_id = source_event_id.strip()
    digest = source_event_digest.strip().lower()
    if not event_id or len(event_id) > 512 or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("intersection projection source identity is invalid")
    return event_id, digest


def _validate_reasons(
    reasons: tuple[Mapping[str, Any], ...],
    *,
    expected_subject: str,
    expected_class: str | None,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(reasons, tuple) or len(reasons) > MAX_INTERSECTION_REASONS:
        raise ValueError("intersection reason snapshot exceeds the canonical bound")
    identities: set[str] = set()
    normalized: list[Mapping[str, Any]] = []
    for raw in reasons:
        if not isinstance(raw, Mapping):
            raise ValueError("intersection reason must be an object")
        try:
            reason = IntersectionReason.model_validate(dict(raw)).model_dump(mode="python")
        except Exception as error:
            raise ValueError("intersection reason violates the canonical contract") from error
        identity = str(reason.get("intersectionId") or "").strip()
        reason_class = str(reason.get("intersectionClass") or "").strip()
        reason_subject = str(reason.get("subjectId") or "").strip()
        if not identity or identity in identities:
            raise ValueError("intersection reason identity must be non-empty and unique")
        if reason_class not in ALLOWED_INTERSECTION_CLASSES:
            raise ValueError("intersection reason class is invalid")
        if expected_class is not None and reason_class != expected_class:
            raise ValueError("intersection reason class does not match snapshot")
        if reason_subject and reason_subject != expected_subject:
            raise ValueError("intersection reason subject does not match snapshot")
        identities.add(identity)
        normalized.append(reason)
    return tuple(normalized)


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"intersection projection {name} must be timezone-aware")
