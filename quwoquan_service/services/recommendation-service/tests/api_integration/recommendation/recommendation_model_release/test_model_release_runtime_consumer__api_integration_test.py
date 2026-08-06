# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/spec.md#sit-001
# readiness_case: apply-model-release-runtime-api
import json

from internal.recommendation.recommendation_model_release.adapters.inbound.stream.model_release_runtime_consumer import (
    CONSUMER_GROUP,
    ModelReleaseRuntimeConsumer,
    STREAM,
)
from internal.recommendation.recommendation_model_release.application.model_runtime_coordinator import (
    RecommendationModelRuntimeCoordinator,
)
from tests.support.recommendation_redis import real_redis


def test_model_release_runtime_consumes_and_acks_the_real_redis_stream(
    real_redis,
) -> None:
    reloads: list[str] = []
    stream_id = real_redis.xadd(
        STREAM,
        {
            "eventId": "model-release-activated-2",
            "eventType": "RecommendationModelReleaseActivated",
            "aggregateType": "RecommendationModelRelease",
            "aggregateId": "release-001",
            "aggregateVersion": "2",
            "payload": json.dumps({"id": "release-001", "status": "active"}),
        },
    )
    consumer = ModelReleaseRuntimeConsumer(
        redis_client=real_redis,
        coordinator=RecommendationModelRuntimeCoordinator(
            lambda: reloads.append("reload")
        ),
        consumer="api-integration",
    )

    assert consumer.process_once() == 1
    assert reloads == ["reload"]
    assert real_redis.xpending(STREAM, CONSUMER_GROUP)["pending"] == 0
    assert real_redis.xrange(STREAM, min=stream_id, max=stream_id)
    assert consumer.healthy()
