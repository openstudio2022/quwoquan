"""Strict path identity checks for immutable App UAT source projections."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar


class SourceProjectionRootError(ValueError):
    """The declared source projection root is not one exact real directory."""


_LoadedEvidence = TypeVar("_LoadedEvidence")


@dataclass(frozen=True, slots=True)
class _OpenedNode:
    descriptor: int
    parent_descriptor: int | None
    name: str
    identity: tuple[int, int, int, int, int, int, int]


def _stat_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def canonical_source_projection_root(value: Any) -> Path:
    """Return an exact absolute projection root without normalizing caller bytes.

    The launch projection is a signed JSON identity.  Accepting a relative,
    dot-normalized, or symlinked spelling would make the checked directory differ
    from the directory named by those bytes.
    """

    if not isinstance(value, str) or not value:
        raise SourceProjectionRootError("source projection root is invalid")
    pure = PurePosixPath(value)
    if (
        not pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise SourceProjectionRootError("source projection root is not canonical")

    root = Path(value)
    current = Path(root.anchor)
    try:
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise SourceProjectionRootError("source projection anchor is invalid")
        for part in root.parts[1:]:
            current = current / part
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise SourceProjectionRootError("source projection path is linked")
            if not stat.S_ISDIR(metadata.st_mode):
                raise SourceProjectionRootError(
                    "source projection path is not a directory"
                )
        if root.resolve(strict=True) != root:
            raise SourceProjectionRootError("source projection root is not exact")
    except OSError as error:
        raise SourceProjectionRootError(
            "source projection root is unavailable"
        ) from error
    return root


def _directory_fds_nofollow(path: Path, *, label: str) -> list[_OpenedNode]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("App UAT dependency evidence requires no-follow IO")
    descriptor = os.open(path.anchor, os.O_RDONLY | directory)
    opened = [
        _OpenedNode(
            descriptor=descriptor,
            parent_descriptor=None,
            name=path.anchor,
            identity=_stat_identity(os.fstat(descriptor)),
        )
    ]
    try:
        for segment in path.parts[1:]:
            next_descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            opened.append(
                _OpenedNode(
                    descriptor=next_descriptor,
                    parent_descriptor=descriptor,
                    name=segment,
                    identity=_stat_identity(os.fstat(next_descriptor)),
                )
            )
            descriptor = next_descriptor
        return opened
    except OSError as error:
        for node in reversed(opened):
            os.close(node.descriptor)
        raise ValueError(f"{label} is unavailable or linked") from error


def _assert_opened_nodes_stable(nodes: list[_OpenedNode], *, label: str) -> None:
    for node in nodes:
        if _stat_identity(os.fstat(node.descriptor)) != node.identity:
            raise ValueError(f"{label} changed during read")
        if node.parent_descriptor is None:
            continue
        named = os.stat(
            node.name,
            dir_fd=node.parent_descriptor,
            follow_symlinks=False,
        )
        if _stat_identity(named) != node.identity:
            raise ValueError(f"{label} path changed during read")


def _canonical_evidence_ref(
    value: Any,
    *,
    projection_root: Path,
    output_root: Path,
    label: str,
) -> tuple[Path, Path]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} is not a canonical POSIX path")
    pure = PurePosixPath(value)
    segments = value.split("/")
    if (
        not pure.is_absolute()
        or pure.as_posix() != value
        or not segments
        or segments[0] != ""
        or any(segment in {"", ".", ".."} for segment in segments[1:])
    ):
        raise ValueError(f"{label} is not a canonical POSIX path")
    candidate = Path(value)
    try:
        projection_root.relative_to(output_root)
        relative = candidate.relative_to(projection_root)
    except ValueError as error:
        raise ValueError(
            f"{label} escapes the current dependency projection"
        ) from error
    if not relative.parts:
        raise ValueError(f"{label} does not name an evidence file")
    return candidate, relative


def _load_canonical_projection_evidence(
    value: Any,
    *,
    projection_root: Path,
    output_root: Path,
    label: str,
    loader: Callable[[Path, bytes, int], _LoadedEvidence],
) -> _LoadedEvidence:
    candidate, relative = _canonical_evidence_ref(
        value,
        projection_root=projection_root,
        output_root=output_root,
        label=label,
    )

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_nodes = _directory_fds_nofollow(
        projection_root,
        label="dependency projection root",
    )
    descriptor = root_nodes[-1].descriptor
    opened: list[_OpenedNode] = []
    file_descriptor: int | None = None
    loaded: _LoadedEvidence | None = None
    try:
        for segment in relative.parts[:-1]:
            parent_descriptor = descriptor
            descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            opened.append(
                _OpenedNode(
                    descriptor=descriptor,
                    parent_descriptor=parent_descriptor,
                    name=segment,
                    identity=_stat_identity(os.fstat(descriptor)),
                )
            )
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=descriptor,
        )
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"{label} is not a single-link regular file")
        chunks: list[bytes] = []
        while chunk := os.read(file_descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(file_descriptor)
        if _stat_identity(before) != _stat_identity(after):
            raise ValueError(f"{label} changed during read")
        named_file = os.stat(
            relative.parts[-1],
            dir_fd=descriptor,
            follow_symlinks=False,
        )
        if _stat_identity(named_file) != _stat_identity(before):
            raise ValueError(f"{label} path changed during read")
        _assert_opened_nodes_stable(root_nodes + opened, label=label)
        loaded = loader(candidate, b"".join(chunks), stat.S_IMODE(before.st_mode))
        if _stat_identity(os.fstat(file_descriptor)) != _stat_identity(before):
            raise ValueError(f"{label} changed during load")
        named_file = os.stat(
            relative.parts[-1],
            dir_fd=descriptor,
            follow_symlinks=False,
        )
        if _stat_identity(named_file) != _stat_identity(before):
            raise ValueError(f"{label} path changed during load")
        _assert_opened_nodes_stable(root_nodes + opened, label=label)
    except OSError as error:
        raise ValueError(f"{label} is unavailable or linked") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for node in reversed(opened):
            os.close(node.descriptor)
        for node in reversed(root_nodes):
            os.close(node.descriptor)
    if loaded is None:
        raise AssertionError("canonical evidence loader did not return")
    return loaded


def canonical_projection_evidence_path(
    value: Any,
    *,
    projection_root: Path,
    output_root: Path,
    label: str,
) -> Path:
    """Validate one evidence path and its stable no-follow file transaction."""

    return _load_canonical_projection_evidence(
        value,
        projection_root=projection_root,
        output_root=output_root,
        label=label,
        loader=lambda path, _encoded, _mode: path,
    )


def load_canonical_projection_evidence(
    value: Any,
    *,
    projection_root: Path,
    output_root: Path,
    label: str,
    loader: Callable[[Path, bytes, int], _LoadedEvidence],
) -> _LoadedEvidence:
    """Read stable no-follow bytes and invoke the canonical loader before close."""

    return _load_canonical_projection_evidence(
        value,
        projection_root=projection_root,
        output_root=output_root,
        label=label,
        loader=loader,
    )
