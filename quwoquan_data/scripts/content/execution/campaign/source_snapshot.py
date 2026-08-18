"""Materialize the governed Data sourceDigest closure without cloning Git."""

from __future__ import annotations

import os
from pathlib import Path

from core.content_library import link_from_library
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

SNAPSHOT_FORMAT = "source-capsule-v2"
_IGNORED_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})
# Capsule digests record the executable bit, so two files with equal bytes but
# different modes are not interchangeable and cannot share one library inode.
_EXECUTABLE_ENTRY_SUFFIX = ".x"


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


def _reference_entry(source: Path, target: Path, *, library_root: Path) -> None:
    if source.is_symlink():
        target.symlink_to(os.readlink(source))
        return
    if not source.is_file():
        raise ValueError(f"campaign source snapshot input is invalid: {source}")
    executable = bool(source.stat().st_mode & 0o111)
    link_from_library(
        source,
        target,
        kind="source",
        library_root=library_root,
        suffix=_EXECUTABLE_ENTRY_SUFFIX if executable else "",
        executable=executable,
    )


def _reference_tree(source: Path, target: Path, *, library_root: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        if entry.name in _IGNORED_NAMES:
            continue
        child = target / entry.name
        if not entry.is_symlink() and entry.is_dir():
            _reference_tree(entry, child, library_root=library_root)
        else:
            _reference_entry(entry, child, library_root=library_root)


def reference_governed_inputs(
    repo_root: Path,
    destination: Path,
    *,
    roots: tuple[str, ...],
    library_root: Path,
) -> None:
    """Expose each governed input as a hard link onto an immutable library entry.

    A lane therefore reads exactly the frozen bytes while the capsule owns no
    second copy of them, so repeated freezes of one revision cost no new bytes.
    """
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("campaign source snapshot destination must be empty")
    for relative in roots:
        source = repo_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_symlink() and source.is_dir():
            _reference_tree(source, target, library_root=library_root)
        else:
            _reference_entry(source, target, library_root=library_root)


def materialize_source_snapshot(
    repo_root: Path,
    destination: Path,
    *,
    roots: tuple[str, ...],
    expected_digest: str,
    expected_execution_bundle: str,
    library_root: Path,
) -> None:
    """Reference each governed input once, then prove source and snapshot stayed equal."""
    reference_governed_inputs(
        repo_root,
        destination,
        roots=roots,
        library_root=library_root,
    )
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
    "reference_governed_inputs",
    "source_snapshot_roots",
]
