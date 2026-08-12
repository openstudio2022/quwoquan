"""Materialize the governed Data sourceDigest closure without cloning Git."""

from __future__ import annotations

import shutil
from pathlib import Path

from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

SNAPSHOT_FORMAT = "source-capsule-v2"
_IGNORED_NAMES = ("__pycache__", ".pytest_cache", ".DS_Store")


def source_snapshot_roots(
    repo_root: Path,
    *,
    expected_digest: str,
) -> tuple[str, ...]:
    """Return the sole sourceDigest input closure after checking its identity."""
    document = current_source_definition_snapshot(repo_root=repo_root).to_document()
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
    expected_execution_bundle: str,
) -> tuple[str, ...]:
    """Bind source definitions and the separate exact execution bundle."""
    source_roots = source_snapshot_roots(
        repo_root,
        expected_digest=expected_digest,
    )
    bundle = current_execution_bundle_identity(repo_root=repo_root).to_document()
    if bundle["digest"] != expected_execution_bundle:
        raise ValueError("campaign execution bundle drift before capsule freeze")
    return tuple(dict.fromkeys((*source_roots, *bundle["inputs"])))


def materialize_source_snapshot(
    repo_root: Path,
    destination: Path,
    *,
    roots: tuple[str, ...],
    expected_digest: str,
    expected_execution_bundle: str,
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
    source_digest = current_source_definition_snapshot(repo_root=repo_root).digest
    snapshot_digest = SourceDefinitionSnapshot.build(repo_root=destination).digest
    source_bundle = current_execution_bundle_identity(repo_root=repo_root).digest
    snapshot_bundle = ExecutionBundleIdentity.build(repo_root=destination).digest
    if (
        source_digest != expected_digest
        or snapshot_digest != expected_digest
        or source_bundle != expected_execution_bundle
        or snapshot_bundle != expected_execution_bundle
    ):
        raise ValueError(
            "campaign source snapshot changed during materialization: "
            f"frozen={expected_digest}/{expected_execution_bundle} "
            f"source={source_digest}/{source_bundle} "
            f"snapshot={snapshot_digest}/{snapshot_bundle}"
        )


__all__ = [
    "SNAPSHOT_FORMAT",
    "campaign_snapshot_roots",
    "materialize_source_snapshot",
    "source_snapshot_roots",
]
