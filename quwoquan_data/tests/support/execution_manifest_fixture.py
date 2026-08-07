"""Explicit builders for canonical execution test workspaces."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from urllib.parse import quote

from content.execution.contracts import ExecutionState, ExecutionStateTransition
from content.execution.identity import parse_execution_id
from content.execution.queue.backend import freeze_execution_queue_backend
from content.execution.spec_contract import ExecutionSpec
from content.execution.store import save_spec
from content.execution.workspace import (
    TARGET_SET_REF,
    create_execution_manifest,
    ensure_execution_work_package_layout,
    write_frozen_target_set,
)
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from core.control_types import (
    ContentType,
    ExecutionStage,
    ExecutionStateStatus,
    SelectionPolicy,
)

_RECIPE_BY_CONTENT_TYPE = {
    ContentType.HOMEPAGE: "content/travel/homepage/homepage",
    ContentType.ARTICLE: "content/travel/article/article",
    ContentType.IMAGE: "content/travel/image/image",
    ContentType.VIDEO: "content/travel/video/video",
}
_DEFAULT_TARGET = {"name": "测试实体甲", "entityType": "地点/景区"}


@dataclass(frozen=True, slots=True)
class ExecutionFixtureBuilder:
    """Build one explicit manifest whose recipe matches its content type."""

    execution_id: str
    targets: tuple[Mapping[str, object], ...] = field(
        default_factory=lambda: (_DEFAULT_TARGET,)
    )
    retry_of: str | None = None
    semantic_selection_id: str = "default"
    semantic_preflight_binding: Mapping[str, object] | None = None
    # 过采场景：候选池大于准出配额。省略时候选池与配额相同（不过采）。
    approved_quota: int | None = None

    def _normalized_targets(self) -> list[dict[str, object]]:
        identity = parse_execution_id(self.execution_id)
        targets = [dict(item) for item in self.targets]
        if identity.content_type is not ContentType.HOMEPAGE:
            return targets
        for target in targets:
            raw_source = target.get("qualifiedHomepageSource")
            if isinstance(raw_source, Mapping):
                target["qualifiedHomepageSource"] = QualifiedHomepageSource.from_mapping(
                    raw_source
                ).to_dict()
                continue
            name = str(target.get("name") or "").strip()
            target["qualifiedHomepageSource"] = QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title=name,
                url=f"https://zh.wikipedia.org/wiki/{quote(name)}",
            ).to_dict()
        return targets

    def build(self) -> dict[str, object]:
        identity = parse_execution_id(self.execution_id)
        recipe_ref = _RECIPE_BY_CONTENT_TYPE[identity.content_type]
        normalized = self._normalized_targets()
        ensure_execution_work_package_layout(identity.execution_id)
        _path, digest = write_frozen_target_set(
            identity.execution_id,
            targets=normalized,
            source_ref="quwoquan_data/tests/support/execution_manifest_fixture.py",
        )
        save_spec(self.spec_payload())
        manifest = create_execution_manifest(
            execution_id=identity.execution_id,
            recipe_ref=recipe_ref,
            request={
                "familyRef": recipe_ref,
                "regionRef": identity.scope,
                "selector": "all",
                "count": len(normalized),
                "topic": None,
                "sourceProviders": [],
            },
            selection_policy=SelectionPolicy.FROZEN,
            target_set_ref=TARGET_SET_REF,
            target_set_digest=digest,
            retry_of=self.retry_of,
            semantic_selection_id=self.semantic_selection_id,
            semantic_preflight_binding=self.semantic_preflight_binding,
        )
        freeze_execution_queue_backend(
            identity.execution_id,
            spec=self.spec_payload(),
            manifest=manifest,
        )
        return manifest

    def spec_payload(self) -> dict[str, object]:
        """Build a complete effective spec without writing runtime output."""
        identity = parse_execution_id(self.execution_id)
        quotas = {
            "entityHomepagesPerTarget": 0,
            "entityArticlesPerTarget": 0,
            "imageWorksPerTarget": 0,
            "videoWorksPerTarget": 0,
            "routeArticles": 0,
        }
        quota_key = {
            ContentType.HOMEPAGE: "entityHomepagesPerTarget",
            ContentType.ARTICLE: "entityArticlesPerTarget",
            ContentType.IMAGE: "imageWorksPerTarget",
            ContentType.VIDEO: "videoWorksPerTarget",
        }[identity.content_type]
        quotas[quota_key] = 1
        targets = self._normalized_targets()
        quota = self.approved_quota if self.approved_quota is not None else len(targets)
        entity_types = tuple(
            dict.fromkeys(str(item["entityType"]) for item in targets)
        )
        return {
            "schema": "quwoquan.content.execution_spec",
            "executionId": identity.execution_id,
            "title": "contract fixture",
            "intentLabel": "contract fixture",
            "executionArchetype": "region_category_coverage",
            "vertical": "travel",
            "organizeBy": "地域",
            "key": identity.scope,
            "entityCategory": "景区",
            "status": "active",
            "scope": {
                "region": identity.scope,
                "entityTypes": list(entity_types),
                "coverageTargets": targets,
            },
            "provenance": {
                "createdAt": "2026-07-16T00:00:00Z",
                "createdBy": "local_contract",
            },
            "presetRef": _RECIPE_BY_CONTENT_TYPE[identity.content_type].rsplit("/", 1)[0] + "/base",
            "content": {
                "modalityContract": "separated_research",
                "research": {
                    "lanes": [identity.content_type.value],
                    "allowAiImages": False,
                },
                "carriers": [identity.content_type.value],
                "quotas": quotas,
            },
            "acceptance": {
                "minEntities": quota,
                "minPostsPerEntity": 1,
                "requiredAngles": [],
            },
            "executionPolicy": {
                "selectionPolicy": "frozen",
                "targetEntityCount": len(targets),
                "targetObjectCount": len(targets),
                "approvedQuota": quota,
                "oversampleFactor": len(targets) / quota,
                "articleCommercialClosure": (
                    identity.content_type is ContentType.ARTICLE
                ),
                "executionBranch": "dev1.0",
                "gitCommitSha": "local-contract-fixture",
            },
            "queuePolicy": {
                "backend": "reliabletask",
                "reliableTask": {
                    "taskType": "data.content_object.execute",
                    "queue": "reliabletask.data.content_supply",
                    "store": "MongoStore",
                    "readyIndex": "RedisReadyIndex",
                },
                "leaseSeconds": 1800,
                "heartbeatSeconds": 60,
                "deadLetterAfterAttempts": 2,
            },
        }

    def spec(self) -> ExecutionSpec:
        return ExecutionSpec.from_mapping(self.spec_payload())

    def state(
        self,
        *,
        status: ExecutionStateStatus = ExecutionStateStatus.QUEUED,
        completed: Iterable[ExecutionStage] = (),
        failed_objects: Iterable[str] = (),
        retry_counts: Mapping[ExecutionStage, int] | None = None,
        infrastructure_retry_counts: Mapping[ExecutionStage, int] | None = None,
        react_rewinds: Mapping[ExecutionStage, int] | None = None,
    ) -> ExecutionStateTransition:
        """Build a validated workflow-state transaction for contract tests."""
        return ExecutionState.from_mapping(
            {
                "schema": "quwoquan.content.execution_state",
                "executionId": self.execution_id,
                "completed": [stage.value for stage in completed],
                "status": status.value,
                "updatedAt": "2026-07-16T00:00:00Z",
                "failedObjects": list(failed_objects),
                "retryCounts": {
                    stage.value: count for stage, count in (retry_counts or {}).items()
                },
                "infrastructureRetryCounts": {
                    stage.value: count
                    for stage, count in (infrastructure_retry_counts or {}).items()
                },
                "reactRewinds": {
                    stage.value: count for stage, count in (react_rewinds or {}).items()
                },
            }
        ).open_transition()


def build_execution_fixture(
    execution_id: str,
    *,
    targets: Iterable[Mapping[str, object]] | None = None,
    retry_of: str | None = None,
    semantic_selection_id: str = "default",
    semantic_preflight_binding: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return ExecutionFixtureBuilder(
        execution_id=execution_id,
        targets=tuple(targets or (_DEFAULT_TARGET,)),
        retry_of=retry_of,
        semantic_selection_id=semantic_selection_id,
        semantic_preflight_binding=semantic_preflight_binding,
    ).build()


__all__ = ["ExecutionFixtureBuilder", "build_execution_fixture"]
