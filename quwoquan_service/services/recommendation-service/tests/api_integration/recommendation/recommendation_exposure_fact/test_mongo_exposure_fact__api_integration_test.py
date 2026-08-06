# spec_ref: specs/feature-tree/discovery-content/exposure-governance/served-dedup-write-behind/spec.md#gwt-001
# readiness_case: append-exposure-api
from datetime import datetime, timezone
import hashlib
import json

from internal.recommendation.recommendation_exposure_fact.adapters.inbound.stream.feed_page_delivered_consumer import (
    CONSUMER_GROUP,
    FEED_PAGE_DELIVERED_STREAM,
    FeedPageDeliveredConsumer,
)
from internal.recommendation.recommendation_exposure_fact.application.appender import (
    Appender,
    ExposureFact,
    canonical_snapshot_digest,
)
from internal.recommendation.recommendation_exposure_fact.infrastructure.mongo_store import (
    MongoExposureFactStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis


class _OpenSubjects:
    def exists(self, _account_id: str) -> bool:
        return False


class _FeatureProjector:
    def __init__(self) -> None:
        self.exposure_ids: list[str] = []

    def project_exposure(self, **values) -> bool:
        self.exposure_ids.append(values["exposure_fact_id"])
        return True


def test_feed_delivery_stream_persists_exposure_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoExposureFactStore(mongo_database)
    store.ensure_indexes()
    delivery_page_id = "delivery-stream-001"
    event_id = hashlib.sha256(
        f"FeedPageDelivered:{delivery_page_id}".encode()
    ).hexdigest()
    user_snapshot = {"travelAffinity": 0.8}
    item_snapshot = {"contentId": "post-stream-001", "qualityScore": 0.9}
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "deliveryPageId": delivery_page_id,
        "feedRequestId": "feed-stream-001",
        "subjectId": "persona-stream-001",
        "personaId": "persona-stream-001",
        "scenario": "content_feed",
        "windowId": "window-stream-001",
        "modelBucket": "model",
        "modelChannel": "champion",
        "modelReleaseId": "release-stream-001",
        "rankingSnapshotDigest": "a" * 64,
        "featureSnapshotAt": occurred_at,
        "userFeatureSnapshot": user_snapshot,
        "items": [{
            "ordinal": 0,
            "contentId": "post-stream-001",
            "contentType": "post",
            "featureSnapshotDigest": canonical_snapshot_digest(
                user_snapshot, item_snapshot
            ),
            "itemFeatureSnapshot": item_snapshot,
        }],
        "occurredAt": occurred_at,
    }
    real_redis.xadd(
        FEED_PAGE_DELIVERED_STREAM,
        {
            "eventId": event_id,
            "eventName": "FeedPageDelivered",
            "deliveryPageId": delivery_page_id,
            "payload": json.dumps(payload),
            "occurredAt": occurred_at,
        },
    )
    projector = _FeatureProjector()
    consumer = FeedPageDeliveredConsumer(
        redis_client=real_redis,
        exposure_store=store,
        subject_closures=_OpenSubjects(),
        feature_projector=projector,
        consumer="exposure-api-test",
    )

    assert consumer.process_once() == 1
    assert mongo_database["recommendation_exposure_facts"].count_documents(
        {"sourceEventId": event_id}
    ) == 1
    assert len(projector.exposure_ids) == 1
    assert real_redis.xpending(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP)[
        "pending"
    ] == 0


def test_exposure_fact_is_immutable_and_attributable_in_mongo(mongo_database) -> None:
    store = MongoExposureFactStore(mongo_database)
    store.ensure_indexes()
    appender = Appender(store, _OpenSubjects())
    now = datetime.now(timezone.utc)
    user_snapshot = {"travelAffinity": 0.8}
    item_snapshot = {"qualityScore": 0.9}
    fact = ExposureFact(
        exposure_id="exposure-001",
        source_event_id="delivery-event-001",
        delivery_page_id="page-001",
        feed_request_id="request-001",
        window_id="window-001",
        subject_id="account-001",
        persona_id="persona-001",
        scenario="content_feed",
        target_type="post",
        target_id="post-001",
        ordinal=0,
        model_bucket="model",
        model_channel="champion",
        model_release_id="release-001",
        feature_snapshot_at=now,
        feature_snapshot_digest=canonical_snapshot_digest(user_snapshot, item_snapshot),
        ranking_snapshot_digest="a" * 64,
        user_feature_snapshot=user_snapshot,
        item_feature_snapshot=item_snapshot,
        exposed_at=now,
        recorded_at=now,
    )
    canonical, inserted = appender.append(fact)
    assert inserted
    replayed, inserted = appender.append(fact)
    assert not inserted and replayed == canonical
    assert appender.find_by_attribution("request-001", "post-001") == canonical
    assert mongo_database["recommendation_exposure_facts"].count_documents({}) == 1
