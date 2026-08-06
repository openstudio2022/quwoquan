"""Atomic create-once storage for per-lane scale promotion receipts."""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json


def write_scale_promotion_create_once(
    path: Path,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> Path:
    frozen = dict(payload)

    def assert_existing() -> None:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} create-once target is not a regular file: {path}")
        if read_json(path) != frozen:
            raise ValueError(f"{label} receipt collision: {path}")

    if path.exists() or path.is_symlink():
        assert_existing()
        return path
    body = (
        json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            assert_existing()
        return path
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


__all__ = ["write_scale_promotion_create_once"]
