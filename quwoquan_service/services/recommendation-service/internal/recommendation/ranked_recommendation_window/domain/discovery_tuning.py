"""Ops-tunable discovery ranking knobs (ops.reco.discovery.*).

The three knobs are declared in config/schema.yaml and rendered into the
service runtime config by the environment composition. They are an ops
intervention layer applied uniformly to both experiment buckets, so they never
change bucket assignment and are recorded in the ranking snapshot for
explainability.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

# Candidates younger than this get the prerank new-content boost. The window
# matches the 24h freshness time scale used by the canonical rule scorer.
NEW_CONTENT_BOOST_MAX_AGE_HOURS = 24.0

# Whitelist mode keeps only canonical-release supply (content-service
# projection value "data_engineering"); UGC is excluded while enabled.
WHITELIST_SUPPLY_SOURCE = "data_engineering"


@dataclass(frozen=True, slots=True)
class DiscoveryRankingTuning:
    new_content_boost: float
    author_diversity_weight: float
    whitelist_enabled: bool

    def __post_init__(self) -> None:
        boost = float(self.new_content_boost)
        weight = float(self.author_diversity_weight)
        if not math.isfinite(boost) or boost <= 0.0:
            raise ValueError("new_content_boost must be a finite positive float")
        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
            raise ValueError("author_diversity_weight must be within [0, 1]")
        if not isinstance(self.whitelist_enabled, bool):
            raise ValueError("whitelist_enabled must be a bool")

    @classmethod
    def neutral(cls) -> "DiscoveryRankingTuning":
        return cls(
            new_content_boost=1.0,
            author_diversity_weight=1.0,
            whitelist_enabled=False,
        )

    @classmethod
    def from_runtime_config(cls, config: Mapping[str, Any]) -> "DiscoveryRankingTuning":
        node: Any = config
        for key in ("ops", "reco", "discovery"):
            if not isinstance(node, Mapping) or key not in node:
                raise RuntimeError(
                    "runtime config is missing the ops.reco.discovery tuning tree"
                )
            node = node[key]
        if not isinstance(node, Mapping):
            raise RuntimeError("ops.reco.discovery must be a mapping")
        try:
            prerank = node["prerank"]["new_content_boost"]
            rank = node["rank"]["author_diversity_weight"]
            recall = node["recall"]["whitelist_enabled"]
        except (KeyError, TypeError) as error:
            raise RuntimeError(
                "ops.reco.discovery is missing prerank.new_content_boost, "
                "rank.author_diversity_weight or recall.whitelist_enabled"
            ) from error
        if not isinstance(recall, bool):
            raise RuntimeError("ops.reco.discovery.recall.whitelist_enabled must be a bool")
        return cls(
            new_content_boost=float(prerank),
            author_diversity_weight=float(rank),
            whitelist_enabled=recall,
        )
