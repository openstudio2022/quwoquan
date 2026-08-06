"""Materialize the governed Data sourceDigest closure without cloning Git."""

from __future__ import annotations

import shutil
from pathlib import Path

from core.source_digest import current_source_digest

SNAPSHOT_FORMAT = "source-snapshot-v1"
_IGNORED_NAMES = ("__pycache__", ".pytest_cache", ".DS_Store")
_CAMPAIGN_GOVERNANCE_ROOTS = (
    "quwoquan_data/requirements-cursor.txt",
    "quwoquan_ops/policies/branch_policy.yaml",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md",
)


def source_snapshot_roots(
    repo_root: Path,
    *,
    expected_digest: str,
) -> tuple[str, ...]:
    """Return the sole sourceDigest input closure after checking its identity."""
    document = current_source_digest(repo_root=repo_root).to_document()
    if document["digest"] != expected_digest:
        raise ValueError(
            "campaign source snapshot digest drift: "
            f"frozen={expected_digest} current={document['digest']}"
        )
    roots = tuple(str(value) for value in document["inputs"])
    if not roots or any(not (repo_root / relative).exists() for relative in roots):
        raise ValueError("campaign source snapshot input closure is incomplete")
    return roots


def campaign_snapshot_roots(
    repo_root: Path,
    *,
    expected_digest: str,
) -> tuple[str, ...]:
    """Bind Data source roots plus the exact cross-repo execution policy."""
    source_roots = source_snapshot_roots(
        repo_root,
        expected_digest=expected_digest,
    )
    for relative in _CAMPAIGN_GOVERNANCE_ROOTS:
        path = repo_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                "campaign governance input is missing or symbolic: "
                f"{relative}"
            )
    return (*source_roots, *_CAMPAIGN_GOVERNANCE_ROOTS)


def materialize_source_snapshot(
    repo_root: Path,
    destination: Path,
    *,
    roots: tuple[str, ...],
    expected_digest: str,
) -> None:
    """Copy each governed input once, then prove source and snapshot stayed equal."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("campaign source snapshot destination must be empty")
    for relative in roots:
        source = repo_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                symlinks=True,
                ignore=shutil.ignore_patterns(*_IGNORED_NAMES),
            )
        elif source.is_file():
            shutil.copy2(source, target, follow_symlinks=False)
        else:
            raise ValueError(f"campaign source snapshot input is invalid: {relative}")
    source_digest = current_source_digest(repo_root=repo_root).digest
    snapshot_digest = current_source_digest(repo_root=destination).digest
    if source_digest != expected_digest or snapshot_digest != expected_digest:
        raise ValueError(
            "campaign source snapshot changed during materialization: "
            f"frozen={expected_digest} source={source_digest} snapshot={snapshot_digest}"
        )


__all__ = [
    "SNAPSHOT_FORMAT",
    "campaign_snapshot_roots",
    "materialize_source_snapshot",
    "source_snapshot_roots",
]
