# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t3

from __future__ import annotations

from datetime import datetime, timezone

from internal.recommendation.ranked_recommendation_window.adapters.inbound.stream.experiment_policy_consumer import (
    ExperimentPolicyConsumer,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
    ExperimentPolicy,
    canonical_policy,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_experiment_policy_stream import (
    CONSUMER_GROUP,
    STREAM,
    RedisExperimentPolicyStream,
)
from tests.support.recommendation_redis import real_redis


def test_policy_consumer_reads_and_acknowledges_real_redis_stream(real_redis) -> None:
    stream_id = real_redis.xadd(
        STREAM,
        {
            "eventId": "experiment-policy-rec-9",
            "eventType": "ExperimentPolicyActivated",
            "producer": "product-ops-service",
            "aggregateType": "Experiment",
            "experimentId": "rec_model_vs_rule",
            "payloadJson": '{"id":"rec_model_vs_rule","version":9,"status":"running","variants":[{"key":"model","allocationBasisPoints":5000},{"key":"rule","allocationBasisPoints":5000}],"updatedAt":"2026-08-11T01:00:00Z"}',
        },
    )
    assignments = ExperimentAssignments(_Publisher())
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(real_redis),
        store=_Store(),
        assignments=assignments,
        consumer="api-integration",
    )

    assert consumer.process_once() == 1
    assert consumer.process_once() == 0
    assert assignments.healthy(
        now=datetime(2026, 8, 11, 1, 1, tzinfo=timezone.utc)
    )
    assert real_redis.xpending(STREAM, CONSUMER_GROUP)["pending"] == 0
    assert real_redis.xrange(STREAM, min=stream_id, max=stream_id)


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
