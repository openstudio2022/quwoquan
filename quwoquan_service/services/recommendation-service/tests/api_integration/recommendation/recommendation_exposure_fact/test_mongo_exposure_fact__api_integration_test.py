from datetime import datetime, timezone

from internal.recommendation.recommendation_exposure_fact.application.appender import (
    Appender,
    ExposureFact,
    canonical_snapshot_digest,
)
from internal.recommendation.recommendation_exposure_fact.infrastructure.mongo_store import (
    MongoExposureFactStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database


class _OpenSubjects:
    def exists(self, _account_id: str) -> bool:
        return False


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
