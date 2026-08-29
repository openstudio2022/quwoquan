"""Strict path identity checks for immutable App UAT source projections."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


class SourceProjectionRootError(ValueError):
    """The declared source projection root is not one exact real directory."""


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


def _directory_fd_nofollow(path: Path, *, label: str) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("App UAT dependency evidence requires no-follow IO")
    descriptor = os.open(path.anchor, os.O_RDONLY | directory)
    try:
        for segment in path.parts[1:]:
            next_descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError as error:
        os.close(descriptor)
        raise ValueError(f"{label} is unavailable or linked") from error


def canonical_projection_evidence_path(
    value: Any,
    *,
    projection_root: Path,
    output_root: Path,
    label: str,
) -> Path:
    """Open one canonical absolute evidence ref through the projection root fd.

    Launch reports currently carry absolute POSIX refs.  Their literal spelling
    is part of the receipt identity: normalization, a linked component, or an
    output-root escape is therefore a typed-invalid receipt, even when ``Path``
    could resolve it to the expected bytes.
    """

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

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_fd = _directory_fd_nofollow(
        projection_root,
        label="dependency projection root",
    )
    descriptor = root_fd
    opened: list[int] = []
    file_descriptor: int | None = None
    try:
        for segment in relative.parts[:-1]:
            descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            opened.append(descriptor)
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=descriptor,
        )
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"{label} is not a single-link regular file")
        while os.read(file_descriptor, 1024 * 1024):
            pass
        after = os.fstat(file_descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_nlink,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise ValueError(f"{label} changed during read")
    except OSError as error:
        raise ValueError(f"{label} is unavailable or linked") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for opened_descriptor in reversed(opened):
            os.close(opened_descriptor)
        os.close(root_fd)
    return candidate
