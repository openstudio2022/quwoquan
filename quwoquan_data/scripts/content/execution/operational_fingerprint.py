"""Stable fingerprint of the live host-only operational contract."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from core.paths import REPO_ROOT

POLICY_PATH = REPO_ROOT / "quwoquan_data/control_plane/execution/host_only_operational_fingerprint.json"
SCHEMA = "quwoquan_data.host_only_operational_fingerprint_policy"
_KEYS = {"schema", "inputs", "excludedUnreachableFamilies"}
_EXCLUSIONS = ["agent", "queue", "controller", "recovery", "campaign"]


def _regular_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError(f"operational fingerprint input may not be a symlink: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"operational fingerprint input must be regular: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"operational fingerprint input changed while reading: {path}")
    return b"".join(chunks)


def _policy(repo_root: Path) -> dict[str, object]:
    path = repo_root / POLICY_PATH.relative_to(REPO_ROOT)
    value = json.loads(_regular_bytes(path))
    if not isinstance(value, dict) or set(value) != _KEYS or value.get("schema") != SCHEMA:
        raise ValueError("host-only operational fingerprint policy is invalid")
    inputs = value.get("inputs")
    if not isinstance(inputs, list) or not inputs or len(set(inputs)) != len(inputs) or not all(isinstance(ref, str) and ref and not Path(ref).is_absolute() and ".." not in Path(ref).parts for ref in inputs):
        raise ValueError("host-only operational fingerprint inputs are invalid")
    if value.get("excludedUnreachableFamilies") != _EXCLUSIONS:
        raise ValueError("host-only operational fingerprint exclusions drifted")
    return value


def operational_fingerprint(*, repo_root: Path = REPO_ROOT) -> str:
    """Hash only live Skill/CLI/deterministic contract inputs, never dead families."""
    root = Path(repo_root).resolve()
    policy = _policy(root)
    digest = hashlib.sha256()
    for ref in policy["inputs"]:
        path = root / str(ref)
        if not path.exists() or path.is_symlink():
            raise FileNotFoundError(f"operational fingerprint input missing or symbolic: {ref}")
        files = (path,) if path.is_file() else tuple(
            item for item in sorted(path.rglob("*")) if item.is_file() and not item.is_symlink()
        )
        for item in files:
            relative = item.relative_to(root).as_posix()
            if any(part in {"__pycache__", ".pytest_cache"} for part in item.parts):
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(_regular_bytes(item))
            digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


__all__ = ["POLICY_PATH", "SCHEMA", "operational_fingerprint"]
