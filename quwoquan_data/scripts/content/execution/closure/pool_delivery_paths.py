"""Digest and path-safety primitives for pool delivery intents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_object_dir(root: Path, value: object) -> tuple[str, Path]:
    relative = str(value or "").strip().strip("/")
    candidate = root / relative
    path = candidate.resolve()
    try:
        normalized = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("pool delivery contentObjectDir escapes execution root") from exc
    relative_parts = Path(relative).parts
    has_symlink = any(
        (root / Path(*relative_parts[:index])).is_symlink()
        for index in range(1, len(relative_parts) + 1)
    )
    if has_symlink:
        raise ValueError("pool delivery contentObjectDir cannot traverse symlinks")
    if not normalized or not path.is_dir():
        raise ValueError("pool delivery contentObjectDir is not a physical object directory")
    return normalized, path
