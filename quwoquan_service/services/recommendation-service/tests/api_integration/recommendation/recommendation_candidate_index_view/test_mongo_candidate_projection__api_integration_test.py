# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
# spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
# spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
# readiness_case: project-candidate-index-api
# readiness_case: project-candidate-premium-pool-api
# readiness_case: project-candidate-persona-relationship-api
# readiness_case: project-candidate-account-restriction-api
# readiness_case: project-candidate-gathering-api
from datetime import datetime, timezone
import json

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import (
    CONSUMER_GROUP,
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.premium_pool_consumer import (
    CONSUMER_GROUP as PREMIUM_POOL_GROUP,
    PREMIUM_POOL_STREAM,
    PremiumPoolConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.persona_relationship_consumer import (
    CONSUMER_GROUP as PERSONA_RELATIONSHIP_GROUP,
    PERSONA_RELATIONSHIP_STREAM,
    PersonaRelationshipConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.user_account_restriction_consumer import (
    CONSUMER_GROUP as ACCOUNT_RESTRICTION_GROUP,
    USER_ACCOUNT_STREAM,
    UserAccountRestrictionConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    CandidateLifecycleSnapshot,
    Projector,
    RecommendationObjectCardCandidate,
)
from internal.recommendation.recommendation_candidate_index_view.application.gathering_projector import (
    GatheringCandidateSnapshot,
)
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (
    MongoCandidateIndexStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


def _gathering_snapshot(
    *,
    version: int,
    remaining_seats: int,
) -> GatheringCandidateSnapshot:
    return GatheringCandidateSnapshot(
        gathering_id="gathering-api-001",
        source_version=version,
        card_digest=f"{version:064x}",
        host_subject_kind="persona",
        host_subject_id="persona-host",
        title="周末山野徒步",
        summary="公开摘要",
        cover_object_type_ref=None,
        cover_object_id=None,
        tag_refs=("Topic/徒步",),
        start_at=datetime(2026, 8, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 8, 5, tzinfo=timezone.utc),
        date_label=None,
        place_mode="physical",
        coarse_place_object_type_ref="entity.Homepage",
        coarse_place_object_id="homepage-park",
        coarse_place_label="城郊公园",
        max_participants=8,
        occupied_seats=8 - remaining_seats,
        remaining_seats=remaining_seats,
        full=remaining_seats == 0,
        admission_state="full" if remaining_seats == 0 else "accepting",
        lifecycle_status="published",
        updated_at=datetime(2026, 8, 5, 8, version, tzinfo=timezone.utc),
    )


def test_gathering_projection_is_idempotent_and_recovers_capacity(
    mongo_database,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    full = _gathering_snapshot(version=8, remaining_seats=0)

    assert store.apply_gathering_source_event(
        event_id="gathering-full-008",
        event_digest="a" * 64,
        snapshot=full,
    )
    assert not store.apply_gathering_source_event(
        event_id="gathering-full-008",
        event_digest="a" * 64,
        snapshot=full,
    )
    projected = mongo_database["rm_gathering_candidates"].find_one(
        {"sourceKey": "gathering-api-001"}
    )
    assert projected is not None
    assert projected["full"] is True
    assert projected["remainingSeats"] == 0

    recovered = _gathering_snapshot(version=9, remaining_seats=2)
    assert store.apply_gathering_source_event(
        event_id="gathering-recovered-009",
        event_digest="b" * 64,
        snapshot=recovered,
    )
    projected = mongo_database["rm_gathering_candidates"].find_one(
        {"sourceKey": "gathering-api-001"}
    )
    assert projected is not None
    assert projected["sourceVersion"] == 9
    assert projected["full"] is False
    assert projected["remainingSeats"] == 2
    assert projected["admissionState"] == "accepting"

    assert store.apply_gathering_source_event(
        event_id="gathering-cancelled-010",
        event_digest="c" * 64,
        removal=("gathering-api-001", 10),
    )
    assert (
        mongo_database["rm_gathering_candidates"].find_one(
            {"sourceKey": "gathering-api-001"}
        )
        is None
    )
    assert not store.apply_gathering_source_event(
        event_id="gathering-stale-009",
        event_digest="d" * 64,
        snapshot=recovered,
    )


def test_post_lifecycle_stream_projects_mongo_candidate_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "postId": "post-stream-001",
        "authorId": "persona-stream-author",
        "contentType": "article",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "publishedAt": occurred_at,
        "updatedAt": occurred_at,
        "tagRefs": ["Topic/旅行"],
        "entityRefs": ["entity-stream-001"],
    }
    real_redis.xadd(
        POST_LIFECYCLE_STREAM,
        {
            "eventId": "post-stream-001:PostPublished:1",
            "eventType": "PostPublished",
            "aggregateType": "Post",
            "aggregateId": "post-stream-001",
            "aggregateVersion": "1",
            "payload": json.dumps(payload, ensure_ascii=False),
            "occurredAt": occurred_at,
        },
    )
    consumer = PostLifecycleConsumer(
        redis_client=real_redis,
        projection=store,
        subject_closures=_OpenSubjects(),
        consumer="candidate-index-api-test",
    )

    assert consumer.process_once() == 1
    projected = mongo_database["rm_discovery_feed"].find_one(
        {"contentId": "post-stream-001"}
    )
    assert projected is not None
    assert projected["authorId"] == "persona-stream-author"
    assert projected["sourceSequence"] == 1
    assert real_redis.xpending(POST_LIFECYCLE_STREAM, CONSUMER_GROUP)["pending"] == 0


def test_premium_pool_stream_projects_mongo_admission_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    payload = {
        "contentId": "post-premium-stream-001",
        "scope": "global",
        "status": "active",
        "qualityScore": 0.91,
        "qualityAdmission": "approved",
        "supplySource": "product_ops",
        "sourceTaskId": "task-premium-001",
        "auditId": "audit-premium-001",
        "rollbackToken": "rollback-premium-001",
        "featuredAt": "2026-08-05T08:00:00Z",
        "expiresAt": "2027-08-05T08:00:00Z",
        "takedownEjected": False,
        "updatedAt": "2026-08-05T08:00:00Z",
    }
    real_redis.xadd(
        PREMIUM_POOL_STREAM,
        {
            "eventId": "premium-stream-001",
            "eventType": "PremiumPoolEntryUpserted",
            "aggregateType": "PremiumPoolEntry",
            "aggregateId": payload["contentId"],
            "occurredAt": "2026-08-05T08:00:00Z",
            "payloadJson": json.dumps(payload),
            "producer": "product-ops-service",
        },
    )
    consumer = PremiumPoolConsumer(
        redis_client=real_redis,
        store=store,
        consumer="candidate-premium-api-test",
    )

    assert consumer.process_once() == 1
    projected = mongo_database["rm_premium_pool"].find_one(
        {"contentId": payload["contentId"]}
    )
    assert projected is not None
    assert projected["qualityAdmission"] == "approved"
    assert real_redis.xpending(PREMIUM_POOL_STREAM, PREMIUM_POOL_GROUP)["pending"] == 0


def test_persona_relationship_stream_projects_mongo_edge_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    real_redis.xadd(
        PERSONA_RELATIONSHIP_STREAM,
        {
            "eventId": "persona-follow-stream-001",
            "eventName": "PersonaFollowStateChanged",
            "pairId": "pair-stream-001",
            "sourcePersonaId": "persona-stream-viewer",
            "targetPersonaId": "persona-stream-author",
            "following": "true",
            "version": "1",
            "occurredAt": "2026-08-05T08:00:00Z",
        },
    )
    consumer = PersonaRelationshipConsumer(
        redis_client=real_redis,
        projection=store,
        consumer="candidate-relationship-api-test",
    )

    assert consumer.process_once() == 1
    projected = mongo_database[
        "recommendation_candidate_persona_relationships"
    ].find_one({"sourcePersonaId": "persona-stream-viewer"})
    assert projected is not None
    assert projected["targetPersonaId"] == "persona-stream-author"
    assert projected["following"] is True
    assert real_redis.xpending(
        PERSONA_RELATIONSHIP_STREAM,
        PERSONA_RELATIONSHIP_GROUP,
    )["pending"] == 0


def test_account_restriction_stream_projects_mongo_state_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    payload = {
        "userId": "account-stream-001",
        "personaIds": ["persona-stream-001"],
        "accountState": "suspended",
        "authEpoch": 4,
        "decisionRef": "decision-stream-001",
        "occurredAt": "2026-08-05T08:00:00Z",
    }
    real_redis.xadd(
        USER_ACCOUNT_STREAM,
        {
            "eventId": "account-suspended-stream-001",
            "eventName": "UserSuspended",
            "accountId": payload["userId"],
            "accountVersion": "7",
            "payload": json.dumps(payload),
            "occurredAt": payload["occurredAt"],
        },
    )
    consumer = UserAccountRestrictionConsumer(
        redis_client=real_redis,
        projection=store,
        subject_closures=_OpenSubjects(),
        consumer="candidate-restriction-api-test",
    )

    assert consumer.process_once() == 1
    projected = mongo_database[
        "recommendation_candidate_account_restrictions"
    ].find_one({"_id": payload["userId"]})
    assert projected is not None
    assert projected["restricted"] is True
    assert real_redis.xpending(USER_ACCOUNT_STREAM, ACCOUNT_RESTRICTION_GROUP)[
        "pending"
    ] == 0


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
