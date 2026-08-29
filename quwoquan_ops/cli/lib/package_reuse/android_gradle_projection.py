"""Verify and materialize one private, forced-offline Gradle projection."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .android_gradle_capsule import (
    _WRAPPER_FILES,
    ANDROID_GRADLE_CAPSULE_MANIFEST,
    ANDROID_GRADLE_CAPSULE_TREE,
    ANDROID_GRADLE_LOGICAL_PATH,
    ANDROID_GRADLE_PROJECTION_RELATIVE,
    AndroidGradleSnapshot,
    _read_regular_nofollow,
    build_android_gradle_snapshot,
    canonical_bytes,
    digest_bytes,
    wrapper_identity,
)
from .android_gradle_store import _copy_regular, copy_android_gradle_snapshot


def _materialize_embedded_wrappers(
    *,
    snapshot: AndroidGradleSnapshot,
    dependency_tree: Path,
    projection_root: Path,
) -> None:
    wrappers = snapshot.manifest["wrappers"]
    expected = {item.relative: item for item in snapshot.files}
    for declaration in wrappers:
        relative_root = str(declaration["root"])
        for relative_file in _WRAPPER_FILES:
            embedded_relative = (
                Path("wrappers") / relative_root / relative_file
            ).as_posix()
            item = expected.get(embedded_relative)
            if item is None:
                raise ValueError("Android Gradle embedded wrapper byte is missing")
            source = dependency_tree / embedded_relative
            destination = projection_root / relative_root / relative_file
            if destination.exists() or destination.is_symlink():
                actual, actual_mode = _read_regular_nofollow(
                    destination,
                    label=f"projected wrapper {embedded_relative}",
                )
                source_bytes, source_mode = _read_regular_nofollow(
                    source,
                    label=f"embedded wrapper {embedded_relative}",
                )
                if actual != source_bytes or actual_mode != source_mode:
                    raise ValueError("Android Gradle projected wrapper bytes drifted")
                continue
            _copy_regular(source, destination, writable=True)
    actual = [
        wrapper_identity(
            project_root=projection_root,
            gradle_root=projection_root / str(item["root"]),
        )
        for item in wrappers
    ]
    actual.sort(key=lambda item: item["root"])
    if actual != wrappers:
        raise ValueError("Android Gradle projected wrapper identity drifted")


def capsule_android_gradle_snapshot(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
) -> AndroidGradleSnapshot | None:
    matching = [
        item
        for item in manifest_entries
        if item.get("logicalPath") == ANDROID_GRADLE_LOGICAL_PATH
    ]
    tree = capsule_root / ANDROID_GRADLE_CAPSULE_TREE
    manifest_path = capsule_root / ANDROID_GRADLE_CAPSULE_MANIFEST
    if not matching and not tree.exists() and not manifest_path.exists():
        return None
    if len(matching) != 1:
        raise ValueError(
            "Android Gradle capsule manifest entry is missing or duplicated"
        )
    entry = matching[0]
    if entry.get("capsulePath") != ANDROID_GRADLE_CAPSULE_MANIFEST.as_posix():
        raise ValueError("Android Gradle capsule manifest path drifted")
    encoded, _mode = _read_regular_nofollow(
        manifest_path,
        label="capsule manifest",
    )
    if entry.get("digest") != digest_bytes(encoded) or entry.get("size") != len(encoded):
        raise ValueError("Android Gradle capsule manifest identity drifted")
    try:
        declared = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Android Gradle capsule manifest is invalid") from exc
    if not isinstance(declared, dict) or canonical_bytes(declared) != encoded:
        raise ValueError("Android Gradle capsule manifest is not canonical")
    repository = capsule_root / "repo"
    wrappers = declared.get("wrappers")
    if not isinstance(wrappers, list):
        raise TypeError("Android Gradle capsule wrapper set is invalid")
    gradle_roots = [repository / str(item.get("root") or "") for item in wrappers]
    snapshot = build_android_gradle_snapshot(
        project_root=repository,
        tree_root=tree,
        gradle_roots=gradle_roots,
    )
    if snapshot.manifest != declared:
        raise ValueError("Android Gradle capsule tree drifted")
    return snapshot


def materialize_capsule_android_gradle_home(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
    projection_root: Path,
) -> Path:
    snapshot = capsule_android_gradle_snapshot(
        capsule_root=capsule_root,
        manifest_entries=manifest_entries,
    )
    if snapshot is None:
        raise ValueError("Android Gradle dependency capsule is required")
    projection = projection_root.expanduser().absolute()
    wrappers = snapshot.manifest["wrappers"]
    gradle_roots = [projection / str(item["root"]) for item in wrappers]
    dependency_tree = projection / ANDROID_GRADLE_PROJECTION_RELATIVE
    home = copy_android_gradle_snapshot(
        snapshot,
        dependency_tree,
        project_root=projection,
        gradle_roots=gradle_roots,
    )
    _materialize_embedded_wrappers(
        snapshot=snapshot,
        dependency_tree=dependency_tree,
        projection_root=projection,
    )
    return home


def private_gradle_environment(
    *,
    gradle_user_home: Path,
    base: Mapping[str, str],
) -> dict[str, str]:
    """Return the only supported environment for a projected Gradle build."""

    home = gradle_user_home.expanduser().absolute()
    if home == Path.home() / ".gradle":
        raise ValueError("Android Gradle global cache fallback is forbidden")
    control = home / "init.d/qwq-offline.gradle"
    properties = home / "gradle.properties"
    if not control.is_file() or control.is_symlink() or not properties.is_file():
        raise ValueError("Android Gradle offline projection control is missing")
    environment = dict(base)
    environment["GRADLE_USER_HOME"] = str(home)
    environment.pop("GRADLE_HOME", None)
    return environment
