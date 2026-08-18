"""Seal, verify and discard the immutable byte surface of a campaign capsule."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

CAPSULE_MANIFEST_NAME = ".qwq_campaign_capsule.json"


def capsule_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capsule_tree_digest(root: Path) -> str:
    """Verify every exported executor byte, not only sourceDigest inputs."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == CAPSULE_MANIFEST_NAME:
            continue
        if path.is_symlink():
            row = f"L\0{relative}\0{os.readlink(path)}\n"
        elif path.is_file():
            executable = path.stat().st_mode & 0o111
            row = f"F\0{relative}\0{executable:o}\0{capsule_file_digest(path)}\n"
        else:
            continue
        digest.update(row.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def seal_capsule_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~0o222)
    root.chmod(root.stat().st_mode & ~0o222)


def capsule_tree_is_sealed(root: Path) -> bool:
    if root.stat().st_mode & 0o222:
        return False
    for path in root.rglob("*"):
        if not path.is_symlink() and path.stat().st_mode & 0o222:
            return False
    return True


def _make_directories_writable(root: Path) -> None:
    """Restore only the directory write bits that unlinking a capsule needs.

    Capsule files are hard links onto immutable library entries, so relaxing a
    file mode here would relax every other capsule sharing that inode. Unlink
    permission comes from the parent directory, so directories are sufficient.
    """
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            path.chmod(path.stat().st_mode | 0o700)
        except OSError:
            pass
    try:
        root.chmod(root.stat().st_mode | 0o700)
    except OSError:
        pass


def discard_capsule_tree(root: Path) -> None:
    if not root.exists():
        return
    _make_directories_writable(root)
    shutil.rmtree(root)


__all__ = [
    "CAPSULE_MANIFEST_NAME",
    "capsule_file_digest",
    "capsule_tree_digest",
    "capsule_tree_is_sealed",
    "discard_capsule_tree",
    "seal_capsule_tree",
]
