"""startup receipt 的 symlink-safe 读写与 staged 原子提交原语（逐字搬移）。

``_secure_read`` / ``_commit_staged_receipt`` 是测试的 patch 锚点，
包内消费一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg


class _UnsafeStartupReceiptPath(ValueError):
    pass


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError(
            "startup receipt persistence requires O_NOFOLLOW/O_DIRECTORY"
        )
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("startup receipt persistence requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _absolute_path(path: Path) -> Path:
    expanded = path.expanduser()
    candidate = expanded if expanded.is_absolute() else Path.cwd() / expanded
    normalized = Path(os.path.abspath(candidate))
    if not normalized.is_absolute() or not normalized.name:
        raise _UnsafeStartupReceiptPath("startup receipt path is unsafe")
    return normalized


def _open_parent(
    path: Path,
    *,
    create: bool,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = _absolute_path(path)
    descriptor = os.open(absolute.anchor, _directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        for part in absolute.parent.parts[1:]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(part, _directory_flags(), dir_fd=descriptor)
                except OSError as exc:
                    raise _UnsafeStartupReceiptPath(
                        f"startup receipt parent is unsafe: {part}"
                    ) from exc
            except OSError as exc:
                raise _UnsafeStartupReceiptPath(
                    f"startup receipt parent is a symlink or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeStartupReceiptPath(
                    f"startup receipt parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_parent(
    path: Path,
    *,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_parent(path, create=False)
    os.close(descriptor)
    if identities != expected:
        raise _UnsafeStartupReceiptPath(
            "startup receipt parent changed during persistence"
        )


def _entry_info(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _UnsafeStartupReceiptPath(
            f"startup receipt final path is unsafe: {name}"
        ) from exc


def _secure_read(
    path: Path,
    *,
    label: str = "startup attempt receipt",
) -> bytes | None:
    absolute = _absolute_path(path)
    try:
        parent_descriptor, identities = _open_parent(absolute, create=False)
    except FileNotFoundError:
        return None
    descriptor = -1
    try:
        before = _entry_info(parent_descriptor, absolute.name)
        if before is None:
            return None
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeStartupReceiptPath(
                f"{label} is a symlink or non-regular file"
            )
        try:
            descriptor = os.open(
                absolute.name,
                _file_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeStartupReceiptPath(
                f"{label} is a symlink or unreadable"
            ) from exc
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise _UnsafeStartupReceiptPath(
                f"{label} changed during validation"
            )
        _revalidate_parent(absolute, expected=identities)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


@dataclass(frozen=True)
class _StagedReceiptWrite:
    path: Path
    temporary_name: str
    temporary_identity: tuple[int, int]
    parent_identities: tuple[tuple[int, int], ...]


def _encode_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _stage_receipt_bytes(path: Path, encoded: bytes) -> _StagedReceiptWrite:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    temporary = f".{absolute.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        descriptor = os.open(
            temporary,
            _file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("startup receipt temporary write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt temporary path is not a regular file"
            )
        expected_identity = (info.st_dev, info.st_ino)
        os.close(descriptor)
        descriptor = -1
        _revalidate_parent(absolute, expected=identities)
        staged = _StagedReceiptWrite(
            path=absolute,
            temporary_name=temporary,
            temporary_identity=expected_identity,
            parent_identities=identities,
        )
        temporary_exists = False
        return staged
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _commit_staged_receipt(staged: _StagedReceiptWrite) -> None:
    absolute = staged.path
    parent_descriptor, identities = _open_parent(absolute, create=False)
    try:
        if identities != staged.parent_identities:
            raise _UnsafeStartupReceiptPath(
                "startup receipt parent changed before commit"
            )
        temporary = _entry_info(parent_descriptor, staged.temporary_name)
        if (
            temporary is None
            or not stat.S_ISREG(temporary.st_mode)
            or (temporary.st_dev, temporary.st_ino) != staged.temporary_identity
        ):
            raise _UnsafeStartupReceiptPath(
                "startup receipt staged entry changed before commit"
            )
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        os.replace(
            staged.temporary_name,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
        final_descriptor = os.open(
            absolute.name,
            _file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        try:
            final_info = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_info.st_mode)
                or (final_info.st_dev, final_info.st_ino)
                != staged.temporary_identity
            ):
                raise _UnsafeStartupReceiptPath(
                    "startup attempt receipt changed after atomic write"
                )
        finally:
            os.close(final_descriptor)
    finally:
        os.close(parent_descriptor)


def _discard_staged_receipt(staged: _StagedReceiptWrite) -> None:
    try:
        parent_descriptor, identities = _open_parent(staged.path, create=False)
    except FileNotFoundError:
        return
    try:
        if identities != staged.parent_identities:
            return
        temporary = _entry_info(parent_descriptor, staged.temporary_name)
        if temporary is None:
            return
        if (
            stat.S_ISREG(temporary.st_mode)
            and (temporary.st_dev, temporary.st_ino) == staged.temporary_identity
        ):
            os.unlink(staged.temporary_name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _atomic_write_bytes(path: Path, encoded: bytes) -> None:
    staged = _stage_receipt_bytes(path, encoded)
    try:
        _pkg._commit_staged_receipt(staged)
    finally:
        _discard_staged_receipt(staged)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(path, _encode_json(payload))


def _prevalidate_write_path(path: Path) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    try:
        current = _entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup attempt receipt final path is a symlink or non-regular file"
            )
        _revalidate_parent(absolute, expected=identities)
    finally:
        os.close(parent_descriptor)


def _secure_unlink_if_matches(path: Path, expected: bytes) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=False)
    descriptor = -1
    try:
        before = _entry_info(parent_descriptor, absolute.name)
        if before is None or not stat.S_ISREG(before.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry is missing or unsafe"
            )
        descriptor = os.open(
            absolute.name,
            _file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry changed during validation"
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            actual = handle.read()
        if actual != expected:
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry content drifted"
            )
        _revalidate_parent(absolute, expected=identities)
        current = _entry_info(parent_descriptor, absolute.name)
        if (
            current is None
            or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise _UnsafeStartupReceiptPath(
                "startup receipt transaction entry changed before removal"
            )
        os.unlink(absolute.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _write_transaction_journal_exclusive(path: Path, encoded: bytes) -> None:
    absolute = _absolute_path(path)
    parent_descriptor, identities = _open_parent(absolute, create=True)
    descriptor = -1
    created_identity: tuple[int, int] | None = None
    completed = False
    try:
        if _entry_info(parent_descriptor, absolute.name) is not None:
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal already exists"
            )
        descriptor = os.open(
            absolute.name,
            _file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal is not a regular file"
            )
        created_identity = (info.st_dev, info.st_ino)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("startup fan-out journal write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.fsync(parent_descriptor)
        _revalidate_parent(absolute, expected=identities)
        current = _entry_info(parent_descriptor, absolute.name)
        if (
            current is None
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != created_identity
        ):
            raise _UnsafeStartupReceiptPath(
                "startup fan-out transaction journal changed after creation"
            )
        completed = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed and created_identity is not None:
            current = _entry_info(parent_descriptor, absolute.name)
            if (
                current is not None
                and (current.st_dev, current.st_ino) == created_identity
            ):
                os.unlink(absolute.name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
        os.close(parent_descriptor)
