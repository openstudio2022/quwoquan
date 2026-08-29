"""Immutable hosted-Pub dependency input for App build projections.

The developer's global Pub cache is deliberately never a package input.  An
explicit sync command creates a pristine managed snapshot below QWQ_OUTPUT_ROOT;
runtime/App packaging copies that snapshot into the read-only input capsule and
the launch executor then copies it into its private writable projection.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml

from .dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)

PUB_CACHE_DEPENDENCY_SCHEMA = "stackctl-dart-pub-cache-dependency.v2"
PUB_CACHE_DEPENDENCY_LOGICAL_PATH = "dependency:dart-pub-cache-v2"
PUB_CACHE_DEPENDENCY_MANIFEST = Path(
    "dependencies/dart-pub-cache-manifest.json"
)
PUB_CACHE_DEPENDENCY_TREE = Path("dependencies/dart-pub-cache")
PUB_CACHE_PROJECTION_RELATIVE = Path("quwoquan_app/.dart_tool/qwq_pub_cache")
PUB_CACHE_ACTIVE_SCHEMA = "stackctl-app-dependency-sync-active.v1"
PUB_CACHE_SYNC_MANIFEST_SCHEMA = "stackctl-app-dependency-sync-snapshot.v1"

_DIGEST_PREFIX = "sha256:"
_PACKAGE_NAME = re.compile(r"^[a-z0-9_]+$")
_VERSION = re.compile(r"^[0-9A-Za-z.+_-]+$")
_HOST = re.compile(r"^[a-z0-9.-]+$")
_FORBIDDEN_CACHE_SEGMENTS = frozenset({".cxx", ".gradle", ".kotlin"})


@dataclass(frozen=True, slots=True)
class PubCacheFile:
    relative: str
    source: Path
    mode: int
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PubCacheSnapshot:
    manifest: dict[str, Any]
    encoded_manifest: bytes
    files: tuple[PubCacheFile, ...]
    directories: tuple[str, ...]
    cache_root: Path
    sync_manifest: dict[str, Any] | None = None
    encoded_sync_manifest: bytes | None = None


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _lock_model(lock_path: Path) -> tuple[bytes, str, list[dict[str, str]]]:
    encoded, _mode = read_regular_nofollow(lock_path, label="pubspec.lock")
    try:
        payload = yaml.safe_load(encoded)
    except yaml.YAMLError as exc:
        raise ValueError("App dependency pubspec.lock is invalid") from exc
    packages = payload.get("packages") if isinstance(payload, Mapping) else None
    if not isinstance(packages, Mapping) or not packages:
        raise ValueError("App dependency pubspec.lock package set is invalid")
    hosted: list[dict[str, str]] = []
    for key, raw in sorted(packages.items()):
        if not isinstance(key, str) or not isinstance(raw, Mapping):
            raise TypeError("App dependency pubspec.lock entry is invalid")
        source = str(raw.get("source") or "")
        if source not in {"hosted", "path", "sdk"}:
            raise ValueError(
                f"App dependency source is unsupported for {key}: {source}"
            )
        if source != "hosted":
            continue
        description = raw.get("description")
        version = str(raw.get("version") or "")
        if not isinstance(description, Mapping):
            raise TypeError(f"App dependency hosted description is invalid: {key}")
        name = str(description.get("name") or "")
        archive_sha = str(description.get("sha256") or "")
        url = str(description.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            key != name
            or not _PACKAGE_NAME.fullmatch(name)
            or not _VERSION.fullmatch(version)
            or len(archive_sha) != 64
            or any(character not in "0123456789abcdef" for character in archive_sha)
            or parsed.scheme != "https"
            or not _HOST.fullmatch(host)
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"App dependency hosted identity is invalid: {key}")
        hosted.append(
            {
                "name": name,
                "version": version,
                "archiveSha256": archive_sha,
                "url": url.rstrip("/"),
                "host": host,
            }
        )
    if not hosted:
        raise ValueError("App dependency hosted package set is empty")
    return encoded, _digest_bytes(encoded), hosted


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("App dependency cache path is unsafe")
    return value


def _package_files(
    cache_root: Path,
    package: Mapping[str, str],
) -> tuple[list[PubCacheFile], set[str]]:
    host = package["host"]
    package_segment = f"{package['name']}-{package['version']}"
    package_root = cache_root / "hosted" / host / package_segment
    assert_real_directory(
        cache_root / "hosted", label="hosted cache directory"
    )
    assert_real_directory(
        cache_root / "hosted" / host, label=f"hosted cache {host}"
    )
    assert_real_directory(package_root, label=f"package {package_segment}")
    files: list[PubCacheFile] = []
    directories = {
        "hosted",
        f"hosted/{host}",
        f"hosted/{host}/{package_segment}",
        "hosted-hashes",
        f"hosted-hashes/{host}",
    }
    for path in sorted(package_root.rglob("*")):
        relative_inside = path.relative_to(package_root)
        if any(part in _FORBIDDEN_CACHE_SEGMENTS for part in relative_inside.parts):
            raise ValueError(
                f"App dependency managed cache contains build output: "
                f"{package_segment}/{relative_inside.as_posix()}"
            )
        if path.is_dir() and not path.is_symlink():
            assert_real_directory(
                path,
                label=f"package directory {package_segment}/{relative_inside}",
            )
            directories.add(
                _safe_relative(
                    f"hosted/{host}/{package_segment}/"
                    f"{relative_inside.as_posix()}"
                )
            )
            continue
        content, mode = read_regular_nofollow(
            path,
            label=f"package file {package_segment}/{relative_inside.as_posix()}",
        )
        relative = _safe_relative(
            f"hosted/{host}/{package_segment}/{relative_inside.as_posix()}"
        )
        files.append(
            PubCacheFile(
                relative=relative,
                source=path,
                mode=mode,
                size=len(content),
                sha256=_digest_bytes(content),
            )
        )
    if not files:
        raise ValueError(f"App dependency package is empty: {package_segment}")
    assert_real_directory(
        cache_root / "hosted-hashes", label="hosted hash directory"
    )
    assert_real_directory(
        cache_root / "hosted-hashes" / host,
        label=f"hosted hash cache {host}",
    )
    hash_path = cache_root / "hosted-hashes" / host / f"{package_segment}.sha256"
    hash_content, hash_mode = read_regular_nofollow(
        hash_path,
        label=f"archive hash {package_segment}",
    )
    if hash_content.decode("ascii", errors="strict").strip() != package["archiveSha256"]:
        raise ValueError(f"App dependency archive hash drifted: {package_segment}")
    hash_relative = _safe_relative(
        f"hosted-hashes/{host}/{package_segment}.sha256"
    )
    files.append(
        PubCacheFile(
            relative=hash_relative,
            source=hash_path,
            mode=hash_mode,
            size=len(hash_content),
            sha256=_digest_bytes(hash_content),
        )
    )
    return files, directories


def build_pub_cache_snapshot(
    *,
    lock_path: Path,
    cache_root: Path,
    reject_unlocked: bool = False,
) -> PubCacheSnapshot:
    """Hash the exact locked hosted package trees from one private cache."""

    lock_encoded, lock_digest, packages = _lock_model(lock_path)
    del lock_encoded
    cache = cache_root.expanduser().absolute()
    assert_real_directory(cache, label="cache root")
    files: list[PubCacheFile] = []
    directories: set[str] = set()
    for package in packages:
        package_files, package_directories = _package_files(cache, package)
        files.extend(package_files)
        directories.update(package_directories)
    files.sort(key=lambda item: item.relative)
    if len({item.relative for item in files}) != len(files):
        raise ValueError("App dependency cache paths are duplicated")
    if reject_unlocked:
        expected_paths = {item.relative for item in files}
        expected_directories = set(directories)
        actual_paths: set[str] = set()
        actual_directories: set[str] = set()
        for path in cache.rglob("*"):
            relative = path.relative_to(cache).as_posix()
            if path.is_dir() and not path.is_symlink():
                assert_real_directory(path, label=f"sealed cache directory {relative}")
                actual_directories.add(relative)
                continue
            read_regular_nofollow(path, label=f"sealed cache file {relative}")
            actual_paths.add(relative)
        if (
            actual_paths != expected_paths
            or actual_directories != expected_directories
        ):
            raise ValueError("App dependency sealed cache contains unlocked bytes")
    entry_values = [item.as_dict() for item in files]
    directory_values = sorted(directories)
    tree_digest = _digest_bytes(
        _canonical_bytes(
            {
                "schema": PUB_CACHE_DEPENDENCY_SCHEMA,
                "directories": directory_values,
                "entries": entry_values,
            }
        )
    )
    manifest = {
        "schema": PUB_CACHE_DEPENDENCY_SCHEMA,
        "lockDigest": lock_digest,
        "hostedPackages": [
            {
                "name": item["name"],
                "version": item["version"],
                "archiveSha256": item["archiveSha256"],
                "url": item["url"],
            }
            for item in packages
        ],
        "entryCount": len(entry_values),
        "directoryCount": len(directory_values),
        "treeDigest": tree_digest,
        "directories": directory_values,
        "entries": entry_values,
    }
    encoded = _canonical_bytes(manifest)
    return PubCacheSnapshot(
        manifest=manifest,
        encoded_manifest=encoded,
        files=tuple(files),
        directories=tuple(directory_values),
        cache_root=cache,
    )


def dependency_required(repo_root: Path, roots: Sequence[str]) -> bool:
    normalized = {str(value).strip().rstrip("/") for value in roots}
    return (
        "quwoquan_app" in normalized
        and (repo_root / "quwoquan_app/pubspec.lock").is_file()
    )


def _copy_snapshot_file(
    source: PubCacheFile,
    destination_root: Path,
    *,
    writable: bool,
) -> None:
    content, normalized_mode = read_regular_nofollow(
        source.source,
        label=f"snapshot file {source.relative}",
    )
    if (
        normalized_mode != source.mode
        or len(content) != source.size
        or _digest_bytes(content) != source.sha256
    ):
        raise ValueError("App dependency snapshot changed during copy")
    write_fresh_relative_file(
        root=destination_root,
        relative=source.relative,
        content=content,
        mode=(0o755 if source.mode & 0o111 else 0o644) if writable else source.mode,
    )


def copy_snapshot_tree_with_lock(
    snapshot: PubCacheSnapshot,
    destination: Path,
    *,
    lock_path: Path,
    writable: bool,
) -> None:
    """Copy then verify against an explicit lock (avoids path inference)."""

    if destination.exists() or destination.is_symlink():
        raise ValueError("App dependency snapshot destination must be fresh")
    destination.mkdir(parents=True, mode=0o700)
    for relative in sorted(
        snapshot.directories,
        key=lambda value: (len(PurePosixPath(value).parts), value),
    ):
        target = destination / Path(*PurePosixPath(relative).parts)
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        assert_real_directory(target, label=f"snapshot directory {relative}")
    for item in snapshot.files:
        _copy_snapshot_file(item, destination, writable=writable)
    rebuilt = build_pub_cache_snapshot(
        lock_path=lock_path,
        cache_root=destination,
        reject_unlocked=True,
    )
    if rebuilt.manifest != snapshot.manifest:
        raise ValueError("App dependency snapshot copy CAS drifted")
    if not writable:
        for directory in sorted(
            (path for path in destination.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o555)
        destination.chmod(0o555)
