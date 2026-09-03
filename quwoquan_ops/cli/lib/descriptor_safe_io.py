"""Descriptor-relative fail-closed repository file reads."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _regular_file_open_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def _validate_regular_single_link(
    descriptor: int, *, display_path: str
) -> os.stat_result:
    """Require one inode-bound fd to name an unlinked-safe immutable file."""

    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError(errno.EINVAL, f"{display_path} 不是 regular file")
    if metadata.st_nlink != 1:
        raise OSError(
            errno.EMLINK,
            f"{display_path} link count 必须为 1，实际为 {metadata.st_nlink}",
        )
    return metadata


def read_regular_single_link_at(
    directory_fd: int,
    name: str,
    *,
    display_path: str | None = None,
    require_current_name: bool = False,
) -> bytes:
    """Read one descriptor-bound inode; optionally require its name to stay bound."""

    descriptor = os.open(name, _regular_file_open_flags(), dir_fd=directory_fd)
    label = display_path or name
    try:
        _validate_regular_single_link(descriptor, display_path=label)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if require_current_name:
            opened = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                opened.st_dev != current.st_dev
                or opened.st_ino != current.st_ino
                or opened.st_nlink != 1
                or current.st_nlink != 1
            ):
                raise OSError(errno.ESTALE, f"{label} 目录项身份漂移")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_repo_relative_regular_single_link(
    repo_root: Path,
    relative_path: str,
    *,
    expected_directory_parts: tuple[str, ...] | None = None,
) -> bytes:
    """Walk from the actual repo root fd and read one exact relative file."""

    parts = Path(relative_path).parts
    if not parts or parts[-1] in ("", ".", ".."):
        raise ValueError(f"repository-relative path 组件无效：{relative_path}")
    if (
        expected_directory_parts is not None
        and parts[:-1] != expected_directory_parts
    ):
        raise ValueError(f"repository-relative path 目录不匹配：{relative_path}")
    if any(component in ("", ".", "..") for component in parts):
        raise ValueError(f"repository-relative path 组件无效：{relative_path}")

    directory_fd: int | None = os.open(repo_root, _directory_open_flags())
    try:
        for component in parts[:-1]:
            child_fd = os.open(
                component, _directory_open_flags(), dir_fd=directory_fd
            )
            os.close(directory_fd)
            directory_fd = child_fd
        return read_regular_single_link_at(
            directory_fd, parts[-1], display_path=relative_path
        )
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
