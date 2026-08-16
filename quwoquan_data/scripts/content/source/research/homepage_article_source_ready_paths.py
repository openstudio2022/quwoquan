"""Safe path resolution for homepage/article source-ready batches."""

from __future__ import annotations

import stat

from content.source.research.homepage_article_source_ready_batch import (
    SOURCE_INVALID_EVIDENCE,
    HomepageArticleSourceReadyBatchError,
    Path,
)


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
        if (final and not stat.S_ISREG(mode)) or (not final and not stat.S_ISDIR(mode)):
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
        roots = (
            (base,)
            if raw == "."
            else (
                base,
                *(
                    base.joinpath(*relative.parts[:index])
                    for index in range(1, len(relative.parts) + 1)
                ),
            )
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
