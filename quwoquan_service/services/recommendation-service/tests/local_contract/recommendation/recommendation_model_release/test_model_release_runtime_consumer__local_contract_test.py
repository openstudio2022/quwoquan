# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/spec.md#sit-001
# readiness_case: apply-model-release-runtime-local
from internal.recommendation.recommendation_model_release.adapters.inbound.stream.model_release_runtime_consumer import (
    CONSUMER_GROUP,
    DLQ,
    ModelReleaseRuntimeConsumer,
    STREAM,
)
from internal.recommendation.recommendation_model_release.application.model_runtime_coordinator import (
    RecommendationModelRuntimeCoordinator,
)


def test_release_stream_acknowledges_stage_and_reloads_active_runtime() -> None:
    redis = _Redis()
    reloads: list[str] = []
    redis.incoming = [
        _event("1-0", "RecommendationModelReleaseStaged", "staged", 1),
        _event("2-0", "RecommendationModelReleaseActivated", "active", 2),
        _event("3-0", "RecommendationModelReleaseRetired", "retired", 3),
    ]
    consumer = ModelReleaseRuntimeConsumer(
        redis_client=redis,
        coordinator=RecommendationModelRuntimeCoordinator(
            lambda: reloads.append("reload")
        ),
        consumer="local-contract",
    )

    assert consumer.process_once() == 3
    assert reloads == ["reload", "reload"]
    assert redis.acked == [
        (STREAM, CONSUMER_GROUP, "1-0"),
        (STREAM, CONSUMER_GROUP, "2-0"),
        (STREAM, CONSUMER_GROUP, "3-0"),
    ]
    assert consumer.healthy()


def test_invalid_release_event_is_dead_lettered_without_reloading() -> None:
    redis = _Redis()
    reloads: list[str] = []
    redis.incoming = [
        (
            "4-0",
            {
                "eventId": "release-1:4",
                "eventType": "RecommendationModelReleaseActivated",
                "aggregateType": "RecommendationModelRelease",
                "aggregateId": "release-1",
                "aggregateVersion": "4",
                "payload": '{"id":"other","status":"active"}',
            },
        )
    ]
    consumer = ModelReleaseRuntimeConsumer(
        redis_client=redis,
        coordinator=RecommendationModelRuntimeCoordinator(
            lambda: reloads.append("reload")
        ),
        consumer="local-contract",
    )

    assert consumer.process_once() == 1
    assert reloads == []
    assert redis.acked == [(STREAM, CONSUMER_GROUP, "4-0")]
    assert len(redis.added) == 1 and redis.added[0][0] == DLQ


def _event(stream_id: str, event_type: str, status: str, version: int):
    return (
        stream_id,
        {
            "eventId": f"release-1:{version}",
            "eventType": event_type,
            "aggregateType": "RecommendationModelRelease",
            "aggregateId": "release-1",
            "aggregateVersion": str(version),
            "payload": f'{{"id":"release-1","status":"{status}"}}',
        },
    )


class _Redis:
    def __init__(self) -> None:
        self.incoming = []
        self.added = []
        self.acked = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        return ("0-0", [])

    def xreadgroup(self, *_args, **_kwargs):
        incoming = self.incoming
        self.incoming = []
        return [(STREAM, incoming)] if incoming else []

    def xack(self, stream, group, stream_id):
        self.acked.append((stream, group, stream_id))
        return 1

    def xadd(self, stream, fields):
        self.added.append((stream, dict(fields)))
        return f"{len(self.added)}-0"

    def time(self):
        return (1_800_000_000, 0)

    def xtrim(self, *_args, **_kwargs):
        return 0

    def expire(self, *_args, **_kwargs):
        return True
