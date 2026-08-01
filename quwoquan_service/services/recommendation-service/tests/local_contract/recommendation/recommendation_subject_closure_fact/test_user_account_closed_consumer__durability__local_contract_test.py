import hashlib
import json

import pytest

from internal.recommendation.recommendation_subject_closure_fact.adapters.inbound.stream.user_account_closed_consumer import (
    CONSUMER_GROUP,
    USER_ACCOUNT_DLQ,
    USER_ACCOUNT_STREAM,
    UserAccountClosedConsumer,
)


def _fields(*, valid: bool = True) -> dict[bytes, bytes]:
    account_id = "account-001"
    event_id = hashlib.sha256(f"UserAccountClosed:{account_id}".encode()).hexdigest()
    if not valid:
        event_id = "invalid-event-id"
    payload = {
        "userId": account_id,
        "personaIds": ["persona-001"],
        "accountState": "closed",
        "updatedAt": "2026-07-31T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": "UserAccountClosed",
        "accountId": account_id,
        "accountVersion": "9",
        "payload": json.dumps(payload),
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields(valid=self.valid))], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(USER_ACCOUNT_STREAM.encode(), [(b"1000-0", _fields(valid=self.valid))])]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, *_args, **_kwargs):
        return True

    def expire(self, *_args):
        return True


class _Store:
    def __init__(self) -> None:
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        existing = self.facts.setdefault(fact.account_id, fact)
        return existing, existing is fact

    def exists(self, account_id):
        return any(account_id in fact.subject_ids for fact in self.facts.values())

    def record_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_failure(self, _stream_id):
        return None


class _Eraser:
    def __init__(self) -> None:
        self.subject_ids = []

    def erase_subject(self, subject_id):
        self.subject_ids.append(subject_id)
        return 0


class _FailingEraser(_Eraser):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def erase_subject(self, subject_id):
        if not self.failed:
            self.failed = True
            raise RuntimeError("privacy cleanup unavailable")
        return super().erase_subject(subject_id)


def test_consumer_appends_terminal_fact_before_ack() -> None:
    redis = _Redis()
    store = _Store()
    eraser = _Eraser()
    consumer = UserAccountClosedConsumer(
        redis_client=redis,
        store=store,
        erasers=(eraser,),
        consumer="closure-test",
    )
    assert consumer.process_once() == 1
    fact = store.facts["account-001"]
    assert fact.source_event_id == hashlib.sha256(b"UserAccountClosed:account-001").hexdigest()
    assert len(fact.source_digest) == 64
    assert fact.subject_ids == ("account-001", "persona-001")
    assert eraser.subject_ids == ["account-001", "persona-001"]
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_dead_letters_invalid_identity_after_fifth_attempt() -> None:
    redis = _Redis(valid=False)
    store = _Store()
    consumer = UserAccountClosedConsumer(
        redis_client=redis,
        store=store,
        erasers=(_Eraser(),),
        consumer="closure-test",
    )
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="identity"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == USER_ACCOUNT_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_retries_local_privacy_cleanup_before_ack() -> None:
    redis = _Redis()
    store = _Store()
    eraser = _FailingEraser()
    consumer = UserAccountClosedConsumer(
        redis_client=redis,
        store=store,
        erasers=(eraser,),
        consumer="closure-test",
    )

    with pytest.raises(RuntimeError, match="privacy cleanup"):
        consumer.process_once()
    assert "account-001" in store.facts
    assert redis.acked == []

    assert consumer.process_once() == 1
    assert eraser.subject_ids == ["account-001", "persona-001"]
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]
