"""Immutable hosted-Pub dependency input for App build projections.

The developer's global Pub cache is deliberately never a package input.  An
explicit sync command creates a pristine managed snapshot below QWQ_OUTPUT_ROOT;
runtime/App packaging copies that snapshot into the read-only input capsule and
the launch executor then copies it into its private writable projection.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml

from .dependency_fs import (
    _directory_fd,
    assert_real_directory,
    clone_fresh_relative_file,
    read_regular_nofollow,
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


def _stable_node_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_scanned_file(
    *,
    parent_fd: int,
    name: str,
    label: str,
    digest: bool,
    capture: bool = False,
) -> tuple[int, int, str | None, bytes | None]:
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parent_fd,
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"App dependency {label} is not a single-link regular file")
        hasher = hashlib.sha256() if digest else None
        captured = bytearray() if capture else None
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if hasher is not None:
                hasher.update(chunk)
            if captured is not None:
                captured.extend(chunk)
        after = os.fstat(descriptor)
        if _stable_node_identity(before) != _stable_node_identity(after):
            raise ValueError(f"App dependency {label} changed during read")
    finally:
        os.close(descriptor)
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    return (
        mode,
        size,
        _DIGEST_PREFIX + hasher.hexdigest() if hasher is not None else None,
        bytes(captured) if captured is not None else None,
    )


def _scan_pub_cache_tree(
    *,
    cache: Path,
    packages: Sequence[Mapping[str, str]],
    admitted_extra: Callable[[str, bool], bool],
) -> tuple[list[PubCacheFile], set[str]]:
    """Scan, classify and hash one sealed cache with descriptor-relative IO."""

    package_roots: dict[str, Mapping[str, str]] = {}
    hash_paths: dict[str, Mapping[str, str]] = {}
    required_directories = {"hosted", "hosted-hashes"}
    for package in packages:
        package_segment = f"{package['name']}-{package['version']}"
        package_root = f"hosted/{package['host']}/{package_segment}"
        hash_path = f"hosted-hashes/{package['host']}/{package_segment}.sha256"
        package_roots[package_root] = package
        hash_paths[hash_path] = package
        required_directories.update(
            {
                f"hosted/{package['host']}",
                package_root,
                f"hosted-hashes/{package['host']}",
            }
        )

    files: list[PubCacheFile] = []
    directories: set[str] = set()
    payload_counts = {relative: 0 for relative in package_roots}

    def package_for(relative: str) -> tuple[str, Mapping[str, str]] | None:
        parts = PurePosixPath(relative).parts
        if len(parts) <= 3 or parts[0] != "hosted":
            return None
        package_root = PurePosixPath(*parts[:3]).as_posix()
        package = package_roots.get(package_root)
        return (package_root, package) if package is not None else None

    def scan_directory(descriptor: int, relative_parent: PurePosixPath) -> None:
        before = os.fstat(descriptor)
        with os.scandir(descriptor) as entries:
            ordered = sorted(entries, key=lambda item: item.name)
        for entry in ordered:
            relative_path = relative_parent / entry.name
            relative = relative_path.as_posix()
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                locked_package = package_for(relative)
                expected = (
                    relative in required_directories or locked_package is not None
                )
                if not expected and not admitted_extra(relative, True):
                    raise ValueError(f"undeclared dependency directory {relative}")
                child = os.open(
                    entry.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
                try:
                    if expected:
                        if locked_package is not None:
                            suffix = PurePosixPath(relative).relative_to(
                                PurePosixPath(locked_package[0])
                            )
                            if any(
                                part in _FORBIDDEN_CACHE_SEGMENTS
                                for part in suffix.parts
                            ):
                                raise ValueError(
                                    "App dependency managed cache contains build output: "
                                    f"{relative}"
                                )
                        directories.add(relative)
                    scan_directory(child, relative_path)
                finally:
                    os.close(child)
                continue

            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"unsafe dependency node {relative}")
            locked_package = package_for(relative)
            expected_hash = hash_paths.get(relative)
            if locked_package is None and expected_hash is None:
                try:
                    _read_scanned_file(
                        parent_fd=descriptor,
                        name=entry.name,
                        label=f"sealed cache file {relative}",
                        digest=False,
                    )
                except OSError as error:
                    raise ValueError(
                        f"App dependency sealed cache file {relative} "
                        "is unavailable or linked"
                    ) from error
                if not admitted_extra(relative, False):
                    raise ValueError(f"undeclared dependency file {relative}")
                continue

            if locked_package is not None:
                package_root, _package = locked_package
                suffix = PurePosixPath(relative).relative_to(
                    PurePosixPath(package_root)
                )
                if any(part in _FORBIDDEN_CACHE_SEGMENTS for part in suffix.parts):
                    raise ValueError(
                        "App dependency managed cache contains build output: "
                        f"{relative}"
                    )
            try:
                mode, size, sha256, content = _read_scanned_file(
                    parent_fd=descriptor,
                    name=entry.name,
                    label=f"sealed cache file {relative}",
                    digest=True,
                    capture=expected_hash is not None,
                )
            except OSError as error:
                raise ValueError(
                    f"App dependency sealed cache file {relative} "
                    "is unavailable or linked"
                ) from error
            if expected_hash is not None:
                try:
                    archive_sha = (content or b"").decode(
                        "ascii", errors="strict"
                    ).strip()
                except UnicodeError as error:
                    raise ValueError(
                        f"App dependency archive hash drifted: {relative}"
                    ) from error
                if archive_sha != expected_hash["archiveSha256"]:
                    raise ValueError(
                        f"App dependency archive hash drifted: {relative}"
                    )
            else:
                payload_counts[locked_package[0]] += 1
            files.append(
                PubCacheFile(
                    relative=relative,
                    source=cache / Path(*relative_path.parts),
                    mode=mode,
                    size=size,
                    sha256=str(sha256),
                )
            )
        after = os.fstat(descriptor)
        if _stable_node_identity(before) != _stable_node_identity(after):
            label = relative_parent.as_posix() if relative_parent.parts else "."
            raise ValueError(
                f"App dependency cache directory changed during scan: {label}"
            )

    root_fd = _directory_fd(cache, label="cache root")
    try:
        scan_directory(root_fd, PurePosixPath())
    finally:
        os.close(root_fd)
    missing_directories = required_directories - directories
    missing_hashes = set(hash_paths) - {item.relative for item in files}
    empty_packages = {
        relative for relative, count in payload_counts.items() if count == 0
    }
    if missing_directories or missing_hashes or empty_packages:
        raise ValueError("App dependency locked cache closure is incomplete")
    files.sort(key=lambda item: item.relative)
    return files, directories


def build_pub_cache_snapshot(
    *,
    lock_path: Path,
    cache_root: Path,
    reject_unlocked: bool = False,
    admitted_extra: Callable[[str, bool], bool] | None = None,
) -> PubCacheSnapshot:
    """Hash the exact locked hosted package trees from one private cache."""

    if reject_unlocked and admitted_extra is not None:
        raise ValueError("App dependency unlocked-node policies conflict")
    lock_encoded, lock_digest, packages = _lock_model(lock_path)
    del lock_encoded
    cache = cache_root.expanduser().absolute()
    assert_real_directory(cache, label="cache root")
    if reject_unlocked or admitted_extra is not None:
        files, directories = _scan_pub_cache_tree(
            cache=cache,
            packages=packages,
            admitted_extra=admitted_extra or (lambda _relative, _directory: False),
        )
    else:
        files = []
        directories = set()
        for package in packages:
            package_files, package_directories = _package_files(cache, package)
            files.extend(package_files)
            directories.update(package_directories)
        files.sort(key=lambda item: item.relative)
        if len({item.relative for item in files}) != len(files):
            raise ValueError("App dependency cache paths are duplicated")
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
    clone_fresh_relative_file(
        root=destination_root,
        relative=source.relative,
        source=source.source,
        mode=(0o755 if source.mode & 0o111 else 0o644) if writable else source.mode,
        expected_size=source.size,
    )


def _normalize_writable_clone_tree(
    *,
    destination: Path,
    snapshot: PubCacheSnapshot,
) -> None:
    expected_files = {item.relative: item for item in snapshot.files}
    expected_directories = set(snapshot.directories)
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    root_metadata = destination.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        raise ValueError("App dependency cloned cache root is unsafe")
    destination.chmod(0o700, follow_symlinks=False)
    for parent, directory_names, file_names in os.walk(
        destination,
        topdown=True,
        followlinks=False,
    ):
        parent_path = Path(parent)
        for name in directory_names:
            path = parent_path / name
            relative = path.relative_to(destination).as_posix()
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ValueError(
                    f"App dependency cloned cache directory is unsafe: {relative}"
                )
            if relative not in expected_directories:
                raise ValueError(
                    f"App dependency cloned cache contains extra directory: {relative}"
                )
            path.chmod(0o700, follow_symlinks=False)
            actual_directories.add(relative)
        for name in file_names:
            path = parent_path / name
            relative = path.relative_to(destination).as_posix()
            metadata = path.lstat()
            expected = expected_files.get(relative)
            if (
                expected is None
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size != expected.size
            ):
                raise ValueError(
                    f"App dependency cloned cache file is unsafe: {relative}"
                )
            path.chmod(
                0o755 if expected.mode & 0o111 else 0o644,
                follow_symlinks=False,
            )
            actual_files.add(relative)
    if actual_files != set(expected_files) or actual_directories != expected_directories:
        raise ValueError("App dependency cloned cache closure drifted")


def _clone_writable_snapshot_tree_darwin(
    *,
    snapshot: PubCacheSnapshot,
    destination: Path,
) -> None:
    source = snapshot.cache_root.expanduser().absolute()
    assert_real_directory(source, label="writable clone source root")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_real_directory(
        destination.parent, label="writable clone destination parent"
    )
    command = ["/bin/cp", "-cRP", str(source), str(destination)]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            raise OSError(
                "App dependency writable cache clone failed"
                + (f": {detail}" if detail else "")
            )
        _normalize_writable_clone_tree(
            destination=destination,
            snapshot=snapshot,
        )
    except BaseException:
        if destination.exists() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise


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
    if writable and sys.platform == "darwin":
        _clone_writable_snapshot_tree_darwin(
            snapshot=snapshot,
            destination=destination,
        )
    else:
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
    try:
        rebuilt = build_pub_cache_snapshot(
            lock_path=lock_path,
            cache_root=destination,
            reject_unlocked=True,
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(
            f"App dependency snapshot copy CAS drifted: {error}"
        ) from error
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
