"""Exact, no-follow CocoaPods dependency closure for iOS App builds.

An explicit dependency-sync step owns network access.  It runs CocoaPods with
fresh private home/cache directories and then seals the resulting ``Pods``
tree plus those private inputs here.  Package/build executors only consume the
sealed bytes; the developer's global CocoaPods state is never a build input.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import ios_pod_identity as _ios_pod_identity
from .ios_pod_identity import (
    CocoaPodsIdentity,
    _canonical_bytes,
    _digest_bytes,
    _read_regular_nofollow,
    inspect_cocoapods_executable,
)
from .ios_pod_inputs import (
    IOS_NATIVE_DEPENDENCY_MODE,
    IOS_POD_DEPENDENCY_DIRECTORIES,
    IOS_POD_DEPENDENCY_LOGICAL_PATHS,
    IOS_POD_PRODUCTION_HOST,
    IOS_PODFILE_RELATIVES,
    validate_ios_pod_host,
)

IOS_POD_CAPSULE_SCHEMA = "stackctl-ios-pod-dependency-capsule.v2"
SUPPORTED_COCOAPODS_VERSION = _ios_pod_identity.SUPPORTED_COCOAPODS_VERSION
# Compatibility names are production-only.  New callers must select a host
# explicitly through IOS_POD_DEPENDENCY_*S.
IOS_POD_DEPENDENCY_LOGICAL_PATH = IOS_POD_DEPENDENCY_LOGICAL_PATHS[
    IOS_POD_PRODUCTION_HOST
]
IOS_POD_DEPENDENCY_DIRECTORY = IOS_POD_DEPENDENCY_DIRECTORIES[IOS_POD_PRODUCTION_HOST]
IOS_POD_MANIFEST_NAME = "manifest.json"
IOS_POD_LOCK_NAME = "Podfile.lock"
IOS_POD_COMPONENTS = ("pods", "home", "cache")


@dataclass(frozen=True, slots=True)
class IosPodNode:
    relative: str
    kind: str
    source: Path
    mode: int
    size: int
    sha256: str
    target: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative,
            "kind": self.kind,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class IosPodSnapshot:
    manifest: dict[str, Any]
    encoded_manifest: bytes
    lock_bytes: bytes
    nodes: tuple[IosPodNode, ...]
    cocoa_pods: CocoaPodsIdentity
    resolution_inputs: tuple[tuple[str, Path], ...]
    upstream_dependency_digest: str
    dependency_host: str


def _safe_component_root(path: Path, *, label: str) -> Path:
    root = path.expanduser().absolute()
    try:
        metadata = root.lstat()
    except OSError as error:
        raise ValueError(f"iOS Pod {label} root is unavailable") from error
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"iOS Pod {label} root is not a real directory")
    return root


def _resolution_input_identity(
    inputs: Mapping[str, Path],
    *,
    dependency_host: str,
) -> tuple[list[dict[str, Any]], str]:
    host = validate_ios_pod_host(dependency_host)
    expected_podfile = IOS_PODFILE_RELATIVES[host].as_posix()
    if expected_podfile not in inputs:
        raise ValueError("iOS Pod resolution inputs must include host Podfile")
    if not any(logical.endswith((".podspec", ".podspec.json")) for logical in inputs):
        raise ValueError("iOS Pod resolution inputs must include local podspecs")
    entries: list[dict[str, Any]] = []
    for logical, path in sorted(inputs.items()):
        normalized = PurePosixPath(logical)
        if (
            not logical
            or logical.startswith("/")
            or "\\" in logical
            or normalized.as_posix() != logical
            or any(part in {"", ".", ".."} for part in normalized.parts)
        ):
            raise ValueError("iOS Pod resolution input logical path is unsafe")
        content, mode = _read_regular_nofollow(
            path, label=f"resolution input {logical}"
        )
        entries.append(
            {
                "logicalPath": logical,
                "mode": mode,
                "size": len(content),
                "sha256": _digest_bytes(content),
            }
        )
    digest = _digest_bytes(
        _canonical_bytes({"schema": IOS_POD_CAPSULE_SCHEMA, "entries": entries})
    )
    return entries, digest


def _scan_component(component: str, root: Path) -> list[IosPodNode]:
    nodes: list[IosPodNode] = []
    directories: dict[Path, tuple[int, int, int, int]] = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative_inside = path.relative_to(root).as_posix()
        relative = f"{component}/{relative_inside}"
        if metadata.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise ValueError(f"iOS Pod tree contains special permissions: {relative}")
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            directories[path] = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_mtime_ns,
            )
            nodes.append(
                IosPodNode(relative, "directory", path, 0o555, 0, _digest_bytes(b""))
            )
            continue
        if stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            content, mode = _read_regular_nofollow(path, label=f"node {relative}")
            nodes.append(
                IosPodNode(
                    relative, "file", path, mode, len(content), _digest_bytes(content)
                )
            )
            continue
        if stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(path)
            after = path.lstat()
            if (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_size,
                metadata.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError(f"iOS Pod symlink changed during read: {relative}")
            encoded = os.fsencode(target)
            nodes.append(
                IosPodNode(
                    relative,
                    "symlink",
                    path,
                    0,
                    len(encoded),
                    _digest_bytes(encoded),
                    target,
                )
            )
            continue
        raise ValueError(f"iOS Pod tree contains a special node: {relative}")
    for path, expected in directories.items():
        current = path.lstat()
        if expected != (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_mtime_ns,
        ):
            raise ValueError("iOS Pod directory changed during scan")
    return nodes


def _lexical_target(link_path: str, raw_target: str) -> str:
    if not raw_target or "\x00" in raw_target or "\\" in raw_target:
        raise ValueError(f"iOS Pod symlink target is unsafe: {link_path}")
    target = PurePosixPath(raw_target)
    if target.is_absolute():
        raise ValueError(f"iOS Pod symlink escapes capsule: {link_path}")
    parts = list(PurePosixPath(link_path).parent.parts)
    for part in target.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"iOS Pod symlink escapes capsule: {link_path}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError(f"iOS Pod symlink target is unsafe: {link_path}")
    return PurePosixPath(*parts).as_posix()


def _validate_symlink_closure(nodes: list[IosPodNode]) -> None:
    by_path = {node.relative: node for node in nodes}
    for link in (node for node in nodes if node.kind == "symlink"):
        current = _lexical_target(link.relative, link.target or "")
        seen = {link.relative}
        for _ in range(len(nodes) + 1):
            parts = PurePosixPath(current).parts
            replacement: str | None = None
            for size in range(1, len(parts) + 1):
                prefix = PurePosixPath(*parts[:size]).as_posix()
                candidate = by_path.get(prefix)
                if candidate is None or candidate.kind != "symlink":
                    continue
                if prefix in seen:
                    raise ValueError(f"iOS Pod symlink cycle detected: {link.relative}")
                seen.add(prefix)
                target = _lexical_target(prefix, candidate.target or "")
                suffix = parts[size:]
                replacement = PurePosixPath(target, *suffix).as_posix()
                break
            if replacement is not None:
                current = replacement
                continue
            if current not in by_path:
                raise ValueError(f"iOS Pod symlink target is absent: {link.relative}")
            break
        else:
            raise ValueError(f"iOS Pod symlink cycle detected: {link.relative}")


def _build_snapshot(
    *,
    podfile_lock: Path,
    pods_root: Path,
    cp_home_dir: Path,
    cp_cache_dir: Path,
    cocoa_pods: CocoaPodsIdentity,
    resolution_inputs: Mapping[str, Path],
    upstream_dependency_digest: str,
    dependency_host: str = IOS_POD_PRODUCTION_HOST,
) -> IosPodSnapshot:
    host = validate_ios_pod_host(dependency_host)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", upstream_dependency_digest):
        raise ValueError("iOS Pod upstream dependency digest is invalid")
    resolution_entries, resolution_digest = _resolution_input_identity(
        resolution_inputs,
        dependency_host=host,
    )
    lock_bytes, _lock_mode = _read_regular_nofollow(podfile_lock, label="Podfile.lock")
    roots = {
        "pods": _safe_component_root(pods_root, label="Pods"),
        "home": _safe_component_root(cp_home_dir, label="CP_HOME_DIR"),
        "cache": _safe_component_root(cp_cache_dir, label="CP_CACHE_DIR"),
    }
    resolved_roots = [root.resolve() for root in roots.values()]
    for index, root in enumerate(resolved_roots):
        for other in resolved_roots[index + 1 :]:
            if (
                root == other
                or root.is_relative_to(other)
                or other.is_relative_to(root)
            ):
                raise ValueError("iOS Pod private dependency roots overlap")
    manifest_lock, _manifest_mode = _read_regular_nofollow(
        roots["pods"] / "Manifest.lock", label="Pods/Manifest.lock"
    )
    if manifest_lock != lock_bytes:
        raise ValueError("iOS Pod Podfile.lock and Pods/Manifest.lock drifted")
    nodes: list[IosPodNode] = []
    for component in IOS_POD_COMPONENTS:
        nodes.extend(_scan_component(component, roots[component]))
    nodes.sort(key=lambda item: item.relative)
    if not nodes or len({item.relative for item in nodes}) != len(nodes):
        raise ValueError("iOS Pod dependency tree is empty or duplicated")
    _validate_symlink_closure(nodes)
    entries = [node.as_dict() for node in nodes]
    tree_digest = _digest_bytes(
        _canonical_bytes({"schema": IOS_POD_CAPSULE_SCHEMA, "entries": entries})
    )
    manifest = {
        "schema": IOS_POD_CAPSULE_SCHEMA,
        "dependencyHost": host,
        "nativeDependencyMode": IOS_NATIVE_DEPENDENCY_MODE,
        "podfileLockDigest": _digest_bytes(lock_bytes),
        "upstreamDependencyDigest": upstream_dependency_digest,
        "resolutionInputDigest": resolution_digest,
        "resolutionInputCount": len(resolution_entries),
        "resolutionInputs": resolution_entries,
        "cocoaPods": cocoa_pods.as_dict(),
        "components": list(IOS_POD_COMPONENTS),
        "entryCount": len(entries),
        "treeDigest": tree_digest,
        "entries": entries,
    }
    return IosPodSnapshot(
        manifest=manifest,
        encoded_manifest=_canonical_bytes(manifest),
        lock_bytes=lock_bytes,
        nodes=tuple(nodes),
        cocoa_pods=cocoa_pods,
        resolution_inputs=tuple(sorted(resolution_inputs.items())),
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=host,
    )


def build_verified_ios_pod_snapshot(
    *,
    podfile_lock: Path,
    pods_root: Path,
    cp_home_dir: Path,
    cp_cache_dir: Path,
    pod_executable: str | Path,
    resolution_inputs: Mapping[str, Path],
    upstream_dependency_digest: str,
    dependency_host: str = IOS_POD_PRODUCTION_HOST,
) -> IosPodSnapshot:
    """Build a CAS only after verifying the live CocoaPods command identity."""

    return _build_snapshot(
        podfile_lock=podfile_lock,
        pods_root=pods_root,
        cp_home_dir=cp_home_dir,
        cp_cache_dir=cp_cache_dir,
        cocoa_pods=inspect_cocoapods_executable(pod_executable),
        resolution_inputs=resolution_inputs,
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=dependency_host,
    )
