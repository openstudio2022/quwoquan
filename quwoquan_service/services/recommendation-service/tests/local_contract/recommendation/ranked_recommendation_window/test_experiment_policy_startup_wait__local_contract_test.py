# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001

from datetime import datetime, timezone
from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from internal.recommendation.ranked_recommendation_window.adapters.inbound.stream.experiment_policy_consumer import (
    ExperimentPolicyConsumer,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
    ExperimentPolicy,
    canonical_policy,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_experiment_policy_stream import (
    STREAM,
    RedisExperimentPolicyStream,
)


def test_startup_wait_consumes_delayed_authored_policy() -> None:
    redis = _Redis(
        batches=[
            [],
            [
                (
                    "1000-0",
                    {
                        "eventId": "experiment-policy-rec-7",
                        "eventType": "ExperimentPolicyActivated",
                        "producer": "product-ops-service",
                        "aggregateType": "Experiment",
                        "experimentId": "rec_model_vs_rule",
                        "payloadJson": '{"id":"rec_model_vs_rule","version":7,"status":"running","variants":[{"key":"model","allocationBasisPoints":5000},{"key":"rule","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"},"updatedAt":"2026-08-09T03:00:00Z"}',
                    },
                )
            ],
        ]
    )
    assignments = ExperimentAssignments(_Publisher())
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(redis),
        store=_Store(),
        assignments=assignments,
        consumer="startup-wait-local-contract",
    )

    assert consumer.wait_for_active_policy(
        timeout_seconds=0.1,
        poll_interval_seconds=0.001,
    )
    assert assignments.healthy(now=datetime(2026, 8, 9, 3, 1, tzinfo=timezone.utc))
    assert redis.acked == [(STREAM, "recommendation-service", "1000-0")]
    assert redis.read_count == 2


def test_startup_wait_replays_acknowledged_history_when_projection_is_lost() -> None:
    """旧 Redis 卷 + 新投影卷：事件已被 consumer group ack，xreadgroup 不再投递，
    启动等待必须用只读 XRANGE 从同一 authored stream 重建投影自愈。"""

    acknowledged_event = (
        "1000-0",
        {
            "eventId": "experiment-policy-rec-7",
            "eventType": "ExperimentPolicyActivated",
            "producer": "product-ops-service",
            "aggregateType": "Experiment",
            "experimentId": "rec_model_vs_rule",
            "payloadJson": '{"id":"rec_model_vs_rule","version":7,"status":"running","variants":[{"key":"model","allocationBasisPoints":5000},{"key":"rule","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"},"updatedAt":"2026-08-09T03:00:00Z"}',
        },
    )
    undecodable_acknowledged_event = ("0999-0", {"eventType": "SomethingElse"})
    redis = _Redis(
        batches=[[], []],
        retained_history=[undecodable_acknowledged_event, acknowledged_event],
    )
    assignments = ExperimentAssignments(_Publisher())
    store = _Store()
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(redis),
        store=store,
        assignments=assignments,
        consumer="startup-wait-local-contract",
    )

    assert consumer.wait_for_active_policy(
        timeout_seconds=0.1,
        poll_interval_seconds=0.001,
    )
    assert assignments.healthy(now=datetime(2026, 8, 9, 3, 1, tzinfo=timezone.utc))
    assert store.policy is not None and store.policy.revision == 7
    # 只读重放：不 ack、不重复消费、坏事件不再进 DLQ（xadd 会直接断言失败）。
    assert redis.acked == []
    assert redis.replay_count == 1


def test_startup_wait_replay_is_empty_on_brand_new_stream_and_keeps_waiting() -> None:
    redis = _Redis(batches=[[], []])
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(redis),
        store=_Store(),
        assignments=ExperimentAssignments(_Publisher()),
        consumer="startup-wait-local-contract",
    )

    assert not consumer.wait_for_active_policy(
        timeout_seconds=0.01,
        poll_interval_seconds=0.001,
    )
    assert redis.replay_count == 1
    assert redis.read_count >= 2


def test_startup_wait_retries_transport_but_times_out_without_authored_policy() -> None:
    redis = _Redis(batches=[[], []], transport_failures=1)
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(redis),
        store=_Store(),
        assignments=ExperimentAssignments(_Publisher()),
        consumer="startup-wait-local-contract",
    )

    assert not consumer.wait_for_active_policy(
        timeout_seconds=0.01,
        poll_interval_seconds=0.001,
    )
    assert redis.read_count >= 1


def test_full_composition_uses_bounded_wait_without_content_policy_fallback() -> None:
    source = (
        Path(__file__).resolve().parents[4] / "cmd" / "api" / "main.py"
    ).read_text(encoding="utf-8")
    startup = source.split(
        "experiment_policy_consumer = ExperimentPolicyConsumer(", 1
    )[1].split("window_store = RedisWindowStore(", 1)[0]

    assert "if content_slice_workload:" in startup
    assert "stream=RedisExperimentPolicyStream(general_redis_client)" in startup
    assert "redis_client=general_redis_client" not in startup
    assert "else:\n            experiment_ready = experiment_policy_consumer.wait_for_active_policy(" in startup
    assert "timeout_seconds=EXPERIMENT_POLICY_STARTUP_TIMEOUT_SECONDS" in startup
    assert "load_content_release_policy" not in startup


@pytest.mark.parametrize(
    ("timeout_seconds", "poll_interval_seconds"),
    ((0, 0.1), (1, 0), (float("inf"), 0.1), (True, 0.1)),
)
def test_startup_wait_rejects_unbounded_or_invalid_timing(
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> None:
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(_Redis(batches=[])),
        store=_Store(),
        assignments=ExperimentAssignments(_Publisher()),
        consumer="startup-wait-local-contract",
    )

    with pytest.raises(ValueError, match="startup (timeout|poll interval)"):
        consumer.wait_for_active_policy(
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


class _Publisher:
    def publish(self, _assignment) -> None:
        return None


class _Store:
    def __init__(self) -> None:
        self.policy: ExperimentPolicy | None = None

    def apply(self, policy: ExperimentPolicy) -> ExperimentPolicy:
        canonical = canonical_policy(policy)
        if self.policy is None or canonical.revision > self.policy.revision:
            self.policy = canonical
        return self.policy


class _Redis:
    def __init__(
        self,
        *,
        batches: list[list[tuple[str, dict[str, str]]]],
        transport_failures: int = 0,
        retained_history: list[tuple[str, dict[str, str]]] | None = None,
    ) -> None:
        self.batches = list(batches)
        self.transport_failures = transport_failures
        self.retained_history = list(retained_history or [])
        self.acked: list[tuple[str, str, str]] = []
        self.read_count = 0
        self.replay_count = 0

    def xgroup_create(self, *_args, **_kwargs):
        if self.transport_failures > 0:
            self.transport_failures -= 1
            raise RedisConnectionError("redis not ready")
        return True

    def xautoclaim(self, *_args, **_kwargs):
        return ("0-0", [])

    def xreadgroup(self, *_args, **_kwargs):
        self.read_count += 1
        batch = self.batches.pop(0) if self.batches else []
        return [(STREAM, batch)] if batch else []

    def xrange(self, _stream, *, min="-", max="+"):
        self.replay_count += 1
        return list(self.retained_history)

    def xack(self, stream, group, stream_id):
        self.acked.append((stream, group, stream_id))
        return 1

    def xadd(self, *_args, **_kwargs):
        raise AssertionError("valid startup policy must not enter the DLQ")

    def time(self):
        return (1_800_000_000, 0)

    def xtrim(self, *_args, **_kwargs):
        return 0

    def expire(self, *_args, **_kwargs):
        return True
