"""Load one managed dependency generation and copy every component to a package.

Only component manifests participate directly in the package input digest; each
manifest contains the exact tree CAS and is re-expanded by its domain verifier.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    COCOAPODS_ENVIRONMENT_KEYS,
    AppDependencyToolchainError,
    cocoapods_identity_from_environment,
    resolve_cocoapods_identity,
)

from .android_gradle_capsule import (
    ANDROID_GRADLE_CAPSULE_MANIFEST,
    ANDROID_GRADLE_CAPSULE_TREE,
    ANDROID_GRADLE_LOGICAL_PATH,
    AndroidGradleSnapshot,
)
from .android_gradle_component import load_android_gradle_component
from .android_gradle_projection import capsule_android_gradle_snapshot
from .android_gradle_store import (
    canonical_android_uat_gradle_invocations,
    write_android_gradle_capsule,
)
from .dependency_bundle import AppDependencyBundle, load_active_dependency_bundle
from .dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)
from .ios_pod_capsule import IosPodSnapshot
from .ios_pod_inputs import (
    IOS_POD_DEPENDENCY_DIRECTORIES,
    IOS_POD_DEPENDENCY_LOGICAL_PATHS,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
    IOS_PODFILE_LOCK_RELATIVES,
    ios_pod_resolution_inputs,
)
from .ios_pod_store import (
    load_ios_pod_capsule_bytes,
    load_verified_ios_pod_capsule,
    write_ios_pod_capsule,
)
from .patrol_pub_store import (
    copy_patrol_pub_snapshot_to_capsule,
    load_patrol_pub_cache_snapshot_at,
    patrol_capsule_snapshot,
)
from .pub_cache_capsule import (
    PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
    PUB_CACHE_DEPENDENCY_MANIFEST,
    PUB_CACHE_DEPENDENCY_TREE,
    PubCacheSnapshot,
    _digest_bytes,
    copy_snapshot_tree_with_lock,
)
from .pub_cache_store import (
    capsule_dependency_snapshot,
    current_flutter_identity,
    load_pub_cache_snapshot_at,
)


@dataclass(frozen=True, slots=True)
class ManagedDependencySnapshots:
    bundle: AppDependencyBundle
    production_pub: PubCacheSnapshot
    patrol_pub: PubCacheSnapshot
    production_ios_pods: IosPodSnapshot
    patrol_ios_pods: IosPodSnapshot
    android_gradle: AndroidGradleSnapshot


VerifiedDependencySnapshots = tuple[
    PubCacheSnapshot,
    PubCacheSnapshot,
    IosPodSnapshot,
    IosPodSnapshot,
    AndroidGradleSnapshot,
]


def _pub_manifest_digest(snapshot: PubCacheSnapshot) -> str:
    encoded = snapshot.encoded_sync_manifest
    if encoded is None:
        raise ValueError("App dependency Pub sync manifest is missing")
    return _digest_bytes(encoded)


def load_managed_dependency_snapshots(
    *, repo_root: Path, pod_executable: str | Path | None = None
) -> ManagedDependencySnapshots:
    """Read one active pointer, then verify every selected domain snapshot."""

    repository = repo_root.expanduser().absolute()
    bundle = load_active_dependency_bundle(repo_root=repository)
    flutter = current_flutter_identity()
    production_pub = load_pub_cache_snapshot_at(
        repo_root=repository,
        snapshot_root=bundle.component_root("productionPub"),
        expected_flutter=flutter,
    )
    patrol_pub = load_patrol_pub_cache_snapshot_at(
        repo_root=repository,
        snapshot_root=bundle.component_root("patrolPub"),
        expected_flutter=flutter,
    )
    if (
        production_pub.sync_manifest
        != bundle.component_manifest("productionPub")
        or patrol_pub.sync_manifest != bundle.component_manifest("patrolPub")
    ):
        raise ValueError("App dependency bundle Pub component drifted")
    try:
        if pod_executable is not None:
            pod_identity = resolve_cocoapods_identity(
                pod_executable,
                search_path=str(Path(pod_executable).expanduser().parent),
            )
        else:
            present_identity_keys = {
                key
                for key in COCOAPODS_ENVIRONMENT_KEYS
                if str(os.environ.get(key) or "").strip()
            }
            if present_identity_keys:
                pod_identity = cocoapods_identity_from_environment(os.environ)
            else:
                pod_identity = resolve_cocoapods_identity(
                    search_path=str(os.environ.get("PATH") or ""),
                )
        pod = pod_identity.executable
    except AppDependencyToolchainError as error:
        raise ValueError(str(error)) from error
    production_manifest = bundle.component_manifest("productionIosPods")
    patrol_manifest = bundle.component_manifest("patrolIosPods")
    production_ios = load_verified_ios_pod_capsule(
        snapshot_root=bundle.component_root("productionIosPods"),
        expected_podfile_lock=(
            repository / IOS_PODFILE_LOCK_RELATIVES[IOS_POD_PRODUCTION_HOST]
        ),
        pod_executable=pod,
        resolution_inputs=ios_pod_resolution_inputs(
            repo_root=repository,
            dependency_host=IOS_POD_PRODUCTION_HOST,
        ),
        upstream_dependency_digest=_pub_manifest_digest(production_pub),
        dependency_host=IOS_POD_PRODUCTION_HOST,
    )
    patrol_ios = load_verified_ios_pod_capsule(
        snapshot_root=bundle.component_root("patrolIosPods"),
        expected_podfile_lock=(
            repository / IOS_PODFILE_LOCK_RELATIVES[IOS_POD_PATROL_HOST]
        ),
        pod_executable=pod,
        resolution_inputs=ios_pod_resolution_inputs(
            repo_root=repository,
            dependency_host=IOS_POD_PATROL_HOST,
        ),
        upstream_dependency_digest=_pub_manifest_digest(patrol_pub),
        dependency_host=IOS_POD_PATROL_HOST,
    )
    if (
        production_ios.manifest != production_manifest
        or patrol_ios.manifest != patrol_manifest
    ):
        raise ValueError("App dependency bundle iOS component drifted")
    invocations = canonical_android_uat_gradle_invocations(repository)
    android = load_android_gradle_component(
        project_root=repository,
        component_root=bundle.component_root("androidGradle"),
        invocations=invocations,
        upstream_dependency_digests={
            "productionPub": _pub_manifest_digest(production_pub),
            "patrolPub": _pub_manifest_digest(patrol_pub),
        },
    )
    android_manifest = bundle.component_manifest("androidGradle")
    dependency = android_manifest.get("dependency")
    if not isinstance(dependency, Mapping) or dict(dependency) != android.manifest:
        raise ValueError("App dependency bundle Android component drifted")
    return ManagedDependencySnapshots(
        bundle=bundle,
        production_pub=production_pub,
        patrol_pub=patrol_pub,
        production_ios_pods=production_ios,
        patrol_ios_pods=patrol_ios,
        android_gradle=android,
    )


def _record(*, logical: str, relative: Path, content: bytes) -> dict[str, object]:
    return {
        "logicalPath": logical,
        "capsulePath": relative.as_posix(),
        "kind": "file",
        "digest": _digest_bytes(content),
        "size": len(content),
        "mode": 0o444,
    }


def _copy_production_pub(
    *, snapshot: PubCacheSnapshot, capsule_root: Path
) -> dict[str, object]:
    content = snapshot.encoded_sync_manifest
    if content is None:
        raise ValueError("Production Pub sync manifest is missing")
    write_fresh_relative_file(
        root=capsule_root,
        relative=PUB_CACHE_DEPENDENCY_MANIFEST.as_posix(),
        content=content,
        mode=0o444,
    )
    copy_snapshot_tree_with_lock(
        snapshot,
        capsule_root / PUB_CACHE_DEPENDENCY_TREE,
        lock_path=capsule_root / "repo/quwoquan_app/pubspec.lock",
        writable=False,
    )
    return _record(
        logical=PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
        relative=PUB_CACHE_DEPENDENCY_MANIFEST,
        content=content,
    )


def _copy_ios(
    *,
    logical: str,
    relative: Path,
    snapshot: IosPodSnapshot,
    capsule_root: Path,
) -> dict[str, object]:
    write_ios_pod_capsule(snapshot, capsule_root / relative)
    return _record(
        logical=logical,
        relative=relative / "manifest.json",
        content=snapshot.encoded_manifest,
    )


def copy_dependency_bundle_to_capsule(
    *, snapshots: ManagedDependencySnapshots, capsule_root: Path
) -> list[dict[str, object]]:
    """Copy all five verified components to one fresh package staging root."""

    root = capsule_root.expanduser().absolute()
    assert_real_directory(root, label="package dependency staging root")
    records = [
        _copy_production_pub(snapshot=snapshots.production_pub, capsule_root=root),
        copy_patrol_pub_snapshot_to_capsule(
            snapshot=snapshots.patrol_pub,
            capsule_root=root,
        ),
        _copy_ios(
            logical=IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PRODUCTION_HOST],
            relative=IOS_POD_DEPENDENCY_DIRECTORIES[IOS_POD_PRODUCTION_HOST],
            snapshot=snapshots.production_ios_pods,
            capsule_root=root,
        ),
        _copy_ios(
            logical=IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PATROL_HOST],
            relative=IOS_POD_DEPENDENCY_DIRECTORIES[IOS_POD_PATROL_HOST],
            snapshot=snapshots.patrol_ios_pods,
            capsule_root=root,
        ),
    ]
    invocations = canonical_android_uat_gradle_invocations(
        root / "repo"
    )
    write_android_gradle_capsule(
        snapshots.android_gradle,
        destination_tree=root / ANDROID_GRADLE_CAPSULE_TREE,
        manifest_path=root / ANDROID_GRADLE_CAPSULE_MANIFEST,
        project_root=root / "repo",
        gradle_roots=[item.gradle_root for item in invocations],
    )
    records.append(
        _record(
            logical=ANDROID_GRADLE_LOGICAL_PATH,
            relative=ANDROID_GRADLE_CAPSULE_MANIFEST,
            content=snapshots.android_gradle.encoded_manifest,
        )
    )
    return records


def dependency_bundle_digest_entries(
    snapshots: ManagedDependencySnapshots,
) -> list[tuple[str, str, bytes]]:
    """Return the marker records used by workspace and package CAS identity."""

    values = (
        (
            PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
            snapshots.production_pub.encoded_sync_manifest,
        ),
        (
            "dependency:patrol-host-dart-pub-cache-v1",
            snapshots.patrol_pub.encoded_sync_manifest,
        ),
        (
            IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PRODUCTION_HOST],
            snapshots.production_ios_pods.encoded_manifest,
        ),
        (
            IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PATROL_HOST],
            snapshots.patrol_ios_pods.encoded_manifest,
        ),
        (ANDROID_GRADLE_LOGICAL_PATH, snapshots.android_gradle.encoded_manifest),
    )
    result: list[tuple[str, str, bytes]] = []
    for logical, content in values:
        if content is None:
            raise ValueError("App dependency bundle marker content is missing")
        result.append((logical, "file", content))
    return result


def _capsule_marker(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
    logical: str,
    relative: Path,
) -> bytes:
    matching = [item for item in manifest_entries if item.get("logicalPath") == logical]
    if len(matching) != 1:
        raise ValueError("iOS Pod capsule manifest entry is missing or duplicated")
    path = capsule_root / relative / "manifest.json"
    encoded, mode = read_regular_nofollow(path, label="iOS Pod capsule manifest")
    marker = matching[0]
    if (
        marker.get("capsulePath") != (relative / "manifest.json").as_posix()
        or marker.get("kind") != "file"
        or marker.get("digest") != _digest_bytes(encoded)
        or marker.get("size") != len(encoded)
        or marker.get("mode") != 0o444
        or mode != 0o444
    ):
        raise ValueError("iOS Pod capsule manifest marker drifted")
    return encoded


def _ios_capsule_snapshot(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
    dependency_host: str,
    upstream_dependency_digest: str,
) -> IosPodSnapshot:
    logical = IOS_POD_DEPENDENCY_LOGICAL_PATHS[dependency_host]
    relative = IOS_POD_DEPENDENCY_DIRECTORIES[dependency_host]
    _capsule_marker(
        capsule_root=capsule_root,
        manifest_entries=manifest_entries,
        logical=logical,
        relative=relative,
    )
    return load_ios_pod_capsule_bytes(
        snapshot_root=capsule_root / relative,
        expected_podfile_lock=(
            capsule_root / "repo" / IOS_PODFILE_LOCK_RELATIVES[dependency_host]
        ),
        resolution_inputs=ios_pod_resolution_inputs(
            repo_root=capsule_root / "repo",
            dependency_host=dependency_host,
        ),
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=dependency_host,
    )


def verify_dependency_bundle_capsule(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
) -> VerifiedDependencySnapshots:
    """Verify all dependency bytes without consulting current global toolchains."""

    root = capsule_root.expanduser().absolute()
    production_pub = capsule_dependency_snapshot(
        capsule_root=root,
        manifest_entries=manifest_entries,
    )
    patrol_pub = patrol_capsule_snapshot(
        capsule_root=root,
        manifest_entries=manifest_entries,
    )
    if production_pub is None or patrol_pub is None:
        raise ValueError("App dependency bundle Pub component is missing")
    production_ios = _ios_capsule_snapshot(
        capsule_root=root,
        manifest_entries=manifest_entries,
        dependency_host=IOS_POD_PRODUCTION_HOST,
        upstream_dependency_digest=_pub_manifest_digest(production_pub),
    )
    patrol_ios = _ios_capsule_snapshot(
        capsule_root=root,
        manifest_entries=manifest_entries,
        dependency_host=IOS_POD_PATROL_HOST,
        upstream_dependency_digest=_pub_manifest_digest(patrol_pub),
    )
    android = capsule_android_gradle_snapshot(
        capsule_root=root,
        manifest_entries=manifest_entries,
    )
    if android is None:
        raise ValueError("App dependency bundle Android component is missing")
    return production_pub, patrol_pub, production_ios, patrol_ios, android
