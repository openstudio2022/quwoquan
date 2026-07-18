"""Typed cold-start supply policy for the Zhejiang/Sichuan launch release."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from core.paths import REPO_DATA_ROOT
from core.schema import assert_valid
from core.control_types import ContentType, RolloutMilestone
from content.execution.identity import ExecutionIdentity, parse_execution_id


COLD_START_SUPPLY_POLICY_PATH = (
    REPO_DATA_ROOT / "verticals/travel/cold_start_supply_policy.yaml"
)
COVERAGE_ROOT = REPO_DATA_ROOT / "verticals/travel/coverage/中国"


@dataclass(frozen=True, slots=True)
class ColdStartContentMix:
    article: int
    image: int
    video: int

    @property
    def total_per_entity(self) -> int:
        return self.article + self.image + self.video


@dataclass(frozen=True, slots=True)
class ColdStartTarget:
    province: str
    name: str
    entity_type: str


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
    minimum_duration_seconds: int
    maximum_duration_seconds: int

    @property
    def minimum_segment_count(self) -> int:
        return (
            self.minimum_duration_seconds + self.segment_duration_seconds - 1
        ) // self.segment_duration_seconds


@dataclass(frozen=True, slots=True)
class ColdStartSupplyPolicy:
    policy_id: str
    feed_minimum_posts: int
    content_mix: ColdStartContentMix
    targets: tuple[ColdStartTarget, ...]
    non_empty_rate_minimum: float
    duplicate_exposure_rate_maximum: float
    video_delivery: VideoDeliveryPolicy

    @property
    def expected_post_count(self) -> int:
        return len(self.targets) * self.content_mix.total_per_entity

    def targets_for_province(self, province: str) -> tuple[ColdStartTarget, ...]:
        return tuple(target for target in self.targets if target.province == province)


@dataclass(frozen=True, slots=True)
class ColdStartExecutionParameters:
    province: str
    target_names: tuple[str, ...]

    @property
    def limit(self) -> int:
        return len(self.target_names)

    @property
    def mandatory(self) -> str:
        return ",".join(self.target_names)


def _coverage_entities(province: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    for path in sorted((COVERAGE_ROOT / province).glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"coverage document must be an object: {path}")
        for district in document.get("districts") or []:
            if not isinstance(district, dict):
                continue
            for leaf in district.get("leaves") or []:
                if not isinstance(leaf, dict):
                    continue
                name = str(leaf.get("name") or "").strip()
                entity_type = str(leaf.get("entityType") or "").strip()
                if name:
                    entities[name] = entity_type
    return entities


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"cold-start policy {label} must be a positive integer")
    return value


@lru_cache(maxsize=1)
def load_cold_start_supply_policy() -> ColdStartSupplyPolicy:
    try:
        raw = yaml.safe_load(COLD_START_SUPPLY_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cold-start supply policy unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("cold-start supply policy must be an object")
    assert_valid(
        raw,
        "governance",
        "cold_start_supply_policy",
        label=COLD_START_SUPPLY_POLICY_PATH.as_posix(),
    )
    mix_raw = raw["contentPerEntity"]
    quality_raw = raw["quality"]
    video_raw = raw["videoDelivery"]
    if not all(isinstance(item, dict) for item in (mix_raw, quality_raw, video_raw)):
        raise ValueError("cold-start policy sections must be objects")
    targets: list[ColdStartTarget] = []
    provinces_seen: set[str] = set()
    for province_entry in raw["provinces"]:
        province = str(province_entry["province"])
        if province in provinces_seen:
            raise ValueError(f"cold-start province duplicated: {province}")
        provinces_seen.add(province)
        coverage = _coverage_entities(province)
        for target_raw in province_entry["targets"]:
            target = ColdStartTarget(
                province=province,
                name=str(target_raw["name"]),
                entity_type=str(target_raw["entityType"]),
            )
            actual_type = coverage.get(target.name)
            if actual_type != target.entity_type:
                raise ValueError(
                    f"cold-start target is not in master coverage with matching type: "
                    f"{province}/{target.name}/{target.entity_type}"
                )
            targets.append(target)
    if len({(target.province, target.name) for target in targets}) != len(targets):
        raise ValueError("cold-start targets must be unique")
    policy = ColdStartSupplyPolicy(
        policy_id=str(raw["policyId"]),
        feed_minimum_posts=_positive_int(raw["feedMinimumPosts"], label="feedMinimumPosts"),
        content_mix=ColdStartContentMix(
            article=_positive_int(mix_raw["article"], label="contentPerEntity.article"),
            image=_positive_int(mix_raw["image"], label="contentPerEntity.image"),
            video=_positive_int(mix_raw["video"], label="contentPerEntity.video"),
        ),
        targets=tuple(targets),
        non_empty_rate_minimum=float(quality_raw["nonEmptyRateMinimum"]),
        duplicate_exposure_rate_maximum=float(quality_raw["duplicateExposureRateMaximum"]),
        video_delivery=VideoDeliveryPolicy(
            container=str(video_raw["container"]),
            codec=str(video_raw["codec"]),
            width=_positive_int(video_raw["width"], label="videoDelivery.width"),
            height=_positive_int(video_raw["height"], label="videoDelivery.height"),
            aspect_ratio=str(video_raw["aspectRatio"]),
            pixel_format=str(video_raw["pixelFormat"]),
            frames_per_second=_positive_int(
                video_raw["framesPerSecond"], label="videoDelivery.framesPerSecond"
            ),
            segment_duration_seconds=_positive_int(
                video_raw["segmentDurationSeconds"],
                label="videoDelivery.segmentDurationSeconds",
            ),
            minimum_duration_seconds=_positive_int(
                video_raw["minimumDurationSeconds"],
                label="videoDelivery.minimumDurationSeconds",
            ),
            maximum_duration_seconds=_positive_int(
                video_raw["maximumDurationSeconds"],
                label="videoDelivery.maximumDurationSeconds",
            ),
        ),
    )
    if policy.feed_minimum_posts > policy.expected_post_count:
        raise ValueError("feed minimum exceeds the complete cold-start supply")
    if policy.video_delivery.minimum_duration_seconds > policy.video_delivery.maximum_duration_seconds:
        raise ValueError("video minimum duration exceeds maximum duration")
    return policy


def cold_start_execution_parameters(
    *,
    execution_id: str,
    retry_of: str | None = None,
) -> ColdStartExecutionParameters:
    """Resolve one launch-supply execution from the frozen cold-start policy."""
    identity = parse_execution_id(execution_id)
    if identity.vertical != "travel" or identity.intent != "cold-start":
        raise ValueError(
            "cold-start execution must use travel-<contentType>-cold-start identity"
        )
    if identity.content_type not in {
        ContentType.ARTICLE,
        ContentType.IMAGE,
        ContentType.VIDEO,
    }:
        raise ValueError("cold-start rollout only accepts article, image, or video")
    if identity.milestone is not RolloutMilestone.M3:
        raise ValueError("cold-start execution requires milestone m3 after homepage closure")

    from content.release.canonical.rollout_contract import load_rollout_contract
    from content.release.canonical.rollout_milestone import (
        assert_milestone_closed,
        retry_target_names,
    )

    contract = load_rollout_contract()
    province = contract.province_for_scope(identity.scope).province
    targets = load_cold_start_supply_policy().targets_for_province(province)
    expected_names = tuple(target.name for target in targets)
    if not expected_names:
        raise ValueError(f"cold-start policy has no targets for {province}")
    assert_milestone_closed(RolloutMilestone.M3)
    if retry_of:
        retry_names = retry_target_names(identity=identity, retry_of=retry_of)
        if retry_names != expected_names:
            raise ValueError("retryOf frozen targets differ from cold-start policy")
    return ColdStartExecutionParameters(
        province=province,
        target_names=expected_names,
    )


__all__ = [
    "COLD_START_SUPPLY_POLICY_PATH",
    "ColdStartExecutionParameters",
    "ColdStartContentMix",
    "ColdStartSupplyPolicy",
    "ColdStartTarget",
    "VideoDeliveryPolicy",
    "load_cold_start_supply_policy",
    "cold_start_execution_parameters",
]
