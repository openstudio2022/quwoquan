"""user-zsh 投影的私有权限原子写入。"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def private_atomic_write(
    path: Path,
    content: bytes,
    *,
    mode: int | None = None,
    private_parent: bool = False,
) -> None:
    path.parent.mkdir(
        mode=0o700 if private_parent else 0o755, parents=True, exist_ok=True
    )
    parent = path.parent.resolve(strict=True)
    if path.is_symlink():
        raise SystemExit("GATE_BLOCK: user-zsh target must not be a symlink")
    if private_parent:
        os.chmod(parent, 0o700)
    target_mode = (
        mode
        if mode is not None
        else stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, target_mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path.parent / path.name)
        os.chmod(path, target_mode)
    finally:
        if temporary.exists():
            temporary.unlink()
