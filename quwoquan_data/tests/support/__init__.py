"""Shared test support modules."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path


_USER_LOCK_FLAGS = getattr(stat, "UF_IMMUTABLE", 0) | getattr(
    stat,
    "UF_APPEND",
    0,
)


def _restore_test_owner_access(path: Path, *, directory: bool) -> None:
    mode = stat.S_IMODE(path.lstat().st_mode)
    if _USER_LOCK_FLAGS and hasattr(os, "chflags"):
        flags = path.lstat().st_flags
        if flags & _USER_LOCK_FLAGS:
            os.chflags(
                path,
                flags & ~_USER_LOCK_FLAGS,
                follow_symlinks=False,
            )
    path.chmod(mode | (0o700 if directory else stat.S_IRUSR | stat.S_IWUSR))


def remove_readonly_test_tree(path: Path, *, test_temp_root: Path) -> None:
    """Remove one test-owned tree without following links outside its boundary.

    Source snapshots preserve directory modes.  A snapshot copied from a
    read-only source capsule therefore has to regain owner permissions before
    pytest can remove its temporary directory.  The explicit boundary keeps
    this teardown helper away from repository and real output roots.
    """
    if path.is_symlink():
        raise ValueError("test cleanup root must not be a symbolic link")
    boundary = test_temp_root.resolve(strict=True)
    candidate = path.resolve(strict=False)
    try:
        relative = candidate.relative_to(boundary)
    except ValueError as error:
        raise ValueError("test cleanup root escapes its temporary boundary") from error
    if relative == Path("."):
        raise ValueError("test cleanup must not remove its temporary boundary")
    if not candidate.exists():
        return

    # Restore traversal top-down first; a nested directory may itself have no
    # owner execute bit.  Symlinks are never followed or chmodded.
    _restore_test_owner_access(candidate, directory=True)
    for current, directories, files in os.walk(
        candidate,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)
        _restore_test_owner_access(current_path, directory=True)
        for name in directories:
            child = current_path / name
            if not child.is_symlink():
                _restore_test_owner_access(child, directory=True)
        for name in files:
            child = current_path / name
            if not child.is_symlink():
                _restore_test_owner_access(child, directory=False)
    shutil.rmtree(candidate)


__all__ = ["remove_readonly_test_tree"]
