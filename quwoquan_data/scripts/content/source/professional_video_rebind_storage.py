"""Create-once destination helpers for video rebind manifests."""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn


def safe_rebind_destination(
    path: Path,
    *,
    root: Path,
    fail: Callable[[str, str], NoReturn],
) -> Path:
    resolved_root = root.resolve()
    resolved = path.expanduser().resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        fail(
            "DATA.SOURCE.REBIND_DESTINATION_UNSAFE",
            "destination must be below the video acquisition root",
        )
    current = resolved_root
    for part in resolved.relative_to(resolved_root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            fail(
                "DATA.SOURCE.REBIND_DESTINATION_UNSAFE",
                "destination must not traverse a symlink",
            )
    return resolved


def write_rebind_manifest_once(
    path: Path,
    payload: Mapping[str, Any],
    *,
    fail: Callable[[str, str], NoReturn],
) -> Path:
    body = json.dumps(dict(payload), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            fail(
                "DATA.SOURCE.REBIND_CREATE_ONCE_CONFLICT",
                f"destination already contains different bytes: {path}",
            )
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


__all__ = ["safe_rebind_destination", "write_rebind_manifest_once"]
