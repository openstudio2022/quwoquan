from datetime import datetime, timezone

from internal.recommendation.recommendation_feedback_fact.application.appender import Appender, FeedbackFact
from internal.recommendation.recommendation_feedback_fact.infrastructure.mongo_store import MongoFeedbackFactStore
from tests.support.recommendation_mongo import mongo_client, mongo_database


class _ExposureReader:
    def exists(self, exposure_id: str) -> bool:
        return exposure_id == "exposure-001"


class _OpenSubjects:
    def exists(self, _account_id: str) -> bool:
        return False


def test_feedback_fact_has_one_source_event_identity_in_mongo(mongo_database) -> None:
    store = MongoFeedbackFactStore(mongo_database)
    store.ensure_indexes()
    appender = Appender(store, _ExposureReader(), _OpenSubjects())
    now = datetime.now(timezone.utc)
    fact = FeedbackFact(
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
