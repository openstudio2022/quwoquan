"""Governed per-carrier thresholds for the M100 to M1000 handoff."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.runtime_policy import active_runtime_policy
from governance.coverage.distribution import load_content_distribution_policy


@dataclass(frozen=True, slots=True)
class M100PromotionThresholds:
    quota: int
    source_ready_minimum: int
    candidate_minimum: int


def m100_promotion_thresholds(carrier: str) -> M100PromotionThresholds:
    if carrier not in {"image", "video"}:
        raise ValueError("scale promotion carrier must be image or video")
    quota = load_content_distribution_policy().scale_target("M100", carrier)
    candidate_minimum = math.ceil(
        quota * active_runtime_policy().oversample_factor
    )
    return M100PromotionThresholds(
        quota=quota,
        source_ready_minimum=quota,
        candidate_minimum=candidate_minimum,
    )


def require_frozen_source_inputs(source_document: Mapping[str, Any]) -> None:
    """Validate the predecessor digest without reading live Git cleanliness."""
    inputs = source_document.get("inputs")
    digest = str(source_document.get("digest") or "")
    if (
        source_document.get("algorithm") != "sha256"
        or not digest.startswith("sha256:")
        or len(digest) != 71
        or not isinstance(inputs, list)
        or not inputs
        or any(not isinstance(item, str) or not item.strip() for item in inputs)
    ):
        raise ValueError("M100 promotion sourceDigest inputs are missing")


__all__ = [
    "M100PromotionThresholds",
    "m100_promotion_thresholds",
    "require_frozen_source_inputs",
]
