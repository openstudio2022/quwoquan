"""搜推联动 consumer 合同：解码、幂等推进、隐私脱敏与有界衰减。"""
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
from datetime import datetime, timedelta, timezone

import pytest

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.search_signal_consumer import (
    CONSUMER_GROUP,
    SEARCH_SIGNAL_DLQ,
    SEARCH_SIGNAL_STREAM,
    SearchSignalConsumer,
    decode_search_signal,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)

SENSITIVE_QUERY = "尿路感染 挂什么科"


def _fields(
    *,
    signal_type: str = "query",
    user_id: str = "persona-001",
    query: str = SENSITIVE_QUERY,
) -> dict[bytes, bytes]:
    values = {
        "eventType": "SearchRecommendationSignalPublished",
        "signalId": "signal-001",
        "signalType": signal_type,
        "searchRequestId": "req-001",
        "sessionId": "session-001",
        "userId": user_id,
        "normalizedQuery": query if signal_type == "query" else "",
        "relatedTerms": '["泌尿科"]' if signal_type == "query" else "[]",
        "engagedObjectIds": "[]" if signal_type == "query" else '["posts/a/1"]',
        "experimentBucket": "",
        "resultCount": "8",
        "createdAt": "2026-08-02T12:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, fields: dict[bytes, bytes]) -> None:
        self.fields = fields
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []
        self.trimmed = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", self.fields)], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(SEARCH_SIGNAL_STREAM.encode(), [(b"1000-0", self.fields)])]

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
    def __init__(self) -> None:
        self.attempts = 0
        self.failures = []
        self.cleared = []

    def record_source_failure(self, stream_id, event_id, error):
        self.attempts += 1
        self.failures.append((stream_id, event_id, str(error)))
        return self.attempts

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


class _Projector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def project_search_signal(self, **event):
        if self.fail:
            raise RuntimeError("search feature projection failed")
        self.events.append(event)
        return True


class _Closures:
    def exists(self, _subject_id: str) -> bool:
        return False


def _consumer(redis, store, projector) -> SearchSignalConsumer:
    return SearchSignalConsumer(
        redis_client=redis,
        feature_store=store,
        feature_projector=projector,
        subject_closures=_Closures(),
        consumer="search-signal-test",
    )


def test_decode_merges_query_and_related_terms() -> None:
    signal = decode_search_signal(
        {key.decode(): value.decode() for key, value in _fields().items()}
    )
    assert signal.signal_type == "query"
    assert signal.terms == (SENSITIVE_QUERY, "泌尿科")
    assert signal.subject_id == "persona-001"


def test_consumer_projects_query_terms_before_ack() -> None:
    redis = _Redis(_fields())
    store = _Store()
    projector = _Projector()
    assert _consumer(redis, store, projector).process_once() == 1
    assert projector.events[0]["signal_id"] == "signal-001"
    assert projector.events[0]["terms"] == (SENSITIVE_QUERY, "泌尿科")
    assert redis.acked == [(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, "1000-0")]
    assert store.cleared == ["1000-0"]


def test_anonymous_signal_is_acked_without_projection() -> None:
    redis = _Redis(_fields(user_id=""))
    store = _Store()
    projector = _Projector()
    assert _consumer(redis, store, projector).process_once() == 1
    assert projector.events == []
    assert redis.acked == [(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, "1000-0")]


def test_dead_letter_and_failure_records_never_carry_query_text() -> None:
    redis = _Redis(_fields())
    store = _Store()
    consumer = _consumer(redis, store, _Projector(fail=True))
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(RuntimeError):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    # 隐私约束：DLQ 与失败记录不得出现原始查询词。
    assert redis.dead_letters[0][0] == SEARCH_SIGNAL_DLQ
    dlq_payload = "".join(str(v) for v in redis.dead_letters[0][1].values())
    assert SENSITIVE_QUERY not in dlq_payload
    assert "泌尿科" not in dlq_payload
    for _stream_id, _event_id, message in store.failures:
        assert SENSITIVE_QUERY not in message
        assert "泌尿科" not in message
    assert redis.acked == [(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, "1000-0")]


def test_decayed_search_terms_half_life_and_bound() -> None:
    now = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)
    # 半衰期语义：7 天前 weight=2.0 的 term 衰减到 1.0，再 +1 后为 2.0。
    merged = MongoFeatureProfileStore._decayed_search_terms(
        [
            {
                "term": "成都",
                "weight": 2.0,
                "lastSeenAt": now - timedelta(days=7),
            }
        ],
        ("成都",),
        now=now,
    )
    assert len(merged) == 1
    assert merged[0]["term"] == "成都"
    assert merged[0]["weight"] == pytest.approx(2.0, rel=1e-6)

    # 上限语义：超过 50 个 term 时按权重保留 top-50。
    stale = [
        {"term": f"term-{index}", "weight": float(index + 1), "lastSeenAt": now}
        for index in range(60)
    ]
    bounded = MongoFeatureProfileStore._decayed_search_terms(stale, (), now=now)
    assert len(bounded) == 50
    weights = [entry["weight"] for entry in bounded]
    assert min(weights) >= 11.0  # 最弱的 10 个被淘汰

    # 衰减到阈值以下的 term 被清除。
    faded = MongoFeatureProfileStore._decayed_search_terms(
        [
            {
                "term": "过期词",
                "weight": 0.02,
                "lastSeenAt": now - timedelta(days=70),
            }
        ],
        (),
        now=now,
    )
    assert faded == []
