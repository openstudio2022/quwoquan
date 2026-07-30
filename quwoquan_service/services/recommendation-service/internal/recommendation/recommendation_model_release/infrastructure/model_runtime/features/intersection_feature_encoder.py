"""Canonical matched-edge feature encoding shared by serving and training.

The categorical vocabulary is loaded from the sole
``intersection_kind_registry.yaml`` contract.  No Python-owned kind map is
allowed: adding or retiring a kind changes the encoder only through that
registry and its contract gates.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

MATCHED_EDGE_FIELDS = (
    "intersectionEdgeWeight",
    "intersectionEdgeFreshness",
    "intersectionEdgeKind",
)

INTERSECTION_USER_NUMERIC = (
    "sharedFolloweesCount",
    "sharedCircleCount",
    "coCommentedCount",
    "coVisitedEntityCount",
    "followeeInObjectActive",
    "followeeViewingActive",
    "affinityIntersectionScore",
)

INTERSECTION_CLASS_CODES = MappingProxyType({"fact": 2, "affinity": 1})
INTERSECTION_SEGMENT_WIDTH = 14
INTERSECTION_EDGE_KIND_OFFSET = 9


def _canonical_registry_path() -> Path:
    """Resolve the source contract in the repo or its packaged image path."""
    relative = Path(
        "contracts/recommendation/recommendation_model_release/"
        "intersection_kind_registry.yaml"
    )
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "canonical intersection_kind_registry.yaml is absent from the model artifact"
    )


@lru_cache(maxsize=1)
def canonical_intersection_kind_codes() -> Mapping[str, int]:
    """Return stable non-zero category codes in canonical registry order."""
    raw = yaml.safe_load(
        _canonical_registry_path().read_text(encoding="utf-8")
    ) or {}
    kinds = raw.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        raise RuntimeError("canonical intersection kind registry has no kinds")

    codes: dict[str, int] = {}
    for index, item in enumerate(kinds, start=1):
        kind = str(item.get("kind") if isinstance(item, dict) else "").strip()
        if not kind:
            raise RuntimeError("canonical intersection kind registry contains an empty kind")
        if kind in codes:
            raise RuntimeError(
                f"canonical intersection kind registry contains duplicate kind {kind!r}"
            )
        codes[kind] = index
    return MappingProxyType(codes)


def encode_intersection_kind(kind: object) -> float:
    """Encode a registered kind; empty or unknown values share the missing bucket 0."""
    normalized = str(kind or "").strip()
    if not normalized:
        return 0.0
    return float(canonical_intersection_kind_codes().get(normalized, 0))


def matched_edge_categorical_features(vector_width: int) -> list[int]:
    """Return LightGBM indexes that must use native categorical semantics."""
    if vector_width < INTERSECTION_SEGMENT_WIDTH:
        raise ValueError(
            f"feature vector width {vector_width} is smaller than the "
            f"intersection segment {INTERSECTION_SEGMENT_WIDTH}"
        )
    return [
        vector_width - INTERSECTION_SEGMENT_WIDTH + INTERSECTION_EDGE_KIND_OFFSET
    ]


def append_intersection_features(
    features: list[float],
    item: dict,
    user: dict,
    matched_edge: dict,
) -> None:
    """Append the canonical 14-dimension intersection segment.

    ``matched_edge`` is candidate scoped.  Online serving passes the three
    fields projected on CandidateInput; training passes the same three fields
    frozen in the immutable exposure snapshot.
    """
    for field in INTERSECTION_USER_NUMERIC:
        features.append(float(user.get(field, 0) or 0))

    features.append(float(matched_edge.get("intersectionEdgeWeight", 0) or 0))
    features.append(float(matched_edge.get("intersectionEdgeFreshness", 0) or 0))
    features.append(encode_intersection_kind(matched_edge.get("intersectionEdgeKind")))

    features.append(float(item.get("intersectionFactStrength", 0) or 0))
    features.append(float(item.get("intersectionFreshness", 0) or 0))
    candidate_affinity = float(item.get("affinityIntersectionScore", 0) or 0)
    if not str(item.get("intersectionConfidenceLabel", "") or "").strip():
        candidate_affinity = 0.0
    features.append(candidate_affinity)
    features.append(
        float(
            INTERSECTION_CLASS_CODES.get(
                str(item.get("intersectionClass", "") or ""),
                0,
            )
        )
    )
