"""Storage, package-capsule readback, and currentness for Patrol Pub."""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)
from .patrol_pub_cache import (
    _SYNC_FIELDS,
    PATROL_HOST_RELATIVE,
    PATROL_PUB_DEPENDENCY_LOGICAL_PATH,
    PATROL_PUB_DEPENDENCY_MANIFEST,
    PATROL_PUB_DEPENDENCY_TREE,
    PATROL_PUB_SYNC_MANIFEST_SCHEMA,
    _assert_unique_tree,
    _flutter_identity,
    patrol_resolution_input_identity,
)
from .pub_cache_capsule import (
    PubCacheSnapshot,
    _canonical_bytes,
    _digest_bytes,
    build_pub_cache_snapshot,
    copy_snapshot_tree_with_lock,
)
from .pub_cache_store import current_flutter_identity


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    encoded, _mode = read_regular_nofollow(path, label=label)
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Patrol Pub {label} is invalid") from error
    if not isinstance(value, dict):
        raise TypeError(f"Patrol Pub {label} is not an object")
    return encoded, value


def _validated_manifest(
    *,
    repo_root: Path,
    manifest: Mapping[str, Any],
    expected_flutter: Mapping[str, str] | None,
) -> dict[str, Any]:
    value = dict(manifest)
    if (
        set(value) != _SYNC_FIELDS
        or value.get("schema") != PATROL_PUB_SYNC_MANIFEST_SCHEMA
    ):
        raise ValueError("Patrol Pub snapshot manifest fields or schema mismatch")
    resolution = patrol_resolution_input_identity(repo_root)
    for field in ("resolutionInputDigest", "resolutionInputCount", "resolutionInputs"):
        if value.get(field) != resolution[field]:
            raise ValueError("Patrol Pub snapshot is stale for resolution inputs")
    identity = _flutter_identity(expected_flutter or value)
    for field, expected in identity.items():
        if value.get(field) != expected:
            raise ValueError("Patrol Pub snapshot is stale for Flutter toolchain")
    if not isinstance(value.get("dependency"), Mapping):
        raise TypeError("Patrol Pub dependency manifest is missing")
    return value


def _seal(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    root.chmod(0o555)


def write_patrol_pub_cache_snapshot(
    *,
    snapshot: PubCacheSnapshot,
    destination: Path,
    repo_root: Path,
) -> Path:
    """Write one managed read-only Patrol snapshot; caller owns atomic publish."""

    if snapshot.sync_manifest is None or snapshot.encoded_sync_manifest is None:
        raise ValueError("Patrol Pub sync manifest is not bound")
    repo = repo_root.expanduser().absolute()
    validated = _validated_manifest(
        repo_root=repo,
        manifest=snapshot.sync_manifest,
        expected_flutter=_flutter_identity(snapshot.sync_manifest),
    )
    canonical = _canonical_bytes(validated)
    if (
        canonical != snapshot.encoded_sync_manifest
        or dict(validated["dependency"]) != snapshot.manifest
    ):
        raise ValueError("Patrol Pub sync manifest does not bind snapshot CAS")
    target = destination.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("Patrol Pub snapshot destination must be fresh")
    assert_real_directory(target.parent, label="Patrol snapshot parent")
    target.mkdir(mode=0o700)
    copy_snapshot_tree_with_lock(
        snapshot,
        target / "pub",
        lock_path=repo / PATROL_HOST_RELATIVE / "pubspec.lock",
        writable=False,
    )
    write_fresh_relative_file(
        root=target,
        relative="manifest.json",
        content=canonical,
        mode=0o444,
    )
    written = load_patrol_pub_cache_snapshot_at(
        repo_root=repo,
        snapshot_root=target,
        expected_flutter=_flutter_identity(validated),
    )
    if written.manifest != snapshot.manifest:
        raise ValueError("Patrol Pub written snapshot CAS drifted")
    _seal(target)
    return target


def load_patrol_pub_cache_snapshot_at(
    *,
    repo_root: Path,
    snapshot_root: Path,
    expected_flutter: Mapping[str, str] | None,
) -> PubCacheSnapshot:
    """Load one exact managed Patrol tree and prove its currentness."""

    repo = repo_root.expanduser().absolute()
    root = snapshot_root.expanduser().absolute()
    assert_real_directory(root, label="Patrol managed snapshot root")
    if {path.name for path in root.iterdir()} != {"manifest.json", "pub"}:
        raise ValueError("Patrol Pub snapshot contains undeclared top-level bytes")
    encoded, manifest = _read_json(
        root / "manifest.json", label="managed snapshot manifest"
    )
    validated = _validated_manifest(
        repo_root=repo,
        manifest=manifest,
        expected_flutter=expected_flutter,
    )
    if encoded != _canonical_bytes(validated):
        raise ValueError("Patrol Pub snapshot manifest is not canonical")
    _assert_unique_tree(
        root / "pub", label="managed sealed cache", require_read_only=True
    )
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / PATROL_HOST_RELATIVE / "pubspec.lock",
        cache_root=root / "pub",
        reject_unlocked=True,
    )
    if snapshot.manifest != dict(validated["dependency"]):
        raise ValueError("Patrol Pub managed snapshot tree drifted")
    return replace(
        snapshot,
        sync_manifest=validated,
        encoded_sync_manifest=_canonical_bytes(validated),
    )


