"""candidate 目录的原子写入与 staging 发布（逐字迁自原单文件）。

对 ``_revalidate_candidate_parent`` 的调用必须走包属性（``_pkg.``），
因为 local_contract 测试通过 ``mock.patch.object(包, "_revalidate_candidate_parent")``
拦截这些内部调用点。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import uuid4

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from .candidate_fs import (
    _UnsafeCandidatePath,
    _candidate_directory_flags,
    _candidate_file_flags,
    _candidate_relative_path,
    _open_candidate_file,
    _open_candidate_parent,
)


def _atomic_write_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    payload: bytes,
    *,
    label: str,
    expected_current: bytes | None = None,
) -> Path:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    temporary = f".{relative.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    expected_identity: tuple[int, int] | None = None
    try:
        try:
            current = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        if current is not None and expected_current is None:
            raise _UnsafeCandidatePath(f"{label} is immutable and already exists")
        if current is None and expected_current is not None:
            raise _UnsafeCandidatePath(f"{label} changed before update")
        current_snapshot = (
            (
                current.st_dev,
                current.st_ino,
                current.st_mode,
                current.st_size,
                current.st_mtime_ns,
                current.st_ctime_ns,
            )
            if current is not None
            else None
        )
        if expected_current is not None:
            current_descriptor = -1
            try:
                current_descriptor = os.open(
                    relative.name,
                    _candidate_file_flags(write=False),
                    dir_fd=parent_descriptor,
                )
                opened = os.fstat(current_descriptor)
                opened_snapshot = (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mode,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened_snapshot != current_snapshot
                ):
                    raise _UnsafeCandidatePath(f"{label} changed before update")
                with os.fdopen(current_descriptor, "rb") as handle:
                    current_descriptor = -1
                    if handle.read() != expected_current:
                        raise _UnsafeCandidatePath(
                            f"{label} content changed before update"
                        )
            finally:
                if current_descriptor >= 0:
                    os.close(current_descriptor)
        descriptor = os.open(
            temporary,
            _candidate_file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            info = os.fstat(handle.fileno())
            expected_identity = (info.st_dev, info.st_ino)
        _pkg._revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=identities,
        )
        try:
            latest = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            latest = None
        if latest is not None and not stat.S_ISREG(latest.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        latest_snapshot = (
            (
                latest.st_dev,
                latest.st_ino,
                latest.st_mode,
                latest.st_size,
                latest.st_mtime_ns,
                latest.st_ctime_ns,
            )
            if latest is not None
            else None
        )
        if latest_snapshot != current_snapshot:
            raise _UnsafeCandidatePath(f"{label} changed before activation")
        if expected_current is not None:
            latest_descriptor = -1
            try:
                latest_descriptor = os.open(
                    relative.name,
                    _candidate_file_flags(write=False),
                    dir_fd=parent_descriptor,
                )
                latest_opened = os.fstat(latest_descriptor)
                latest_opened_snapshot = (
                    latest_opened.st_dev,
                    latest_opened.st_ino,
                    latest_opened.st_mode,
                    latest_opened.st_size,
                    latest_opened.st_mtime_ns,
                    latest_opened.st_ctime_ns,
                )
                if latest_opened_snapshot != current_snapshot:
                    raise _UnsafeCandidatePath(
                        f"{label} changed before activation"
                    )
                with os.fdopen(latest_descriptor, "rb") as handle:
                    latest_descriptor = -1
                    if handle.read() != expected_current:
                        raise _UnsafeCandidatePath(
                            f"{label} content changed before activation"
                        )
            finally:
                if latest_descriptor >= 0:
                    os.close(latest_descriptor)
        if current_snapshot is None:
            try:
                os.link(
                    temporary,
                    relative.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} appeared before activation"
                ) from exc
            os.unlink(temporary, dir_fd=parent_descriptor)
            temporary_exists = False
        else:
            os.replace(
                temporary,
                relative.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            temporary_exists = False
        os.fsync(parent_descriptor)
        final_descriptor, final_parent, _relative, final_identities, final_identity = (
            _open_candidate_file(candidate_root, relative, label=label)
        )
        os.close(final_descriptor)
        os.close(final_parent)
        if final_identities != identities or final_identity != expected_identity:
            raise _UnsafeCandidatePath(f"{label} changed after rename")
        return candidate_root / relative
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _validate_open_candidate_tree(descriptor: int, *, label: str) -> None:
    """Reject links and special files anywhere in one runnable payload tree."""

    try:
        entries = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise _UnsafeCandidatePath(f"{label} is unreadable") from exc
    expected_entries: dict[str, tuple[int, int, int]] = {}
    for name in entries:
        try:
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise _UnsafeCandidatePath(
                f"{label} changed during traversal: {name}"
            ) from exc
        expected_entries[name] = (before.st_dev, before.st_ino, before.st_mode)
        if stat.S_ISREG(before.st_mode):
            file_descriptor = -1
            try:
                file_descriptor = os.open(
                    name,
                    _candidate_file_flags(write=False),
                    dir_fd=descriptor,
                )
                opened = os.fstat(file_descriptor)
                if not stat.S_ISREG(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (before.st_dev, before.st_ino):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} contains a symlink or unreadable file: {name}"
                ) from exc
            finally:
                if file_descriptor >= 0:
                    os.close(file_descriptor)
            continue
        if stat.S_ISDIR(before.st_mode):
            child_descriptor = -1
            try:
                child_descriptor = os.open(
                    name,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
                opened = os.fstat(child_descriptor)
                if not stat.S_ISDIR(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (before.st_dev, before.st_ino):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
                _validate_open_candidate_tree(
                    child_descriptor,
                    label=f"{label}/{name}",
                )
                after = os.fstat(child_descriptor)
                if (after.st_dev, after.st_ino) != (
                    opened.st_dev,
                    opened.st_ino,
                ):
                    raise _UnsafeCandidatePath(
                        f"{label} changed during traversal: {name}"
                    )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} contains a symlink or unreadable directory: {name}"
                ) from exc
            finally:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
            continue
        raise _UnsafeCandidatePath(
            f"{label} contains a symlink or non-regular payload: {name}"
        )
    try:
        if tuple(sorted(os.listdir(descriptor))) != entries:
            raise _UnsafeCandidatePath(f"{label} changed during traversal")
        for name, expected in expected_entries.items():
            after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (after.st_dev, after.st_ino, after.st_mode) != expected:
                raise _UnsafeCandidatePath(
                    f"{label} changed during traversal: {name}"
                )
    except OSError as exc:
        raise _UnsafeCandidatePath(f"{label} changed during traversal") from exc


def _validate_candidate_payload_tree(candidate_root: Path) -> None:
    relative = Path("packages/__candidate_payload_probe__")
    descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label="deployment candidate payload",
    )
    try:
        _validate_open_candidate_tree(
            descriptor,
            label="deployment candidate packages",
        )
        _pkg._revalidate_candidate_parent(
            candidate_root,
            relative,
            label="deployment candidate payload",
            expected_identities=identities,
        )
    finally:
        os.close(descriptor)


def _begin_candidate_directory_materialization(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> tuple[
    Path,
    int,
    tuple[tuple[int, int], ...],
    str,
    tuple[int, int],
]:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    temporary = f".{relative.name}.{uuid4().hex}.tmp"
    try:
        try:
            os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise _UnsafeCandidatePath(f"{label} already exists")
        os.mkdir(temporary, 0o700, dir_fd=parent_descriptor)
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        try:
            staging = os.fstat(staging_descriptor)
            staging_identity = (staging.st_dev, staging.st_ino)
        finally:
            os.close(staging_descriptor)
        return (
            relative,
            parent_descriptor,
            identities,
            temporary,
            staging_identity,
        )
    except Exception:
        os.close(parent_descriptor)
        raise


def _discard_candidate_staging_directory(
    parent_descriptor: int,
    temporary: str,
    *,
    expected_identity: tuple[int, int],
) -> None:
    """Best-effort cleanup that never traverses a replaced staging entry."""

    staging_descriptor = -1
    try:
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        info = os.fstat(staging_descriptor)
        if (info.st_dev, info.st_ino) != expected_identity:
            return
        for name in os.listdir(staging_descriptor):
            try:
                entry = os.stat(
                    name,
                    dir_fd=staging_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(entry.st_mode):
                continue
            try:
                os.unlink(name, dir_fd=staging_descriptor)
            except FileNotFoundError:
                pass
    except OSError:
        return
    finally:
        if staging_descriptor >= 0:
            os.close(staging_descriptor)
    try:
        os.rmdir(temporary, dir_fd=parent_descriptor)
    except OSError:
        pass


def _publish_candidate_staging_directory(
    candidate_root: Path,
    relative: Path,
    parent_descriptor: int,
    parent_identities: tuple[tuple[int, int], ...],
    temporary: str,
    staging_identity: tuple[int, int],
    *,
    label: str,
) -> None:
    staging_descriptor = -1
    final_descriptor = -1
    final_identity: tuple[int, int] | None = None
    published: dict[str, tuple[int, int]] = {}
    try:
        _pkg._revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        staging_descriptor = os.open(
            temporary,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        temporary_info = os.fstat(staging_descriptor)
        if (temporary_info.st_dev, temporary_info.st_ino) != staging_identity:
            raise _UnsafeCandidatePath(f"{label} staging directory changed")
        names = tuple(
            sorted(
                os.listdir(staging_descriptor),
                key=lambda name: (name == "manifest.json", name),
            )
        )
        staged_identities: dict[str, tuple[int, int]] = {}
        for name in names:
            item = os.stat(
                name,
                dir_fd=staging_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(item.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} staging payload is a symlink or non-regular file: "
                    f"{name}"
                )
            staged_identities[name] = (item.st_dev, item.st_ino)
        try:
            os.mkdir(relative.name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError as exc:
            raise _UnsafeCandidatePath(
                f"{label} appeared before activation"
            ) from exc
        final_descriptor = os.open(
            relative.name,
            _candidate_directory_flags(),
            dir_fd=parent_descriptor,
        )
        final_info = os.fstat(final_descriptor)
        final_identity = (final_info.st_dev, final_info.st_ino)
        _pkg._revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        for name in names:
            try:
                os.link(
                    name,
                    name,
                    src_dir_fd=staging_descriptor,
                    dst_dir_fd=final_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} payload appeared before activation: {name}"
                ) from exc
            final_item = os.stat(
                name,
                dir_fd=final_descriptor,
                follow_symlinks=False,
            )
            identity = (final_item.st_dev, final_item.st_ino)
            if not stat.S_ISREG(final_item.st_mode) or identity != (
                staged_identities[name]
            ):
                raise _UnsafeCandidatePath(
                    f"{label} payload changed during activation: {name}"
                )
            published[name] = identity
            os.unlink(name, dir_fd=staging_descriptor)
        os.fsync(final_descriptor)
        if tuple(
            sorted(
                os.listdir(final_descriptor),
                key=lambda name: (name == "manifest.json", name),
            )
        ) != names:
            raise _UnsafeCandidatePath(f"{label} payload changed during activation")
        os.rmdir(temporary, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        _pkg._revalidate_candidate_parent(
            candidate_root,
            relative,
            label=label,
            expected_identities=parent_identities,
        )
        after = os.stat(
            relative.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(after.st_mode) or (after.st_dev, after.st_ino) != (
            final_identity
        ):
            raise _UnsafeCandidatePath(f"{label} changed after activation")
    except Exception:
        if final_descriptor >= 0 and final_identity is not None:
            try:
                current = os.stat(
                    relative.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISDIR(current.st_mode) and (
                    current.st_dev,
                    current.st_ino,
                ) == final_identity:
                    for name, expected_identity in published.items():
                        try:
                            item = os.stat(
                                name,
                                dir_fd=final_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            continue
                        if stat.S_ISREG(item.st_mode) and (
                            item.st_dev,
                            item.st_ino,
                        ) == expected_identity:
                            os.unlink(name, dir_fd=final_descriptor)
                    os.rmdir(relative.name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if final_descriptor >= 0:
            os.close(final_descriptor)
        if staging_descriptor >= 0:
            os.close(staging_descriptor)
