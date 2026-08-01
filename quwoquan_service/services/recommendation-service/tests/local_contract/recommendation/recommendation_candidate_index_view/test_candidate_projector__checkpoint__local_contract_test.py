from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    CandidateLifecycleSnapshot,
    PremiumAdmissionSnapshot,
    Projector,
)


class _Store:
    def __init__(self) -> None:
        self.items = {}

    def remove_if_newer(self, *, scenario, content_id, source_sequence) -> bool:
        key = (scenario, content_id)
        current = self.items.get(key)
        if current and current.source_sequence > source_sequence:
            return False
        return self.items.pop(key, None) is not None

    def upsert_lifecycle_if_newer(self, snapshot) -> bool:
        key = (snapshot.scenario, snapshot.content_id)
        current = self.items.get(key)
        if current and current.source_sequence >= snapshot.source_sequence:
            return False
        self.items[key] = snapshot
        return True

    def apply_premium_source_event(self, *, event_id, snapshot) -> bool:
        key = ("premium", snapshot.content_id)
        current = self.items.get(key)
        if current and current.updated_at >= snapshot.updated_at:
            return False
        self.items[key] = snapshot
        return True


def _lifecycle(sequence: int, tags=("Topic/旅行",)) -> CandidateLifecycleSnapshot:
    return CandidateLifecycleSnapshot(
        scenario="content_feed",
        content_id="post-001",
        content_type="article",
        author_id="persona-author",
        tag_refs=tags,
        entity_refs=("地点/景区/色达",),
        published_at=datetime.now(timezone.utc),
        content_vertical="travel",
        entity_tag_ids=(),
        source_sequence=sequence,
        updated_at=datetime.now(timezone.utc),
    )


def test_candidate_projector_rejects_stale_sequence() -> None:
    store = _Store()
    projector = Projector(store)
    assert projector.project_lifecycle(_lifecycle(2)) is True
    assert projector.project_lifecycle(_lifecycle(1)) is False
    assert store.items[("content_feed", "post-001")].source_sequence == 2


def test_candidate_projector_rejects_duplicate_entity_tags() -> None:
    with pytest.raises(ValueError):
        Projector(_Store()).project_lifecycle(_lifecycle(1, ("Topic/旅行", "Topic/旅行")))


def test_candidate_projector_stale_delete_cannot_remove_newer_projection() -> None:
    store = _Store()
    projector = Projector(store)
    assert projector.project_lifecycle(_lifecycle(2)) is True
    assert projector.remove(
        scenario="content_feed",
        content_id="post-001",
        source_sequence=1,
    ) is False
    assert ("content_feed", "post-001") in store.items


def test_candidate_lifecycle_projection_keeps_monotonic_source_sequence() -> None:
    store = _Store()
    projector = Projector(store)
    snapshot = CandidateLifecycleSnapshot(
        scenario="content_feed",
        content_id="post-001",
        content_type="article",
        author_id="persona-author",
        tag_refs=("Topic/旅行",),
        entity_refs=("地点/景区/色达",),
        published_at=datetime.now(timezone.utc),
        content_vertical="travel",
        entity_tag_ids=(),
        source_sequence=4,
        updated_at=datetime.now(timezone.utc),
    )
    assert projector.project_lifecycle(snapshot) is True
    assert projector.project_lifecycle(snapshot) is False


def test_premium_admission_uses_its_own_updated_at_watermark() -> None:
    store = _Store()
    projector = Projector(store)
    now = datetime.now(timezone.utc)
    newer = PremiumAdmissionSnapshot(
        content_id="post-001",
        status="active",
        scope="global",
        quality_admission="approved",
        quality_score=0.9,
        supply_source="product_ops",
        source_task_id=None,
        audit_id="audit-001",
        rollback_token="rollback-001",
        featured_at=now,
        expires_at=now + timedelta(days=1),
        takedown_ejected=False,
        updated_at=now + timedelta(minutes=1),
    )
    stale = replace(newer, updated_at=now)
    assert projector.apply_premium_source_event(event_id="premium-2", snapshot=newer)
    assert not projector.apply_premium_source_event(event_id="premium-1", snapshot=stale)
    assert store.items[("premium", "post-001")].updated_at == newer.updated_at
