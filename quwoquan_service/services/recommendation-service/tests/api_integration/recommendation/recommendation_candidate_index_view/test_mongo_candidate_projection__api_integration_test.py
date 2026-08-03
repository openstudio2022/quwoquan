from datetime import datetime, timezone

from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    CandidateLifecycleSnapshot,
    Projector,
    RecommendationObjectCardCandidate,
)
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (
    MongoCandidateIndexStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database


def test_candidate_projection_commits_checkpoint_and_tombstone_atomically(mongo_database) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
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
        entity_tag_ids=("entity-tag-001",),
        source_sequence=7,
        updated_at=datetime.now(timezone.utc),
        object_card=RecommendationObjectCardCandidate(
            homepage_id="homepage-001",
            canonical_entity_id="entity-001",
            title="公开对象页",
            subtitle="公开副标题",
            cover_url="https://cdn.example/homepage-001.jpg",
            tag_refs=("Topic/旅行",),
        ),
    )
    assert store.apply_source_event(event_id="post-published-7", snapshot=snapshot)
    assert not store.apply_source_event(event_id="post-published-7", snapshot=snapshot)
    assert mongo_database["rm_discovery_feed"].count_documents({"contentId": "post-001"}) == 1
    assert mongo_database["rm_entity_tags"].count_documents({"contentId": "post-001"}) == 1
    object_card_candidates = store.list_object_card_candidates()
    assert len(object_card_candidates) == 1
    assert object_card_candidates[0]["primaryHomepageId"] == "homepage-001"
    assert object_card_candidates[0]["primaryHomepageSnapshot"]["canonicalEntityId"] == "entity-001"
    assert not projector.remove(scenario="content_feed", content_id="post-001", source_sequence=6)
    assert projector.remove(scenario="content_feed", content_id="post-001", source_sequence=8)
    assert mongo_database["rm_discovery_feed"].count_documents({"contentId": "post-001"}) == 0
    assert mongo_database["recommendation_candidate_tombstones"].find_one(
        {"_id": "content_feed\x1fpost-001"}
    )["sourceSequence"] == 8


def test_candidate_account_restriction_is_monotonic_and_owner_local(mongo_database) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    snapshot = CandidateLifecycleSnapshot(
        scenario="content_feed",
        content_id="post-restricted",
        content_type="article",
        author_id="persona-restricted",
        tag_refs=("Topic/旅行",),
        entity_refs=(),
        published_at=datetime.now(timezone.utc),
        content_vertical="travel",
        entity_tag_ids=(),
        source_sequence=3,
        updated_at=datetime.now(timezone.utc),
    )
    assert store.apply_source_event(event_id="post-restricted-published", snapshot=snapshot)
    candidate_updated_at = mongo_database["rm_discovery_feed"].find_one(
        {"contentId": "post-restricted"}
    )["updatedAt"]

    assert store.apply_account_restriction_event(
        event_id="account-suspended-7",
        event_digest="a" * 64,
        account_id="account-restricted",
        account_version=7,
        subject_ids=("account-restricted", "persona-restricted"),
        restricted=True,
    ) == 1
    assert store.list_for_ranking(scenario="content_feed") == []
    assert mongo_database["rm_discovery_feed"].find_one(
        {"contentId": "post-restricted"}
    )["updatedAt"] == candidate_updated_at

    assert store.apply_account_restriction_event(
        event_id="account-restored-stale-6",
        event_digest="b" * 64,
        account_id="account-restricted",
        account_version=6,
        subject_ids=("account-restricted", "persona-restricted"),
        restricted=False,
    ) == 0
    assert mongo_database["rm_discovery_feed"].find_one(
        {"contentId": "post-restricted"}
    )["accountRestricted"] is True

    assert store.apply_account_restriction_event(
        event_id="account-restored-8",
        event_digest="c" * 64,
        account_id="account-restricted",
        account_version=8,
        subject_ids=("account-restricted", "persona-restricted"),
        restricted=False,
    ) == 1
    assert [row["contentId"] for row in store.list_for_ranking(scenario="content_feed")] == [
        "post-restricted"
    ]

    assert store.erase_subject("persona-restricted") == 1
    assert mongo_database["rm_discovery_feed"].count_documents(
        {"contentId": "post-restricted"}
    ) == 0
    assert mongo_database["recommendation_candidate_account_restrictions"].count_documents(
        {"subjectIds": "persona-restricted"}
    ) == 0


def test_following_candidates_use_local_relationship_projection_and_block_is_irreversible(
    mongo_database,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    snapshot = CandidateLifecycleSnapshot(
        scenario="content_feed",
        content_id="post-following",
        content_type="article",
        author_id="persona-author",
        tag_refs=(),
        entity_refs=(),
        published_at=datetime.now(timezone.utc),
        content_vertical=None,
        entity_tag_ids=(),
        source_sequence=1,
        updated_at=datetime.now(timezone.utc),
    )
    assert store.apply_source_event(event_id="post-following-published", snapshot=snapshot)
    occurred_at = datetime.now(timezone.utc)
    assert store.apply_persona_relationship_event(
        event_id="persona-followed-1",
        event_digest="d" * 64,
        event_name="PersonaFollowStateChanged",
        source_persona_id="persona-viewer",
        target_persona_id="persona-author",
        following=True,
        version=1,
        occurred_at=occurred_at,
    )
    assert [
        row["contentId"]
        for row in store.list_for_ranking(
            subject_id="persona-viewer",
            scenario="following",
        )
    ] == ["post-following"]

    assert store.apply_persona_relationship_event(
        event_id="persona-blocked-2",
        event_digest="e" * 64,
        event_name="PersonaBlocked",
        source_persona_id="persona-viewer",
        target_persona_id="persona-author",
        following=False,
        version=2,
        occurred_at=occurred_at,
    )
    assert store.list_for_ranking(
        subject_id="persona-viewer",
        scenario="following",
    ) == []

    assert store.apply_persona_relationship_event(
        event_id="persona-unblocked-3",
        event_digest="f" * 64,
        event_name="PersonaUnblocked",
        source_persona_id="persona-viewer",
        target_persona_id="persona-author",
        following=False,
        version=3,
        occurred_at=occurred_at,
    )
    assert store.list_for_ranking(
        subject_id="persona-viewer",
        scenario="following",
    ) == []
