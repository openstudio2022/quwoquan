"""Published homepage closure used as the sole parent for post targets."""
from __future__ import annotations

from dataclasses import dataclass

from content.execution.identity import parse_execution_id
from content.execution.request import RuntimeExecutionRequest
from content.execution.workspace import (
    FrozenTarget,
    execution_request_path,
    execution_root,
    load_execution_manifest,
    load_frozen_target_set,
)
from core.io import read_json
from core.schema import assert_valid


@dataclass(frozen=True, slots=True)
class PublishedHomepageBinding:
    execution_id: str
    region_ref: str
    targets: tuple[FrozenTarget, ...]
    published_refs: frozenset[str]

    @classmethod
    def load(cls, execution_id: str) -> "PublishedHomepageBinding":
        identity = parse_execution_id(execution_id)
        if identity.content_type.value != "homepage":
            raise ValueError("homepage execution binding must reference homepage content")
        load_execution_manifest(execution_id)
        request = RuntimeExecutionRequest.from_document(
            read_json(execution_request_path(execution_id))
        )
        publish_ref_path = execution_root(execution_id) / "publish_ref.json"
        if not publish_ref_path.is_file():
            raise ValueError("homepage execution has no canonical publish closure")
        publish_ref = read_json(publish_ref_path)
        assert_valid(
            publish_ref,
            "execution",
            "publish_ref",
            label=f"publish_ref:{execution_id}",
        )
        published = publish_ref.get("publishedRefs")
        if not isinstance(published, dict):
            raise ValueError("homepage publish closure is invalid")
        target_set = load_frozen_target_set(execution_id)
        raw_targets = target_set.get("targets")
        if not isinstance(raw_targets, list):
            raise ValueError("homepage target set is invalid")
        targets = tuple(FrozenTarget.from_mapping(raw) for raw in raw_targets)
        return cls(
            execution_id=execution_id,
            region_ref=request.region_ref,
            targets=targets,
            published_refs=frozenset(
                str(ref).strip().strip("/")
                for ref in published.get("entities") or []
            ),
        )

    def target_names(self, *, region_ref: str, count: int) -> tuple[str, ...]:
        if self.region_ref != region_ref:
            raise ValueError("post region must equal its homepage execution region")
        expected_refs = {
            f"{target.entity_type}/{target.name}" for target in self.targets
        }
        if self.published_refs != expected_refs:
            raise ValueError(
                "homepage canonical publish closure does not equal its frozen target set"
            )
        if count > len(self.targets):
            raise ValueError(
                f"post count {count} exceeds published homepage count {len(self.targets)}"
            )
        return tuple(target.name for target in self.targets[:count])


def published_homepage_target_names(
    homepage_execution_id: str,
    *,
    region_ref: str,
    count: int,
) -> tuple[str, ...]:
    return PublishedHomepageBinding.load(homepage_execution_id).target_names(
        region_ref=region_ref,
        count=count,
    )


__all__ = ["PublishedHomepageBinding", "published_homepage_target_names"]
