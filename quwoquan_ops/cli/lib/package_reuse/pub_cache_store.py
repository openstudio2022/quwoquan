"""Managed Pub snapshot identity, currentness, and capsule readback."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)
from quwoquan_ops.cli.lib.output_paths import output_root

from .dependency_fs import assert_real_directory, read_regular_nofollow
from .pub_cache_capsule import (
    PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
    PUB_CACHE_DEPENDENCY_MANIFEST,
    PUB_CACHE_DEPENDENCY_TREE,
    PUB_CACHE_SYNC_MANIFEST_SCHEMA,
    PubCacheSnapshot,
    _canonical_bytes,
    _digest_bytes,
    build_pub_cache_snapshot,
    dependency_required,
)

_SYNC_FIELDS = {
    "schema",
    "flutterVersion",
    "flutterCommandResolutionDigest",
    "resolutionInputDigest",
    "resolutionInputCount",
    "resolutionInputs",
    "dependency",
}


def managed_snapshot_root() -> Path:
    return (
        output_root().expanduser().absolute()
        / "env/repo/local/app-dependency-sync/cache"
    )


def _read_json_nofollow(path: Path, *, label: str) -> dict[str, Any]:
    encoded, _mode = read_regular_nofollow(path, label=label)
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"App dependency {label} is invalid") from exc
    if not isinstance(value, dict):
        raise TypeError(f"App dependency {label} is not an object")
    return value


def current_flutter_identity() -> dict[str, str]:
    try:
        raw = resolved_flutter_identity(dict(os.environ))
    except FacadeError as exc:
        raise ValueError(
            f"APP.DEPENDENCY.flutter_identity_invalid: {exc}"
        ) from exc
    return {
        "flutterVersion": str(raw.get("flutterVersion") or ""),
        "flutterCommandResolutionDigest": str(
            raw.get("commandResolutionDigest") or ""
        ),
    }


def pub_resolution_input_paths(repo_root: Path) -> list[Path]:
    root = repo_root.expanduser().absolute()
    app = root / "quwoquan_app"
    lock_path = app / "pubspec.lock"
    encoded, _mode = read_regular_nofollow(lock_path, label="pubspec.lock")
    try:
        payload = yaml.safe_load(encoded)
    except yaml.YAMLError as exc:
        raise ValueError("App dependency pubspec.lock is invalid") from exc
    packages = payload.get("packages") if isinstance(payload, Mapping) else None
    if not isinstance(packages, Mapping):
        raise TypeError("App dependency pubspec.lock package set is invalid")
    paths = {app / "pubspec.yaml", app / ".flutter-version"}
    for name, raw in packages.items():
        if not isinstance(raw, Mapping) or raw.get("source") != "path":
            continue
        description = raw.get("description")
        if not isinstance(description, Mapping):
            raise TypeError(f"App dependency path description is invalid: {name}")
        relative = description.get("relative")
        raw_path = str(description.get("path") or "")
        if (
            relative is not True
            or not raw_path
            or Path(raw_path).is_absolute()
            or "\\" in raw_path
        ):
            raise ValueError(f"App dependency path identity is unsafe: {name}")
        package_root = Path(os.path.abspath(app / raw_path))
        if not package_root.is_relative_to(root):
            raise ValueError(f"App dependency path escapes repository: {name}")
        paths.add(package_root / "pubspec.yaml")
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def resolution_input_identity(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().absolute()
    assert_real_directory(root, label="resolution repository root")
    entries: list[dict[str, Any]] = []
    for path in pub_resolution_input_paths(root):
        content, _mode = read_regular_nofollow(
            path,
            label=f"resolution input {path.relative_to(root).as_posix()}",
        )
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": len(content),
                "sha256": _digest_bytes(content),
            }
        )
    payload = {"schema": "stackctl-pub-resolution-inputs.v1", "entries": entries}
    return {
        "resolutionInputDigest": _digest_bytes(_canonical_bytes(payload)),
        "resolutionInputCount": len(entries),
        "resolutionInputs": entries,
    }


def build_sync_manifest(
    *,
    repo_root: Path,
    snapshot: PubCacheSnapshot,
    flutter_identity: Mapping[str, str],
) -> dict[str, Any]:
    identity = {
        "flutterVersion": str(flutter_identity.get("flutterVersion") or ""),
        "flutterCommandResolutionDigest": str(
            flutter_identity.get("flutterCommandResolutionDigest")
            or flutter_identity.get("commandResolutionDigest")
            or ""
        ),
    }
    if not identity["flutterVersion"] or not identity[
        "flutterCommandResolutionDigest"
    ].startswith("sha256:"):
        raise ValueError("App dependency Flutter identity is incomplete")
    return {
        "schema": PUB_CACHE_SYNC_MANIFEST_SCHEMA,
        **identity,
        **resolution_input_identity(repo_root),
        "dependency": snapshot.manifest,
    }


def _validated_sync_manifest(
    *,
    repo_root: Path,
    manifest: Mapping[str, Any],
    expected_flutter: Mapping[str, str] | None,
) -> dict[str, Any]:
    value = dict(manifest)
    if set(value) != _SYNC_FIELDS:
        raise ValueError("App dependency sync snapshot fields mismatch")
    if value.get("schema") != PUB_CACHE_SYNC_MANIFEST_SCHEMA:
        raise ValueError("App dependency sync snapshot schema mismatch")
    resolution = resolution_input_identity(repo_root)
    for field in ("resolutionInputDigest", "resolutionInputCount", "resolutionInputs"):
        if value.get(field) != resolution[field]:
            raise ValueError("App dependency sync is stale for Pub resolution inputs")
    if expected_flutter is not None:
        for field in ("flutterVersion", "flutterCommandResolutionDigest"):
            if value.get(field) != expected_flutter.get(field):
                raise ValueError("App dependency sync is stale for Flutter toolchain")
    elif (
        not isinstance(value.get("flutterVersion"), str)
        or not str(value.get("flutterCommandResolutionDigest") or "").startswith(
            "sha256:"
        )
    ):
        raise ValueError("App dependency sync Flutter identity is invalid")
    if not isinstance(value.get("dependency"), Mapping):
        raise TypeError("App dependency sync dependency manifest is missing")
    return value


def load_pub_cache_snapshot_at(
    *,
    repo_root: Path,
    snapshot_root: Path,
    expected_flutter: Mapping[str, str] | None,
) -> PubCacheSnapshot:
    assert_real_directory(snapshot_root, label="managed snapshot root")
    manifest = _read_json_nofollow(
        snapshot_root / "manifest.json",
        label="sync snapshot manifest",
    )
    validated = _validated_sync_manifest(
        repo_root=repo_root,
        manifest=manifest,
        expected_flutter=expected_flutter,
    )
    snapshot = build_pub_cache_snapshot(
        lock_path=repo_root / "quwoquan_app/pubspec.lock",
        cache_root=snapshot_root / "pub",
        reject_unlocked=True,
    )
    if snapshot.manifest != dict(validated["dependency"]):
        raise ValueError("App dependency sync snapshot tree drifted")
    return replace(
        snapshot,
        sync_manifest=validated,
        encoded_sync_manifest=_canonical_bytes(validated),
    )


def load_managed_pub_cache_snapshot(*, repo_root: Path) -> PubCacheSnapshot:
    from .dependency_bundle import load_active_dependency_bundle

    flutter = current_flutter_identity()
    bundle = load_active_dependency_bundle(repo_root=repo_root)
    snapshot_root = bundle.component_root("productionPub")
    snapshot = load_pub_cache_snapshot_at(
        repo_root=repo_root,
        snapshot_root=snapshot_root,
        expected_flutter=flutter,
    )
    if snapshot.sync_manifest != bundle.component_manifest("productionPub"):
        raise ValueError("App dependency bundle production Pub manifest drifted")
    return snapshot


def snapshot_for_package_inputs(
    *, repo_root: Path, roots: Sequence[str]
) -> PubCacheSnapshot | None:
    if not dependency_required(repo_root, roots):
        return None
    return load_managed_pub_cache_snapshot(repo_root=repo_root)


def sync_manifest_bytes(snapshot: PubCacheSnapshot) -> bytes:
    if snapshot.encoded_sync_manifest is None:
        raise ValueError("App dependency sync manifest is not bound")
    return snapshot.encoded_sync_manifest


def capsule_dependency_snapshot(
    *,
    capsule_root: Path,
    manifest_entries: Sequence[Mapping[str, Any]],
) -> PubCacheSnapshot | None:
    matching = [
        item
        for item in manifest_entries
        if item.get("logicalPath") == PUB_CACHE_DEPENDENCY_LOGICAL_PATH
    ]
    repo_root = capsule_root / "repo"
    lock_path = repo_root / "quwoquan_app/pubspec.lock"
    if not lock_path.exists():
        if matching or (capsule_root / PUB_CACHE_DEPENDENCY_TREE).exists():
            raise ValueError("App dependency capsule exists without pubspec.lock")
        return None
    if len(matching) != 1:
        raise ValueError("App dependency capsule manifest entry is missing or duplicated")
    if matching[0].get("capsulePath") != PUB_CACHE_DEPENDENCY_MANIFEST.as_posix():
        raise ValueError("App dependency capsule manifest path drifted")
    manifest = _read_json_nofollow(
        capsule_root / PUB_CACHE_DEPENDENCY_MANIFEST,
        label="capsule dependency manifest",
    )
    validated = _validated_sync_manifest(
        repo_root=repo_root,
        manifest=manifest,
        expected_flutter=None,
    )
    snapshot = build_pub_cache_snapshot(
        lock_path=lock_path,
        cache_root=capsule_root / PUB_CACHE_DEPENDENCY_TREE,
        reject_unlocked=True,
    )
    if snapshot.manifest != dict(validated["dependency"]):
        raise ValueError("App dependency capsule tree drifted")
    return replace(
        snapshot,
        sync_manifest=validated,
        encoded_sync_manifest=_canonical_bytes(validated),
    )


def verify_snapshot_flutter_toolchain(snapshot: PubCacheSnapshot) -> None:
    manifest = snapshot.sync_manifest
    if manifest is None:
        raise ValueError("App dependency sync manifest is not bound")
    current = current_flutter_identity()
    for field in ("flutterVersion", "flutterCommandResolutionDigest"):
        if manifest.get(field) != current[field]:
            raise ValueError("App dependency capsule Flutter toolchain drifted")