def load_managed_patrol_pub_cache_snapshot(*, repo_root: Path) -> PubCacheSnapshot:
    """Load Patrol Pub from the same atomic bundle as every native closure."""

    from .dependency_bundle import load_active_dependency_bundle

    repo = repo_root.expanduser().absolute()
    bundle = load_active_dependency_bundle(repo_root=repo)
    snapshot = load_patrol_pub_cache_snapshot_at(
        repo_root=repo,
        snapshot_root=bundle.component_root("patrolPub"),
        expected_flutter=current_flutter_identity(),
    )
    if snapshot.sync_manifest != bundle.component_manifest("patrolPub"):
        raise ValueError("App dependency bundle Patrol Pub manifest drifted")
    return snapshot


def patrol_sync_manifest_bytes(snapshot: PubCacheSnapshot) -> bytes:
    if snapshot.encoded_sync_manifest is None:
        raise ValueError("Patrol Pub sync manifest is not bound")
    return snapshot.encoded_sync_manifest


def verify_patrol_snapshot_flutter_toolchain(snapshot: PubCacheSnapshot) -> None:
    manifest = snapshot.sync_manifest
    if manifest is None:
        raise ValueError("Patrol Pub sync manifest is not bound")
    current = _flutter_identity(current_flutter_identity())
    for field, expected in current.items():
        if manifest.get(field) != expected:
            raise ValueError("Patrol Pub capsule Flutter toolchain drifted")


def copy_patrol_pub_snapshot_to_capsule(
    *,
    snapshot: PubCacheSnapshot,
    capsule_root: Path,
) -> dict[str, object]:
    """Add the independent Patrol marker/tree to a fresh package staging root."""

    root = capsule_root.expanduser().absolute()
    assert_real_directory(root, label="Patrol package capsule root")
    repo = root / "repo"
    if snapshot.sync_manifest is None or snapshot.encoded_sync_manifest is None:
        raise ValueError("Patrol Pub sync manifest is not bound")
    validated = _validated_manifest(
        repo_root=repo,
        manifest=snapshot.sync_manifest,
        expected_flutter=None,
    )
    content = _canonical_bytes(validated)
    if (
        content != snapshot.encoded_sync_manifest
        or dict(validated["dependency"]) != snapshot.manifest
    ):
        raise ValueError("Patrol Pub capsule input is internally inconsistent")
    write_fresh_relative_file(
        root=root,
        relative=PATROL_PUB_DEPENDENCY_MANIFEST.as_posix(),
        content=content,
        mode=0o444,
    )
    copy_snapshot_tree_with_lock(
        snapshot,
        root / PATROL_PUB_DEPENDENCY_TREE,
        lock_path=repo / PATROL_HOST_RELATIVE / "pubspec.lock",
        writable=False,
    )
    return {
        "logicalPath": PATROL_PUB_DEPENDENCY_LOGICAL_PATH,
        "capsulePath": PATROL_PUB_DEPENDENCY_MANIFEST.as_posix(),
        "kind": "file",
        "digest": _digest_bytes(content),
        "size": len(content),
        "mode": 0o444,
    }


def patrol_capsule_snapshot(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
) -> PubCacheSnapshot | None:
    """Verify and read the Patrol dependency bytes from a package capsule."""

    root = capsule_root.expanduser().absolute()
    assert_real_directory(root, label="Patrol package capsule root")
    matching = [
        item
        for item in manifest_entries
        if item.get("logicalPath") == PATROL_PUB_DEPENDENCY_LOGICAL_PATH
    ]
    repo = root / "repo"
    lock_path = repo / PATROL_HOST_RELATIVE / "pubspec.lock"
    marker_path = root / PATROL_PUB_DEPENDENCY_MANIFEST
    tree_path = root / PATROL_PUB_DEPENDENCY_TREE
    if not lock_path.exists():
        if matching or marker_path.exists() or tree_path.exists():
            raise ValueError("Patrol Pub capsule exists without Patrol pubspec.lock")
        return None
    if len(matching) != 1:
        raise ValueError("Patrol Pub capsule manifest entry is missing or duplicated")
    marker = matching[0]
    encoded, manifest = _read_json(marker_path, label="capsule dependency manifest")
    metadata = marker_path.lstat()
    if (
        marker.get("capsulePath") != PATROL_PUB_DEPENDENCY_MANIFEST.as_posix()
        or marker.get("kind") != "file"
        or marker.get("digest") != _digest_bytes(encoded)
        or marker.get("size") != len(encoded)
        or marker.get("mode") != 0o444
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o222
    ):
        raise ValueError("Patrol Pub capsule manifest marker drifted")
    validated = _validated_manifest(
        repo_root=repo,
        manifest=manifest,
        expected_flutter=None,
    )
    if encoded != _canonical_bytes(validated):
        raise ValueError("Patrol Pub capsule manifest is not canonical")
    _assert_unique_tree(tree_path, label="capsule sealed cache", require_read_only=True)
    snapshot = build_pub_cache_snapshot(
        lock_path=lock_path,
        cache_root=tree_path,
        reject_unlocked=True,
    )
    if snapshot.manifest != dict(validated["dependency"]):
        raise ValueError("Patrol Pub capsule tree drifted")
    return replace(
        snapshot,
        sync_manifest=validated,
        encoded_sync_manifest=_canonical_bytes(validated),
    )
