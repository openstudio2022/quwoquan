"""Deterministic tree integrity for publish and release evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

_SENSITIVE_RE = re.compile(
    r"(?:api[_-]?key|credential|secret|password|access[_-]?token|refresh[_-]?token|cookie|session)",
    re.IGNORECASE,
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _safe_rel(rel: str) -> tuple[str, bool]:
    if not _SENSITIVE_RE.search(rel):
        return rel, False
    return f"redacted/{hashlib.sha256(rel.encode('utf-8')).hexdigest()}", True


def _entries(root: Path) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    redacted = 0
    if not root.is_dir():
        return entries, redacted
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        rel, was_redacted = _safe_rel(path.relative_to(root).as_posix())
        redacted += int(was_redacted)
        size = path.stat().st_size
        blob_hash = _sha256(path.read_bytes())
        entries.append(
            {
                "path": rel,
                "sha256": blob_hash,
                "bytes": size,
                "leafHash": _sha256(
                    b"blob\0"
                    + rel.encode("utf-8")
                    + b"\0"
                    + blob_hash.encode("ascii")
                    + b"\0"
                    + str(size).encode("ascii")
                ),
            }
        )
    return entries, redacted


def _merkle_root(entries: Sequence[Mapping[str, Any]]) -> str:
    level = [bytes.fromhex(str(row["leafHash"]).removeprefix("sha256:")) for row in entries]
    if not level:
        return _sha256(b"")
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"node\0" + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return "sha256:" + level[0].hex()


def tree_integrity_stats(root: Path) -> dict[str, Any]:
    entries, redacted = _entries(root)
    inventory = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256-path-blob-merkle",
        "merkleRoot": _merkle_root(entries),
        "fileCount": len(entries),
        "totalBytes": sum(int(row["bytes"]) for row in entries),
        "inventoryHash": _sha256(inventory.encode("utf-8")),
        "root": str(root),
        "redactedPathCount": redacted,
    }
