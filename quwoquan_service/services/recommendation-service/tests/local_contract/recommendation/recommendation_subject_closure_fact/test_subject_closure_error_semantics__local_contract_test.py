# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
"""账号关闭事实 consumer 错误码语义合约。

RECOMMENDATION.SYSTEM.subject_closure_source_event_invalid 与
RECOMMENDATION.SYSTEM.subject_closure_append_unavailable 只有 consumer 面,
canonical 语义是 errors.yaml 声明的 recovery 行为:invalid -> absorb
(重试穷尽进对象 DLQ,关闭栅栏缺失不伪造成功),unavailable -> retry
(不 ack、有界重试直至关闭终态可被强制执行)。本测试逐码断言契约声明
与 consumer 真实失败行为同源。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from internal.recommendation.recommendation_subject_closure_fact.adapters.inbound.stream.user_account_closed_consumer import (
    CONSUMER_GROUP,
    USER_ACCOUNT_DLQ,
    USER_ACCOUNT_STREAM,
    UserAccountClosedConsumer,
)

SERVICE_ROOT = Path(__file__).resolve().parents[4]
ERRORS_YAML = (
    SERVICE_ROOT
    / "contracts/recommendation/recommendation_subject_closure_fact/errors.yaml"
)

SOURCE_EVENT_INVALID_CODE = (
    "RECOMMENDATION.SYSTEM.subject_closure_source_event_invalid"
)
APPEND_UNAVAILABLE_CODE = "RECOMMENDATION.SYSTEM.subject_closure_append_unavailable"


def _declared(code: str) -> dict:
    document = yaml.safe_load(ERRORS_YAML.read_text(encoding="utf-8"))
    return next(entry for entry in document["errors"] if entry["code"] == code)


def _fields(*, valid_identity: bool = True) -> dict[bytes, bytes]:
    account_id = "account-001"
    event_id = hashlib.sha256(f"UserAccountClosed:{account_id}".encode()).hexdigest()
    if not valid_identity:
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
    def __init__(self, *, valid_identity: bool = True) -> None:
        self.valid_identity = valid_identity
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return (
                "0-0",
                [(b"1000-0", _fields(valid_identity=self.valid_identity))],
                [],
            )
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [
            (
                USER_ACCOUNT_STREAM.encode(),
                [(b"1000-0", _fields(valid_identity=self.valid_identity))],
            )
        ]

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
    def __init__(self, *, append_failures: int = 0) -> None:
        self.append_failures = append_failures
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        if self.append_failures > 0:
            self.append_failures -= 1
            raise RuntimeError("subject closure append unavailable")
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


def _consumer(redis, store):
    return UserAccountClosedConsumer(
        redis_client=redis,
        store=store,
        erasers=(_Eraser(),),
        consumer="closure-error-semantics-test",
    )


def test_source_event_invalid_is_absorbed_into_the_object_dlq() -> None:
    declared = _declared(SOURCE_EVENT_INVALID_CODE)
    assert declared["recovery_action"] == "absorb"
    assert {"surface": "consumer"} in declared["emitted_by"]

    redis = _Redis(valid_identity=False)
    store = _Store()
    consumer = _consumer(redis, store)
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="identity"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert store.facts == {}
    assert redis.dead_letters[0][0] == USER_ACCOUNT_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]


def test_append_unavailable_keeps_the_message_pending_until_storage_recovers() -> None:
    declared = _declared(APPEND_UNAVAILABLE_CODE)
    assert declared["recovery_action"] == "retry"
    assert declared["recovery_after_seconds"] == 5

    redis = _Redis()
    store = _Store(append_failures=2)
    consumer = _consumer(redis, store)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="append unavailable"):
            consumer.process_once()
        assert redis.acked == []
        assert redis.dead_letters == []

    assert consumer.process_once() == 1
    assert "account-001" in store.facts
    assert redis.dead_letters == []
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]
