from __future__ import annotations

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from internal.recommendation.ranked_recommendation_window.application.experiment_policy_stream import (
    ExperimentPolicyStreamUnavailable,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_experiment_policy_stream import (
    RedisExperimentPolicyStream,
)


def test_redis_driver_failure_is_translated_at_infrastructure_boundary() -> None:
    driver_error = RedisConnectionError("redis not ready")
    stream = RedisExperimentPolicyStream(_FailingRedis(driver_error))

    with pytest.raises(ExperimentPolicyStreamUnavailable) as captured:
        stream.ensure_consumer_group()

    assert captured.value.__cause__ is driver_error
    assert "redis not ready" not in str(captured.value)


def test_non_driver_programming_failure_is_not_hidden_as_dependency_unavailable() -> None:
    stream = RedisExperimentPolicyStream(_FailingRedis(RuntimeError("bad fake shape")))

    with pytest.raises(RuntimeError, match="bad fake shape"):
        stream.ensure_consumer_group()


class _FailingRedis:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def xgroup_create(self, *_args, **_kwargs):
        raise self.error
