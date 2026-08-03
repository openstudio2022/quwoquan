from datetime import datetime, timezone

from internal.recommendation.recommendation_subject_closure_fact.application.appender import Appender
from internal.recommendation.recommendation_subject_closure_fact.domain.fact import SubjectClosureFact
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (
    MongoSubjectClosureStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database


def test_subject_closure_fact_is_irreversible_for_all_subject_ids(mongo_database) -> None:
    store = MongoSubjectClosureStore(mongo_database)
    store.ensure_indexes()
    appender = Appender(store)
    now = datetime.now(timezone.utc)
    fact = SubjectClosureFact(
        account_id="account-001",
        subject_ids=("account-001", "persona-001"),
        source_event_id="account-closed-001",
        source_digest="a" * 64,
        closed_at=now,
        recorded_at=now,
    )
    assert appender.append(fact)[1]
    assert not appender.append(fact)[1]
    assert appender.is_blocked("account-001")
    assert appender.is_blocked("persona-001")
    assert mongo_database["recommendation_subject_closure_facts"].count_documents({}) == 1
