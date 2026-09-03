"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.release.canonical.aggregate_release_builder import (
    _build_aggregate_release,
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
    cohort_file: Path,
    release_class: str,
) -> dict[str, Any]:
    """Build one immutable release from an exact caller-owned cohort file."""
    cohort = read_json(cohort_file)
    assert_valid(cohort, "release", "release_cohort", label=str(cohort_file))
    return _build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=release_id,
        execution_ids=[],
        source_revision="",
        entity_catalog_digest="",
        release_class=release_class,
        pool_wide=True,
        cohort=cohort,
    )


__all__ = ["build_aggregate_release", "build_pool_release"]
