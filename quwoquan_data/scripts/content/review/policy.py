"""Strict loader for the repository-owned review policy."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.schema import assert_valid


REVIEW_POLICY_PATH = CONTROL_PLANE_SHARED_ROOT / "catalogs" / "review_policy.yaml"


@dataclass(frozen=True, slots=True)
class ReviewScoreBand:
    minimum: float
    score: int


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    policy_id: str
    minimum_score: int
    maximum_score: int
    agent_publish_at_least: int
    human_publish_at_least: int
    auto_discard_at_most: int
    require_human_when_doubtful: bool
    max_reprocess_attempts: int
    quality_score_bands: tuple[ReviewScoreBand, ...]

    def score_for_quality(self, quality_score: float) -> int:
        for band in self.quality_score_bands:
            if quality_score >= band.minimum:
                return band.score
        raise ValueError("review policy must contain a quality score fallback band")

    def validate_score(self, score: int, *, label: str) -> int:
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError(f"{label} must be an integer")
        if not self.minimum_score <= score <= self.maximum_score:
            raise ValueError(
                f"{label} must be {self.minimum_score}..{self.maximum_score}: {score!r}"
            )
        return score


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"review policy {label} must be an object")
    return value


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"review policy {label} must be an integer")
    return value


def _number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"review policy {label} must be a number")
    return float(value)


@lru_cache(maxsize=1)
def review_policy() -> ReviewPolicy:
    try:
        raw = yaml.safe_load(REVIEW_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"review policy unreadable: {REVIEW_POLICY_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("review policy must be an object")
    assert_valid(raw, "governance", "review_policy", label=REVIEW_POLICY_PATH.as_posix())
    score = _mapping(raw.get("score"), label="score")
    reprocess = _mapping(raw.get("reprocess"), label="reprocess")
    raw_bands = raw.get("qualityScoreBands")
    if not isinstance(raw_bands, list):
        raise ValueError("review policy qualityScoreBands must be an array")
    bands: list[ReviewScoreBand] = []
    for item in raw_bands:
        row = _mapping(item, label="qualityScoreBands item")
        bands.append(
            ReviewScoreBand(
                minimum=_number(row.get("minimum"), label="qualityScoreBands.minimum"),
                score=_integer(row.get("score"), label="qualityScoreBands.score"),
            )
        )
    typed_bands = tuple(bands)
    if tuple(sorted(typed_bands, key=lambda item: item.minimum, reverse=True)) != typed_bands:
        raise ValueError("review policy qualityScoreBands must be sorted by descending minimum")
    policy = ReviewPolicy(
        policy_id=str(raw["policyId"]),
        minimum_score=_integer(score.get("minimum"), label="score.minimum"),
        maximum_score=_integer(score.get("maximum"), label="score.maximum"),
        agent_publish_at_least=_integer(score.get("agentPublishAtLeast"), label="score.agentPublishAtLeast"),
        human_publish_at_least=_integer(score.get("humanPublishAtLeast"), label="score.humanPublishAtLeast"),
        auto_discard_at_most=_integer(score.get("autoDiscardAtMost"), label="score.autoDiscardAtMost"),
        require_human_when_doubtful=bool(raw["requireHumanWhenDoubtful"]),
        max_reprocess_attempts=_integer(reprocess.get("maxAttempts"), label="reprocess.maxAttempts"),
        quality_score_bands=typed_bands,
    )
    if policy.minimum_score > policy.maximum_score:
        raise ValueError("review policy score.minimum must not exceed score.maximum")
    for label, value in (
        ("score.agentPublishAtLeast", policy.agent_publish_at_least),
        ("score.humanPublishAtLeast", policy.human_publish_at_least),
        ("score.autoDiscardAtMost", policy.auto_discard_at_most),
    ):
        policy.validate_score(value, label=label)
    for band in policy.quality_score_bands:
        policy.validate_score(band.score, label="qualityScoreBands.score")
    return policy


__all__ = ["REVIEW_POLICY_PATH", "ReviewPolicy", "ReviewScoreBand", "review_policy"]
