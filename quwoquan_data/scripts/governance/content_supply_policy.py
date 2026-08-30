"""Typed reusable supply policy for one vertical.

This module deliberately owns quality and delivery constraints only. Regions,
targets, counts, and execution phases are runtime request data and therefore
never belong to the versioned policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

import yaml

from core.paths import REPO_DATA_ROOT
from core.schema import assert_valid


_VERTICAL_REF = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True, slots=True)
class ContentMix:
    article: int
    image: int
    video: int

    @property
    def total_per_entity(self) -> int:
        return self.article + self.image + self.video


@dataclass(frozen=True, slots=True)
class VideoDeliveryPolicy:
    container: str
    codec: str
    width: int
    height: int
    aspect_ratio: str
    pixel_format: str
    frames_per_second: int
    segment_duration_seconds: int
    minimum_source_frames: int
    minimum_duration_seconds: int
    maximum_duration_seconds: int

    @property
    def minimum_segment_count(self) -> int:
        return (
            self.minimum_duration_seconds + self.segment_duration_seconds - 1
        ) // self.segment_duration_seconds


@dataclass(frozen=True, slots=True)
class MediaSubjectPolicy:
    representative_indicators: tuple[str, ...]
    prohibited_indicators: tuple[str, ...]

    def prohibited_indicator(self, *descriptions: object) -> str:
        subject = " ".join(str(value or "") for value in descriptions).casefold()
        if any(
            indicator.casefold() in subject
            for indicator in self.representative_indicators
        ):
            return ""
        return next(
            (
                indicator
                for indicator in self.prohibited_indicators
                if indicator.casefold() in subject
            ),
            "",
        )


@dataclass(frozen=True, slots=True)
class ContentSupplyPolicy:
    policy_id: str
    feed_minimum_posts: int
    content_mix: ContentMix
    non_empty_rate_minimum: float
    duplicate_exposure_rate_maximum: float
    homepage_max_source_fidelity: float
    homepage_minimum_body_chars: int
    homepage_minimum_fact_count: int
    homepage_minimum_fact_chars: int
    homepage_minimum_section_chars: int
    homepage_source_outline_section_chars: int
    homepage_max_source_paragraph_overlap: float
    homepage_max_intra_body_paragraph_similarity: float
    homepage_derivation_paragraph_minimum_chars: int
    media_subject: MediaSubjectPolicy
    video_delivery: VideoDeliveryPolicy


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"content supply policy {label} must be a positive integer")
    return value


def _ratio(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"content supply policy {label} must be a number")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError(f"content supply policy {label} must be within [0, 1]")
    return result


def content_supply_policy_path(vertical: str) -> Path:
    normalized = str(vertical or "").strip()
    if not _VERTICAL_REF.fullmatch(normalized):
        raise ValueError("content supply policy vertical is invalid")
    return REPO_DATA_ROOT / "verticals" / normalized / "content_policy.yaml"


@lru_cache(maxsize=None)
def load_content_supply_policy(vertical: str) -> ContentSupplyPolicy:
    policy_path = content_supply_policy_path(vertical)
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"content supply policy unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("content supply policy must be an object")
    assert_valid(
        raw,
        "governance",
        "content_supply_policy",
        label=policy_path.as_posix(),
    )
    mix = raw["contentPerEntity"]
    quality = raw["quality"]
    media_subject = raw["mediaSubject"]
    video = raw["videoDelivery"]
    if not all(
        isinstance(section, dict)
        for section in (mix, quality, media_subject, video)
    ):
        raise ValueError("content supply policy sections must be objects")
    policy = ContentSupplyPolicy(
        policy_id=str(raw["policyId"]),
        feed_minimum_posts=_positive_int(raw["feedMinimumPosts"], label="feedMinimumPosts"),
        content_mix=ContentMix(
            article=_positive_int(mix["article"], label="contentPerEntity.article"),
            image=_positive_int(mix["image"], label="contentPerEntity.image"),
            video=_positive_int(mix["video"], label="contentPerEntity.video"),
        ),
        non_empty_rate_minimum=_ratio(
            quality["nonEmptyRateMinimum"], label="quality.nonEmptyRateMinimum"
        ),
        duplicate_exposure_rate_maximum=_ratio(
            quality["duplicateExposureRateMaximum"],
            label="quality.duplicateExposureRateMaximum",
        ),
        homepage_max_source_fidelity=_ratio(
            quality["homepageMaxSourceFidelity"],
            label="quality.homepageMaxSourceFidelity",
        ),
        homepage_minimum_body_chars=_positive_int(
            quality["homepageMinimumBodyChars"],
            label="quality.homepageMinimumBodyChars",
        ),
        homepage_minimum_fact_count=_positive_int(
            quality["homepageMinimumFactCount"],
            label="quality.homepageMinimumFactCount",
        ),
        homepage_minimum_fact_chars=_positive_int(
            quality["homepageMinimumFactChars"],
            label="quality.homepageMinimumFactChars",
        ),
        homepage_minimum_section_chars=_positive_int(
            quality["homepageMinimumSectionChars"],
            label="quality.homepageMinimumSectionChars",
        ),
        homepage_source_outline_section_chars=_positive_int(
            quality["homepageSourceOutlineSectionChars"],
            label="quality.homepageSourceOutlineSectionChars",
        ),
        homepage_max_source_paragraph_overlap=_ratio(
            quality["homepageMaxSourceParagraphOverlap"],
            label="quality.homepageMaxSourceParagraphOverlap",
        ),
        homepage_max_intra_body_paragraph_similarity=_ratio(
            quality["homepageMaxIntraBodyParagraphSimilarity"],
            label="quality.homepageMaxIntraBodyParagraphSimilarity",
        ),
        homepage_derivation_paragraph_minimum_chars=_positive_int(
            quality["homepageDerivationParagraphMinimumChars"],
            label="quality.homepageDerivationParagraphMinimumChars",
        ),
        media_subject=MediaSubjectPolicy(
            representative_indicators=tuple(
                str(value).strip()
                for value in media_subject["representativeIndicators"]
                if str(value).strip()
            ),
            prohibited_indicators=tuple(
                str(value).strip()
                for value in media_subject["prohibitedIndicators"]
                if str(value).strip()
            ),
        ),
        video_delivery=VideoDeliveryPolicy(
            container=str(video["container"]),
            codec=str(video["codec"]),
            width=_positive_int(video["width"], label="videoDelivery.width"),
            height=_positive_int(video["height"], label="videoDelivery.height"),
            aspect_ratio=str(video["aspectRatio"]),
            pixel_format=str(video["pixelFormat"]),
            frames_per_second=_positive_int(
                video["framesPerSecond"], label="videoDelivery.framesPerSecond"
            ),
            segment_duration_seconds=_positive_int(
                video["segmentDurationSeconds"],
                label="videoDelivery.segmentDurationSeconds",
            ),
            minimum_source_frames=_positive_int(
                video["minimumSourceFrames"],
                label="videoDelivery.minimumSourceFrames",
            ),
            minimum_duration_seconds=_positive_int(
                video["minimumDurationSeconds"],
                label="videoDelivery.minimumDurationSeconds",
            ),
            maximum_duration_seconds=_positive_int(
                video["maximumDurationSeconds"],
                label="videoDelivery.maximumDurationSeconds",
            ),
        ),
    )
    if policy.video_delivery.minimum_duration_seconds > policy.video_delivery.maximum_duration_seconds:
        raise ValueError("video minimum duration exceeds maximum duration")
    if not (
        policy.media_subject.representative_indicators
        and policy.media_subject.prohibited_indicators
    ):
        raise ValueError("media subject policy must declare both indicator sets")
    return policy


__all__ = [
    "ContentMix",
    "ContentSupplyPolicy",
    "MediaSubjectPolicy",
    "VideoDeliveryPolicy",
    "content_supply_policy_path",
    "load_content_supply_policy",
]
