"""Descriptor-relative, fail-closed storage primitives for Objective journals."""
from __future__ import annotations

import contextlib
import ctypes
import errno
import fcntl
import os
import platform
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

sys.dont_write_bytecode = True

DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
_DARWIN_RENAME_SWAP = 0x00000002
_DARWIN_RENAME_EXCL = 0x00000004
_LINUX_RENAME_NOREPLACE = 0x00000001
_LINUX_RENAME_EXCHANGE = 0x00000002
_LINUX_RENAMEAT2_SYSCALLS = {
    "aarch64": 276,
    "arm64": 276,
    "x86_64": 316,
}
Failpoint = Callable[[str], None]


class StorageError(RuntimeError):
    """Fail-closed storage invariant or syscall failure."""

    def __init__(self, detail: str, *, tampered: bool = False) -> None:
        super().__init__(detail)
        self.detail = detail
        self.tampered = tampered


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    device: int
    inode: int


@dataclass(slots=True)
class StorageView:
    """Retained read scope for the exact trusted journal inode chain."""

    root_fd: int
    kind_fd: int
    subject_fd: int
    events_fd: int
    canonical_root: Path
    subject_kind: str
    subject_id: str
    root_identity: NodeIdentity
    kind_identity: NodeIdentity
    subject_identity: NodeIdentity
    events_identity: NodeIdentity
    owner_uid: int
    active: bool = True


@dataclass(slots=True)
class StorageLease(StorageView):
    """Private capability retaining the exact trusted journal inode chain."""

    _token: object = None
    lock_fd: int = -1
    lock_identity: NodeIdentity | None = None


_CAPABILITY_TOKEN = object()


def _identity(metadata: os.stat_result) -> NodeIdentity:
    return NodeIdentity(metadata.st_dev, metadata.st_ino)


def _close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _open_flags(*, directory: bool = False, writable: bool = False) -> int:
    flags = (os.O_RDWR | os.O_NONBLOCK) if writable else os.O_RDONLY
    if directory:
        if not hasattr(os, "O_DIRECTORY"):
            raise StorageError("platform lacks O_DIRECTORY")
        flags |= os.O_DIRECTORY
    if not hasattr(os, "O_NOFOLLOW"):
        raise StorageError("platform lacks O_NOFOLLOW")
    return flags | os.O_NOFOLLOW


