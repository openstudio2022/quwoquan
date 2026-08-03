# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    ObjectIntersectionMaterialization,
    Projector,
    SubjectIntersectionMaterialization,
)
from tests.support.intersection_reason import canonical_intersection_reason


class _Store:
    def __init__(self) -> None:
        self.subject: SubjectIntersectionMaterialization | None = None
        self.object: ObjectIntersectionMaterialization | None = None

    def replace_subject_intersections_if_absent(
        self, mutation: SubjectIntersectionMaterialization
    ) -> bool:
        self.subject = mutation
        return True

    def replace_object_intersections_if_absent(
        self, mutation: ObjectIntersectionMaterialization
    ) -> bool:
        self.object = mutation
        return True

    def replace_intersection_supply_if_absent(self, _mutation) -> bool:
        return True


def test_intersection_projector_accepts_only_complete_canonical_snapshots() -> None:
    store = _Store()
    projector = Projector(store)
    digest = hashlib.sha256(b"event-001").hexdigest()
    generated_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)

    assert projector.replace_subject_snapshot(
        source_event_id="event-001",
        source_event_digest=digest,
        subject_id="persona-001",
        intersection_class="fact",
        channel="feed",
        reasons=(canonical_intersection_reason(),),
        generated_at=generated_at,
    )
    assert store.subject is not None
    assert store.subject.reasons[0]["intersectionId"] == "intersection-001"

    assert projector.replace_object_snapshot(
        source_event_id="event-001",
        source_event_digest=digest,
        subject_id="persona-001",
        object_type="post",
        object_id="post-001",
        reasons=(canonical_intersection_reason(),),
        generated_at=generated_at,
    )
    assert store.object is not None
    assert store.object.object_id == "post-001"

    incomplete = canonical_intersection_reason()
    incomplete.pop("primaryText")
    with pytest.raises(ValueError, match="canonical contract"):
        projector.replace_subject_snapshot(
            source_event_id="event-002",
            source_event_digest=hashlib.sha256(b"event-002").hexdigest(),
            subject_id="persona-001",
            intersection_class="fact",
            channel="feed",
            reasons=(incomplete,),
            generated_at=generated_at,
        )


def test_intersection_projector_rejects_identity_drift_and_duplicate_reason_ids() -> None:
    projector = Projector(_Store())
    digest = hashlib.sha256(b"event-identity").hexdigest()
    generated_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="subject does not match"):
        projector.replace_subject_snapshot(
            source_event_id="event-identity",
            source_event_digest=digest,
            subject_id="persona-001",
            intersection_class="fact",
            channel=None,
            reasons=(canonical_intersection_reason(subject_id="persona-other"),),
            generated_at=generated_at,
        )
    reason = canonical_intersection_reason()
    with pytest.raises(ValueError, match="unique"):
        projector.replace_subject_snapshot(
            source_event_id="event-identity",
            source_event_digest=digest,
            subject_id="persona-001",
            intersection_class="fact",
            channel=None,
            reasons=(reason, reason),
            generated_at=generated_at,
        )
