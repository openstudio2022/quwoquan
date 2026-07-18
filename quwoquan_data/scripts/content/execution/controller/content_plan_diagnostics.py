"""Strongly typed source diagnostics for content-plan admission."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from content.post.content_plan import ARTICLE_MIN_BASE_DRAFT_CHARS


@dataclass(frozen=True)
class SourceDiagnosticInput:
    desired_articles: int
    minimum_articles: int
    article_raw_count: int
    article_candidates: tuple[dict[str, Any], ...]
    picked_articles: tuple[dict[str, Any], ...]
    desired_images: int
    minimum_images: int
    image_raw_count: int
    image_candidates: tuple[dict[str, Any], ...]
    picked_images: tuple[dict[str, Any], ...]
    article_lane_enabled: bool
    image_lane_enabled: bool
    article_rejects: dict[str, int]
    article_reject_examples: dict[str, list[str]]
    article_image_warnings: dict[str, int]
    article_image_warning_examples: dict[str, list[str]]
    image_rejects: dict[str, int]
    image_reject_examples: dict[str, list[str]]


def _normalized_quality_score(candidate: dict[str, Any]) -> float:
    try:
        raw = float(candidate.get("sourceQualityScore") or 0)
    except (TypeError, ValueError):
        raw = 0.0
    return max(0.0, min(raw / 10.0 if raw > 1 else raw, 1.0))


def _article_length_score(candidate: dict[str, Any]) -> float:
    try:
        text_len = int(candidate.get("textLen") or 0)
    except (TypeError, ValueError):
        text_len = 0
    return max(0.0, min(text_len / ARTICLE_MIN_BASE_DRAFT_CHARS, 1.0))


def build_source_diagnostic(value: SourceDiagnosticInput) -> dict[str, Any]:
    article_quality_score = (
        round(
            sum(_normalized_quality_score(row) for row in value.picked_articles)
            / len(value.picked_articles),
            4,
        )
        if value.picked_articles
        else 0.0
    )
    article_length_score = (
        round(
            sum(_article_length_score(row) for row in value.picked_articles)
            / len(value.picked_articles),
            4,
        )
        if value.picked_articles
        else 0.0
    )
    image_count_score = (
        1.0 if (value.picked_images or not value.image_lane_enabled) else 0.0
    )
    minimum_quality_passed = (
        (value.minimum_articles <= 0 or bool(value.picked_articles))
        and (value.minimum_images <= 0 or bool(value.picked_images))
    )
    composite_score = (
        round(
            70.0
            + 15.0 * article_quality_score
            + 5.0 * article_length_score
            + 10.0 * image_count_score,
            2,
        )
        if minimum_quality_passed
        else 0.0
    )
    return {
        "desiredArticleSources": value.desired_articles,
        "minimumRequiredArticleSources": value.minimum_articles,
        "rawArticleBaseSources": value.article_raw_count,
        "qualifiedArticleBaseSources": len(value.article_candidates),
        "pickedArticleBaseSources": len(value.picked_articles),
        "desiredImageSources": value.desired_images,
        "minimumRequiredImageSources": value.minimum_images,
        "rawImageAssets": value.image_raw_count,
        "qualifiedImageAssets": len(value.image_candidates),
        "pickedImageSources": len(value.picked_images),
        "articleLaneEnabled": value.article_lane_enabled,
        "imageLaneEnabled": value.image_lane_enabled,
        "minimumQualityPassed": minimum_quality_passed,
        "articleQualityScore": article_quality_score,
        "articleLengthScore": article_length_score,
        "imageCountScore": image_count_score,
        "compositeScore": composite_score,
        "articleRejects": dict(sorted(value.article_rejects.items())),
        "articleRejectExamples": dict(sorted(value.article_reject_examples.items())),
        "articleImageSoftWarnings": dict(sorted(value.article_image_warnings.items())),
        "articleImageSoftWarningExamples": dict(
            sorted(value.article_image_warning_examples.items())
        ),
        "imageRejects": dict(sorted(value.image_rejects.items())),
        "imageRejectExamples": dict(sorted(value.image_reject_examples.items())),
    }