def _validate_directory_fd(fd: int, label: str, owner_uid: int) -> NodeIdentity:
    try:
        metadata = os.fstat(fd)
    except OSError as error:
        raise StorageError(f"{label} fstat failed: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise StorageError(f"{label} must be a directory", tampered=True)
    if metadata.st_uid != owner_uid:
        raise StorageError(f"{label} owner is not the trusted uid", tampered=True)
    if metadata.st_gid != os.getegid():
        raise StorageError(f"{label} group is not the trusted effective gid", tampered=True)
    if stat.S_IMODE(metadata.st_mode) != DIRECTORY_MODE:
        raise StorageError(f"{label} mode must be 0700", tampered=True)
    return _identity(metadata)


def _validate_regular_fd(fd: int, label: str, owner_uid: int) -> NodeIdentity:
    try:
        metadata = os.fstat(fd)
    except OSError as error:
        raise StorageError(f"{label} fstat failed: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise StorageError(f"{label} must be a regular file", tampered=True)
    if metadata.st_uid != owner_uid:
        raise StorageError(f"{label} owner is not the trusted uid", tampered=True)
    if metadata.st_gid != os.getegid():
        raise StorageError(f"{label} group is not the trusted effective gid", tampered=True)
    if stat.S_IMODE(metadata.st_mode) != FILE_MODE:
        raise StorageError(f"{label} mode must be 0600", tampered=True)
    if metadata.st_nlink != 1:
        raise StorageError(f"{label} must have exactly one link", tampered=True)
    return _identity(metadata)


def _fsync(fd: int, label: str) -> None:
    try:
        os.fsync(fd)
    except OSError as error:
        raise StorageError(f"{label} fsync failed: {error}") from error


def _open_existing_directory(
    name: str, parent_fd: int, label: str, owner_uid: int, *, trusted: bool = True,
) -> int:
    try:
        fd = os.open(name, _open_flags(directory=True), dir_fd=parent_fd)
    except OSError as error:
        raise StorageError(f"{label} open failed: {error}", tampered=error.errno in {errno.ELOOP, errno.ENOTDIR}) from error
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise StorageError(f"{label} must be a directory", tampered=True)
        if trusted:
            _validate_directory_fd(fd, label, owner_uid)
        return fd
    except BaseException:
        _close(fd)
        raise


def _open_or_create_directory(name: str, parent_fd: int, label: str, owner_uid: int) -> int:
    try:
        return _open_existing_directory(name, parent_fd, label, owner_uid)
    except StorageError as error:
        cause = error.__cause__
        if not isinstance(cause, OSError) or cause.errno != errno.ENOENT:
            raise
    try:
        os.mkdir(name, DIRECTORY_MODE, dir_fd=parent_fd)
    except FileExistsError:
        return _open_existing_directory(name, parent_fd, label, owner_uid)
    except OSError as error:
        raise StorageError(f"{label} mkdir failed: {error}") from error
    try:
        os.chmod(name, DIRECTORY_MODE, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise StorageError(f"{label} chmod failed: {error}") from error
    _fsync(parent_fd, f"{label} parent")
    fd = _open_existing_directory(name, parent_fd, label, owner_uid)
    _fsync(fd, label)
    return fd


def _open_canonical_root(root: Path, *, create: bool, owner_uid: int) -> tuple[int, Path]:
    absolute = Path(os.path.abspath(os.fspath(root)))
    parts = absolute.parts
    if not parts or parts[0] != os.sep or len(parts) < 2:
        raise StorageError("journal root must be a non-filesystem-root absolute lexical path")
    current_fd = os.open(os.sep, _open_flags(directory=True))
    creating = False
    try:
        for index, component in enumerate(parts[1:]):
            label = f"journal root component {index + 1}"
            is_root = index == len(parts[1:]) - 1
            if creating:
                next_fd = _open_or_create_directory(component, current_fd, label, owner_uid)
            else:
                try:
                    next_fd = _open_existing_directory(
                        component, current_fd, label, owner_uid, trusted=is_root,
                    )
                except StorageError as error:
                    cause = error.__cause__
                    if not create or not isinstance(cause, OSError) or cause.errno != errno.ENOENT:
                        raise
                    creating = True
                    next_fd = _open_or_create_directory(component, current_fd, label, owner_uid)
            _close(current_fd)
            current_fd = next_fd
        _validate_directory_fd(current_fd, "canonical journal root", owner_uid)
        return current_fd, absolute
    except BaseException:
        _close(current_fd)
        raise


def root_exists_trusted(root: Path) -> tuple[bool, StorageLease | None]:
    """Probe only true ENOENT as absent; callers do not receive a usable lease."""
    owner_uid = os.geteuid()
    try:
        fd, _canonical = _open_canonical_root(root, create=False, owner_uid=owner_uid)
    except StorageError as error:
        cause = error.__cause__
        if isinstance(cause, OSError) and cause.errno == errno.ENOENT:
            return False, None
        raise
    _close(fd)
    return True, None



def _reject_nonregular_entry(parent_fd: int, name: str, label: str, owner_uid: int) -> None:
    """Inspect type without following before any potentially blocking open."""
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise StorageError(f"{label} lstat failed: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise StorageError(f"{label} must be a regular non-symlink file", tampered=True)
    if metadata.st_uid != owner_uid or metadata.st_gid != os.getegid():
        raise StorageError(f"{label} owner/group is untrusted", tampered=True)
    if stat.S_IMODE(metadata.st_mode) != FILE_MODE or metadata.st_nlink != 1:
        raise StorageError(f"{label} mode/link count is unsafe", tampered=True)


def _open_lock(subject_fd: int, owner_uid: int) -> tuple[int, NodeIdentity]:
    _reject_nonregular_entry(subject_fd, "writer.lock", "writer lock", owner_uid)
    flags = _open_flags(writable=True) | os.O_NONBLOCK
    try:
        fd = os.open("writer.lock", flags, dir_fd=subject_fd)
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise StorageError(
                f"writer lock open failed: {error}",
                tampered=error.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENXIO},
            ) from error
        try:
            fd = os.open(
                "writer.lock", flags | os.O_CREAT | os.O_EXCL, FILE_MODE,
                dir_fd=subject_fd,
            )
        except FileExistsError:
            try:
                fd = os.open("writer.lock", flags, dir_fd=subject_fd)
            except OSError as raced:
                raise StorageError(
                    f"writer lock raced open failed: {raced}", tampered=True,
                ) from raced
        except OSError as create_error:
            raise StorageError(
                f"writer lock create failed: {create_error}",
                tampered=create_error.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENXIO},
            ) from create_error
        else:
            os.fchmod(fd, FILE_MODE)
            _fsync(subject_fd, "subject directory after writer lock create")
    try:
        return fd, _validate_regular_fd(fd, "writer lock", owner_uid)
    except BaseException:
        _close(fd)
        raise


def _same_open_node(parent_fd: int, name: str, expected: NodeIdentity, *, directory: bool, label: str, owner_uid: int) -> None:
    flags = _open_flags(directory=directory)
    try:
        candidate = os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise StorageError(f"{label} path identity check failed: {error}", tampered=True) from error
    try:
        actual = _validate_directory_fd(candidate, label, owner_uid) if directory else _validate_regular_fd(candidate, label, owner_uid)
        if actual != expected:
            raise StorageError(f"{label} inode identity drifted", tampered=True)
    finally:
        _close(candidate)


def validate_view(view: StorageView) -> None:
    if not isinstance(view, StorageView) or not view.active:
        raise StorageError("journal storage view is invalid", tampered=True)
    if os.geteuid() != view.owner_uid:
        raise StorageError("journal storage uid changed", tampered=True)
    checks = (
        (_validate_directory_fd(view.root_fd, "canonical journal root", view.owner_uid), view.root_identity),
        (_validate_directory_fd(view.kind_fd, "subject kind directory", view.owner_uid), view.kind_identity),
        (_validate_directory_fd(view.subject_fd, "subject directory", view.owner_uid), view.subject_identity),
        (_validate_directory_fd(view.events_fd, "events directory", view.owner_uid), view.events_identity),
    )
    if any(actual != expected for actual, expected in checks):
        raise StorageError("retained journal descriptor identity drifted", tampered=True)
    root_parent = os.open("..", _open_flags(directory=True), dir_fd=view.root_fd)
    try:
        _same_open_node(root_parent, view.canonical_root.name, view.root_identity, directory=True, label="canonical journal root", owner_uid=view.owner_uid)
    finally:
        _close(root_parent)
    _same_open_node(view.root_fd, view.subject_kind, view.kind_identity, directory=True, label="subject kind directory", owner_uid=view.owner_uid)
    _same_open_node(view.kind_fd, view.subject_id, view.subject_identity, directory=True, label="subject directory", owner_uid=view.owner_uid)
    _same_open_node(view.subject_fd, "events", view.events_identity, directory=True, label="events directory", owner_uid=view.owner_uid)


def validate_lease(lease: StorageLease) -> None:
    if not isinstance(lease, StorageLease) or lease._token is not _CAPABILITY_TOKEN:
        raise StorageError("writer lease capability is invalid", tampered=True)
    validate_view(lease)
    if lease.lock_identity is None:
        raise StorageError("writer lease lock identity is missing", tampered=True)
    if _validate_regular_fd(lease.lock_fd, "writer lock", lease.owner_uid) != lease.lock_identity:
        raise StorageError("retained writer lock identity drifted", tampered=True)
    _same_open_node(lease.subject_fd, "writer.lock", lease.lock_identity, directory=False, label="writer lock", owner_uid=lease.owner_uid)


@contextlib.contextmanager
def acquire_lease(root: Path, subject_kind: str, subject_id: str) -> Iterator[StorageLease]:
    owner_uid = os.geteuid()
    root_fd = kind_fd = subject_fd = events_fd = lock_fd = -1
    lease: StorageLease | None = None
    try:
        root_fd, canonical_root = _open_canonical_root(root, create=True, owner_uid=owner_uid)
        kind_fd = _open_or_create_directory(subject_kind, root_fd, "subject kind directory", owner_uid)
        subject_fd = _open_or_create_directory(subject_id, kind_fd, "subject directory", owner_uid)
        events_fd = _open_or_create_directory("events", subject_fd, "events directory", owner_uid)
        lock_fd, lock_identity = _open_lock(subject_fd, owner_uid)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise StorageError("another writer owns the subject lease") from error
        lease = StorageLease(
            root_fd=root_fd, kind_fd=kind_fd, subject_fd=subject_fd, events_fd=events_fd,
            canonical_root=canonical_root, subject_kind=subject_kind, subject_id=subject_id,
            root_identity=_validate_directory_fd(root_fd, "canonical journal root", owner_uid),
            kind_identity=_validate_directory_fd(kind_fd, "subject kind directory", owner_uid),
            subject_identity=_validate_directory_fd(subject_fd, "subject directory", owner_uid),
            events_identity=_validate_directory_fd(events_fd, "events directory", owner_uid),
            owner_uid=owner_uid, _token=_CAPABILITY_TOKEN, lock_fd=lock_fd,
            lock_identity=lock_identity,
        )
        validate_lease(lease)
        yield lease
    finally:
        if lease is not None:
            lease.active = False
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        for fd in (lock_fd, events_fd, subject_fd, kind_fd, root_fd):
            if fd >= 0:
                _close(fd)



@contextlib.contextmanager
def open_view(root: Path, subject_kind: str, subject_id: str) -> Iterator[StorageView | None]:
    owner_uid = os.geteuid()
    root_fd = kind_fd = subject_fd = events_fd = -1
    view: StorageView | None = None
    try:
        try:
            root_fd, canonical_root = _open_canonical_root(root, create=False, owner_uid=owner_uid)
        except StorageError as error:
            cause = error.__cause__
            if isinstance(cause, OSError) and cause.errno == errno.ENOENT:
                yield None
                return
            raise
        try:
            kind_fd = _open_existing_directory(subject_kind, root_fd, "subject kind directory", owner_uid)
        except StorageError as error:
            cause = error.__cause__
            if isinstance(cause, OSError) and cause.errno == errno.ENOENT:
                yield None
                return
            raise
        try:
            subject_fd = _open_existing_directory(subject_id, kind_fd, "subject directory", owner_uid)
        except StorageError as error:
            cause = error.__cause__
            if isinstance(cause, OSError) and cause.errno == errno.ENOENT:
                yield None
                return
            raise
        events_fd = _open_existing_directory("events", subject_fd, "events directory", owner_uid)
        if entry_exists(subject_fd, "writer.lock", directory=False, label="writer lock", owner_uid=owner_uid):
            pass
        view = StorageView(
            root_fd, kind_fd, subject_fd, events_fd, canonical_root, subject_kind, subject_id,
            _validate_directory_fd(root_fd, "canonical journal root", owner_uid),
            _validate_directory_fd(kind_fd, "subject kind directory", owner_uid),
            _validate_directory_fd(subject_fd, "subject directory", owner_uid),
            _validate_directory_fd(events_fd, "events directory", owner_uid), owner_uid,
        )
        validate_view(view)
        yield view
    finally:
        if view is not None:
            view.active = False
        for fd in (events_fd, subject_fd, kind_fd, root_fd):
            if fd >= 0:
                _close(fd)

def open_regular_at(parent_fd: int, name: str, label: str, owner_uid: int) -> int:
    _reject_nonregular_entry(parent_fd, name, label, owner_uid)
    try:
        fd = os.open(name, _open_flags() | os.O_NONBLOCK, dir_fd=parent_fd)
    except OSError as error:
        raise StorageError(f"{label} open failed: {error}", tampered=error.errno in {errno.ELOOP, errno.ENOTDIR}) from error
    try:
        _validate_regular_fd(fd, label, owner_uid)
        return fd
    except BaseException:
        _close(fd)
        raise


def entry_exists(parent_fd: int, name: str, *, directory: bool, label: str, owner_uid: int) -> bool:
    if not directory:
        _reject_nonregular_entry(parent_fd, name, label, owner_uid)
    flags = _open_flags(directory=directory) | (0 if directory else os.O_NONBLOCK)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        if error.errno == errno.ENOENT:
            return False
        raise StorageError(f"{label} probe failed: {error}", tampered=error.errno in {errno.ELOOP, errno.ENOTDIR}) from error
    try:
        if directory:
            _validate_directory_fd(fd, label, owner_uid)
        else:
            _validate_regular_fd(fd, label, owner_uid)
        return True
    finally:
        _close(fd)


def list_entries(parent_fd: int) -> list[str]:
    try:
        names = os.listdir(parent_fd)
    except OSError as error:
        raise StorageError(f"directory listing failed: {error}") from error
    if any(name in {"", ".", ".."} or "/" in name for name in names):
        raise StorageError("directory contains an unsafe entry name", tampered=True)
    return sorted(names)


def read_all(fd: int, label: str) -> bytes:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as error:
        raise StorageError(f"{label} read failed: {error}") from error


def _create_private(parent_fd: int, prefix: str) -> tuple[int, str]:
    flags = _open_flags(writable=True) | os.O_CREAT | os.O_EXCL
    for _attempt in range(128):
        name = f".{prefix}.{os.getpid()}.{secrets.token_hex(16)}.staging"
        try:
            fd = os.open(name, flags, FILE_MODE, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as error:
            raise StorageError(f"private staging create failed: {error}") from error
        try:
            os.fchmod(fd, FILE_MODE)
            _validate_regular_fd(fd, "private staging file", os.geteuid())
            return fd, name
        except BaseException:
            _close(fd)
            raise
    raise StorageError("private staging name allocation exhausted")


def _write_complete(fd: int, content: bytes, failpoint: Failpoint | None) -> None:
    split = max(1, len(content) // 2)
    offset = 0
    while offset < split:
        offset += os.write(fd, content[offset:split])
    if failpoint is not None:
        failpoint("after_staging_partial_write")
    while offset < len(content):
        offset += os.write(fd, content[offset:])



def _encoded_entry_name(name: str, label: str) -> bytes:
    try:
        encoded = os.fsencode(name)
    except (TypeError, UnicodeEncodeError) as error:
        raise StorageError(f"{label} is not a valid filesystem entry name") from error
    if not encoded or b"\x00" in encoded:
        raise StorageError(f"{label} is not a valid filesystem entry name")
    return encoded


def _darwin_renameatx_np(parent_fd: int, source: str, destination: str, flags: int) -> None:
    """Small testable wrapper around Darwin renameatx_np."""
    if sys.platform != "darwin":
        raise StorageError("platform lacks supported Darwin renameatx_np")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except (OSError, TypeError) as error:
        raise StorageError("Darwin libc is unavailable") from error
    renameatx_np = getattr(libc, "renameatx_np", None)
    if renameatx_np is None:
        raise StorageError("Darwin renameatx_np is unavailable")
    renameatx_np.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        parent_fd, _encoded_entry_name(source, "source"),
        parent_fd, _encoded_entry_name(destination, "destination"), flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


def _linux_renameat2(parent_fd: int, source: str, destination: str, flags: int) -> None:
    """Descriptor-relative Linux renameat2 with a fail-closed symbol/syscall path."""
    if sys.platform != "linux":
        raise StorageError("platform lacks supported Linux renameat2")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except (OSError, TypeError) as error:
        raise StorageError("Linux libc is unavailable") from error
    source_bytes = _encoded_entry_name(source, "source")
    destination_bytes = _encoded_entry_name(destination, "destination")
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            parent_fd, source_bytes, parent_fd, destination_bytes, flags,
        )
    else:
        syscall = getattr(libc, "syscall", None)
        syscall_number = _LINUX_RENAMEAT2_SYSCALLS.get(platform.machine().lower())
        if syscall is None or syscall_number is None:
            raise StorageError("Linux renameat2 is unavailable for this architecture")
        syscall.restype = ctypes.c_long
        result = syscall(
            ctypes.c_long(syscall_number), ctypes.c_int(parent_fd),
            ctypes.c_char_p(source_bytes), ctypes.c_int(parent_fd),
            ctypes.c_char_p(destination_bytes), ctypes.c_uint(flags),
        )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.ENOSYS:
            raise StorageError("Linux renameat2 syscall is unavailable")
        if error_number in {errno.EINVAL, errno.EOPNOTSUPP, errno.ENOTSUP}:
            raise StorageError(
                f"Linux renameat2 flags are unsupported: {os.strerror(error_number)}"
            )
        raise OSError(error_number, os.strerror(error_number), destination)


def _exclusive_rename_at(parent_fd: int, source: str, destination: str) -> None:
    if sys.platform == "darwin":
        _darwin_renameatx_np(
            parent_fd, source, destination, _DARWIN_RENAME_EXCL,
        )
        return
    if sys.platform == "linux":
        _linux_renameat2(
            parent_fd, source, destination, _LINUX_RENAME_NOREPLACE,
        )
        return
    raise StorageError(f"platform {sys.platform!r} lacks supported exclusive rename")


def _exchange_rename_at(parent_fd: int, source: str, destination: str) -> None:
    if sys.platform == "darwin":
        _darwin_renameatx_np(
            parent_fd, source, destination, _DARWIN_RENAME_SWAP,
        )
        return
    if sys.platform == "linux":
        _linux_renameat2(
            parent_fd, source, destination, _LINUX_RENAME_EXCHANGE,
        )
        return
    raise StorageError(f"platform {sys.platform!r} lacks supported exchange rename")


def exclusive_publish_at(parent_fd: int, source: str, destination: str) -> None:
    _exclusive_rename_at(parent_fd, source, destination)


def publish_staged_event(lease: StorageLease, final_name: str, content: bytes, *, failpoint: Failpoint | None = None) -> None:
    validate_lease(lease)
    staging_fd, staging_name = _create_private(lease.events_fd, "event")
    published = False
    try:
        if failpoint is not None:
            failpoint("after_staging_create")
        _write_complete(staging_fd, content, failpoint)
        _fsync(staging_fd, "event staging file")
        if failpoint is not None:
            failpoint("after_staging_fsync")
            failpoint("before_event_publish")
        validate_lease(lease)
        try:
            exclusive_publish_at(lease.events_fd, staging_name, final_name)
        except FileExistsError:
            raise StorageError(f"authoritative event {final_name} already exists", tampered=True)
        except OSError as error:
            raise StorageError(f"exclusive event publish failed: {error}") from error
        published = True
        if failpoint is not None:
            failpoint("after_event_publish_before_directory_fsync")
        _fsync(lease.events_fd, "events directory")
        if failpoint is not None:
            failpoint("after_event_fsync")
        validate_lease(lease)
    finally:
        _close(staging_fd)
        if not published:
            try:
                os.unlink(staging_name, dir_fd=lease.events_fd)
                _fsync(lease.events_fd, "events directory staging cleanup")
            except FileNotFoundError:
                pass
            except OSError:
                pass


def replace_regular_at(lease: StorageLease, name: str, content: bytes, *, failpoint: Failpoint | None = None) -> None:
    validate_lease(lease)
    temporary_fd, temporary_name = _create_private(lease.subject_fd, name)
    try:
        _write_complete(temporary_fd, content, None)
        _fsync(temporary_fd, f"{name} staging file")
        validate_lease(lease)
        destination_exists = False
        try:
            existing_fd = open_regular_at(lease.subject_fd, name, name, lease.owner_uid)
        except StorageError as error:
            cause = error.__cause__
            if not isinstance(cause, OSError) or cause.errno != errno.ENOENT:
                raise
        else:
            destination_exists = True
            _close(existing_fd)
        if destination_exists:
            _exchange_rename_at(lease.subject_fd, temporary_name, name)
            os.unlink(temporary_name, dir_fd=lease.subject_fd)
        else:
            _exclusive_rename_at(lease.subject_fd, temporary_name, name)
        temporary_name = ""
        _fsync(lease.subject_fd, "subject directory")
        if failpoint is not None:
            failpoint(f"after_{name.removesuffix('.json')}_materialized")
        validate_lease(lease)
    except OSError as error:
        raise StorageError(f"derived {name} replace failed: {error}") from error
    finally:
        _close(temporary_fd)
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=lease.subject_fd)
            except OSError:
                pass


def remove_staging_entries(lease: StorageLease) -> None:
    validate_lease(lease)
    changed = False
    for name in list_entries(lease.events_fd):
        if name.startswith(".event.") and name.endswith(".staging"):
            staging_fd = open_regular_at(lease.events_fd, name, "private staging file", lease.owner_uid)
            _close(staging_fd)
            try:
                os.unlink(name, dir_fd=lease.events_fd)
            except OSError as error:
                raise StorageError(f"staging cleanup failed: {error}") from error
            changed = True
    if changed:
        _fsync(lease.events_fd, "events directory staging cleanup")
    derived_changed = False
    for name in list_entries(lease.subject_fd):
        if any(name.startswith(f".{artifact}.") for artifact in ("snapshot.json", "head.json")) and name.endswith(".staging"):
            staging_fd = open_regular_at(lease.subject_fd, name, "derived staging file", lease.owner_uid)
            _close(staging_fd)
            try:
                os.unlink(name, dir_fd=lease.subject_fd)
            except OSError as error:
                raise StorageError(f"derived staging cleanup failed: {error}") from error
            derived_changed = True
    if derived_changed:
        _fsync(lease.subject_fd, "subject directory staging cleanup")
    validate_lease(lease)
