"""RecommendationCandidateIndexView 投影观测。

契约 runtime_entrypoints[].telemetry.metric 同名计数器
（recommendation_candidate_index_projection，consumer+outcome 标签），
五个上游流消费者共用。
"""
from __future__ import annotations

from prometheus_client import Counter

_PROJECTION_OUTCOMES = Counter(
    "recommendation_candidate_index_projection",
    "Contract runtime entrypoint outcome counter (candidate index stream consumers).",
    ["consumer", "outcome"],
)


def record_projection_outcome(consumer: str, outcome: str) -> None:
    _PROJECTION_OUTCOMES.labels(consumer=consumer, outcome=outcome).inc()
