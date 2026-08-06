# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
# readiness_case: append-subject-closure-api
from datetime import datetime, timezone
import hashlib
import json

from internal.recommendation.recommendation_subject_closure_fact.adapters.inbound.stream.user_account_closed_consumer import (
    CONSUMER_GROUP,
    USER_ACCOUNT_STREAM,
    UserAccountClosedConsumer,
)
from internal.recommendation.recommendation_subject_closure_fact.application.appender import Appender
from internal.recommendation.recommendation_subject_closure_fact.domain.fact import SubjectClosureFact
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (
    MongoSubjectClosureStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis


class _Eraser:
    def __init__(self) -> None:
        self.subjects: list[str] = []

    def erase_subject(self, subject_id: str) -> int:
        self.subjects.append(subject_id)
        return 1


def test_user_account_closed_stream_persists_closure_before_ack(
    mongo_database,
    real_redis,
) -> None:
    store = MongoSubjectClosureStore(mongo_database)
    store.ensure_indexes()
    account_id = "account-stream-001"
    event_id = hashlib.sha256(f"UserAccountClosed:{account_id}".encode()).hexdigest()
    occurred_at = "2026-08-05T08:00:00Z"
    payload = {
        "userId": account_id,
        "accountState": "closed",
        "personaIds": ["persona-stream-001"],
        "updatedAt": occurred_at,
    }
    real_redis.xadd(
        USER_ACCOUNT_STREAM,
        {
            "eventId": event_id,
            "eventName": "UserAccountClosed",
            "accountId": account_id,
            "accountVersion": "1",
            "payload": json.dumps(payload),
            "occurredAt": occurred_at,
        },
    )
    eraser = _Eraser()
    consumer = UserAccountClosedConsumer(
        redis_client=real_redis,
        store=store,
        erasers=(eraser,),
        consumer="subject-closure-api-test",
    )

    assert consumer.process_once() == 1
    assert store.exists(account_id)
    assert eraser.subjects == [account_id, "persona-stream-001"]
    assert real_redis.xpending(USER_ACCOUNT_STREAM, CONSUMER_GROUP)["pending"] == 0


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
