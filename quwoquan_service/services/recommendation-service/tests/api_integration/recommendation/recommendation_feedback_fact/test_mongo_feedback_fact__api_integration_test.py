# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
# readiness_case: append-feedback-api
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

from internal.recommendation.recommendation_feedback_fact.adapters.inbound.stream.content_behavior_consumer import (
    CONSUMER_GROUP,
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feedback_fact.application.appender import Appender
from internal.recommendation.recommendation_feedback_fact.domain.fact import (
    RecommendationFeedbackFact,
)
from internal.recommendation.recommendation_feedback_fact.infrastructure.mongo_store import (
    MongoRecommendationFeedbackFactStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis


class _ExposureReader:
    def exists(self, exposure_id: str) -> bool:
        return exposure_id == "exposure-001"

    def find_by_attribution(self, feed_request_id: str, target_id: str):
        if (feed_request_id, target_id) != ("feed-stream-001", "post-stream-001"):
            return None
        return SimpleNamespace(
            exposure_id="exposure-001",
            subject_id="persona-stream-001",
        )


class _OpenSubjects:
    def exists(self, _account_id: str) -> bool:
        return False


class _FeatureProjector:
    def __init__(self) -> None:
        self.feedback_ids: list[str] = []

    def project_behavior(self, **values) -> bool:
        self.feedback_ids.append(values["feedback_fact_id"])
        return True


def test_content_behavior_stream_persists_feedback_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoRecommendationFeedbackFactStore(mongo_database)
    store.ensure_indexes()
    subject_id = "persona-stream-001"
    client_event_id = "behavior-stream-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "clientEventId": client_event_id,
        "personaId": subject_id,
        "deviceActorId": "",
        "sessionId": "session-stream-001",
        "contentId": "post-stream-001",
        "contentType": "post",
        "action": "like",
        "state": "interaction",
        "duration": 0.0,
        "tagRefs": ["Topic/旅行"],
        "entityRefs": [],
        "authorId": "persona-author",
        "feedRequestId": "feed-stream-001",
        "occurredAt": occurred_at,
    }
    real_redis.xadd(
        CONTENT_BEHAVIOR_STREAM,
        {
            "eventId": event_id,
            "eventName": "ContentBehaviorRecorded",
            "sourceSequence": "64c000000000000000000001",
            "subjectId": subject_id,
            "feedRequestId": "feed-stream-001",
            "targetId": "post-stream-001",
            "payload": json.dumps(payload),
            "occurredAt": occurred_at,
        },
    )
    projector = _FeatureProjector()
    consumer = ContentBehaviorConsumer(
        redis_client=real_redis,
        feedback_store=store,
        exposure_store=_ExposureReader(),
        subject_closures=_OpenSubjects(),
        feature_projector=projector,
        consumer="feedback-api-test",
    )

    assert consumer.process_once() == 1
    assert mongo_database["recommendation_feedback_facts"].count_documents(
        {"sourceEventId": event_id}
    ) == 1
    assert len(projector.feedback_ids) == 1
    assert real_redis.xpending(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP)[
        "pending"
    ] == 0


def test_feedback_fact_has_one_source_event_identity_in_mongo(mongo_database) -> None:
    store = MongoRecommendationFeedbackFactStore(mongo_database)
    store.ensure_indexes()
    appender = Appender(store, _ExposureReader(), _OpenSubjects())
    now = datetime.now(timezone.utc)
    fact = RecommendationFeedbackFact(
        feedback_id="feedback-001",
        source_event_id="behavior-001",
        exposure_id="exposure-001",
        feed_request_id="request-001",
        subject_id="account-001",
        persona_id="persona-001",
        target_type="post",
        target_id="post-001",
        feedback_type="like",
        value=1.0,
        occurred_at=now,
        recorded_at=now,
    )
    assert appender.append(fact)[1]
    assert not appender.append(fact)[1]
    assert mongo_database["recommendation_feedback_facts"].count_documents({"sourceEventId": "behavior-001"}) == 1
