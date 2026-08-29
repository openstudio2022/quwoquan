"""Fail-closed CAS seal for source plus admitted Flutter build outputs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_DIGEST_PREFIX = "sha256:"
_POLICY_SCHEMA = "quwoquan_ops.app_build_projection_policy.v1"
_SEAL_SCHEMA = "quwoquan_ops.app_build_projection_seal.v1"
_DERIVED_TREE_SCHEMA = "quwoquan_ops.app_build_projection_tree.v1"
_POLICY_RELATIVE_PATH = "quwoquan_ops/policies/app_build_projection_policy.json"
FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID = (
    "flutter-android-3.47-gradle-8.14-agp-8.11.1"
)
FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID = "flutter-ios-3.47-cocoapods-1.16.2"
_POLICY_FIELDS = {"toolchain", "exact", "subtrees", "reject"}
_NODE_KINDS = {"directory", "file", "symlink"}


@dataclass(frozen=True, slots=True)
class ProjectionBuildSeal:
    """Immutable identity for one fully inventoried writable build projection."""

    policy_id: str
    source_projection_digest: str
    source_entry_count: int
    derived_output_digest: str
    derived_output_policy_digest: str
    derived_entry_count: int
    build_projection_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": _SEAL_SCHEMA,
            "policyId": self.policy_id,
            "sourceProjectionDigest": self.source_projection_digest,
            "sourceEntryCount": self.source_entry_count,
            "derivedOutputDigest": self.derived_output_digest,
            "derivedOutputPolicyDigest": self.derived_output_policy_digest,
            "derivedEntryCount": self.derived_entry_count,
            "buildProjectionDigest": self.build_projection_digest,
        }


@dataclass(frozen=True, slots=True)
class _Policy:
    policy_id: str
    exact: tuple[tuple[str, tuple[str, ...]], ...]
    subtrees: tuple[str, ...]
    reject: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class _Node:
    path: str
    kind: str
    mode: int
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
        }


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _read_regular_nofollow(path: Path, *, label: str) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("App build projection seal requires O_NOFOLLOW")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ValueError(f"App build projection {label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"App build projection {label} is not a regular file")
        chunks = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
        )
        if identity(before) != identity(after):
            raise ValueError(f"App build projection {label} changed during read")
    finally:
        os.close(descriptor)
    return bytes(chunks)


def _safe_policy_path(value: object) -> str:
    raw = str(value or "")
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or path.as_posix() != raw
        or any(part in {"", ".", "..", ".git"} for part in path.parts)
    ):
        raise ValueError("App build projection policy path is unsafe")
    return raw


def _load_policy(policy_path: Path, policy_id: str) -> _Policy:
    raw = json.loads(
        _read_regular_nofollow(policy_path, label="policy").decode("utf-8")
    )
    if not isinstance(raw, Mapping) or set(raw) != {"schema", "policies"}:
        raise ValueError("App build projection policy fields mismatch")
    if raw.get("schema") != _POLICY_SCHEMA or not isinstance(
        raw.get("policies"), Mapping
    ):
        raise ValueError("App build projection policy schema mismatch")
    selected = raw["policies"].get(policy_id)
    if not isinstance(selected, Mapping) or set(selected) != _POLICY_FIELDS:
        raise ValueError("App build projection policy id is unknown")
    toolchain = selected.get("toolchain")
    if (
        not isinstance(toolchain, Mapping)
        or not {"flutter", "platform"}.issubset(toolchain)
        or any(
            not isinstance(key, str)
            or not key.isidentifier()
            or not isinstance(value, str)
            or not value
            for key, value in toolchain.items()
        )
    ):
        raise ValueError("App build projection policy toolchain is invalid")
    exact_raw = selected.get("exact")
    if not isinstance(exact_raw, Mapping):
        raise TypeError("App build projection exact policy is invalid")
    exact: list[tuple[str, tuple[str, ...]]] = []
    for raw_path, raw_kinds in exact_raw.items():
        path = _safe_policy_path(raw_path)
        if (
            not isinstance(raw_kinds, list)
            or not raw_kinds
            or any(kind not in _NODE_KINDS for kind in raw_kinds)
            or raw_kinds != sorted(set(raw_kinds))
        ):
            raise ValueError("App build projection exact kinds are invalid")
        exact.append((path, tuple(raw_kinds)))
    exact.sort()
    subtrees = _policy_path_list(selected.get("subtrees"), label="subtrees")
    reject = _policy_path_list(selected.get("reject"), label="reject")
    for admitted in [*(path for path, _kinds in exact), *subtrees]:
        if any(_under(admitted, denied) for denied in reject):
            raise ValueError("App build projection policy admit/reject overlap")
    projection = {
        "schema": _POLICY_SCHEMA,
        "policyId": policy_id,
        "policy": dict(selected),
    }
    return _Policy(
        policy_id=policy_id,
        exact=tuple(exact),
        subtrees=subtrees,
        reject=reject,
        digest=_canonical_digest(projection),
    )


def _policy_path_list(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"App build projection policy {label} are invalid")
    paths = tuple(_safe_policy_path(item) for item in value)
    if list(paths) != sorted(set(paths)):
        raise ValueError(f"App build projection policy {label} are not canonical")
    return paths


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _is_parent(path: str, child: str) -> bool:
    return child.startswith(path + "/")


def _read_regular_at(
    directory_descriptor: int,
    name: str,
    expected: os.stat_result,
) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_descriptor,
    )
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_mode) != (
            expected.st_dev,
            expected.st_ino,
            expected.st_mode,
        ):
            raise ValueError("App build projection node changed during inventory")
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("App build projection node changed during inventory")
    finally:
        os.close(descriptor)
    return bytes(content)


def _inventory(projection: Path) -> list[_Node]:
    root_metadata = projection.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or projection.is_symlink():
        raise ValueError("App build projection root must be a real directory")
    root = projection.resolve()
    nodes: list[_Node] = []

    def visit(directory: Path) -> None:
        descriptor = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            with os.scandir(descriptor) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
            for entry in entries:
                child = directory / entry.name
                relative = child.relative_to(root).as_posix()
                metadata = entry.stat(follow_symlinks=False)
                mode = stat.S_IMODE(metadata.st_mode)
                if stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        raise ValueError(
                            f"App build projection hardlink is forbidden: {relative}"
                        )
                    content = _read_regular_at(descriptor, entry.name, metadata)
                    kind, size = "file", len(content)
                elif stat.S_ISLNK(metadata.st_mode):
                    target = os.readlink(entry.name, dir_fd=descriptor)
                    try:
                        target_path = Path(target)
                        resolved = (
                            target_path
                            if target_path.is_absolute()
                            else child.parent / target_path
                        ).resolve(strict=True)
                    except OSError as exc:
                        raise ValueError(
                            f"App build projection symlink target is unavailable: {relative}"
                        ) from exc
                    if not resolved.is_relative_to(root):
                        raise ValueError(
                            f"App build projection symlink escapes build root: {relative}"
                        )
                    content = os.fsencode(target)
                    kind, size = "symlink", len(content)
                elif stat.S_ISDIR(metadata.st_mode):
                    content = b""
                    kind, size = "directory", 0
                else:
                    raise ValueError(
                        f"App build projection special node is forbidden: {relative}"
                    )
                nodes.append(
                    _Node(
                        path=relative,
                        kind=kind,
                        mode=mode,
                        size=size,
                        sha256=_DIGEST_PREFIX + hashlib.sha256(content).hexdigest(),
                    )
                )
                if kind == "directory":
                    visit(child)
        finally:
            os.close(descriptor)

    visit(root)
    return sorted(
        nodes,
        key=lambda node: (node.path, node.kind, node.mode, node.size, node.sha256),
    )


def _admit(policy: _Policy, node: _Node) -> None:
    if any(_under(node.path, denied) for denied in policy.reject):
        raise ValueError(
            f"App build projection derived output rejected by policy: {node.path}"
        )
    exact = dict(policy.exact)
    if node.path in exact:
        if node.kind not in exact[node.path]:
            raise ValueError(
                f"App build projection derived output kind rejected by policy: {node.path}"
            )
        return
    for subtree in policy.subtrees:
        if node.path == subtree:
            if node.kind != "directory":
                raise ValueError(
                    f"App build projection derived subtree root is not a directory: {node.path}"
                )
            return
        if _under(node.path, subtree):
            return
    policy_roots = [*exact, *policy.subtrees]
    if node.kind == "directory" and any(
        _is_parent(node.path, admitted) for admitted in policy_roots
    ):
        return
    raise ValueError(
        f"App build projection derived output rejected by policy: {node.path}"
    )


def _source_paths(entries: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    source = {
        Path(entry["repoRelative"]).as_posix(): str(entry["kind"]) for entry in entries
    }
    parents: set[str] = set()
    for path in source:
        parent = PurePosixPath(path).parent
        while parent.as_posix() != ".":
            parents.add(parent.as_posix())
            parent = parent.parent
    return source, parents


def _valid_digest(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX) or len(value) != 71:
        return False
    try:
        bytes.fromhex(value.removeprefix(_DIGEST_PREFIX))
    except ValueError:
        return False
    return True


def seal_projection_build(
    manifest_path: Path,
    projection_root: Path,
    *,
    policy_id: str,
    expected_build_projection_digest: str | None = None,
) -> ProjectionBuildSeal:
    """Inventory every node; source entries never inherit a derived-output rule."""

    from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch

    manifest_ref = Path(manifest_path).expanduser()
    if (
        manifest_ref.name != "manifest.json"
        or manifest_ref.is_symlink()
        or not manifest_ref.is_file()
    ):
        raise ValueError("App build projection source capsule manifest is invalid")
    manifest = launch.verify_package_input_capsule(manifest_ref.parent)
    entries = launch._projection_manifest_entries(
        manifest,
        capsule_root=manifest_ref.parent,
    )
    source, source_parents = _source_paths(entries)
    if source.get(_POLICY_RELATIVE_PATH) != "file":
        raise ValueError("App build projection source capsule lacks policy")
    projection = Path(projection_root).expanduser().absolute()
    source_digest, source_count = launch._projection_cas(
        manifest=manifest,
        capsule_root=manifest_ref.parent,
        projection_root=projection,
        reject_unmanifested=False,
    )
    policy = _load_policy(projection / _POLICY_RELATIVE_PATH, policy_id)
    inventory = _inventory(projection)
    indexed = {node.path: node for node in inventory}
    for path, kind in source.items():
        node = indexed.get(path)
        if node is None or node.kind != kind:
            raise ValueError("App build projection source inventory drifted")
    derived: list[_Node] = []
    for node in inventory:
        if node.path in source:
            continue
        if node.path in source_parents:
            if node.kind != "directory":
                raise ValueError("App build projection source parent kind drifted")
            continue
        _admit(policy, node)
        derived.append(node)
    final_source_digest, final_source_count = launch._projection_cas(
        manifest=manifest,
        capsule_root=manifest_ref.parent,
        projection_root=projection,
        reject_unmanifested=False,
    )
    if (source_digest, source_count) != (final_source_digest, final_source_count):
        raise ValueError("App build projection source CAS changed during inventory")
    if _inventory(projection) != inventory:
        raise ValueError("App build projection tree changed during inventory")
    derived_digest = _canonical_digest(
        {
            "schema": _DERIVED_TREE_SCHEMA,
            "entries": [node.as_dict() for node in derived],
        }
    )
    build_projection_digest = _canonical_digest(
        {
            "schema": _SEAL_SCHEMA,
            "sourceProjectionDigest": source_digest,
            "sourceEntryCount": source_count,
            "derivedOutputDigest": derived_digest,
            "derivedOutputPolicyDigest": policy.digest,
            "derivedEntryCount": len(derived),
        }
    )
    if expected_build_projection_digest is not None:
        if not _valid_digest(expected_build_projection_digest):
            raise ValueError("App build projection expected digest is invalid")
        if build_projection_digest != expected_build_projection_digest:
            raise ValueError("App build projection digest mismatch")
    return ProjectionBuildSeal(
        policy_id=policy.policy_id,
        source_projection_digest=source_digest,
        source_entry_count=source_count,
        derived_output_digest=derived_digest,
        derived_output_policy_digest=policy.digest,
        derived_entry_count=len(derived),
        build_projection_digest=build_projection_digest,
    )
