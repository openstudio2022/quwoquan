# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
# readiness_case: list-subject-intersections-api
# readiness_case: list-object-intersections-api
# readiness_case: get-intersection-supply-api
# readiness_case: recommendation-feature-profile-view-get-recommendation-author-impact-api
# readiness_case: recommendation-feature-profile-view-list-recommendation-author-impact-evidence-api
# readiness_case: project-feature-profile-api
# readiness_case: project-feature-tag-feedback-api
# readiness_case: project-feature-persona-relationship-api
# readiness_case: project-feature-circle-membership-api
# readiness_case: project-feature-post-lifecycle-api
from datetime import datetime, timezone
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.http.router import (
    FEATURE_PROFILE_READ_SCOPE,
    build_router,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.content_behavior_consumer import (
    CONSUMER_GROUP as CONTENT_BEHAVIOR_GROUP,
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.circle_membership_consumer import (
    CIRCLE_MEMBERSHIP_STREAM,
    CONSUMER_GROUP as CIRCLE_MEMBERSHIP_GROUP,
    CircleMembershipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.persona_relationship_consumer import (
    CONSUMER_GROUP as PERSONA_RELATIONSHIP_GROUP,
    PERSONA_RELATIONSHIP_STREAM,
    PersonaRelationshipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import (
    CONSUMER_GROUP as POST_LIFECYCLE_GROUP,
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.tag_feedback_consumer import (
    CONSUMER_GROUP as TAG_FEEDBACK_GROUP,
    TAG_FEEDBACK_STREAM,
    TagFeedbackConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (
    Reader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    Reader as IntersectionReader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    Projector as IntersectionProjector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_event_projector import (
    IntersectionEventProjector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    Materializer as IntersectionMaterializer,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_rebuild import (
    IntersectionRebuilder,
)
from internal.recommendation.recommendation_feature_profile_view.application.projector import Projector
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)
from security.service_authorization import AuthorizationFailure
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis
from tests.support.intersection_reason import (
    canonical_intersection_reason,
)


class _Verifier:
    def verify(self, authorization: str | None, *, required_scope: str):
        assert required_scope == FEATURE_PROFILE_READ_SCOPE
        if authorization != "Bearer content-service":
            raise AuthorizationFailure(401, "ignored")
        return {"sub": "service:content-service"}


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


class _ClosedSubject:
    def __init__(self, subject_id: str) -> None:
        self._subject_id = subject_id

    def exists(self, subject_id: str) -> bool:
        return subject_id == self._subject_id


def _intersection_reader(
    store: MongoFeatureProfileStore,
    subject_closures=None,
) -> IntersectionReader:
    return IntersectionReader(
        store,
        IntersectionMaterializer(
            evidence=store,
            projector=IntersectionProjector(store),
        ),
        subject_closures or _OpenSubjects(),
    )


def test_content_behavior_stream_projects_mongo_state_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    projector = IntersectionEventProjector(
        store=store,
        materializer=IntersectionMaterializer(
            evidence=store,
            projector=IntersectionProjector(store),
        ),
        subject_closures=_OpenSubjects(),
    )
    subject_id = "persona-stream-viewer"
    client_event_id = "behavior-stream-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "clientEventId": client_event_id,
        "personaId": subject_id,
        "contentId": "post-stream-001",
        "contentType": "post",
        "objectId": "post-stream-001",
        "objectKind": "post",
        "displayName": "流式投影内容",
        "action": "view",
        "entityRefs": ["entity-stream-001"],
        "occurredAt": occurred_at,
    }
    real_redis.xadd(
        CONTENT_BEHAVIOR_STREAM,
        {
            "eventId": event_id,
            "eventName": "ContentBehaviorRecorded",
            "subjectId": subject_id,
            "targetId": "post-stream-001",
            "payload": json.dumps(payload, ensure_ascii=False),
            "occurredAt": occurred_at,
        },
    )
    consumer = ContentBehaviorConsumer(
        redis_client=real_redis,
        feature_store=store,
        projector=projector,
        consumer="feature-profile-api-test",
    )

    assert consumer.process_once() == 1
    projected = mongo_database["recommendation_intersection_behaviors"].find_one(
        {"_id": event_id}
    )
    assert projected is not None
    assert projected["subjectId"] == subject_id
    assert projected["targetId"] == "post-stream-001"
    assert real_redis.xpending(CONTENT_BEHAVIOR_STREAM, CONTENT_BEHAVIOR_GROUP)[
        "pending"
    ] == 0


def test_remaining_feature_streams_project_object_state_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    materializer = IntersectionMaterializer(
        evidence=store,
        projector=IntersectionProjector(store),
    )
    intersection_projector = IntersectionEventProjector(
        store=store,
        materializer=materializer,
        subject_closures=_OpenSubjects(),
    )

    real_redis.xadd(
        TAG_FEEDBACK_STREAM,
        {
            "eventName": "TagFeedbackRecorded",
            "eventId": "tag-feedback-stream-001",
            "id": "tag-feedback-stream-001",
            "actorId": "persona-feature-stream",
            "actorKind": "persona",
            "tagRef": "Topic/旅行",
            "action": "dislike",
            "recordedAt": "2026-08-05T08:00:00Z",
        },
    )
    tag_consumer = TagFeedbackConsumer(
        redis_client=real_redis,
        feature_store=store,
        feature_projector=Projector(store),
        subject_closures=_OpenSubjects(),
        consumer="feature-tag-api-test",
    )
    assert tag_consumer.process_once() == 1
    assert store.read_for_scoring("persona-feature-stream")["tagAffinities"] == {
        "Topic/旅行": -1.0
    }
    assert real_redis.xpending(TAG_FEEDBACK_STREAM, TAG_FEEDBACK_GROUP)["pending"] == 0

    real_redis.xadd(
        PERSONA_RELATIONSHIP_STREAM,
        {
            "eventId": "feature-relationship-stream-001",
            "eventName": "PersonaFollowStateChanged",
            "sourcePersonaId": "persona-feature-stream",
            "targetPersonaId": "persona-feature-author",
            "following": "true",
            "sourceFollowCleared": "false",
            "targetFollowCleared": "false",
            "version": "1",
            "occurredAt": "2026-08-05T08:00:00Z",
        },
    )
    relationship_consumer = PersonaRelationshipConsumer(
        redis_client=real_redis,
        feature_store=store,
        projector=intersection_projector,
        consumer="feature-relationship-api-test",
    )
    assert relationship_consumer.process_once() == 1
    relationship = mongo_database[
        "recommendation_intersection_persona_relationships"
    ].find_one({"sourcePersonaId": "persona-feature-stream"})
    assert relationship is not None
    assert relationship["targetPersonaId"] == "persona-feature-author"
    assert real_redis.xpending(
        PERSONA_RELATIONSHIP_STREAM,
        PERSONA_RELATIONSHIP_GROUP,
    )["pending"] == 0

    membership_payload = {
        "id": "membership-feature-stream-001",
        "version": 1,
        "circleId": "circle-feature-stream",
        "personaId": "persona-feature-stream",
        "role": "member",
        "state": "active",
    }
    real_redis.xadd(
        CIRCLE_MEMBERSHIP_STREAM,
        {
            "eventId": "membership-feature-event-001",
            "eventType": "CircleMembershipJoined",
            "aggregateType": "CircleMembership",
            "aggregateId": membership_payload["id"],
            "aggregateVersion": "1",
            "payload": json.dumps(membership_payload),
            "occurredAt": "2026-08-05T08:00:00Z",
        },
    )
    membership_consumer = CircleMembershipConsumer(
        redis_client=real_redis,
        feature_store=store,
        projector=intersection_projector,
        consumer="feature-membership-api-test",
    )
    assert membership_consumer.process_once() == 1
    membership = mongo_database[
        "recommendation_intersection_circle_memberships"
    ].find_one({"_id": membership_payload["id"]})
    assert membership is not None
    assert membership["state"] == "active"
    assert real_redis.xpending(
        CIRCLE_MEMBERSHIP_STREAM,
        CIRCLE_MEMBERSHIP_GROUP,
    )["pending"] == 0

    post_payload = {
        "postId": "post-feature-stream-001",
        "authorId": "persona-feature-author",
        "authorDisplayNameSnapshot": "公开作者",
        "authorAvatarUrlSnapshot": "https://image.invalid/author",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "primaryHomepageId": "homepage-feature-stream",
        "visitedAt": "2026-08-05T08:00:00Z",
    }
    real_redis.xadd(
        POST_LIFECYCLE_STREAM,
        {
            "eventId": "post-feature-event-001",
            "eventType": "PostPublished",
            "aggregateType": "Post",
            "aggregateId": post_payload["postId"],
            "aggregateVersion": "1",
            "payload": json.dumps(post_payload),
            "occurredAt": "2026-08-05T08:00:00Z",
        },
    )
    post_consumer = PostLifecycleConsumer(
        redis_client=real_redis,
        feature_store=store,
        projector=intersection_projector,
        consumer="feature-post-api-test",
    )
    assert post_consumer.process_once() == 1
    profile = mongo_database[
        "recommendation_intersection_persona_profiles"
    ].find_one({"personaId": "persona-feature-author"})
    assert profile is not None
    assert profile["displayName"] == "公开作者"
    assert real_redis.xpending(POST_LIFECYCLE_STREAM, POST_LIFECYCLE_GROUP)[
        "pending"
    ] == 0


def test_feature_profile_applies_behavior_once_with_transactional_checkpoint(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    projector = Projector(store)
    command = dict(
        event_id="behavior-001",
        source_sequence=9,
        subject_id="persona-viewer",
        payload={
            "contentId": "post-001",
            "action": "like",
            "state": "interaction",
            "tagRefs": ["Topic/旅行"],
            "entityRefs": ["地点/景区/色达"],
            "authorId": "persona-author",
            "contentType": "post",
            "impactHelpType": "decision",
            "intersectionDimension": "same_city",
            "intersectionTagRefs": ["Topic/旅行"],
        },
        feedback_fact_id="feedback-001",
        exposure_fact_id="exposure-001",
        occurred_at=datetime.now(timezone.utc),
    )
    assert projector.project_behavior(**command)
    assert not projector.project_behavior(**command)
    profile = store.read_for_scoring("persona-viewer")
    assert profile["checkpoint"] == 1
    assert profile["sparseFeatures"]["action:like"] == 1.0
    assert profile["intersectionFeatures"]["intersectionDimension:same_city"] == 1.0
    assert mongo_database["recommendation_feature_projection_checkpoints"].count_documents({}) == 1
    impact = mongo_database["rm_author_impact"].find_one(
        {"authorId": "persona-author"}
    )
    assert impact is not None
    assert impact["helpType"] == "decision"
    assert impact["tagRef"] == "Topic/旅行"
    assert impact["count"] == 1
    evidence = mongo_database["rm_author_impact_evidence"].find_one(
        {"authorId": "persona-author"}
    )
    assert evidence is not None
    assert evidence["impactId"] == impact["impactId"]
    assert evidence["contentId"] == "post-001"


def test_author_impact_http_reads_the_object_owned_mongo_projection(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    projector = Projector(store)
    assert projector.project_behavior(
        event_id="behavior-http-001",
        source_sequence=1,
        subject_id="persona-viewer",
        payload={
            "contentId": "post-http-001",
            "action": "save",
            "state": "interaction",
            "authorId": "persona-author-http",
            "contentType": "post",
            "impactHelpType": "planning",
            "intersectionDimension": "shared_interest",
            "intersectionTagRefs": ["Topic/旅行"],
        },
        feedback_fact_id="feedback-http-001",
        exposure_fact_id="exposure-http-001",
        occurred_at=datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
    )

    app = FastAPI()
    app.include_router(
        build_router(
            reader_provider=lambda _request: Reader(store),
            intersection_reader_provider=lambda _request: _intersection_reader(store),
            token_verifier=_Verifier(),
        )
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer content-service"}

    summary = client.get(
        "/internal/recommendation/authors/persona-author-http/impact",
        headers=headers,
    )
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    item = summary.json()["items"][0]
    assert item["helpType"] == "planning"
    assert item["representativeContentId"] == "post-http-001"

    evidence = client.get(
        "/internal/recommendation/authors/persona-author-http/impact/"
        f"{item['impactId']}/evidence",
        headers=headers,
    )
    assert evidence.status_code == 200
    assert evidence.json()["items"][0]["contentId"] == "post-http-001"


def test_intersection_http_reads_only_explicit_object_owned_snapshots(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    generated_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    assert store.apply_persona_relationship_evidence(
        event_id="relationship-reader",
        event_digest=hashlib.sha256(b"relationship-reader").hexdigest(),
        source_persona_id="persona-reader",
        target_persona_id="persona-actor",
        following=True,
        blocked=False,
        version=1,
        occurred_at=generated_at,
    )
    assert store.apply_persona_relationship_evidence(
        event_id="relationship-target-reader",
        event_digest=hashlib.sha256(b"relationship-target-reader").hexdigest(),
        source_persona_id="persona-target",
        target_persona_id="persona-actor",
        following=True,
        blocked=False,
        version=1,
        occurred_at=generated_at,
    )
    assert store.apply_persona_profile_evidence(
        event_id="profile-reader",
        event_digest=hashlib.sha256(b"profile-reader").hexdigest(),
        persona_id="persona-actor",
        display_name="公开作者",
        avatar_url="https://image.invalid/actor",
        source_version=1,
        occurred_at=generated_at,
    )
    assert store.apply_behavior_evidence(
        event_id="behavior-reader",
        event_digest=hashlib.sha256(b"behavior-reader").hexdigest(),
        subject_id="persona-actor",
        target_id="post-reader",
        target_type="post",
        action="like",
        entity_refs=(),
        display_name="公开游记",
        occurred_at=generated_at,
    )
    assert store.apply_circle_membership_evidence(
        event_id="membership-reader",
        event_digest=hashlib.sha256(b"membership-reader").hexdigest(),
        membership_id="membership-reader",
        circle_id="circle-reader",
        persona_id="persona-reader",
        state="active",
        version=1,
        occurred_at=generated_at,
    )

    app = FastAPI()
    app.include_router(
        build_router(
            reader_provider=lambda _request: Reader(store),
            intersection_reader_provider=lambda _request: _intersection_reader(store),
            token_verifier=_Verifier(),
        )
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer content-service"}
    response = client.get(
        "/internal/recommendation/subjects/persona-reader/intersections",
        params={"intersectionClass": "fact", "channel": "feed"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["channel"] is None
    assert response.json()["reasons"][0]["kind"] == "followeeViewing"
    receipt_count = mongo_database[
        "recommendation_intersection_projection_inbox"
    ].count_documents({})
    replay = client.get(
        "/internal/recommendation/subjects/persona-reader/intersections",
        params={"intersectionClass": "fact", "channel": "feed"},
        headers=headers,
    )
    assert replay.status_code == 200
    assert mongo_database[
        "recommendation_intersection_projection_inbox"
    ].count_documents({}) == receipt_count

    object_response = client.get(
        "/internal/recommendation/subjects/persona-reader/objects/user/persona-target/intersections",
        headers=headers,
    )
    assert object_response.status_code == 200
    assert object_response.json()["reasons"][0]["kind"] == "sharedFollowees"
    supply = client.get(
        "/internal/recommendation/intersection-supply/circle_membership",
        headers=headers,
    )
    assert supply.status_code == 200
    assert supply.json()["distinctObjectCount"] == 1

    missing = client.get(
        "/internal/recommendation/subjects/persona-missing/intersections",
        params={"intersectionClass": "fact", "channel": "feed"},
        headers=headers,
    )
    assert missing.status_code == 200
    assert missing.json()["reasons"] == []


def test_intersection_http_rejects_closed_subject_without_rebuilding(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    subject_id = "persona-closed-reader"
    receipt_count = mongo_database[
        "recommendation_intersection_projection_inbox"
    ].count_documents({})
    app = FastAPI()
    app.include_router(
        build_router(
            reader_provider=lambda _request: Reader(store),
            intersection_reader_provider=lambda _request: _intersection_reader(
                store,
                _ClosedSubject(subject_id),
            ),
            token_verifier=_Verifier(),
        )
    )
    response = TestClient(app).get(
        f"/internal/recommendation/subjects/{subject_id}/intersections",
        params={"intersectionClass": "fact"},
        headers={"Authorization": "Bearer content-service"},
    )
    assert response.status_code == 410
    assert response.json()["detail"]["code"].endswith(
        "feature_profile_subject_closed"
    )
    assert mongo_database[
        "recommendation_intersection_projection_inbox"
    ].count_documents({}) == receipt_count


def test_intersection_rebuild_reconciles_identity_digest_and_closed_tombstone(
    mongo_database,
) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    occurred_at = datetime(2026, 8, 2, 15, tzinfo=timezone.utc)
    for event_id, source_id in (
        ("rebuild-open", "persona-rebuild-open"),
        ("rebuild-closed", "persona-rebuild-closed"),
    ):
        assert store.apply_persona_relationship_evidence(
            event_id=event_id,
            event_digest=hashlib.sha256(event_id.encode()).hexdigest(),
            source_persona_id=source_id,
            target_persona_id="persona-rebuild-actor",
            following=True,
            blocked=False,
            version=1,
            occurred_at=occurred_at,
        )
    assert store.apply_persona_profile_evidence(
        event_id="rebuild-profile",
        event_digest=hashlib.sha256(b"rebuild-profile").hexdigest(),
        persona_id="persona-rebuild-actor",
        display_name="重建证据作者",
        avatar_url="https://image.invalid/rebuild",
        source_version=1,
        occurred_at=occurred_at,
    )
    assert store.apply_behavior_evidence(
        event_id="rebuild-behavior",
        event_digest=hashlib.sha256(b"rebuild-behavior").hexdigest(),
        subject_id="persona-rebuild-actor",
        target_id="post-rebuild",
        target_type="post",
        action="like",
        entity_refs=(),
        display_name="重建内容",
        occurred_at=occurred_at,
    )
    rebuilder = IntersectionRebuilder(
        store=store,
        materializer=IntersectionMaterializer(
            evidence=store,
            projector=IntersectionProjector(store),
            now=lambda: occurred_at,
        ),
        subject_closures=_ClosedSubject("persona-rebuild-closed"),
    )
    initial_plan = rebuilder.plan()
    assert "persona-rebuild-closed" in initial_plan.closed_subjects
    report = rebuilder.rebuild(initial_plan.source_identity_digest)
    assert report.closed_subject_count == 1
    assert report.snapshot_count == report.source_subject_count * 2
    assert report.changed_snapshot_count == report.snapshot_count
    assert report.supply_count == 4
    assert len(report.source_identity_digest) == 64
    assert len(report.projection_identity_digest) == 64
    assert mongo_database[
        "recommendation_intersection_persona_relationships"
    ].count_documents(
        {
            "$or": [
                {"sourcePersonaId": "persona-rebuild-closed"},
                {"targetPersonaId": "persona-rebuild-closed"},
            ]
        }
    ) == 0

    replay_plan = rebuilder.plan()
    replay = rebuilder.rebuild(replay_plan.source_identity_digest)
    assert replay.changed_snapshot_count == 0
    assert replay.changed_supply_count == 0
    assert replay.source_identity_digest == report.source_identity_digest
    assert replay.projection_identity_digest == report.projection_identity_digest


def test_subject_intersection_channel_uses_canonical_global_snapshot(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    projector = IntersectionProjector(store)
    generated_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    assert projector.replace_subject_snapshot(
        source_event_id="intersection-global-001",
        source_event_digest=hashlib.sha256(b"intersection-global-001").hexdigest(),
        subject_id="persona-global",
        intersection_class="fact",
        channel=None,
        reasons=(canonical_intersection_reason(subject_id="persona-global"),),
        generated_at=generated_at,
    )

    snapshot = store.read_subject_intersections("persona-global", "fact", "video_book")
    assert snapshot.channel == ""
    assert snapshot.reasons[0]["intersectionId"] == "intersection-001"


def test_intersection_evidence_is_versioned_idempotent_and_object_local(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    occurred_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    relationship_digest = hashlib.sha256(b"relationship-seed").hexdigest()
    assert store.apply_persona_relationship_evidence(
        event_id="relationship-seed",
        event_digest=relationship_digest,
        source_persona_id="viewer",
        target_persona_id="actor",
        following=True,
        blocked=False,
        version=1,
        occurred_at=occurred_at,
    )
    assert not store.apply_persona_relationship_evidence(
        event_id="relationship-seed",
        event_digest=relationship_digest,
        source_persona_id="viewer",
        target_persona_id="actor",
        following=True,
        blocked=False,
        version=1,
        occurred_at=occurred_at,
    )
    try:
        store.apply_persona_relationship_evidence(
            event_id="relationship-conflict",
            event_digest=hashlib.sha256(b"relationship-conflict").hexdigest(),
            source_persona_id="viewer",
            target_persona_id="actor",
            following=False,
            blocked=False,
            version=1,
            occurred_at=occurred_at,
        )
    except RuntimeError as error:
        assert "version conflicts" in str(error)
    else:
        raise AssertionError("same relationship version with another digest must fail")
    assert store.list_following("viewer", 10) == ("actor",)
    assert store.list_followers("actor", 10) == ("viewer",)

    membership_digest = hashlib.sha256(b"membership-seed").hexdigest()
    assert store.apply_circle_membership_evidence(
        event_id="membership-seed",
        event_digest=membership_digest,
        membership_id="membership-001",
        circle_id="circle-001",
        persona_id="actor",
        state="active",
        version=1,
        occurred_at=occurred_at,
    )
    assert store.list_circle_ids("actor", 10) == ("circle-001",)
    assert store.count_intersection_supply("circle_membership") == 1

    profile_digest = hashlib.sha256(b"profile-seed").hexdigest()
    assert store.apply_persona_profile_evidence(
        event_id="profile-seed",
        event_digest=profile_digest,
        persona_id="actor",
        display_name="公开昵称",
        avatar_url="https://image.invalid/actor",
        source_version=1,
        occurred_at=occurred_at,
    )
    profile = store.read_persona_profile("actor")
    assert profile is not None
    assert profile.display_name == "公开昵称"
    assert store.apply_persona_profile_evidence(
        event_id="profile-another-post",
        event_digest=hashlib.sha256(b"profile-another-post").hexdigest(),
        persona_id="actor",
        display_name="最新公开昵称",
        avatar_url="https://image.invalid/actor-latest",
        source_version=1,
        occurred_at=datetime(2026, 8, 2, 13, tzinfo=timezone.utc),
    )
    latest_profile = store.read_persona_profile("actor")
    assert latest_profile is not None
    assert latest_profile.display_name == "最新公开昵称"


def test_intersection_behavior_and_supply_fold_are_transactional(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    occurred_at = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    add_digest = hashlib.sha256(b"wishlist-add").hexdigest()
    assert store.apply_behavior_evidence(
        event_id="wishlist-add",
        event_digest=add_digest,
        subject_id="actor",
        target_id="post-001",
        target_type="post",
        action="wishlist_add",
        entity_refs=("entity-001", "entity-001"),
        display_name="公开游记",
        occurred_at=occurred_at,
    )
    assert not store.apply_behavior_evidence(
        event_id="wishlist-add",
        event_digest=add_digest,
        subject_id="actor",
        target_id="post-001",
        target_type="post",
        action="wishlist_add",
        entity_refs=("entity-001",),
        display_name="公开游记",
        occurred_at=occurred_at,
    )
    assert store.count_intersection_supply("entity_wishlist") == 1
    behavior = store.list_behaviors("actor", 10)[0]
    assert behavior.entity_refs == ("entity-001",)
    assert behavior.display_name == "公开游记"

    remove_digest = hashlib.sha256(b"wishlist-remove").hexdigest()
    assert store.apply_behavior_evidence(
        event_id="wishlist-remove",
        event_digest=remove_digest,
        subject_id="actor",
        target_id="post-001",
        target_type="post",
        action="wishlist_remove",
        entity_refs=("entity-001",),
        display_name="公开游记",
        occurred_at=occurred_at,
    )
    assert store.count_intersection_supply("entity_wishlist") == 0

    visit_digest = hashlib.sha256(b"declared-visit").hexdigest()
    assert store.apply_declared_visit_evidence(
        event_id="declared-visit",
        event_digest=visit_digest,
        post_id="post-visited",
        persona_id="actor",
        entity_id="entity-visited",
        active=True,
        source_version=1,
        occurred_at=occurred_at,
    )
    assert store.count_intersection_supply("post_declared_visit") == 1


def test_tag_feedback_sets_clears_and_deduplicates_explicit_affinity(mongo_database) -> None:
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    projector = Projector(store)
    common = dict(
        subject_id="persona-tag-feedback",
        actor_kind="persona",
        tag_ref="Topic/旅行",
        recorded_at=datetime.now(timezone.utc),
    )
    assert projector.project_tag_feedback(
        event_id="tag-feedback-click",
        action="click",
        **common,
    )
    assert not projector.project_tag_feedback(
        event_id="tag-feedback-click",
        action="click",
        **common,
    )
    assert store.read_for_scoring("persona-tag-feedback")["tagAffinities"] == {
        "Topic/旅行": 1.0
    }
    assert projector.project_tag_feedback(
        event_id="tag-feedback-dislike",
        action="dislike",
        **common,
    )
    assert store.read_for_scoring("persona-tag-feedback")["tagAffinities"] == {
        "Topic/旅行": -1.0
    }
    assert projector.project_tag_feedback(
        event_id="tag-feedback-ignore",
        action="ignore",
        **common,
    )
    assert store.read_for_scoring("persona-tag-feedback")["tagAffinities"] == {}
