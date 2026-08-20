"""Canonical post surface and media projection helpers."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_id,
    _safe_rel,
)


def _post_asset_path(post_root: Path, raw: Mapping[str, Any]) -> Path:
    file_name = str(raw.get("fileName") or "").strip()
    if not file_name:
        raise ObjectTransactionError("post manifest asset 缺 fileName")
    relative = _safe_rel(file_name, label="manifest.assets.fileName")
    direct = post_root / relative
    nested = post_root / "assets" / relative
    path = direct if direct.is_file() else nested
    if not path.is_file():
        raise ObjectTransactionError(f"post manifest asset 不存在：{file_name}")
    return path


def _media_dimensions(path: Path, raw: Mapping[str, Any]) -> tuple[int, int, str]:
    mime = str(raw.get("mimeType") or "").strip()
    if mime.startswith("video/"):
        width = int(raw.get("width") or 0)
        height = int(raw.get("height") or 0)
        if width < 1 or height < 1:
            raise ObjectTransactionError(f"video asset 缺有效尺寸：{path}")
        return width, height, mime
    from core.image_decode import probe_image_path

    probe = probe_image_path(path)
    if not probe.succeeded:
        raise ObjectTransactionError(
            f"post image asset 不可解析：{path}: {probe.failure.value}"
        )
    resolved_mime = probe.mime_type or mime
    if probe.width < 1 or probe.height < 1 or not resolved_mime.startswith("image/"):
        raise ObjectTransactionError(f"post image asset 缺有效尺寸或 MIME：{path}")
    return probe.width, probe.height, resolved_mime


def _copy_post_surface(source: Path, target: Path) -> None:
    """Copy the reviewed post surface into the transaction package.

    The package still carries the bodies alongside the documents, because the
    transaction is what admits them into the content library. Which of those
    files canonical publish ends up owning is decided once, in
    ``build_transaction_delta``, not by what is copied here.
    """
    for name in ("article.md", "video.md", "provenance.json", "subtitles.vtt"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)
    assets = source / "assets"
    if assets.is_dir():
        shutil.copytree(assets, target / "assets")


def _final_content_ref(target: Path, *, holds_media: bool) -> str:
    """Name the document a consumer opens first for one canonical post.

    It must name a document, because canonical publish holds no media body: an
    image post therefore points at its asset reference record, which is the
    surface that resolves the work's bodies in the content library.
    """
    if (target / "article.md").is_file():
        return "article.md"
    if (target / "video.md").is_file():
        return "video.md"
    if holds_media:
        return "asset.refs.json"
    raise ObjectTransactionError("post object has no final publishable content")


def _creator_ref(manifest: Mapping[str, Any]) -> str:
    ref = str(manifest.get("creatorProfileId") or "").strip()
    if not ref:
        raise ObjectTransactionError("post manifest 缺 creatorProfileId")
    return _safe_id(ref, label="creatorProfileId")


__all__ = [
    "_copy_post_surface",
    "_creator_ref",
    "_final_content_ref",
    "_media_dimensions",
    "_post_asset_path",
]
