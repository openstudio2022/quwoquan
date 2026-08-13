"""package fingerprint 的 symlink-safe 原子持久化（逐字迁自原单文件）。

``fingerprint_path`` 经包属性（``_pkg.``）消费 ``app_deployment_package_dir``，
保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import uuid4

import quwoquan_ops.cli.lib.package_reuse as _pkg

from .constants import FINGERPRINT_NAME


class _UnsafeFingerprintPath(ValueError):
    pass


def _fingerprint_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError(
            "package fingerprint persistence requires O_NOFOLLOW/O_DIRECTORY"
        )
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _fingerprint_file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("package fingerprint persistence requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _absolute_fingerprint_path(path: Path) -> Path:
    expanded = path.expanduser()
    candidate = expanded if expanded.is_absolute() else Path.cwd() / expanded
    normalized = Path(os.path.abspath(candidate))
    if len(normalized.parts) > 1 and normalized.parts[1] in {"tmp", "var"}:
        remainder = normalized.parts[2:]
        alias = Path(normalized.anchor) / normalized.parts[1]
        if alias.is_symlink():
            target = os.readlink(alias)
            expected = f"private/{normalized.parts[1]}"
            if target != expected:
                raise _UnsafeFingerprintPath(
                    f"package fingerprint system path alias is unsafe: {alias}"
                )
            normalized = (Path(normalized.anchor) / target).joinpath(*remainder)
    if not normalized.is_absolute() or not normalized.name:
        raise _UnsafeFingerprintPath("package fingerprint path is unsafe")
    return normalized


def _open_fingerprint_parent(
    path: Path,
    *,
    create: bool,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = _absolute_fingerprint_path(path)
    descriptor = os.open(absolute.anchor, _fingerprint_directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        for part in absolute.parent.parts[1:]:
            try:
                child = os.open(
                    part,
                    _fingerprint_directory_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(
                        part,
                        _fingerprint_directory_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise _UnsafeFingerprintPath(
                        f"package fingerprint parent is unsafe: {part}"
                    ) from exc
            except OSError as exc:
                raise _UnsafeFingerprintPath(
                    f"package fingerprint parent is a symlink or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeFingerprintPath(
                    f"package fingerprint parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_fingerprint_parent(
    path: Path,
    *,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_fingerprint_parent(path, create=False)
    os.close(descriptor)
    if identities != expected:
        raise _UnsafeFingerprintPath(
            "package fingerprint parent changed during persistence"
        )


def _fingerprint_entry_info(
    parent_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _UnsafeFingerprintPath(
            f"package fingerprint entry is unsafe: {name}"
        ) from exc


def _atomic_write_fingerprint(path: Path, encoded: bytes) -> None:
    absolute = _absolute_fingerprint_path(path)
    parent_descriptor, identities = _open_fingerprint_parent(
        absolute,
        create=True,
    )
    predictable_temporary = f".{absolute.name}.tmp"
    temporary = f".{absolute.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    expected_identity: tuple[int, int] | None = None
    try:
        if _fingerprint_entry_info(parent_descriptor, predictable_temporary) is not None:
            raise _UnsafeFingerprintPath(
                "package fingerprint predictable temporary path is occupied"
            )
        current = _fingerprint_entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint final path is a symlink or non-regular file"
            )
        descriptor = os.open(
            temporary,
            _fingerprint_file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("package fingerprint temporary write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint temporary path is not a regular file"
            )
        expected_identity = (info.st_dev, info.st_ino)
        os.close(descriptor)
        descriptor = -1

        _revalidate_fingerprint_parent(absolute, expected=identities)
        if _fingerprint_entry_info(parent_descriptor, predictable_temporary) is not None:
            raise _UnsafeFingerprintPath(
                "package fingerprint predictable temporary path is occupied"
            )
        current = _fingerprint_entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint final path is a symlink or non-regular file"
            )
        os.replace(
            temporary,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_exists = False
        os.fsync(parent_descriptor)
        _revalidate_fingerprint_parent(absolute, expected=identities)
        final_descriptor = os.open(
            absolute.name,
            _fingerprint_file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        try:
            final_info = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_info.st_mode)
                or expected_identity != (final_info.st_dev, final_info.st_ino)
            ):
                raise _UnsafeFingerprintPath(
                    "package fingerprint changed after atomic write"
                )
        finally:
            os.close(final_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def fingerprint_path(env_name: str, target_name: str) -> Path:
    return _pkg.app_deployment_package_dir(env_name, target=target_name) / FINGERPRINT_NAME
