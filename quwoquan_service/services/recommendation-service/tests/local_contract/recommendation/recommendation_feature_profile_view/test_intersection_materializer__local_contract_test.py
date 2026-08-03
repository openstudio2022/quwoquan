# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    BehaviorSnapshot,
    Materializer,
    PersonaProfileSnapshot,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    IntersectionSupplyMaterialization,
    ObjectIntersectionMaterialization,
    Projector,
    SubjectIntersectionMaterialization,
)


class _Writer:
    def __init__(self) -> None:
        self.subjects: list[SubjectIntersectionMaterialization] = []
        self.objects: list[ObjectIntersectionMaterialization] = []
        self.supplies: list[IntersectionSupplyMaterialization] = []

    def replace_subject_intersections_if_absent(self, mutation) -> bool:
        self.subjects.append(mutation)
        return True

    def replace_object_intersections_if_absent(self, mutation) -> bool:
        self.objects.append(mutation)
        return True

    def replace_intersection_supply_if_absent(self, mutation) -> bool:
        self.supplies.append(mutation)
        return True


class _Evidence:
    following = {
        "viewer": ("actor-a", "actor-b"),
        "profile-target": ("actor-a", "actor-c"),
    }
    followers = {}
    circles = {
        "viewer": ("circle-a", "circle-b"),
        "profile-target": ("circle-b", "circle-c"),
        "actor-a": ("circle-target",),
    }
    profiles = {
        "actor-a": PersonaProfileSnapshot("actor-a", "甲", "https://img/a"),
        "actor-b": PersonaProfileSnapshot("actor-b", "乙", "https://img/b"),
        "actor-c": PersonaProfileSnapshot("actor-c", "丙", "https://img/c"),
    }
    behaviors = {
        "actor-a": (
            BehaviorSnapshot(
                subject_id="actor-a",
                target_id="post-001",
                target_type="post",
                action="like",
                entity_refs=("place-001",),
                display_name="西湖游记",
                occurred_at=datetime(2026, 8, 2, 11, tzinfo=timezone.utc),
            ),
        ),
        "actor-b": (
            BehaviorSnapshot(
                subject_id="actor-b",
                target_id="post-002",
                target_type="post",
                action="comment",
                entity_refs=(),
                display_name="山野照片",
                occurred_at=datetime(2026, 8, 2, 10, tzinfo=timezone.utc),
            ),
        ),
    }

    def list_following(self, persona_id: str, limit: int):
        return tuple(self.following.get(persona_id, ()))[:limit]

    def list_followers(self, persona_id: str, limit: int):
        return tuple(self.followers.get(persona_id, ()))[:limit]

    def list_circle_ids(self, persona_id: str, limit: int):
        return tuple(self.circles.get(persona_id, ()))[:limit]

    def list_behaviors(self, persona_id: str, limit: int):
        return tuple(self.behaviors.get(persona_id, ()))[:limit]

    def read_persona_profile(self, persona_id: str):
        return self.profiles.get(persona_id)

    def count_intersection_supply(self, supply_key: str) -> int:
        return {
            "entity_page_view": 3,
            "entity_wishlist": 2,
            "circle_membership": 4,
            "post_declared_visit": 1,
        }[supply_key]


def _materializer() -> tuple[Materializer, _Writer]:
    writer = _Writer()
    materializer = Materializer(
        evidence=_Evidence(),
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
    )
    return materializer, writer


def test_materializer_publishes_explicit_empty_and_nonempty_subject_snapshots() -> None:
    materializer, writer = _materializer()
    digest = hashlib.sha256(b"behavior-event").hexdigest()
    assert materializer.rebuild_subject(
        source_event_id="behavior-event",
        source_event_digest=digest,
        subject_id="viewer",
        channel="feed",
    ) == (True, True)
    assert len(writer.subjects) == 2
    fact, affinity = writer.subjects
    assert fact.intersection_class == "fact"
    assert fact.reasons[0]["actorEvidenceTotalCount"] == 2
    assert "".join(
        str(span["text"]) for span in fact.reasons[0]["primarySpans"]
    ) == fact.reasons[0]["primaryText"]
    assert fact.reasons[0]["primarySpans"][-1]["target"]["objectId"] == "post-001"
    assert affinity.intersection_class == "affinity"

    assert materializer.rebuild_subject(
        source_event_id="empty-event",
        source_event_digest=hashlib.sha256(b"empty-event").hexdigest(),
        subject_id="no-evidence",
    ) == (True, True)
    assert writer.subjects[-2].reasons == ()
    assert writer.subjects[-1].reasons == ()


def test_materializer_builds_person_and_nonperson_object_evidence_without_raw_ids() -> None:
    materializer, writer = _materializer()
    assert materializer.rebuild_object(
        source_event_id="relationship-event",
        source_event_digest=hashlib.sha256(b"relationship-event").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reasons = writer.objects[-1].reasons
    assert {reason["kind"] for reason in reasons} == {"sharedFollowees", "sharedCircle"}
    actor_reason = next(reason for reason in reasons if reason["kind"] == "sharedFollowees")
    assert actor_reason["actorEvidence"][0]["displayName"] == "甲"
    assert "actor-a" not in actor_reason["primaryText"]

    assert materializer.rebuild_object(
        source_event_id="circle-event",
        source_event_digest=hashlib.sha256(b"circle-event").hexdigest(),
        subject_id="viewer",
        object_type="circle",
        object_id="circle-target",
    )
    assert writer.objects[-1].reasons[0]["kind"] == "followeeInObject"


def test_materializer_owns_all_four_supply_snapshots() -> None:
    materializer, writer = _materializer()
    changed = materializer.rebuild_supplies(
        source_event_id="supply-event",
        source_event_digest=hashlib.sha256(b"supply-event").hexdigest(),
    )
    assert changed == 4
    assert {item.supply_key for item in writer.supplies} == {
        "entity_page_view",
        "entity_wishlist",
        "circle_membership",
        "post_declared_visit",
    }
