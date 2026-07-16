"""Explicit builders for canonical v2 execution test workspaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from core.control_types import ContentType, SelectionPolicy
from content.execution.identity import parse_execution_id
from content.execution.workspace import (
    TARGET_SET_REF,
    create_execution_manifest,
    ensure_execution_work_package_layout,
    write_frozen_target_set,
)


_RECIPE_BY_CONTENT_TYPE = {
    ContentType.HOMEPAGE: "content/travel/homepage/homepage",
    ContentType.ARTICLE: "content/travel/article/article",
    ContentType.IMAGE: "content/travel/image/image",
    ContentType.VIDEO: "content/travel/video/video",
}
_DEFAULT_TARGET = {"name": "测试实体", "entityType": "地点/景区"}


@dataclass(frozen=True, slots=True)
class ExecutionFixtureBuilder:
    """Build one explicit v2 manifest whose recipe matches its content type."""

    execution_id: str
    targets: tuple[Mapping[str, object], ...] = field(
        default_factory=lambda: (_DEFAULT_TARGET,)
    )
    retry_of: str | None = None

    def build(self) -> dict[str, object]:
        identity = parse_execution_id(self.execution_id)
        recipe_ref = _RECIPE_BY_CONTENT_TYPE[identity.content_type]
        normalized = [dict(item) for item in self.targets]
        ensure_execution_work_package_layout(identity.execution_id)
        _path, digest = write_frozen_target_set(
            identity.execution_id,
            targets=normalized,
            source_ref="quwoquan_data/tests/support/execution_manifest_fixture.py",
        )
        return create_execution_manifest(
            execution_id=identity.execution_id,
            recipe_ref=recipe_ref,
            resolved_params={},
            selection_policy=SelectionPolicy.FROZEN,
            target_set_ref=TARGET_SET_REF,
            target_set_sha256=digest,
            retry_of=self.retry_of,
        )


def build_execution_fixture(
    execution_id: str,
    *,
    targets: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    return ExecutionFixtureBuilder(
        execution_id=execution_id,
        targets=tuple(targets or (_DEFAULT_TARGET,)),
    ).build()


__all__ = ["ExecutionFixtureBuilder", "build_execution_fixture"]
