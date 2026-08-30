"""Project the independent Patrol hosted-Pub CAS into its private host."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .dependency_fs import assert_real_directory
from .patrol_pub_cache import (
    PATROL_HOST_RELATIVE,
    PATROL_PUB_PROJECTION_RELATIVE,
    _assert_unique_tree,
)
from .patrol_pub_store import (
    patrol_capsule_snapshot,
    verify_patrol_snapshot_flutter_toolchain,
)
from .pub_cache_capsule import copy_snapshot_tree_with_lock


def materialize_capsule_patrol_pub_cache(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
    projection_root: Path,
    verified_snapshot: Any | None = None,
) -> Path:
    """Copy one verified Patrol-only cache into a writable build projection."""

    snapshot = verified_snapshot
    if snapshot is None:
        snapshot = patrol_capsule_snapshot(
            capsule_root=capsule_root,
            manifest_entries=manifest_entries,
        )
    if snapshot is None:
        raise ValueError("Patrol Pub dependency capsule is required for projection")
    verify_patrol_snapshot_flutter_toolchain(snapshot)
    projection = projection_root.expanduser().absolute()
    assert_real_directory(projection, label="Patrol build projection root")
    host = projection / PATROL_HOST_RELATIVE
    assert_real_directory(host, label="Patrol build host root")
    dot_tool = host / ".dart_tool"
    if dot_tool.exists() or dot_tool.is_symlink():
        assert_real_directory(dot_tool, label="Patrol build .dart_tool root")
    else:
        dot_tool.mkdir(mode=0o700)
        assert_real_directory(dot_tool, label="Patrol build .dart_tool root")
    target = projection / PATROL_PUB_PROJECTION_RELATIVE
    lock_path = host / "pubspec.lock"
    copy_snapshot_tree_with_lock(
        snapshot,
        target,
        lock_path=lock_path,
        writable=True,
    )
    _assert_unique_tree(
        target,
        label="projected writable cache",
        require_read_only=False,
    )
    return target


def materialize_verified_capsule_patrol_pub_cache(
    *,
    manifest_path: Path,
    projection_root: Path,
) -> Path:
    """Verify the package capsule identity before projecting Patrol Pub bytes."""

    from .input_capsule import verify_package_input_capsule

    manifest_ref = manifest_path.expanduser().absolute()
    if manifest_ref.name != "manifest.json" or manifest_ref.is_symlink():
        raise ValueError("Patrol Pub source capsule manifest is invalid")
    capsule_root = manifest_ref.parent
    manifest = verify_package_input_capsule(capsule_root)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise TypeError("Patrol Pub source capsule entries are invalid")
    return materialize_capsule_patrol_pub_cache(
        capsule_root=capsule_root,
        manifest_entries=raw_entries,
        projection_root=projection_root.expanduser().absolute(),
    )
