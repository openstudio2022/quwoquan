"""Canonical post surface and media projection helpers."""

from __future__ import annotations

import re
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


_MARKDOWN_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


def copy_markdown_surface(
    source: Path, target: Path, *, source_assets: list[dict[str, Any]],
    canonical_assets: list[dict[str, Any]],
) -> None:
    """只投影图片引用，保留正文其余字节；原稿与审核原件不写入。"""
    destinations = {str(row["assetId"]): str(row["path"]) for row in canonical_assets}
    aliases: dict[str, set[str]] = {}
    for asset in source_assets:
        asset_id = str(asset["assetId"])
        filename = str(asset.get("fileName") or "")
        bare = filename.removeprefix("assets/")
        refs = {filename, bare, f"assets/{bare}"}
        refs.update(asset.get("sourceAssetRefs") or [])
        if asset.get("sourceAssetRef"):
            refs.add(str(asset["sourceAssetRef"]))
        for ref in refs - {""}:
            aliases.setdefault(ref, set()).add(asset_id)

    def replace(match: re.Match[str]) -> str:
        ref = match.group(1)
        matches = aliases.get(ref, set())
        if len(matches) != 1 or not matches <= destinations.keys():
            raise ObjectTransactionError(
                f"DATA.PUBLISH.BODY_MEDIA_REF_INVALID: {ref!r}"
            )
        destination = _safe_rel(destinations[next(iter(matches))], label="body media path")
        body = target.parent / destination
        if body.is_symlink() or not body.is_file():
            raise ObjectTransactionError(f"DATA.PUBLISH.BODY_MEDIA_MISSING: {destination}")
        start, end = match.start(1) - match.start(), match.end(1) - match.start()
        return match.group()[:start] + destination.as_posix() + match.group()[end:]

    text = source.read_bytes().decode("utf-8")
    target.write_bytes(_MARKDOWN_IMAGE_RE.sub(replace, text).encode("utf-8"))

def _final_content_ref(target: Path, *, holds_media: bool) -> str:
    """Name the document a consumer opens first for one canonical post.

    It must name a document, because canonical publish holds no media body: an
    image post therefore points at its manifest, which also binds the work's
    ordered media bodies in the content library.
    """
    if (target / "article.md").is_file():
        return "article.md"
    if (target / "video.md").is_file():
        return "video.md"
    if holds_media:
        return "manifest.json"
    raise ObjectTransactionError("post object has no final publishable content")


def _creator_ref(manifest: Mapping[str, Any]) -> str:
    ref = str(manifest.get("creatorProfileId") or "").strip()
    if not ref:
        raise ObjectTransactionError("post manifest 缺 creatorProfileId")
    return _safe_id(ref, label="creatorProfileId")


__all__ = [
    "copy_markdown_surface",
    "_creator_ref",
    "_final_content_ref",
    "_media_dimensions",
    "_post_asset_path",
]
