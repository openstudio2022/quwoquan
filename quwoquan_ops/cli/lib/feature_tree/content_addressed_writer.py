"""Descriptor-relative content-addressed immutable output writer."""
from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import threading
import uuid
from collections.abc import Mapping
from pathlib import Path

from ..descriptor_safe_io import read_regular_single_link_at
from ..evidence_fingerprint import canonical_json_bytes
from . import context


def _content_addressed_path(content: bytes, *, subdirectory: str | None = None) -> Path:
    digest = hashlib.sha256(content).hexdigest()
    parent = context.OUTPUT_ROOT / "by-fingerprint"
    if subdirectory is not None:
        parent /= subdirectory
    return parent / f"{digest}.json"


def _fd_path(descriptor: int) -> Path:
    """返回已打开 fd 的物理路径；无法确认时 fail closed。"""

    if hasattr(fcntl, "F_GETPATH"):
        raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, bytes(1024))
        if not isinstance(raw, bytes):
            raise OSError(
                errno.EIO, "F_GETPATH 返回类型无效，无法确认目录 fd 物理路径"
            )
        if not raw:
            raise OSError(
                errno.EIO, "F_GETPATH 返回空结果，无法确认目录 fd 物理路径"
            )
        terminator = raw.find(b"\0")
        if terminator < 0:
            raise OSError(
                errno.EIO, "F_GETPATH 返回结果缺少 NUL 终止符"
            )
        encoded_path = raw[:terminator]
        if not encoded_path:
            raise OSError(
                errno.EIO, "F_GETPATH 返回空路径，无法确认目录 fd 物理路径"
            )
        try:
            decoded_path = encoded_path.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OSError(
                errno.EILSEQ, "F_GETPATH 返回路径不是有效 UTF-8"
            ) from error
        return Path(decoded_path)
    try:
        return Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    except OSError as error:
        raise OSError(
            errno.ENOTSUP, "当前平台不支持目录 fd 物理路径校验"
        ) from error


def _safe_directory_fd(
    path: Path,
    *,
    repository_root: Path,
    physical_root: Path,
    create: bool,
) -> int:
    """逐级无跟随地打开目录，并校验词法与物理边界。"""

    lexical = Path(os.path.abspath(path))
    repository = Path(os.path.abspath(repository_root))
    root = Path(os.path.abspath(physical_root))
    try:
        lexical.relative_to(repository)
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"GATE_BLOCK: immutable ref 目录越出 repository/output root：{lexical}"
        ) from error

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(root, flags)
        opened_root = _fd_path(descriptor).resolve(strict=True)
        repository_physical = repository.resolve(strict=True)
        if not opened_root.is_relative_to(repository_physical):
            raise ValueError(
                "GATE_BLOCK: immutable ref OUTPUT_ROOT 物理路径越出 repository"
            )
        for component in relative.parts:
            if component in ("", ".", ".."):
                raise ValueError(
                    f"GATE_BLOCK: immutable ref 目录组件无效：{component!r}"
                )
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        opened = _fd_path(descriptor).resolve(strict=True)
        if not opened.is_relative_to(opened_root):
            raise ValueError(
                "GATE_BLOCK: immutable ref 目录物理路径越出 OUTPUT_ROOT"
            )
        return descriptor
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        raise


def _read_exact_bytes_at(directory_fd: int, name: str) -> bytes:
    try:
        return read_regular_single_link_at(
            directory_fd,
            name,
            display_path=f"immutable ref {name}",
            require_current_name=True,
        )
    except OSError as error:
        if isinstance(error, FileNotFoundError):
            raise
        raise ValueError(
            f"GATE_BLOCK: immutable ref 内容冲突：{name}：{error}"
        ) from error


def _write_content_addressed_bytes(
    content: bytes, *, subdirectory: str | None = None
) -> Path:
    """目录 fd 绑定的原子 create-once；既不跟随 symlink，也不覆盖。"""

    if subdirectory not in (None, "receipts"):
        raise ValueError(
            "GATE_BLOCK: immutable ref 只允许 canonical receipts 子目录"
        )
    path = _content_addressed_path(content, subdirectory=subdirectory)
    output_root = Path(os.path.abspath(context.OUTPUT_ROOT))
    repository_root = Path(os.path.abspath(context.REPO_ROOT))
    canonical_output_root = (
        repository_root / ".qwq_output/env/repo/runs/feature-tree"
    )
    if output_root != canonical_output_root:
        raise ValueError(
            "GATE_BLOCK: immutable ref OUTPUT_ROOT 不是 canonical repository output root"
        )
    absolute_parent = Path(os.path.abspath(path.parent))
    try:
        output_root.relative_to(repository_root)
        relative_parent = absolute_parent.relative_to(output_root)
    except ValueError as error:
        raise ValueError(
            "GATE_BLOCK: immutable ref 目标越出 repository/output root"
        ) from error
    if relative_parent.parts[:1] != ("by-fingerprint",):
        raise ValueError(
            "GATE_BLOCK: immutable ref 目标不在 canonical by-fingerprint 目录"
        )
    parent_fd: int | None = None
    temporary_name = (
        f".{path.stem}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    temporary_created = False
    descriptor: int | None = None
    try:
        parent_fd = _safe_directory_fd(
            output_root,
            repository_root=repository_root,
            physical_root=repository_root,
            create=True,
        )
        opened_output = _fd_path(parent_fd).resolve(strict=True)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for component in relative_parent.parts:
            try:
                child = os.open(component, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o755, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        opened_parent = _fd_path(parent_fd).resolve(strict=True)
        if not opened_parent.is_relative_to(opened_output):
            raise ValueError(
                "GATE_BLOCK: immutable ref 目录物理路径越出 OUTPUT_ROOT"
            )
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        try:
            existing = _read_exact_bytes_at(parent_fd, path.name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != content:
                raise ValueError(
                    f"GATE_BLOCK: immutable ref 内容冲突：{path.name}"
                )
            return path

        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=parent_fd,
        )
        temporary_created = True
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(errno.EIO, "immutable ref 临时文件短写")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=parent_fd)
            temporary_created = False
            os.fsync(parent_fd)
        except FileExistsError:
            pass
        try:
            exact = _read_exact_bytes_at(parent_fd, path.name)
        except (OSError, ValueError) as error:
            raise ValueError(
                f"GATE_BLOCK: immutable ref exact bytes 校验失败：{path.name}"
            ) from error
        if exact != content:
            raise ValueError(
                f"GATE_BLOCK: immutable ref 内容冲突：{path.name}"
            )
        return path
    except ValueError:
        raise
    except OSError as error:
        raise ValueError(
            f"GATE_BLOCK: immutable ref create-once 失败：{error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            if temporary_created:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            os.close(parent_fd)


def _write_content_addressed_json(
    payload: Mapping[str, object], *, subdirectory: str | None = None
) -> Path:
    return _write_content_addressed_bytes(
        canonical_json_bytes(payload), subdirectory=subdirectory
    )
