"""candidate 根内 symlink-safe 的打开/读取/校验原语（逐字迁自原单文件）。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


class _UnsafeCandidatePath(ValueError):
    pass


def _candidate_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("candidate verification requires O_NOFOLLOW/O_DIRECTORY")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _candidate_file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("candidate verification requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _candidate_relative_path(value: str | Path, *, label: str) -> Path:
    reference = Path(value)
    if (
        reference.is_absolute()
        or not reference.parts
        or any(part in {"", ".", ".."} for part in reference.parts)
    ):
        raise _UnsafeCandidatePath(f"{label} escapes the candidate root")
    return reference


def _open_candidate_root(
    candidate_root: Path,
    *,
    label: str,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Open every absolute candidate ancestor without following symlinks."""

    absolute = Path(candidate_root).expanduser().absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise _UnsafeCandidatePath(f"{label} candidate root is unsafe")
    try:
        descriptor = os.open(Path(absolute.anchor), _candidate_directory_flags())
    except OSError as exc:
        raise _UnsafeCandidatePath(
            f"{label} candidate filesystem root is unavailable"
        ) from exc
    identities: list[tuple[int, int]] = []
    try:
        root_info = os.fstat(descriptor)
        if not stat.S_ISDIR(root_info.st_mode):
            raise _UnsafeCandidatePath(
                f"{label} candidate filesystem root is not a directory"
            )
        identities.append((root_info.st_dev, root_info.st_ino))
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} candidate ancestor is a symlink, missing, or "
                    f"non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} candidate ancestor is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _open_candidate_parent(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    descriptor, root_identities = _open_candidate_root(
        candidate_root,
        label=label,
    )
    identities = list(root_identities)
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(
                    part,
                    _candidate_directory_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise _UnsafeCandidatePath(
                    f"{label} parent is missing, a symlink, or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeCandidatePath(
                    f"{label} parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_candidate_parent(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
    expected_identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    os.close(descriptor)
    if identities != expected_identities:
        raise _UnsafeCandidatePath(f"{label} parent changed during access")


def _open_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> tuple[int, int, Path, tuple[tuple[int, int], ...], tuple[int, int]]:
    relative = _candidate_relative_path(relative_value, label=label)
    parent_descriptor, identities = _open_candidate_parent(
        candidate_root,
        relative,
        label=label,
    )
    try:
        try:
            before = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise _UnsafeCandidatePath(f"{label} is missing or unsafe") from exc
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeCandidatePath(f"{label} is a symlink or non-regular file")
        try:
            descriptor = os.open(
                relative.name,
                _candidate_file_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeCandidatePath(f"{label} is a symlink or unreadable") from exc
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or identity != (
            before.st_dev,
            before.st_ino,
        ):
            os.close(descriptor)
            raise _UnsafeCandidatePath(f"{label} changed during validation")
        return descriptor, parent_descriptor, relative, identities, identity
    except Exception:
        os.close(parent_descriptor)
        raise


def _revalidate_candidate_file(
    candidate_root: Path,
    relative: Path,
    *,
    label: str,
    expected_parent_identities: tuple[tuple[int, int], ...],
    expected_file_identity: tuple[int, int],
) -> None:
    descriptor, parent_descriptor, _relative, identities, identity = (
        _open_candidate_file(candidate_root, relative, label=label)
    )
    os.close(descriptor)
    os.close(parent_descriptor)
    if (
        identities != expected_parent_identities
        or identity != expected_file_identity
    ):
        raise _UnsafeCandidatePath(f"{label} changed during validation")


def _read_candidate_bytes(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> bytes:
    descriptor, parent_descriptor, relative, identities, identity = (
        _open_candidate_file(candidate_root, relative_value, label=label)
    )
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read()
        _revalidate_candidate_file(
            candidate_root,
            relative,
            label=label,
            expected_parent_identities=identities,
            expected_file_identity=identity,
        )
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _read_candidate_object(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_candidate_bytes(
                candidate_root,
                relative_value,
                label=label,
            ).decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _sha256_candidate_file(
    candidate_root: Path,
    relative_value: str | Path,
    *,
    label: str,
) -> str:
    payload = _read_candidate_bytes(candidate_root, relative_value, label=label)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_candidate_artifact_ref(
    value: object,
    *,
    prefix: str,
    label: str,
) -> str:
    reference = str(value or "").strip()
    path = Path(reference)
    if (
        not reference.startswith(prefix)
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != reference
    ):
        raise ValueError(f"{label} artifactRef is invalid")
    return reference
