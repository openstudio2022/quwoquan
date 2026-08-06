from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from internal.recommendation.recommendation_model_release.application.outbox_relay import (
    RecommendationModelReleaseOutboxRelay,
)
from internal.recommendation.recommendation_model_release.domain.outbox import (
    MODEL_RELEASE_EVENT_PAYLOAD_FIELDS,
    OutboxClaimLostError,
    OutboxEvent,
    build_model_release_event_payload,
)
from internal.recommendation.recommendation_model_release.infrastructure.redis_event_publisher import (
    MODEL_RELEASE_EVENT_RETENTION_SECONDS,
    MODEL_RELEASE_EVENT_STREAM,
    RedisRecommendationModelReleaseEventPublisher,
)


class OutboxFixture:
    def __init__(self, event: OutboxEvent) -> None:
        self.event = event
        self.available = True
        self.claim_owner = ""
        self.marked = 0
        self.retried = 0

    def claim_pending_outbox(self, owner_id, _now, _lease_seconds):
        self.claim_owner = owner_id
        return self.event if self.available else None

    def mark_outbox_published(self, _event_id, owner_id, _published_at):
        if owner_id != self.claim_owner:
            raise OutboxClaimLostError("claim lost")
        self.marked += 1
        self.available = False

    def schedule_outbox_retry(
        self, _event_id, owner_id, _next_attempt_at, _failure_code
    ):
        if owner_id != self.claim_owner:
            raise OutboxClaimLostError("claim lost")
        self.retried += 1
        self.available = False


class RedisFixture:
    def __init__(self) -> None:
        self.fail = True
        self.stream = ""
        self.fields = {}
        self.trimmed = False
        self.retention = 0

    def xadd(self, stream, fields):
        if self.fail:
            raise RuntimeError("transport unavailable")
        self.stream = stream
        self.fields = dict(fields)
        return "1-0"

    def time(self):
        return (1_800_000_000, 0)

    def xtrim(self, stream, *, minid, approximate):
        assert stream == MODEL_RELEASE_EVENT_STREAM
        assert minid.endswith("-0")
        assert approximate is False
        self.trimmed = True

    def expire(self, stream, retention):
        assert stream == MODEL_RELEASE_EVENT_STREAM
        self.retention = retention


def test_model_release_relay_checkpoints_only_after_durable_publish() -> None:
    now = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)
    event = OutboxEvent(
        event_id="release-1\x1f1\x1fRecommendationModelReleaseStaged",
        event_type="RecommendationModelReleaseStaged",
        aggregate_id="release-1",
        aggregate_version=1,
        payload=build_model_release_event_payload(
            "RecommendationModelReleaseStaged",
            release_id="release-1",
            scenario="content_feed",
            model_digest="a" * 64,
            feature_contract_digest="b" * 64,
            occurred_at=now,
        ),
        occurred_at=now,
        attempt_count=1,
    )
    outbox = OutboxFixture(event)
    redis = RedisFixture()
    relay = RecommendationModelReleaseOutboxRelay(
        outbox,
        RedisRecommendationModelReleaseEventPublisher(redis),
    )

    with pytest.raises(RuntimeError, match="transport unavailable"):
        relay.drain(limit=1)
    assert outbox.marked == 0
    assert outbox.retried == 1
    assert not relay.healthy(max_staleness_seconds=60)

    outbox.available = True
    redis.fail = False
    assert relay.drain(limit=1) == 1
    assert outbox.marked == 1
    assert redis.stream == MODEL_RELEASE_EVENT_STREAM
    assert redis.fields["aggregateId"] == event.aggregate_id
    assert json.loads(redis.fields["payload"]) == event.payload
    assert redis.trimmed
    assert redis.retention == MODEL_RELEASE_EVENT_RETENTION_SECONDS
    assert relay.healthy(max_staleness_seconds=60)


def test_model_release_payload_shapes_are_owned_by_events_contract() -> None:
    service_root = Path(__file__).resolve().parents[4]
    metadata = yaml.safe_load(
        (
            service_root
            / "contracts/recommendation/recommendation_model_release/events.yaml"
        ).read_text(encoding="utf-8")
    )
    declared = {
        event["name"]: tuple(event["payload_fields"])
        for event in metadata["events"]
    }
    assert declared == MODEL_RELEASE_EVENT_PAYLOAD_FIELDS

    now = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)
    payloads = {
        event_type: build_model_release_event_payload(
            event_type,
            release_id="release-1",
            scenario="content_feed",
            model_digest="a" * 64,
            feature_contract_digest="b" * 64,
            occurred_at=now,
        )
        for event_type in declared
    }
    for event_type, payload in payloads.items():
        assert tuple(key for key in declared[event_type] if key in payload) == declared[
            event_type
        ]
        assert set(payload) == set(declared[event_type])


def test_model_release_relay_rejects_legacy_or_extra_payload_fields() -> None:
    now = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)
    legacy_event = OutboxEvent(
        event_id="release-1\x1f1\x1fRecommendationModelReleaseActivated",
        event_type="RecommendationModelReleaseActivated",
        aggregate_id="release-1",
        aggregate_version=1,
        payload={
            "releaseId": "release-1",
            "scenario": "content_feed",
            "modelDigest": "a" * 64,
            "featureContractDigest": "b" * 64,
            "previousActiveReleaseId": None,
        },
        occurred_at=now,
        attempt_count=1,
    )
    outbox = OutboxFixture(legacy_event)
    redis = RedisFixture()
    redis.fail = False
    relay = RecommendationModelReleaseOutboxRelay(
        outbox,
        RedisRecommendationModelReleaseEventPublisher(redis),
    )

    with pytest.raises(ValueError, match="does not match its contract"):
        relay.drain(limit=1)
    assert outbox.retried == 1
    assert outbox.marked == 0
    assert redis.fields == {}
