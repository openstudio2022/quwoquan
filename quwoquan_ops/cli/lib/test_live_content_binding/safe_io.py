"""test-live content binding 的 symlink-safe 读取与 create-once 写入原语。

原单文件 ``test_live_content_binding.py`` 拆分出的文件系统子模块。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .constants import UnsafeTestLiveContentBindingPath


@dataclass(frozen=True)
class _RegularJson:
    value: dict[str, Any]
    digest: str
    identity: tuple[int, int, int, int, int]


def _file_digest(encoded: bytes) -> str:
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("test-live content binding requires O_NOFOLLOW/O_DIRECTORY")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags(*, create: bool = False) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("test-live content binding requires O_NOFOLLOW")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
    return flags | nofollow | getattr(os, "O_CLOEXEC", 0)


def _open_directory_chain(path: Path, *, label: str) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = path.expanduser().absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise UnsafeTestLiveContentBindingPath(f"{label} parent path is unsafe")
    descriptor = os.open(Path(absolute.anchor), _directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        root = os.fstat(descriptor)
        identities.append((root.st_dev, root.st_ino))
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=descriptor)
            except OSError as exc:
                raise UnsafeTestLiveContentBindingPath(
                    f"{label} parent is a symlink, missing, or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_directory_chain(
    path: Path,
    *,
    label: str,
    identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, observed = _open_directory_chain(path, label=label)
    os.close(descriptor)
    if observed != identities:
        raise UnsafeTestLiveContentBindingPath(f"{label} parent changed during access")


def _regular_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_regular_json(path: Path, *, label: str, optional: bool = False) -> _RegularJson | None:
    try:
        parent_descriptor, parent_identities = _open_directory_chain(
            path.parent,
            label=label,
        )
    except UnsafeTestLiveContentBindingPath:
        if optional and not path.parent.exists():
            return None
        raise
    descriptor = -1
    try:
        try:
            before = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if optional:
                return None
            raise ValueError(f"{label} is missing")
        if not stat.S_ISREG(before.st_mode):
            raise UnsafeTestLiveContentBindingPath(
                f"{label} is a symlink or non-regular file"
            )
        try:
            descriptor = os.open(path.name, _file_flags(), dir_fd=parent_descriptor)
        except OSError as exc:
            raise UnsafeTestLiveContentBindingPath(
                f"{label} is a symlink or unreadable"
            ) from exc
        opened = os.fstat(descriptor)
        identity = _regular_identity(opened)
        if not stat.S_ISREG(opened.st_mode) or identity != _regular_identity(before):
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if _regular_identity(after_fd) != identity:
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
        encoded = b"".join(chunks)
        _revalidate_directory_chain(
            path.parent,
            label=label,
            identities=parent_identities,
        )
        after = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(after.st_mode) or _regular_identity(after) != identity:
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
    except FileNotFoundError as exc:
        raise UnsafeTestLiveContentBindingPath(f"{label} changed during access") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _RegularJson(dict(value), _file_digest(encoded), identity)


def _create_once(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    parent_descriptor, parent_identities = _open_directory_chain(
        path.parent,
        label="test-live content binding",
    )
    temporary = f".{path.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        descriptor = os.open(
            temporary,
            _file_flags(create=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _revalidate_directory_chain(
            path.parent,
            label="test-live content binding",
            identities=parent_identities,
        )
        try:
            os.link(
                temporary,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            raise
        else:
            os.fsync(parent_descriptor)
        finally:
            os.unlink(temporary, dir_fd=parent_descriptor)
            temporary_exists = False
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)
