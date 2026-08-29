"""Currentness wrapper around the sealed multi-root Android Gradle tree."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .android_gradle_capsule import (
    AndroidGradleSnapshot,
    canonical_bytes,
    digest_bytes,
    load_android_gradle_snapshot,
)
from .android_gradle_store import GradleInvocation, write_android_gradle_capsule
from .dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)
from .native_dependency_inputs import native_resolution_input_identity

ANDROID_GRADLE_SYNC_SCHEMA = "stackctl-android-gradle-sync-snapshot.v2"
ANDROID_GRADLE_SYNC_MANIFEST = Path("manifest.json")
ANDROID_GRADLE_SYNC_DEPENDENCY_MANIFEST = Path("dependency-manifest.json")
ANDROID_GRADLE_SYNC_TREE = Path("tree")

_SYNC_FIELDS = {
    "schema",
    "nativeResolutionInputDigest",
    "nativeResolutionInputCount",
    "nativeResolutionInputs",
    "invocationSetDigest",
    "invocations",
    "upstreamDependencyDigests",
    "dependency",
}


def android_gradle_invocation_identity(
    *, project_root: Path, invocations: Sequence[GradleInvocation]
) -> dict[str, Any]:
    repository = project_root.expanduser().absolute()
    entries: list[dict[str, Any]] = []
    for invocation in invocations:
        root = invocation.gradle_root.expanduser().absolute()
        if not root.is_relative_to(repository) or not invocation.tasks:
            raise ValueError("Android Gradle invocation identity is unsafe")
        entries.append(
            {
                "root": root.relative_to(repository).as_posix(),
                "tasks": list(invocation.tasks),
            }
        )
    entries.sort(key=lambda item: str(item["root"]))
    if not entries or len({str(item["root"]) for item in entries}) != len(entries):
        raise ValueError("Android Gradle invocation identity is empty or duplicated")
    payload = {
        "schema": "stackctl-android-gradle-invocation-set.v1",
        "invocations": entries,
    }
    return {
        "invocationSetDigest": digest_bytes(canonical_bytes(payload)),
        "invocations": entries,
    }


def build_android_gradle_sync_manifest(
    *,
    project_root: Path,
    snapshot: AndroidGradleSnapshot,
    invocations: Sequence[GradleInvocation],
    upstream_dependency_digests: Mapping[str, str],
) -> dict[str, Any]:
    upstream = _upstream_dependency_digests(upstream_dependency_digests)
    return {
        "schema": ANDROID_GRADLE_SYNC_SCHEMA,
        **native_resolution_input_identity(project_root),
        **android_gradle_invocation_identity(
            project_root=project_root,
            invocations=invocations,
        ),
        "upstreamDependencyDigests": upstream,
        "dependency": snapshot.manifest,
    }


def _upstream_dependency_digests(
    values: Mapping[str, str],
) -> dict[str, str]:
    expected = {"productionPub", "patrolPub"}
    normalized = {str(key): str(value) for key, value in values.items()}
    if set(normalized) != expected or any(
        not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for value in normalized.values()
    ):
        raise ValueError("Android Gradle upstream Pub identity is invalid")
    return {key: normalized[key] for key in sorted(normalized)}


def _seal(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    root.chmod(0o555)


def write_android_gradle_component(
    *,
    project_root: Path,
    snapshot: AndroidGradleSnapshot,
    invocations: Sequence[GradleInvocation],
    upstream_dependency_digests: Mapping[str, str],
    destination: Path,
) -> Path:
    """Write one read-only component root for the atomic dependency bundle."""

    target = destination.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("Android Gradle component destination must be fresh")
    assert_real_directory(target.parent, label="Android component parent")
    target.mkdir(mode=0o700)
    manifest = build_android_gradle_sync_manifest(
        project_root=project_root,
        snapshot=snapshot,
        invocations=invocations,
        upstream_dependency_digests=upstream_dependency_digests,
    )
    write_android_gradle_capsule(
        snapshot,
        destination_tree=target / ANDROID_GRADLE_SYNC_TREE,
        manifest_path=target / ANDROID_GRADLE_SYNC_DEPENDENCY_MANIFEST,
        project_root=project_root,
        gradle_roots=[item.gradle_root for item in invocations],
    )
    write_fresh_relative_file(
        root=target,
        relative=ANDROID_GRADLE_SYNC_MANIFEST.as_posix(),
        content=canonical_bytes(manifest),
        mode=0o444,
    )
    loaded = load_android_gradle_component(
        project_root=project_root,
        component_root=target,
        invocations=invocations,
        upstream_dependency_digests=upstream_dependency_digests,
    )
    if loaded.manifest != snapshot.manifest:
        raise ValueError("Android Gradle written component CAS drifted")
    _seal(target)
    return target


def _read_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    encoded, _mode = read_regular_nofollow(path, label="Android sync manifest")
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Android Gradle sync manifest is invalid") from error
    if not isinstance(value, dict) or canonical_bytes(value) != encoded:
        raise ValueError("Android Gradle sync manifest is not canonical")
    return encoded, value


def load_android_gradle_component(
    *,
    project_root: Path,
    component_root: Path,
    invocations: Sequence[GradleInvocation],
    upstream_dependency_digests: Mapping[str, str],
) -> AndroidGradleSnapshot:
    """Verify task/source currentness and then the complete sealed Gradle CAS."""

    repository = project_root.expanduser().absolute()
    root = component_root.expanduser().absolute()
    assert_real_directory(root, label="Android Gradle component root")
    if {path.name for path in root.iterdir()} != {
        ANDROID_GRADLE_SYNC_MANIFEST.name,
        ANDROID_GRADLE_SYNC_DEPENDENCY_MANIFEST.name,
        ANDROID_GRADLE_SYNC_TREE.name,
    }:
        raise ValueError("Android Gradle component contains undeclared top-level bytes")
    _encoded, manifest = _read_manifest(root / ANDROID_GRADLE_SYNC_MANIFEST)
    if set(manifest) != _SYNC_FIELDS or manifest.get("schema") != ANDROID_GRADLE_SYNC_SCHEMA:
        raise ValueError("Android Gradle sync manifest fields or schema mismatch")
    native = native_resolution_input_identity(repository)
    for field in (
        "nativeResolutionInputDigest",
        "nativeResolutionInputCount",
        "nativeResolutionInputs",
    ):
        if manifest.get(field) != native[field]:
            raise ValueError("Android Gradle component is stale for native inputs")
    invocation = android_gradle_invocation_identity(
        project_root=repository,
        invocations=invocations,
    )
    for field in ("invocationSetDigest", "invocations"):
        if manifest.get(field) != invocation[field]:
            raise ValueError("Android Gradle component is stale for invocation set")
    if manifest.get("upstreamDependencyDigests") != _upstream_dependency_digests(
        upstream_dependency_digests
    ):
        raise ValueError("Android Gradle component is stale for upstream Pub")
    snapshot = load_android_gradle_snapshot(
        project_root=repository,
        tree_root=root / ANDROID_GRADLE_SYNC_TREE,
        manifest_path=root / ANDROID_GRADLE_SYNC_DEPENDENCY_MANIFEST,
        gradle_roots=[item.gradle_root for item in invocations],
    )
    dependency = manifest.get("dependency")
    if not isinstance(dependency, Mapping) or dict(dependency) != snapshot.manifest:
        raise ValueError("Android Gradle sync manifest dependency CAS drifted")
    return snapshot


def android_gradle_sync_manifest_bytes(component_root: Path) -> bytes:
    encoded, _manifest = _read_manifest(
        component_root.expanduser().absolute() / ANDROID_GRADLE_SYNC_MANIFEST
    )
    return encoded
