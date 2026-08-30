"""Independent hosted-Pub closure for the physically isolated Patrol host.

Production and Patrol are distinct Pub resolution roots.  A networked sync may
populate one fresh private cache with their union, but this module selects and
seals only the exact packages locked by the Patrol host.  No developer-global
cache is consulted and no production lock is used as a substitute.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .dependency_fs import assert_real_directory, read_regular_nofollow
from .pub_cache_capsule import (
    PubCacheSnapshot,
    _canonical_bytes,
    _digest_bytes,
    _lock_model,
    build_pub_cache_snapshot,
)

PATROL_PUB_SYNC_MANIFEST_SCHEMA = "stackctl-patrol-pub-cache-snapshot.v1"
PATROL_PUB_DEPENDENCY_LOGICAL_PATH = "dependency:patrol-host-dart-pub-cache-v1"
PATROL_PUB_DEPENDENCY_MANIFEST = Path(
    "dependencies/patrol-host-dart-pub-cache-manifest.json"
)
PATROL_PUB_DEPENDENCY_TREE = Path("dependencies/patrol-host-dart-pub-cache")
PATROL_PUB_PROJECTION_RELATIVE = Path(
    "quwoquan_app/test_host/patrol/.dart_tool/qwq_pub_cache"
)
PATROL_HOST_RELATIVE = Path("quwoquan_app/test_host/patrol")

_SYNC_FIELDS = {
    "schema",
    "flutterVersion",
    "flutterCommandResolutionDigest",
    "resolutionInputDigest",
    "resolutionInputCount",
    "resolutionInputs",
    "dependency",
}
_DEPENDENCY_SECTIONS = ("dependencies", "dev_dependencies", "dependency_overrides")


def _read_yaml(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    encoded, _mode = read_regular_nofollow(path, label=label)
    try:
        value = yaml.safe_load(encoded)
    except yaml.YAMLError as error:
        raise ValueError(f"Patrol Pub {label} is invalid") from error
    if not isinstance(value, Mapping):
        raise TypeError(f"Patrol Pub {label} is not an object")
    return encoded, value


def _repo_relative_root(*, repo_root: Path, package_root: Path, label: str) -> Path:
    root = Path(os.path.abspath(package_root))
    if not root.is_relative_to(repo_root):
        raise ValueError(f"Patrol Pub {label} escapes repository")
    assert_real_directory(root, label=label)
    return root


def _declared_path_roots(
    *, repo_root: Path, package_root: Path, document: Mapping[str, Any]
) -> set[Path]:
    roots: set[Path] = set()
    for section in _DEPENDENCY_SECTIONS:
        declarations = document.get(section)
        if declarations is None:
            continue
        if not isinstance(declarations, Mapping):
            raise TypeError(f"Patrol Pub {section} is invalid")
        for name, raw in declarations.items():
            if not isinstance(raw, Mapping) or "path" not in raw:
                continue
            raw_path = str(raw.get("path") or "")
            if not raw_path or Path(raw_path).is_absolute() or "\\" in raw_path:
                raise ValueError(f"Patrol Pub path identity is unsafe: {name}")
            roots.add(
                _repo_relative_root(
                    repo_root=repo_root,
                    package_root=package_root / raw_path,
                    label=f"path package {name}",
                )
            )
    return roots


def _locked_path_roots(
    *, repo_root: Path, host_root: Path, lock_document: Mapping[str, Any]
) -> set[Path]:
    packages = lock_document.get("packages")
    if not isinstance(packages, Mapping) or not packages:
        raise ValueError("Patrol Pub lock package set is invalid")
    roots: set[Path] = set()
    for name, raw in packages.items():
        if not isinstance(raw, Mapping) or raw.get("source") != "path":
            continue
        description = raw.get("description")
        if not isinstance(description, Mapping):
            raise TypeError(f"Patrol Pub locked path is invalid: {name}")
        raw_path = str(description.get("path") or "")
        if (
            description.get("relative") is not True
            or not raw_path
            or Path(raw_path).is_absolute()
            or "\\" in raw_path
        ):
            raise ValueError(f"Patrol Pub locked path identity is unsafe: {name}")
        roots.add(
            _repo_relative_root(
                repo_root=repo_root,
                package_root=host_root / raw_path,
                label=f"locked path package {name}",
            )
        )
    return roots


def patrol_resolution_input_paths(repo_root: Path) -> list[Path]:
    """Return Patrol pubspec plus the transitive repo-local pubspec closure."""

    root = repo_root.expanduser().absolute()
    assert_real_directory(root, label="Patrol resolution repository root")
    host = _repo_relative_root(
        repo_root=root,
        package_root=root / PATROL_HOST_RELATIVE,
        label="Patrol host root",
    )
    _lock_bytes, lock = _read_yaml(host / "pubspec.lock", label="pubspec.lock")
    pending = {
        host,
        *_locked_path_roots(repo_root=root, host_root=host, lock_document=lock),
    }
    visited: set[Path] = set()
    inputs: set[Path] = {host / "pubspec.lock", root / "quwoquan_app/.flutter-version"}
    package_names: dict[str, Path] = {}
    while pending:
        package_root = min(pending, key=lambda item: item.as_posix())
        pending.remove(package_root)
        if package_root in visited:
            continue
        visited.add(package_root)
        pubspec_path = package_root / "pubspec.yaml"
        _encoded, document = _read_yaml(
            pubspec_path,
            label=f"resolution input {pubspec_path.relative_to(root).as_posix()}",
        )
        name = str(document.get("name") or "")
        if not name:
            raise ValueError("Patrol Pub path package name is missing")
        previous = package_names.setdefault(name, package_root)
        if previous != package_root:
            raise ValueError(f"Patrol Pub path package name is duplicated: {name}")
        inputs.add(pubspec_path)
        pending.update(
            _declared_path_roots(
                repo_root=root,
                package_root=package_root,
                document=document,
            )
            - visited
        )
    return sorted(inputs, key=lambda item: item.relative_to(root).as_posix())


def patrol_resolution_input_identity(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().absolute()
    entries: list[dict[str, Any]] = []
    for path in patrol_resolution_input_paths(root):
        relative = path.relative_to(root).as_posix()
        content, _mode = read_regular_nofollow(
            path, label=f"resolution input {relative}"
        )
        entries.append(
            {"path": relative, "size": len(content), "sha256": _digest_bytes(content)}
        )
    payload = {"schema": "stackctl-patrol-pub-resolution-inputs.v1", "entries": entries}
    return {
        "resolutionInputDigest": _digest_bytes(_canonical_bytes(payload)),
        "resolutionInputCount": len(entries),
        "resolutionInputs": entries,
    }


def _flutter_identity(value: Mapping[str, str]) -> dict[str, str]:
    identity = {
        "flutterVersion": str(value.get("flutterVersion") or ""),
        "flutterCommandResolutionDigest": str(
            value.get("flutterCommandResolutionDigest")
            or value.get("commandResolutionDigest")
            or ""
        ),
    }
    if not identity["flutterVersion"] or not identity[
        "flutterCommandResolutionDigest"
    ].startswith("sha256:"):
        raise ValueError("Patrol Pub Flutter identity is incomplete")
    return identity


def build_patrol_pub_cache_snapshot(
    *,
    repo_root: Path,
    cache_root: Path,
    flutter_identity: Mapping[str, str],
) -> PubCacheSnapshot:
    """Select the Patrol lock's packages from one explicit private sync cache."""

    root = repo_root.expanduser().absolute()
    lock_path = root / PATROL_HOST_RELATIVE / "pubspec.lock"
    _assert_selected_source_nodes(lock_path=lock_path, cache_root=cache_root)
    snapshot = build_pub_cache_snapshot(
        lock_path=lock_path,
        cache_root=cache_root,
    )
    wrapper = {
        "schema": PATROL_PUB_SYNC_MANIFEST_SCHEMA,
        **_flutter_identity(flutter_identity),
        **patrol_resolution_input_identity(root),
        "dependency": snapshot.manifest,
    }
    return replace(
        snapshot,
        sync_manifest=wrapper,
        encoded_sync_manifest=_canonical_bytes(wrapper),
    )


