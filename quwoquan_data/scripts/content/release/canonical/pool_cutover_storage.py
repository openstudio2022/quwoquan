"""Cutover 的有限存储原语；不依赖 Ops journal，也不提供通用 repair 框架。

exchange 的 ABI 与 Ops secure_storage 一致；Data 不反向 import Ops 应用层。
所有调用者必须持有 canonical 锁、验证 exact paths，且没有授权外的目录写者。
"""
from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from content.release.canonical.object_transaction_contract import (
    _digest_bytes, _digest_file, _json_bytes, _tree_digest,
)


def _fail(code: str, detail: object) -> None:
    from content.release.canonical.pool_cutover import _fail as fail
    fail(code, detail)


def identity(path: Path) -> list[int]:
    node = path.lstat()
    return [node.st_dev, node.st_ino]


@contextmanager
def directory(path: Path) -> Iterator[int]:
    """逐组件 O_NOFOLLOW，保留父目录 fd；禁止在 syscall 时重新走可变祖先。"""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def sync_directory(path: Path) -> None:
    with directory(path) as fd:
        os.fsync(fd)


def sync_tree(root: Path) -> None:
    from content.release.canonical.pool_cutover import _regular_tree
    for path in _regular_tree(root):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        sync_directory(path)
    sync_directory(root)


def _rename_function():
    name = {"darwin": "renameatx_np", "linux": "renameat2"}.get(sys.platform)
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, name, None) if name else None
    if function is None:
        _fail("ATOMIC_EXCHANGE_UNSUPPORTED", f"{sys.platform}: 缺 OS 原子 rename ABI")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    return function


def rename_exact(source: Path, destination: Path, *, exchange: bool, expected: list[int], destination_identity: list[int] | None = None) -> None:
    """单 syscall 交换/独占迁移；不以两次 rename 降级。fsync 由提交边界负责。"""
    function = _rename_function()
    flags = 2 if exchange else 4 if sys.platform == "darwin" else 1
    with directory(source.parent) as source_fd, directory(destination.parent) as destination_fd:
        node = os.stat(source.name, dir_fd=source_fd, follow_symlinks=False)
        if [node.st_dev, node.st_ino] != expected or not stat.S_ISDIR(node.st_mode):
            _fail("DIRECTORY_IDENTITY_DRIFT", source)
        if exchange:
            target = os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
            if [target.st_dev, target.st_ino] != destination_identity or not stat.S_ISDIR(target.st_mode):
                _fail("DIRECTORY_IDENTITY_DRIFT", destination)
        if function(source_fd, os.fsencode(source.name), destination_fd, os.fsencode(destination.name), flags) != 0:
            number = ctypes.get_errno()
            if number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                _fail("ATOMIC_EXCHANGE_UNSUPPORTED", os.strerror(number))
            raise OSError(number, os.strerror(number), str(destination))


def write_once(path: Path, document: dict) -> dict[str, str]:
    """create-once + fsync；先写私有文件，再 link 发布完整 JSON，无部分成功 receipt。"""
    temporary = path.with_name("." + path.name + ".writing")
    with temporary.open("xb") as handle:
        handle.write(_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path, follow_symlinks=False)
        sync_directory(path.parent)
    finally:
        temporary.unlink()
    return {"ref": str(path), "digest": _digest_file(path)}


def archive_before(root: Path, destination: Path, expected_digest: str) -> dict[str, str]:
    """离线 tar，不提供解包或 reader；原文逐文件保留，拒绝 links/特殊文件。"""
    from content.release.canonical.pool_cutover import _regular_tree
    files = _regular_tree(root)
    with destination.open("xb") as handle:
        with tarfile.open(fileobj=handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                info = archive.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
                # 同一树内的硬链接也逐文件存原字节，不让 tar 引用成为恢复解析分支。
                info.type, info.linkname, info.size = tarfile.REGTYPE, "", path.stat().st_size
                with path.open("rb") as source:
                    archive.addfile(info, source)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(destination.parent)
    verify_archive(destination, expected_digest)
    return {"ref": str(destination), "digest": _digest_file(destination)}


def verify_archive(path: Path, expected_digest: str) -> None:
    from content.release.canonical.pool_cutover import _relative
    rows = []
    with tarfile.open(path, "r:") as archive:
        for member in archive:
            if not member.isfile() or member.name != _relative(member.name):
                _fail("ARCHIVE_INVALID", member.name)
            source = archive.extractfile(member)
            if source is None:
                _fail("ARCHIVE_INVALID", member.name)
            import hashlib
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
            rows.append({"path": member.name, "sha256": "sha256:" + digest.hexdigest(), "bytes": member.size})
    if len({row["path"] for row in rows}) != len(rows) or _digest_bytes(_json_bytes(sorted(rows, key=lambda row: Path(row["path"])))) != expected_digest:
        _fail("ARCHIVE_DIGEST_DRIFT", path)


def remove_exact_tree(root: Path, expected_digest: str, expected_identity: list[int]) -> None:
    """只删已验证旧树；不接受任意 rmtree。调用者已持有精确清理授权和 archive。"""
    from content.release.canonical.pool_cutover import _regular_tree
    _regular_tree(root)
    if identity(root) != expected_identity or _tree_digest(root) != expected_digest:
        _fail("RETIRED_TREE_DRIFT", root)
    # 打开根 fd 后所有删除都 descriptor-relative；不跟随新插入的 symlink。
    with directory(root) as fd:
        _remove_children(fd)
    with directory(root.parent) as parent:
        node = os.stat(root.name, dir_fd=parent, follow_symlinks=False)
        if [node.st_dev, node.st_ino] != expected_identity:
            _fail("DIRECTORY_IDENTITY_DRIFT", root)
        os.rmdir(root.name, dir_fd=parent)
        os.fsync(parent)


def _remove_children(fd: int) -> None:
    for name in sorted(os.listdir(fd)):
        node = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISREG(node.st_mode):
            os.unlink(name, dir_fd=fd)
        elif stat.S_ISDIR(node.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                _remove_children(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            _fail("SPECIAL_FILE_FORBIDDEN", name)
    os.fsync(fd)
