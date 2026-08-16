"""Media helpers for canonical post transaction packaging."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_rel,
)


def post_asset_path(post_root: Path, raw: Mapping[str, Any]) -> Path:
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


def media_dimensions(path: Path, raw: Mapping[str, Any]) -> tuple[int, int, str]:
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


def copy_post_surface(source: Path, target: Path) -> str:
    for name in ("article.md", "video.md", "provenance.json", "subtitles.vtt"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)
    assets = source / "assets"
    if assets.is_dir():
        shutil.copytree(assets, target / "assets")
    if (target / "article.md").is_file():
        return "article.md"
    if (target / "assets/video.mp4").is_file():
        return "assets/video.mp4"
    candidates = sorted(
        path for path in (target / "assets").glob("*") if path.is_file()
    )
    if candidates:
        return candidates[0].relative_to(target).as_posix()
    raise ObjectTransactionError("post object has no final publishable content")
