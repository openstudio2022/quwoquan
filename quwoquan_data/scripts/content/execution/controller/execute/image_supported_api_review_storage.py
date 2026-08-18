"""Safe immutable storage primitives for supported-API image review evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.paths import OUTPUT_ROOT
from content.source.professional_safety_evidence import file_sha256


class ImageSupportedApiReviewStorageError(ValueError):
    def __init__(self, code: str, detail: str, *, batch_fatal: bool = False) -> None:
        self.code = code
        self.detail = detail
        self.batch_fatal = batch_fatal
        super().__init__(f"{code}: {detail}")


def canonical_digest(value: Mapping[str, Any]) -> str:
    body = (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def write_review_json_once(path: Path, payload: Mapping[str, Any]) -> Path:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise ImageSupportedApiReviewStorageError(
                "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
                str(path),
                batch_fatal=True,
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def safe_review_file(root: Path, ref: object, *, require_file: bool = True) -> Path:
    relative = Path(str(ref or ""))
    candidate = (root / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or candidate == root
        or root not in candidate.parents
        or (require_file and not candidate.is_file())
        or (candidate.exists() and candidate.is_symlink())
    ):
        raise ImageSupportedApiReviewStorageError(
            "DATA.SOURCE.REVIEW_INPUT_UNSAFE",
            str(ref),
        )
    return candidate


def safe_review_ref(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if resolved == root.resolve() or root.resolve() not in resolved.parents:
        raise ImageSupportedApiReviewStorageError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            str(path),
        )
    return resolved.relative_to(root.resolve()).as_posix()


def portable_review_ref(path: Path, *, output_root: Path = OUTPUT_ROOT) -> str:
    root = output_root.resolve()
    candidate = path.resolve()
    if not candidate.is_relative_to(root):
        raise ImageSupportedApiReviewStorageError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            "evidence escapes output root",
        )
    return candidate.relative_to(root).as_posix()


def _read_nofollow(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def copy_review_file_once(source: Path, destination: Path) -> None:
    body = _read_nofollow(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != body:
            raise ImageSupportedApiReviewStorageError(
                "DATA.SOURCE.REVIEW_STAGING_CONFLICT",
                str(destination),
                batch_fatal=True,
            ) from None
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def validate_review_dependencies(
    preparation_root: Path,
    request: Mapping[str, Any],
) -> None:
    """Fail before dispatch when frozen source/CAS identity has drifted."""
    for field in ("originalAssetRef", "apiResponseRef", "machineAssessmentRef"):
        dependency = safe_review_file(preparation_root, request[field])
        expected_sha = request[field.removesuffix("Ref") + "Sha256"]
        if file_sha256(dependency) != expected_sha:
            raise ImageSupportedApiReviewStorageError(
                "DATA.SOURCE.REVIEW_SOURCE_IDENTITY_DRIFT",
                field,
            )


__all__ = [
    "ImageSupportedApiReviewStorageError",
    "canonical_digest",
    "copy_review_file_once",
    "portable_review_ref",
    "safe_review_file",
    "safe_review_ref",
    "validate_review_dependencies",
    "write_review_json_once",
]