def _assert_unique_tree(
    root: Path,
    *,
    label: str,
    require_read_only: bool,
) -> None:
    """Reject linked, multiply-linked, special, or writable CAS nodes."""

    assert_real_directory(root, label=label)
    nodes = [root, *sorted(root.rglob("*"))]
    for path in nodes:
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise ValueError(f"Patrol Pub {label} has special permissions: {relative}")
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Patrol Pub {label} contains a symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            assert_real_directory(path, label=f"{label} directory {relative}")
        elif stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise ValueError(f"Patrol Pub {label} contains a hardlink: {relative}")
        else:
            raise ValueError(f"Patrol Pub {label} contains a special node: {relative}")
        if require_read_only and metadata.st_mode & 0o222:
            raise ValueError(f"Patrol Pub {label} contains writable bytes: {relative}")


def _assert_selected_source_nodes(*, lock_path: Path, cache_root: Path) -> None:
    """Preflight only Patrol-selected packages in a possibly unioned sync cache."""

    _lock_bytes, _lock_digest, packages = _lock_model(lock_path)
    cache = cache_root.expanduser().absolute()
    assert_real_directory(cache, label="Patrol private union cache")
    for package in packages:
        segment = f"{package['name']}-{package['version']}"
        package_root = cache / "hosted" / package["host"] / segment
        _assert_unique_tree(
            package_root,
            label=f"selected package {segment}",
            require_read_only=False,
        )
        archive_hash = cache / "hosted-hashes" / package["host"] / f"{segment}.sha256"
        metadata = archive_hash.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
        ):
            raise ValueError(f"Patrol Pub archive hash is unsafe: {segment}")
