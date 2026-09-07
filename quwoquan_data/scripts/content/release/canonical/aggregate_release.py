"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

from pathlib import Path

from core.io import read_json
from core.schema import assert_valid

from content.release.canonical.aggregate_release_builder import (
    _build_aggregate_release,
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
    cohort_path = cohort_file.expanduser()
    if cohort_path.is_symlink() or not cohort_path.is_file():
        raise ValueError("DATA.RELEASE.COHORT_REF_INVALID: cohort must be a regular non-symlink file")
    cohort = read_json(cohort_path)
    assert_valid(cohort, "release", "release_cohort", label=str(cohort_path))
    return _build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=release_id,
        release_class=release_class,
        cohort=cohort,
    )


__all__ = ["build_pool_release"]
