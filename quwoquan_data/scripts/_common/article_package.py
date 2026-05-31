"""Shared helpers for article post packages (materialize + promote)."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

MARKDOWN_VERSION = "qwq-rich-md/1"


def sha256_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def asset_id_from_object_key(object_key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", object_key.replace("/", "_"))
    return f"data_asset_{safe}"


def infer_format_angle(tag_refs: list[str]) -> str:
    prefix = "Format/内容角度/"
    for ref in tag_refs:
        if ref.startswith(prefix):
            parts = ref[len(prefix) :].strip("/").split("/")
            return parts[-1] if parts else "攻略"
    return "攻略"


def build_gallery_markdown(title: str, assets: list[dict[str, Any]]) -> str:
    lines = [f"# {title}｜图集\n", "> 冷启动配图清单，正文通过 asset:// 引用。\n"]
    for item in assets:
        aid = item.get("assetId", "")
        caption = item.get("caption") or item.get("fileName", "")
        lines.append(f"- **{caption}**: `asset://{aid}`\n")
    return "".join(lines)


def build_article_asset_manifest(
    article_markdown: str,
    assets: list[dict[str, Any]],
) -> dict[str, Any]:
    digest = sha256_text(article_markdown)
    manifest_assets = []
    for item in assets:
        entry = {
            "assetId": item["assetId"],
            "kind": item.get("kind", "image"),
            "scope": item.get("scope", "cold_start"),
            "objectKey": item.get("objectKey", ""),
            "caption": item.get("caption", ""),
            "sha256": item.get("sha256", ""),
        }
        if item.get("width"):
            entry["width"] = item["width"]
        if item.get("height"):
            entry["height"] = item["height"]
        manifest_assets.append(entry)
    return {
        "schemaVersion": 1,
        "articleMarkdownVersion": MARKDOWN_VERSION,
        "articleMarkdownDigest": digest,
        "assets": manifest_assets,
    }


def copy_asset_files(
    assets: list[dict[str, Any]],
    assets_dir: Path,
    download_images_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Copy image files into post assets/ and fill sha256 when possible."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for item in assets:
        file_name = item.get("fileName") or f"{item['assetId']}.jpg"
        dest = assets_dir / file_name
        src_path = item.get("sourcePath")
        if src_path:
            src = Path(src_path)
            if src.is_file():
                shutil.copy2(src, dest)
        elif download_images_dir and download_images_dir.is_dir():
            candidate = download_images_dir / file_name
            if candidate.is_file():
                shutil.copy2(candidate, dest)
        if dest.is_file():
            item = {**item, "sha256": sha256_file(dest)}
        out.append(item)
    return out
