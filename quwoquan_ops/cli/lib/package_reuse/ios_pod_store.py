"""Immutable storage and copy helpers for an :mod:`ios_pod_capsule` CAS."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

from .ios_pod_capsule import (
    IOS_POD_CAPSULE_SCHEMA,
    IOS_POD_COMPONENTS,
    IOS_POD_LOCK_NAME,
    IOS_POD_MANIFEST_NAME,
    SUPPORTED_COCOAPODS_VERSION,
    CocoaPodsIdentity,
    IosPodNode,
    IosPodSnapshot,
    _build_snapshot,
    _canonical_bytes,
    _digest_bytes,
    _read_regular_nofollow,
    _scan_component,
    _validate_symlink_closure,
    inspect_cocoapods_executable,
)
from .ios_pod_inputs import IOS_POD_PRODUCTION_HOST, validate_ios_pod_host


def _write_exclusive(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("iOS Pod capsule copy made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(mode)


def _copy_file(node: IosPodNode, destination: Path, *, writable: bool) -> None:
    content, source_mode = _read_regular_nofollow(
        node.source, label=f"snapshot node {node.relative}"
    )
    if (
        source_mode != node.mode
        or len(content) != node.size
        or _digest_bytes(content) != node.sha256
    ):
        raise ValueError("iOS Pod snapshot changed during copy")
    mode = 0o755 if writable and node.mode & 0o111 else 0o644 if writable else node.mode
    _write_exclusive(destination, content, mode=mode)


def _copy_symlink(node: IosPodNode, destination: Path) -> None:
    before = node.source.lstat()
    if not stat.S_ISLNK(before.st_mode):
        raise ValueError("iOS Pod snapshot symlink changed during copy")
    target = os.readlink(node.source)
    after = node.source.lstat()
    encoded = os.fsencode(target)
    if (
        target != node.target
        or len(encoded) != node.size
        or _digest_bytes(encoded) != node.sha256
        or (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
        != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
    ):
        raise ValueError("iOS Pod snapshot symlink changed during copy")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, destination)


def _seal_directories(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    root.chmod(0o555)


def copy_ios_pod_component(
    snapshot: IosPodSnapshot,
    *,
    component: str,
    destination: Path,
    writable: bool,
) -> Path:
    """Copy one CAS component without hardlinks and verify its exact node set."""

    if component not in IOS_POD_COMPONENTS:
        raise ValueError("iOS Pod capsule component is unsupported")
    target = destination.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("iOS Pod component destination must be fresh")
    target.mkdir(parents=True, mode=0o700)
    prefix = f"{component}/"
    selected = [node for node in snapshot.nodes if node.relative.startswith(prefix)]
    for node in selected:
        if node.kind != "directory":
            continue
        (target / node.relative.removeprefix(prefix)).mkdir(
            parents=True, exist_ok=False, mode=0o700
        )
    for node in selected:
        relative = node.relative.removeprefix(prefix)
        destination_node = target / relative
        if node.kind == "file":
            _copy_file(node, destination_node, writable=writable)
        elif node.kind == "symlink":
            _copy_symlink(node, destination_node)
    copied = _scan_component(component, target)
    copied.sort(key=lambda item: item.relative)
    _validate_symlink_closure(copied)
    if [node.as_dict() for node in copied] != [node.as_dict() for node in selected]:
        raise ValueError("iOS Pod component copy CAS drifted")
    if not writable:
        _seal_directories(target)
    return target


def write_ios_pod_capsule(snapshot: IosPodSnapshot, destination: Path) -> Path:
    """Write a fresh read-only CAS.  The caller owns atomic publication."""

    target = destination.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("iOS Pod capsule destination must be fresh")
    target.mkdir(parents=True, mode=0o700)
    _write_exclusive(target / IOS_POD_LOCK_NAME, snapshot.lock_bytes, mode=0o444)
    for component in IOS_POD_COMPONENTS:
        copy_ios_pod_component(
            snapshot,
            component=component,
            destination=target / component,
            writable=False,
        )
    rebuilt = _build_snapshot(
        podfile_lock=target / IOS_POD_LOCK_NAME,
        pods_root=target / "pods",
        cp_home_dir=target / "home",
        cp_cache_dir=target / "cache",
        cocoa_pods=snapshot.cocoa_pods,
        resolution_inputs=dict(snapshot.resolution_inputs),
        upstream_dependency_digest=snapshot.upstream_dependency_digest,
        dependency_host=snapshot.dependency_host,
    )
    if rebuilt.manifest != snapshot.manifest:
        raise ValueError("iOS Pod written capsule CAS drifted")
    _write_exclusive(
        target / IOS_POD_MANIFEST_NAME,
        snapshot.encoded_manifest,
        mode=0o444,
    )
    _seal_directories(target)
    return target


def _load_declared_manifest(snapshot_root: Path) -> dict[str, object]:
    encoded, _mode = _read_regular_nofollow(
        snapshot_root / IOS_POD_MANIFEST_NAME,
        label="capsule manifest",
    )
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("iOS Pod capsule manifest is invalid") from error
    if not isinstance(value, dict):
        raise TypeError("iOS Pod capsule manifest is not an object")
    if encoded != _canonical_bytes(value):
        raise ValueError("iOS Pod capsule manifest is not canonical")
    return value


def _declared_cocoapods_identity(
    manifest: Mapping[str, object],
) -> CocoaPodsIdentity:
    raw = manifest.get("cocoaPods")
    if not isinstance(raw, Mapping) or set(raw) != {
        "version",
        "executableDigest",
        "runtimeEnvironmentDigest",
        "commandResolutionDigest",
    }:
        raise ValueError("iOS Pod capsule CocoaPods identity fields mismatch")
    version = str(raw.get("version") or "")
    executable_digest = str(raw.get("executableDigest") or "")
    runtime_environment_digest = str(raw.get("runtimeEnvironmentDigest") or "")
    command_digest = str(raw.get("commandResolutionDigest") or "")
    if (
        version != SUPPORTED_COCOAPODS_VERSION
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", executable_digest)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_environment_digest)
        or command_digest
        != _digest_bytes(
            _canonical_bytes(
                {
                    "version": version,
                    "executableDigest": executable_digest,
                    "runtimeEnvironmentDigest": runtime_environment_digest,
                }
            )
        )
    ):
        raise ValueError("iOS Pod capsule CocoaPods identity is invalid")
    return CocoaPodsIdentity(
        executable=None,
        version=version,
        executable_digest=executable_digest,
        runtime_environment_digest=runtime_environment_digest,
        command_resolution_digest=command_digest,
    )


def _assert_sealed_snapshot_root(root: Path) -> None:
    for path in (root, *sorted(root.rglob("*"))):
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise ValueError(f"iOS Pod capsule has special permissions: {relative}")
        if stat.S_ISLNK(metadata.st_mode):
            continue
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ValueError(f"iOS Pod capsule contains a special node: {relative}")
        if metadata.st_mode & 0o222:
            raise ValueError(f"iOS Pod capsule contains writable bytes: {relative}")


def load_ios_pod_capsule_bytes(
    *,
    snapshot_root: Path,
    expected_podfile_lock: Path,
    resolution_inputs: Mapping[str, Path],
    upstream_dependency_digest: str,
    dependency_host: str = IOS_POD_PRODUCTION_HOST,
) -> IosPodSnapshot:
    """Verify sealed bytes and domain identities without reading a host tool."""

    host = validate_ios_pod_host(dependency_host)
    root = snapshot_root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("iOS Pod capsule root is not a real directory")
    actual_top_level = {path.name for path in root.iterdir()}
    expected_top_level = {
        IOS_POD_MANIFEST_NAME,
        IOS_POD_LOCK_NAME,
        *IOS_POD_COMPONENTS,
    }
    if actual_top_level != expected_top_level:
        raise ValueError("iOS Pod capsule contains undeclared top-level bytes")
    _assert_sealed_snapshot_root(root)
    declared = _load_declared_manifest(root)
    if (
        declared.get("schema") != IOS_POD_CAPSULE_SCHEMA
        or declared.get("dependencyHost") != host
    ):
        raise ValueError("iOS Pod capsule schema or dependency host drifted")
    rebuilt = _build_snapshot(
        podfile_lock=root / IOS_POD_LOCK_NAME,
        pods_root=root / "pods",
        cp_home_dir=root / "home",
        cp_cache_dir=root / "cache",
        cocoa_pods=_declared_cocoapods_identity(declared),
        resolution_inputs=resolution_inputs,
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=host,
    )
    if rebuilt.manifest != declared:
        raise ValueError("iOS Pod capsule tree or resolution input identity drifted")
    expected_lock, _expected_mode = _read_regular_nofollow(
        expected_podfile_lock, label="current Podfile.lock"
    )
    if expected_lock != rebuilt.lock_bytes:
        raise ValueError("iOS Pod capsule is stale for current Podfile.lock")
    return rebuilt


def load_verified_ios_pod_capsule(
    *,
    snapshot_root: Path,
    expected_podfile_lock: Path,
    pod_executable: str | Path,
    resolution_inputs: Mapping[str, Path],
    upstream_dependency_digest: str,
    dependency_host: str = IOS_POD_PRODUCTION_HOST,
) -> IosPodSnapshot:
    """Additionally bind the current CocoaPods executable at projection time."""

    snapshot = load_ios_pod_capsule_bytes(
        snapshot_root=snapshot_root,
        expected_podfile_lock=expected_podfile_lock,
        resolution_inputs=resolution_inputs,
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=dependency_host,
    )
    identity = inspect_cocoapods_executable(pod_executable)
    if identity.as_dict() != snapshot.cocoa_pods.as_dict():
        raise ValueError("iOS Pod capsule CocoaPods tool identity drifted")
    return _build_snapshot(
        podfile_lock=snapshot_root / IOS_POD_LOCK_NAME,
        pods_root=snapshot_root / "pods",
        cp_home_dir=snapshot_root / "home",
        cp_cache_dir=snapshot_root / "cache",
        cocoa_pods=identity,
        resolution_inputs=resolution_inputs,
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=dependency_host,
    )
