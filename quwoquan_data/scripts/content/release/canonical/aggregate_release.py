"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_builder import (
    _build_aggregate_release,
)
from content.release.canonical.release_identity_incident import (
    canonical_release_identity_guard,
    release_output_root,
)


def build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    entity_catalog_digest: str,
    release_class: str,
    reviewed_closure_adoption: Mapping[str, Any] | None = None,
    adoption_output_root: Path | None = None,
    target_environment: str | None = None,
) -> dict[str, Any]:
    """Guard the canonical release identity across create-once/reuse."""

    with canonical_release_identity_guard(
        output_root=release_output_root(release_root),
        release_id=release_id,
    ):
        return _build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            entity_catalog_digest=entity_catalog_digest,
            release_class=release_class,
            reviewed_closure_adoption=reviewed_closure_adoption,
            adoption_output_root=adoption_output_root,
            target_environment=target_environment,
        )


def build_pool_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    target_environment: str | None = None,
    all_publishable: bool = False,
    milestone: str | None = None,
    release_class: str,
    sampling_authority_artifact_root: Path | None = None,
    sampling_authority_binding: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build one immutable pool release under one explicit selection scope."""

    with canonical_release_identity_guard(
        output_root=release_output_root(release_root),
        release_id=release_id,
    ):
        return _build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=release_id,
            execution_ids=[],
            source_revision="",
            entity_catalog_digest="",
            target_environment=target_environment,
            all_publishable=all_publishable,
            milestone=milestone,
            release_class=release_class,
            pool_wide=True,
            sampling_authority_artifact_root=sampling_authority_artifact_root,
            sampling_authority_binding=sampling_authority_binding,
        )


__all__ = ["build_aggregate_release", "build_pool_release"]
