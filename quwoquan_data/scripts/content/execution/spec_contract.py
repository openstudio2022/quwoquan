"""Strongly typed immutable execution specification admitted from YAML."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.control_types import (
    ContentType,
    ExecutionSpecStatus,
    ImageAssetStrategy,
    ImageCountPolicy,
    ModalityContract,
    SelectionPolicy,
)
from content.source.contracts import QualifiedHomepageSource


EXECUTION_SPEC_SCHEMA = "quwoquan.content.execution_spec"


def approved_quota(execution_id: str) -> int:
    """本次 execution 的准出配额：候选池过采后必须交付的达标对象数。

    批次准出、checkpoint 推进与 fleet dispatch 共用这一个读取口，
    避免「配额」在各层出现第二真相源。
    """
    from content.execution import store

    policy = store.load_spec(execution_id).get("executionPolicy") or {}
    value = policy.get("approvedQuota")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"execution {execution_id} executionPolicy.approvedQuota is required"
        )
    return value


def _object(payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise TypeError(f"execution spec {field} must be an object")
    return value


def _string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"execution spec {field} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"execution spec {field} must be a string or null")
    return value.strip() or None


def _strings(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"execution spec {field} must be an array")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError(f"execution spec {field} must contain non-empty strings")
    return result


def _non_negative_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"execution spec {field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class CoverageTarget:
    name: str
    entity_type: str
    geo_tag_ref: str | None = None
    geo_tag_refs: tuple[str, ...] = ()
    type_tag_refs: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    qualified_homepage_source: QualifiedHomepageSource | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CoverageTarget":
        return cls(
            name=_string(payload, "name"),
            entity_type=_string(payload, "entityType"),
            geo_tag_ref=_optional_string(payload, "geoTagRef"),
            geo_tag_refs=_strings(payload.get("geoTagRefs"), field="geoTagRefs"),
            type_tag_refs=_strings(payload.get("typeTagRefs"), field="typeTagRefs"),
            aliases=_strings(payload.get("aliases"), field="aliases"),
            qualified_homepage_source=(
                QualifiedHomepageSource.from_mapping(raw)
                if isinstance(raw := payload.get("qualifiedHomepageSource"), Mapping)
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "entityType": self.entity_type,
        }
        if self.geo_tag_ref:
            payload["geoTagRef"] = self.geo_tag_ref
        if self.geo_tag_refs:
            payload["geoTagRefs"] = list(self.geo_tag_refs)
        if self.type_tag_refs:
            payload["typeTagRefs"] = list(self.type_tag_refs)
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        if self.qualified_homepage_source is not None:
            payload["qualifiedHomepageSource"] = self.qualified_homepage_source.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionScope:
    region: str
    entity_types: tuple[str, ...]
    coverage_targets: tuple[CoverageTarget, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionScope":
        rows = payload.get("coverageTargets")
        if not isinstance(rows, list) or not rows:
            raise ValueError("execution spec scope.coverageTargets must be non-empty")
        if not all(isinstance(row, Mapping) for row in rows):
            raise TypeError("execution spec scope.coverageTargets must contain objects")
        targets = tuple(CoverageTarget.from_mapping(row) for row in rows)
        if len({target.name for target in targets}) != len(targets):
            raise ValueError("execution spec scope.coverageTargets contains duplicate names")
        return cls(
            region=_string(payload, "region"),
            entity_types=_strings(payload.get("entityTypes"), field="scope.entityTypes"),
            coverage_targets=targets,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "region": self.region,
            "entityTypes": list(self.entity_types),
            "coverageTargets": [target.to_dict() for target in self.coverage_targets],
        }


@dataclass(frozen=True, slots=True)
class ContentQuotas:
    entity_homepages_per_target: int
    entity_articles_per_target: int
    image_works_per_target: int
    video_works_per_target: int
    route_articles: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ContentQuotas":
        return cls(
            entity_homepages_per_target=_non_negative_int(payload, "entityHomepagesPerTarget"),
            entity_articles_per_target=_non_negative_int(payload, "entityArticlesPerTarget"),
            image_works_per_target=_non_negative_int(payload, "imageWorksPerTarget"),
            video_works_per_target=_non_negative_int(payload, "videoWorksPerTarget"),
            route_articles=_non_negative_int(payload, "routeArticles"),
        )

    def for_type(self, content_type: ContentType) -> int:
        return {
            ContentType.HOMEPAGE: self.entity_homepages_per_target,
            ContentType.ARTICLE: self.entity_articles_per_target,
            ContentType.IMAGE: self.image_works_per_target,
            ContentType.VIDEO: self.video_works_per_target,
        }[content_type]

    def to_dict(self) -> dict[str, int]:
        return {
            "entityHomepagesPerTarget": self.entity_homepages_per_target,
            "entityArticlesPerTarget": self.entity_articles_per_target,
            "imageWorksPerTarget": self.image_works_per_target,
            "videoWorksPerTarget": self.video_works_per_target,
            "routeArticles": self.route_articles,
        }


@dataclass(frozen=True, slots=True)
class ResearchPolicy:
    lanes: tuple[ContentType, ...]
    max_concurrency: int | None
    lane_concurrency: tuple[tuple[ContentType, int], ...]
    image_asset_strategy: ImageAssetStrategy | None
    image_count_policy: ImageCountPolicy | None
    minimum_publishable_images_per_target: int | None
    allow_ai_images: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ResearchPolicy":
        lane_values = _strings(payload.get("lanes"), field="content.research.lanes")
        lanes = tuple(ContentType(value) for value in lane_values)
        raw_max = payload.get("maxConcurrency")
        max_concurrency = None
        if raw_max is not None:
            max_concurrency = _non_negative_int(payload, "maxConcurrency")
            if max_concurrency < 1:
                raise ValueError("execution spec content.research.maxConcurrency must be positive")
        raw_lane_concurrency = payload.get("laneConcurrency") or {}
        if not isinstance(raw_lane_concurrency, Mapping):
            raise TypeError("execution spec content.research.laneConcurrency must be an object")
        lane_concurrency = tuple(
            sorted(
                (
                    ContentType(str(key)),
                    _non_negative_int(raw_lane_concurrency, str(key)),
                )
                for key in raw_lane_concurrency
            )
        )
        raw_ai = payload.get("allowAiImages")
        if not isinstance(raw_ai, bool):
            raise TypeError("execution spec content.research.allowAiImages must be boolean")
        strategy = _optional_string(payload, "imageAssetStrategy")
        count_policy = _optional_string(payload, "imageCountPolicy")
        raw_minimum = payload.get("minimumPublishableImagesPerTarget")
        minimum_publishable_images = None
        if raw_minimum is not None:
            minimum_publishable_images = _non_negative_int(
                payload,
                "minimumPublishableImagesPerTarget",
            )
        return cls(
            lanes=lanes,
            max_concurrency=max_concurrency,
            lane_concurrency=lane_concurrency,
            image_asset_strategy=ImageAssetStrategy(strategy) if strategy else None,
            image_count_policy=ImageCountPolicy(count_policy) if count_policy else None,
            minimum_publishable_images_per_target=minimum_publishable_images,
            allow_ai_images=raw_ai,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "lanes": [lane.value for lane in self.lanes],
            "allowAiImages": self.allow_ai_images,
        }
        if self.max_concurrency is not None:
            payload["maxConcurrency"] = self.max_concurrency
        if self.lane_concurrency:
            payload["laneConcurrency"] = {
                lane.value: count for lane, count in self.lane_concurrency
            }
        if self.image_asset_strategy:
            payload["imageAssetStrategy"] = self.image_asset_strategy.value
        if self.image_count_policy:
            payload["imageCountPolicy"] = self.image_count_policy.value
        if self.minimum_publishable_images_per_target is not None:
            payload["minimumPublishableImagesPerTarget"] = (
                self.minimum_publishable_images_per_target
            )
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionContent:
    modality_contract: ModalityContract
    research: ResearchPolicy
    carriers: tuple[ContentType, ...]
    quotas: ContentQuotas
    angles: tuple[str, ...]
    audiences: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionContent":
        return cls(
            modality_contract=ModalityContract(_string(payload, "modalityContract")),
            research=ResearchPolicy.from_mapping(_object(payload, "research")),
            carriers=tuple(
                ContentType(value)
                for value in _strings(payload.get("carriers"), field="content.carriers")
            ),
            quotas=ContentQuotas.from_mapping(_object(payload, "quotas")),
            angles=_strings(payload.get("angles"), field="content.angles"),
            audiences=_strings(payload.get("audiences"), field="content.audiences"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "modalityContract": self.modality_contract.value,
            "research": self.research.to_dict(),
            "carriers": [carrier.value for carrier in self.carriers],
            "quotas": self.quotas.to_dict(),
        }
        if self.angles:
            payload["angles"] = list(self.angles)
        if self.audiences:
            payload["audiences"] = list(self.audiences)
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionAcceptance:
    min_entities: int
    min_posts_per_entity: int
    required_angles: tuple[str, ...]
    scored_angles: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionAcceptance":
        return cls(
            min_entities=_non_negative_int(payload, "minEntities"),
            min_posts_per_entity=_non_negative_int(payload, "minPostsPerEntity"),
            required_angles=_strings(payload.get("requiredAngles"), field="acceptance.requiredAngles"),
            scored_angles=_strings(payload.get("scoredAngles"), field="acceptance.scoredAngles"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "minEntities": self.min_entities,
            "minPostsPerEntity": self.min_posts_per_entity,
            "requiredAngles": list(self.required_angles),
        }
        if self.scored_angles:
            payload["scoredAngles"] = list(self.scored_angles)
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    selection_policy: SelectionPolicy
    target_entity_count: int
    target_object_count: int
    approved_quota: int
    oversample_factor: float
    execution_branch: str
    git_commit_sha: str
    article_commercial_closure: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.approved_quota <= self.target_entity_count:
            raise ValueError(
                "executionPolicy.approvedQuota must be between 1 and "
                "targetEntityCount (the oversampled candidate pool)"
            )
        if self.oversample_factor < 1:
            raise ValueError("executionPolicy.oversampleFactor must be >= 1")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionPolicy":
        raw_factor = payload.get("oversampleFactor")
        if isinstance(raw_factor, bool) or not isinstance(raw_factor, (int, float)):
            raise ValueError("executionPolicy.oversampleFactor must be a number")
        raw_article_closure = payload.get("articleCommercialClosure", False)
        if not isinstance(raw_article_closure, bool):
            raise ValueError(
                "executionPolicy.articleCommercialClosure must be boolean"
            )
        return cls(
            selection_policy=SelectionPolicy(_string(payload, "selectionPolicy")),
            target_entity_count=_non_negative_int(payload, "targetEntityCount"),
            target_object_count=_non_negative_int(payload, "targetObjectCount"),
            approved_quota=_non_negative_int(payload, "approvedQuota"),
            oversample_factor=float(raw_factor),
            execution_branch=_string(payload, "executionBranch"),
            git_commit_sha=_string(payload, "gitCommitSha"),
            article_commercial_closure=raw_article_closure,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "selectionPolicy": self.selection_policy.value,
            "targetEntityCount": self.target_entity_count,
            "targetObjectCount": self.target_object_count,
            "approvedQuota": self.approved_quota,
            "oversampleFactor": self.oversample_factor,
            "executionBranch": self.execution_branch,
            "gitCommitSha": self.git_commit_sha,
            "articleCommercialClosure": self.article_commercial_closure,
        }


@dataclass(frozen=True, slots=True)
class Provenance:
    created_at: str
    created_by: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Provenance":
        return cls(
            created_at=_string(payload, "createdAt"),
            created_by=_string(payload, "createdBy"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"createdAt": self.created_at, "createdBy": self.created_by}


@dataclass(frozen=True, slots=True)
class ReliableTaskPolicy:
    task_type: str
    queue: str
    store: str
    ready_index: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ReliableTaskPolicy":
        return cls(
            task_type=_string(payload, "taskType"),
            queue=_string(payload, "queue"),
            store=_string(payload, "store"),
            ready_index=_string(payload, "readyIndex"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "taskType": self.task_type,
            "queue": self.queue,
            "store": self.store,
            "readyIndex": self.ready_index,
        }


@dataclass(frozen=True, slots=True)
class QueuePolicy:
    backend: str
    reliable_task: ReliableTaskPolicy
    lease_seconds: int
    heartbeat_seconds: int
    dead_letter_after_attempts: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "QueuePolicy":
        return cls(
            backend=_string(payload, "backend"),
            reliable_task=ReliableTaskPolicy.from_mapping(_object(payload, "reliableTask")),
            lease_seconds=_non_negative_int(payload, "leaseSeconds"),
            heartbeat_seconds=_non_negative_int(payload, "heartbeatSeconds"),
            dead_letter_after_attempts=_non_negative_int(payload, "deadLetterAfterAttempts"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "reliableTask": self.reliable_task.to_dict(),
            "leaseSeconds": self.lease_seconds,
            "heartbeatSeconds": self.heartbeat_seconds,
            "deadLetterAfterAttempts": self.dead_letter_after_attempts,
        }


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    schema: str
    execution_id: str
    title: str
    intent_label: str
    execution_archetype: str
    vertical: str
    organize_by: str
    key: str
    entity_category: str | None
    status: ExecutionSpecStatus
    scope: ExecutionScope
    provenance: Provenance
    preset_ref: str
    content: ExecutionContent
    acceptance: ExecutionAcceptance
    execution_policy: ExecutionPolicy
    queue_policy: QueuePolicy

    def __post_init__(self) -> None:
        if self.schema != EXECUTION_SPEC_SCHEMA:
            raise ValueError(
                f"execution spec schema must be {EXECUTION_SPEC_SCHEMA}"
            )
        target_count = len(self.scope.coverage_targets)
        if self.execution_policy.target_entity_count != target_count:
            raise ValueError(
                "executionPolicy.targetEntityCount must equal "
                "scope.coverageTargets length"
            )
        target_types = {target.entity_type for target in self.scope.coverage_targets}
        if set(self.scope.entity_types) != target_types:
            raise ValueError(
                "scope.entityTypes must exactly match coverage target entity types"
            )
        positive_carriers = tuple(
            content_type
            for content_type in ContentType
            if self.content.quotas.for_type(content_type) > 0
        )
        if len(positive_carriers) != 1:
            raise ValueError(
                "execution must contain exactly one positive content quota"
            )
        if set(self.content.carriers) != set(positive_carriers):
            raise ValueError(
                "content.carriers must exactly match positive content quotas"
            )
        if set(self.content.research.lanes) != set(self.content.carriers):
            raise ValueError(
                "content.research.lanes must exactly match content.carriers"
            )
        if self.content.quotas.route_articles:
            raise ValueError(
                "content.quotas.routeArticles is unsupported without a route carrier"
            )
        if positive_carriers[0] is ContentType.HOMEPAGE:
            missing = [
                target.name
                for target in self.scope.coverage_targets
                if target.qualified_homepage_source is None
            ]
            if missing:
                raise ValueError(
                    "homepage execution targets require qualifiedHomepageSource: "
                    + ", ".join(missing)
                )
        objects_per_target = self.content.quotas.for_type(positive_carriers[0])
        expected_object_count = target_count * objects_per_target
        if self.execution_policy.target_object_count != expected_object_count:
            raise ValueError(
                "executionPolicy.targetObjectCount must equal the frozen quota total"
            )
        if self.acceptance.min_entities != self.execution_policy.approved_quota:
            raise ValueError(
                "acceptance.minEntities must equal executionPolicy.approvedQuota"
            )
        if self.acceptance.min_posts_per_entity != objects_per_target:
            raise ValueError(
                "acceptance.minPostsPerEntity must equal the per-target quota total"
            )
        if self.queue_policy.heartbeat_seconds >= self.queue_policy.lease_seconds:
            raise ValueError(
                "queuePolicy.heartbeatSeconds must be less than leaseSeconds"
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionSpec":
        return cls(
            schema=_string(payload, "schema"),
            execution_id=_string(payload, "executionId"),
            title=_string(payload, "title"),
            intent_label=_string(payload, "intentLabel"),
            execution_archetype=_string(payload, "executionArchetype"),
            vertical=_string(payload, "vertical"),
            organize_by=_string(payload, "organizeBy"),
            key=_string(payload, "key"),
            entity_category=_optional_string(payload, "entityCategory"),
            status=ExecutionSpecStatus(_string(payload, "status")),
            scope=ExecutionScope.from_mapping(_object(payload, "scope")),
            provenance=Provenance.from_mapping(_object(payload, "provenance")),
            preset_ref=_string(payload, "presetRef"),
            content=ExecutionContent.from_mapping(_object(payload, "content")),
            acceptance=ExecutionAcceptance.from_mapping(_object(payload, "acceptance")),
            execution_policy=ExecutionPolicy.from_mapping(_object(payload, "executionPolicy")),
            queue_policy=QueuePolicy.from_mapping(_object(payload, "queuePolicy")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "executionId": self.execution_id,
            "title": self.title,
            "intentLabel": self.intent_label,
            "executionArchetype": self.execution_archetype,
            "vertical": self.vertical,
            "organizeBy": self.organize_by,
            "key": self.key,
            "entityCategory": self.entity_category,
            "status": self.status.value,
            "scope": self.scope.to_dict(),
            "provenance": self.provenance.to_dict(),
            "presetRef": self.preset_ref,
            "content": self.content.to_dict(),
            "acceptance": self.acceptance.to_dict(),
            "executionPolicy": self.execution_policy.to_dict(),
            "queuePolicy": self.queue_policy.to_dict(),
        }
