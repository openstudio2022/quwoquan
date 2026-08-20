"""Physical evidence validation support for source-ready batch capsules."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from core.io import read_json
from content.source.research.homepage_article_source_ready_provenance import (
    verify_source_ready_provenance,
)

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
BATCH_SCHEMA = "quwoquan_data.homepage_article_source_ready_batch"
CAPSULE_SCHEMA = "quwoquan_data.homepage_article_source_ready_candidate"


class HomepageArticleSourceReadyBatchError(ValueError):
    """Typed physical-evidence or pool shortfall blocker."""

    def __init__(self, code: str, issues: Sequence[object]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("source-ready batch error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_file(root: Path, ref: object, *, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be a non-empty relative reference"],
        )
    current = root.expanduser().resolve()
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} is missing: {relative.as_posix()}"],
            ) from exc
        if stat.S_ISLNK(mode):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} must not traverse a symlink: {relative.as_posix()}"],
            )
        final = index == len(relative.parts) - 1
        if (final and not stat.S_ISREG(mode)) or (
            not final and not stat.S_ISDIR(mode)
        ):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} must resolve to a regular file: {relative.as_posix()}"],
            )
    return current


def _safe_directory(root: Path, ref: object, *, label: str) -> Path:
    base = root.expanduser().absolute()
    raw = str(ref or "").strip()
    relative = Path(raw)
    if raw != "." and (not raw or relative.is_absolute() or ".." in relative.parts):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label} must be a safe relative directory"]
        )
    try:
        roots = (base,) if raw == "." else (
            base,
            *(base.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)),
        )
        for current in roots:
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise OSError("symlink or non-directory")
    except OSError as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label} is missing or not a real directory"]
        ) from exc
    return roots[-1]


def _load_json_file(
    root: Path,
    binding: Mapping[str, Any],
    *,
    label: str,
    digest_field: str | None = None,
) -> tuple[dict[str, Any], Path]:
    path = _safe_file(root, binding.get("ref"), label=label)
    actual_file_sha = _file_sha256(path)
    if actual_file_sha != binding.get("fileSha256"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} fileSha256 drift"],
        )
    try:
        document = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} is not readable JSON: {exc}"],
        ) from exc
    if not isinstance(document, dict):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be one JSON object"],
        )
    if digest_field and document.get(digest_field) != binding.get("digest"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} {digest_field} drift"],
        )
    return document, path


def _verify_bound_file(
    root: Path,
    binding: Mapping[str, Any],
    *,
    label: str,
) -> str:
    path = _safe_file(root, binding.get("ref"), label=label)
    actual = _file_sha256(path)
    if actual != binding.get("fileSha256"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} physical bytes drift"],
        )
    expected_content = str(binding.get("contentSha256") or "")
    if expected_content and actual != expected_content:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} contentSha256 drift"],
        )
    return actual


def _verify_provenance(root: Path, provenance: Mapping[str, Any], *, label: str) -> None:
    def reject(issue: str) -> NoReturn:
        raise HomepageArticleSourceReadyBatchError(SOURCE_INVALID_EVIDENCE, [issue])

    verify_source_ready_provenance(
        root,
        provenance,
        label=label,
        load_json_file=_load_json_file,
        safe_file=_safe_file,
        file_sha256=_file_sha256,
        reject=reject,
    )


def _verify_raw_source_evidence(
    root: Path, provenance: Mapping[str, Any], *, label: str
) -> None:
    binding = {
        "ref": provenance.get("discoveryEvidenceRef"),
        "fileSha256": provenance.get("discoveryEvidenceFileSha256"),
    }
    evidence, _ = _load_json_file(root, binding, label=f"{label}.acquisition")
    if evidence.get("schema") != (
        "quwoquan_data.homepage_article_source_ready_acquisition_evidence"
    ):
        return
    source_unit = evidence.get("sourceUnit")
    if not isinstance(source_unit, Mapping):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label}.sourceUnit is missing"]
        )
    _verify_bound_file(
        root,
        {
            "ref": source_unit.get("rawEvidenceRef"),
            "fileSha256": source_unit.get("rawEvidenceFileSha256"),
        },
        label=f"{label}.rawEvidence",
    )


