import json

import pytest

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.premium_pool_consumer import (
    CONSUMER_GROUP,
    PREMIUM_POOL_DLQ,
    PREMIUM_POOL_STREAM,
    PremiumPoolConsumer,
    decode_premium_pool_event,
)


def _fields(*, event_type: str = "PremiumPoolEntryUpserted", status: str = "active"):
    payload = {
        "contentId": "post-001",
        "scope": "global",
        "status": status,
        "qualityScore": 0.91,
        "qualityAdmission": "approved",
        "supplySource": "product_ops",
        "sourceTaskId": "task-001",
        "auditId": "audit-001",
        "rollbackToken": "rollback-001",
        "featuredAt": "2026-07-31T10:00:00Z",
        "expiresAt": "2026-08-01T10:00:00Z",
        "takedownEjected": status == "takedown_ejected",
        "updatedAt": "2026-07-31T11:00:00Z",
    }
    values = {
        "eventId": "premium-event-001",
        "eventType": event_type,
        "aggregateType": "PremiumPoolEntry",
        "aggregateId": "post-001",
        "occurredAt": "2026-07-31T11:00:00Z",
        "payloadJson": json.dumps(payload),
        "producer": "product-ops-service",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self) -> None:
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []
        self.trimmed = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields())], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(PREMIUM_POOL_STREAM.encode(), [(b"1000-0", _fields())])]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, stream, **kwargs):
        self.trimmed.append((stream, kwargs))

    def expire(self, *_args):
        return True


class _Store:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []
        self.attempts = 0
        self.cleared = []

    def apply_premium_source_event(self, **event):
        if self.fail:
            raise RuntimeError("premium projection failed")
        self.events.append(event)
        return True

    def record_source_failure(self, _stream_id, _event_id, _cause):
        self.attempts += 1
        return self.attempts

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


def test_consumer_projects_then_acks_one_typed_premium_event() -> None:
    redis = _Redis()
    store = _Store()
    consumer = PremiumPoolConsumer(
        redis_client=redis,
        store=store,
        consumer="premium-test",
    )
    assert consumer.process_once() == 1
    assert store.events[0]["event_id"] == "premium-event-001"
    assert store.events[0]["snapshot"].content_id == "post-001"
    assert redis.acked == [(PREMIUM_POOL_STREAM, CONSUMER_GROUP, "1000-0")]
    assert store.cleared == ["1000-0"]


def test_event_type_and_status_must_be_one_typed_transition() -> None:
    values = {key.decode(): value.decode() for key, value in _fields().items()}
    payload = json.loads(values["payloadJson"])
    payload["status"] = "rolled_back"
    values["payloadJson"] = json.dumps(payload)
    with pytest.raises(ValueError, match="type and status mismatch"):
        decode_premium_pool_event(values)


def test_consumer_dead_letters_and_acks_only_after_fifth_failure() -> None:
    redis = _Redis()
    store = _Store(fail=True)
    consumer = PremiumPoolConsumer(
        redis_client=redis,
        store=store,
        consumer="premium-test",
    )
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(RuntimeError, match="premium projection failed"):
                consumer.process_once()
            assert redis.acked == []
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == PREMIUM_POOL_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(PREMIUM_POOL_STREAM, CONSUMER_GROUP, "1000-0")]
