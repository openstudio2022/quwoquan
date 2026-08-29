"""Canonical source inputs which control iOS/Android dependency resolution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .dependency_fs import assert_real_directory, read_regular_nofollow
from .pub_cache_capsule import _canonical_bytes, _digest_bytes
from .pub_cache_store import pub_resolution_input_paths

NATIVE_RESOLUTION_INPUT_SCHEMA = "stackctl-native-resolution-inputs.v1"

_EXCLUDED_SEGMENTS = frozenset(
    {
        ".dart_tool",
        ".gradle",
        ".symlinks",
        "Pods",
        "build",
        "example",
        "example_ohos",
    }
)
_EXACT_NAMES = frozenset(
    {
        "Gemfile",
        "Gemfile.lock",
        "Package.resolved",
        "Package.swift",
        "Podfile",
        "Podfile.lock",
        "gradle-wrapper.jar",
        "gradle-wrapper.properties",
        "gradle.properties",
        "gradlew",
        "gradlew.bat",
        "libs.versions.toml",
    }
)


def _is_resolution_file(path: Path) -> bool:
    return (
        path.name in _EXACT_NAMES
        or path.name.endswith(".podspec")
        or path.name.endswith(".gradle")
        or path.name.endswith(".gradle.kts")
    )


def native_resolution_input_paths(repo_root: Path) -> list[Path]:
    root = repo_root.expanduser().absolute()
    assert_real_directory(root, label="native resolution repository root")
    subtrees: set[Path] = set()
    for pubspec in pub_resolution_input_paths(root):
        if pubspec.name != "pubspec.yaml":
            continue
        package_root = pubspec.parent
        for name in ("android", "ios", "darwin", "macos"):
            subtree = package_root / name
            if subtree.is_dir() and not subtree.is_symlink():
                subtrees.add(subtree)
    patrol_host = root / "quwoquan_app/test_host/patrol"
    for name in ("android", "ios"):
        subtree = patrol_host / name
        if subtree.is_dir() and not subtree.is_symlink():
            subtrees.add(subtree)
    relative_subtrees = sorted(
        subtree.relative_to(root).as_posix() for subtree in subtrees
    )
    if not relative_subtrees:
        raise ValueError("App native dependency subtree set is empty")
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *relative_subtrees,
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("cannot enumerate App native dependency resolution inputs")
    paths: set[Path] = set()
    for encoded in result.stdout.split(b"\0"):
        if not encoded:
            continue
        path = root / os.fsdecode(encoded)
        relative = path.relative_to(root)
        if any(part in _EXCLUDED_SEGMENTS for part in relative.parts):
            continue
        if _is_resolution_file(path):
            paths.add(path)
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def native_resolution_input_identity(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().absolute()
    entries: list[dict[str, Any]] = []
    for path in native_resolution_input_paths(root):
        relative = path.relative_to(root).as_posix()
        content, _mode = read_regular_nofollow(
            path,
            label=f"native resolution input {relative}",
        )
        entries.append(
            {
                "path": relative,
                "size": len(content),
                "sha256": _digest_bytes(content),
            }
        )
    if not entries:
        raise ValueError("App native dependency resolution input set is empty")
    payload = {"schema": NATIVE_RESOLUTION_INPUT_SCHEMA, "entries": entries}
    return {
        "nativeResolutionInputDigest": _digest_bytes(_canonical_bytes(payload)),
        "nativeResolutionInputCount": len(entries),
        "nativeResolutionInputs": entries,
    }
