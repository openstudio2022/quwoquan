from datetime import datetime, timezone
from pathlib import Path

from internal.recommendation.ranked_recommendation_window.adapters.inbound.config.content_release_policy import (
    load_content_release_policy,
)
from internal.recommendation.ranked_recommendation_window.adapters.inbound.stream.experiment_policy_consumer import (
    ExperimentPolicyConsumer,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
    assign_bucket,
    canonical_policy,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.experiment_assignment_publisher import (
    RedisExperimentAssignmentPublisher,
    STREAM as ASSIGNMENT_STREAM,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_experiment_policy_store import (
    COLLECTION,
    MongoExperimentPolicyStore,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_experiment_policy_stream import (
    STREAM as POLICY_STREAM,
    RedisExperimentPolicyStream,
)


def test_product_ops_policy_is_projected_and_assignment_observation_is_published() -> None:
    redis = _Redis()
    publisher = RedisExperimentAssignmentPublisher(redis)
    assignments = ExperimentAssignments(publisher)
    store = _Store()
    redis.incoming = [
        (
            "1000-0",
            {
                "eventId": "experiment-policy-rec-5",
                "eventType": "ExperimentPolicyActivated",
                "producer": "product-ops-service",
                "aggregateType": "Experiment",
                "experimentId": "rec_model_vs_rule",
                "payloadJson": '{"id":"rec_model_vs_rule","version":5,"status":"running","variants":[{"key":"model","allocationBasisPoints":5000},{"key":"rule","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"},"updatedAt":"2026-07-31T10:00:00Z"}',
            },
        )
    ]
    consumer = ExperimentPolicyConsumer(
        stream=RedisExperimentPolicyStream(redis),
        store=store,
        assignments=assignments,
        consumer="local-contract",
    )
    assert consumer.process_once() == 1
    assignment = assignments.assign(
        "persona-viewer",
        now=datetime(2026, 7, 31, 11, tzinfo=timezone.utc),
    )
    assert assignment.experiment_revision == 5
    assert assignment.bucket == "rule"
    assignment_events = [item for item in redis.added if item[0] == ASSIGNMENT_STREAM]
    assert len(assignment_events) == 1
    assert assignment_events[0][1]["producer"] == "recommendation-service"
    assert redis.acked == [(POLICY_STREAM, "recommendation-service", "1000-0")]


def test_python_assignment_matches_canonical_fnv1a32_vectors() -> None:
    variants = (PolicyVariant("model", 5000), PolicyVariant("rule", 5000))
    assert assign_bucket("rec_model_vs_rule", "persona-viewer", variants) == "rule"
    assert (
        assign_bucket(
            "rec_model_vs_rule",
            "persona:search-local-contract",
            variants,
        )
        == "model"
    )
    assert assign_bucket("rec_model_vs_rule", "device:1", variants) == "model"
    assert assign_bucket("rec_model_vs_rule", "用户甲", variants) == "model"


def test_content_release_policy_uses_canonical_rule_only_baseline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "recommendation_policy.yaml"
    source.write_text(
        """
experiments:
  - id: rec_model_vs_rule
    enabled: true
    buckets:
      - name: rule
        weightPct: 100
      - name: model
        weightPct: 0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    policy = load_content_release_policy(str(source))

    assert policy.revision == 1
    assert policy.status == "running"
    assert {
        item.key: item.allocation_basis_points for item in policy.variants
    } == {"rule": 10_000, "model": 0}


def test_experiment_policy_store_startup_relies_only_on_declared_id_index() -> None:
    collection = _CollectionWithoutCustomIndexes()
    store = MongoExperimentPolicyStore({COLLECTION: collection})

    assert store.ensure_indexes() is None
    assert collection.create_index_calls == 0


class _Store:
    def __init__(self) -> None:
        self.policy = None

    def apply(self, policy: ExperimentPolicy) -> ExperimentPolicy:
        canonical = canonical_policy(policy)
        if self.policy is None or canonical.revision > self.policy.revision:
            self.policy = canonical
        return self.policy


class _CollectionWithoutCustomIndexes:
    def __init__(self) -> None:
        self.create_index_calls = 0

    def create_index(self, *_args, **_kwargs):
        self.create_index_calls += 1
        raise AssertionError("ranked recommendation policy declares no custom index")


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
        return [(POLICY_STREAM, incoming)] if incoming else []

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
