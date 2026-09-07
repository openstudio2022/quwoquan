# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t2
# readiness_case: append-feedback-api
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

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
from internal.recommendation.recommendation_feature_profile_view.application.projector import (
    Projector,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)
from stream_redis import StreamConsumerRedis
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import durable_redis, real_redis


class _ExposureReader:
    def __init__(self, *, subject_id: str = "persona-stream-001") -> None:
        self._subject_id = subject_id

    def exists(self, exposure_id: str) -> bool:
        return exposure_id == "exposure-001"

    def find_by_attribution(self, feed_request_id: str, target_id: str):
        if (feed_request_id, target_id) != ("feed-stream-001", "post-stream-001"):
            return None
        return SimpleNamespace(
            exposure_id="exposure-001",
            subject_id=self._subject_id,
            experiment_bucket="model",
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
        # Client behavior cannot select or overwrite experiment attribution.
        "experimentBucket": "rule",
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
    persisted = mongo_database["recommendation_feedback_facts"].find_one(
        {"sourceEventId": event_id}
    )
    assert persisted is not None
    assert persisted["experimentBucket"] == "model"
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
        experiment_bucket="model",
        subject_id="account-001",
        persona_id="persona-001",
        target_type="post",
        target_id="post-001",
        feedback_type="like",
        value=1.0,
        occurred_at=now,
        recorded_at=now,
    )
    persisted, created = appender.append(fact)
    assert created
    replayed, replay_created = appender.append(
        replace(fact, recorded_at=now + timedelta(seconds=1))
    )
    assert not replay_created
    assert replayed.recorded_at == persisted.recorded_at
    with pytest.raises(RuntimeError, match="identity conflicts"):
        store.append_if_absent(
            replace(
                fact,
                target_id="post-conflicting",
                recorded_at=now + timedelta(seconds=2),
            )
        )
    assert mongo_database["recommendation_feedback_facts"].count_documents(
        {"sourceEventId": "behavior-001"}
    ) == 1


class _CrashBeforeAckRedis:
    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def xack(self, *_args, **_kwargs):
        raise RuntimeError("simulated application crash before Redis ACK")


class _ClaimRecordingRedis:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.claimed_ids: list[str] = []

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def xautoclaim(self, *args, **kwargs):
        result = self._inner.xautoclaim(*args, **kwargs)
        entries = (
            result[1]
            if isinstance(result, (list, tuple)) and len(result) > 1
            else []
        )
        self.claimed_ids.extend(
            stream_id.decode("utf-8") if isinstance(stream_id, bytes) else str(stream_id)
            for stream_id, _fields in entries
        )
        return result


# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
def test_content_behavior_stream_recovers_pel_after_sigkill_without_duplicate_business_result(
    mongo_database,
    durable_redis,
) -> None:
    feedback_store = MongoRecommendationFeedbackFactStore(mongo_database)
    feedback_store.ensure_indexes()
    feature_store = MongoFeatureProfileStore(mongo_database)
    feature_store.ensure_indexes()
    subject_id = "persona-durable-001"
    client_event_id = "behavior-durable-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "clientEventId": client_event_id,
        "personaId": subject_id,
        "deviceActorId": "",
        "sessionId": "session-durable-001",
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
    stream_id = durable_redis.client.xadd(
        CONTENT_BEHAVIOR_STREAM,
        {
            "eventId": event_id,
            "eventName": "ContentBehaviorRecorded",
            "sourceSequence": "0000000000000002",
            "subjectId": subject_id,
            "feedRequestId": "feed-stream-001",
            "targetId": "post-stream-001",
            "payload": json.dumps(payload),
            "occurredAt": occurred_at,
        },
    )
    stream_id_text = (
        stream_id.decode("utf-8") if isinstance(stream_id, bytes) else str(stream_id)
    )
    crashing_redis = _CrashBeforeAckRedis(
        StreamConsumerRedis(durable_redis.client)
    )
    crashing_consumer = ContentBehaviorConsumer(
        redis_client=crashing_redis,
        feedback_store=feedback_store,
        exposure_store=_ExposureReader(subject_id=subject_id),
        subject_closures=_OpenSubjects(),
        feature_projector=Projector(feature_store),
        consumer="feedback-before-crash",
    )

    with pytest.raises(RuntimeError, match="before Redis ACK"):
        crashing_consumer.process_once()
    assert durable_redis.client.xpending(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP)[
        "pending"
    ] == 1
    assert mongo_database["recommendation_feedback_facts"].count_documents(
        {"sourceEventId": event_id}
    ) == 1
    profile_before = mongo_database["rm_recommend_feature"].find_one(
        {"_id": subject_id}
    )
    assert profile_before is not None
    assert profile_before["checkpoint"] == 1
    assert profile_before["sparseFeatures"]["action:like"] == 1.0

    durable_redis.client.xclaim(
        CONTENT_BEHAVIOR_STREAM,
        CONSUMER_GROUP,
        "feedback-before-crash",
        min_idle_time=0,
        message_ids=[stream_id],
        idle=30_001,
    )
    pending_before_restart = durable_redis.client.xpending_range(
        CONTENT_BEHAVIOR_STREAM,
        CONSUMER_GROUP,
        min="-",
        max="+",
        count=1,
    )
    assert pending_before_restart[0]["time_since_delivered"] >= 30_000
    container_before, container_after = durable_redis.restart_after_sigkill()
    assert container_before != container_after
    assert durable_redis.client.config_get("appendonly") == {"appendonly": "yes"}
    assert durable_redis.client.config_get("appendfsync") == {"appendfsync": "always"}
    recovered_messages = durable_redis.client.xrange(
        CONTENT_BEHAVIOR_STREAM, min=stream_id, max=stream_id
    )
    assert len(recovered_messages) == 1
    assert durable_redis.client.xlen(CONTENT_BEHAVIOR_STREAM) == 1
    assert durable_redis.client.xpending(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP)[
        "pending"
    ] == 1

    recovering_redis = _ClaimRecordingRedis(
        StreamConsumerRedis(durable_redis.client)
    )
    recovering_consumer = ContentBehaviorConsumer(
        redis_client=recovering_redis,
        feedback_store=feedback_store,
        exposure_store=_ExposureReader(subject_id=subject_id),
        subject_closures=_OpenSubjects(),
        feature_projector=Projector(feature_store),
        consumer="feedback-after-restart",
    )
    assert recovering_consumer.process_once() == 1
    assert recovering_redis.claimed_ids == [stream_id_text]
    assert durable_redis.client.xpending(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP)[
        "pending"
    ] == 0
    assert mongo_database["recommendation_feedback_facts"].count_documents(
        {"sourceEventId": event_id}
    ) == 1
    profile_after = mongo_database["rm_recommend_feature"].find_one(
        {"_id": subject_id}
    )
    assert profile_after is not None
    assert profile_after["checkpoint"] == 1
    assert profile_after["sparseFeatures"]["action:like"] == 1.0
    assert mongo_database["recommendation_feature_projection_checkpoints"].count_documents(
        {"eventId": event_id, "subjectId": subject_id}
    ) == 1
