"""Pure path and byte helpers for immutable scale source-pool evidence."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path


class ScaleSourcePoolEvidencePathError(ValueError):
    """A source-pool evidence path is unsafe, missing, or unreadable."""


def _relative_ref(ref: object, *, label: str) -> Path:
    text = str(ref or "").strip()
    relative = Path(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise ScaleSourcePoolEvidencePathError(
            f"{label} must be a non-empty relative reference"
        )
    return relative


def resolve_evidence_root(path: Path) -> Path:
    root = path.expanduser().absolute()
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise ScaleSourcePoolEvidencePathError(
            f"evidence root is missing or unreadable: {root}"
        ) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ScaleSourcePoolEvidencePathError(
            f"evidence root must be a real directory: {root}"
        )
    return root


def resolve_evidence_directory(path: Path, ref: object, *, label: str) -> Path:
    relative = _relative_ref(ref, label=label)
    current = path
    if relative.as_posix() == ".":
        return current
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ScaleSourcePoolEvidencePathError(
                f"{label} is missing or unreadable: {relative.as_posix()}"
            ) from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ScaleSourcePoolEvidencePathError(
                f"{label} must not traverse a symlink: {relative.as_posix()}"
            )
    return current


def resolve_evidence_file(path: Path, ref: object, *, label: str) -> Path:
    relative = _relative_ref(ref, label=label)
    current = path
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ScaleSourcePoolEvidencePathError(
                f"{label} file is missing or unreadable: {relative.as_posix()}"
            ) from exc
        if stat.S_ISLNK(mode):
            raise ScaleSourcePoolEvidencePathError(
                f"{label} must not traverse a symlink: {relative.as_posix()}"
            )
        final = index == len(relative.parts) - 1
        if (not final and not stat.S_ISDIR(mode)) or (
            final and not stat.S_ISREG(mode)
        ):
            raise ScaleSourcePoolEvidencePathError(
                f"{label} is not a regular evidence file: {relative.as_posix()}"
            )
    return current


def compute_evidence_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ScaleSourcePoolEvidencePathError(
            f"evidence file became unreadable: {path}"
        ) from exc
    return "sha256:" + digest.hexdigest()


__all__ = [
    "ScaleSourcePoolEvidencePathError",
    "compute_evidence_file_sha256",
    "resolve_evidence_directory",
    "resolve_evidence_file",
    "resolve_evidence_root",
]
