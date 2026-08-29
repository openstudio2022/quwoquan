"""Materialize a verified dependency capsule inside one private App projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .pub_cache_capsule import (
    PUB_CACHE_PROJECTION_RELATIVE,
    build_pub_cache_snapshot,
    copy_snapshot_tree_with_lock,
)
from .pub_cache_store import (
    capsule_dependency_snapshot,
    verify_snapshot_flutter_toolchain,
)


def materialize_capsule_pub_cache(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
    projection_root: Path,
) -> Path:
    snapshot = capsule_dependency_snapshot(
        capsule_root=capsule_root,
        manifest_entries=manifest_entries,
    )
    if snapshot is None:
        raise ValueError("App dependency capsule is required for Flutter projection")
    verify_snapshot_flutter_toolchain(snapshot)
    target = projection_root / PUB_CACHE_PROJECTION_RELATIVE
    lock_path = projection_root / "quwoquan_app/pubspec.lock"
    copy_snapshot_tree_with_lock(
        snapshot,
        target,
        lock_path=lock_path,
        writable=True,
    )
    final = build_pub_cache_snapshot(
        lock_path=lock_path,
        cache_root=target,
        reject_unlocked=True,
    )
    if final.manifest != snapshot.manifest:
        raise ValueError("App dependency projected cache CAS drifted")
    return target


def materialize_verified_capsule_pub_cache(
    *,
    manifest_path: Path,
    projection_root: Path,
) -> Path:
    from .input_capsule import verify_package_input_capsule

    manifest_ref = manifest_path.expanduser().absolute()
    if manifest_ref.name != "manifest.json" or manifest_ref.is_symlink():
        raise ValueError("App dependency source capsule manifest is invalid")
    capsule_root = manifest_ref.parent
    manifest = verify_package_input_capsule(capsule_root)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise TypeError("App dependency source capsule entries are invalid")
    return materialize_capsule_pub_cache(
        capsule_root=capsule_root,
        manifest_entries=raw_entries,
        projection_root=projection_root.expanduser().absolute(),
    )
