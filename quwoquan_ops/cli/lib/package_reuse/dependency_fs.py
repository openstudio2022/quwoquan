"""No-follow filesystem primitives for immutable dependency capsules."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path, PurePosixPath


def _absolute(path: Path) -> Path:
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else expanded.absolute()


def _directory_fd(path: Path, *, label: str) -> int:
    """Open every path component as a real directory without following links."""

    absolute = _absolute(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("App dependency capsule requires no-follow directory IO")
    descriptor = os.open(absolute.anchor, os.O_RDONLY | directory)
    try:
        for segment in absolute.parts[1:]:
            next_descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"App dependency {label} is not a real directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def assert_real_directory(path: Path, *, label: str) -> None:
    try:
        descriptor = _directory_fd(path, label=label)
    except OSError as exc:
        raise ValueError(f"App dependency {label} is unavailable or linked") from exc
    os.close(descriptor)


def read_regular_nofollow(path: Path, *, label: str) -> tuple[bytes, int]:
    """Read one single-link file through a no-follow directory chain."""

    absolute = _absolute(path)
    try:
        parent_fd = _directory_fd(absolute.parent, label=f"{label} parent")
        descriptor = os.open(
            absolute.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise ValueError(f"App dependency {label} is unavailable or linked") from exc
    finally:
        if "parent_fd" in locals():
            os.close(parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(
                f"App dependency {label} is not a single-link regular file"
            )
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
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
            raise ValueError(f"App dependency {label} changed during read")
    finally:
        os.close(descriptor)
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    return bytes(content), mode


def write_fresh_relative_file(
    *,
    root: Path,
    relative: str,
    content: bytes,
    mode: int,
) -> None:
    """Create a file using openat from a previously fresh private root."""

    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.as_posix() != relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError("App dependency destination path is unsafe")
    root_fd = _directory_fd(root, label="snapshot destination root")
    descriptor = root_fd
    opened: list[int] = []
    try:
        for segment in pure.parts[:-1]:
            try:
                os.mkdir(segment, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                segment,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            opened.append(next_descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            pure.parts[-1],
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=descriptor,
        )
        try:
            view = memoryview(content)
            while view:
                written = os.write(file_descriptor, view)
                if written <= 0:
                    raise OSError("App dependency snapshot copy made no progress")
                view = view[written:]
            os.fchmod(file_descriptor, mode)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
    finally:
        for opened_descriptor in reversed(opened):
            os.close(opened_descriptor)
        os.close(root_fd)


def remove_private_tree(root: Path) -> None:
    """Make one exact private tree writable, delete it, and assert absence."""

    target = _absolute(root)
    if target == Path(target.anchor) or target.parent == target:
        raise ValueError("App dependency cleanup target is unsafe")
    if target.is_symlink():
        raise ValueError("App dependency cleanup target is linked")
    if not target.exists():
        return
    target.chmod(0o700)
    for current, directories, _files in os.walk(target, topdown=True, followlinks=False):
        current_path = Path(current)
        current_path.chmod(0o700)
        retained: list[str] = []
        for name in directories:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                child.unlink()
            elif stat.S_ISDIR(metadata.st_mode):
                child.chmod(0o700)
                retained.append(name)
            else:
                raise ValueError("App dependency cleanup found an unsafe directory node")
        directories[:] = retained
    shutil.rmtree(target)
    if target.exists() or target.is_symlink():
        raise OSError("App dependency private cleanup did not converge")
