"""Shared helpers for article post packages (materialize + promote)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from _common.asset_identity import (
    compute_post_asset_id as _compute_post_asset_id,
    parse_post_asset_id as _parse_post_asset_id,
)

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


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def canonicalize_markdown(markdown: str) -> str:
    normalized = _normalize_newlines(markdown).rstrip() + "\n"
    if not normalized.startswith("---\n"):
        return normalized
    parts = normalized.split("\n---\n", 1)
    if len(parts) != 2:
        return normalized
    front_raw = parts[0][4:]
    body = parts[1]
    loaded = yaml.safe_load(front_raw) or {}
    if not isinstance(loaded, dict):
        return normalized
    canonical_front = yaml.safe_dump(
        loaded,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{canonical_front}\n---\n{body}"


def compute_document_sha256(markdown: str) -> str:
    return sha256_text(canonicalize_markdown(markdown))


def compute_asset_manifest_sha256(assets: list[dict[str, Any]]) -> str:
    canonical_assets: list[dict[str, Any]] = []
    for item in assets:
        canonical_assets.append(
            {
                "assetId": item.get("assetId", ""),
                "kind": item.get("kind", "image"),
                "objectKey": item.get("objectKey", ""),
                "sha256": item.get("sha256", ""),
                "mimeType": item.get("mimeType", ""),
                "width": item.get("width", 0),
                "height": item.get("height", 0),
                "durationMs": item.get("durationMs", 0),
            }
        )
    canonical_assets.sort(key=lambda item: (str(item.get("assetId") or ""), str(item.get("objectKey") or "")))
    return _canonical_json_digest(canonical_assets)


def compute_document_version_sha256(
    *,
    document_sha256: str,
    asset_manifest_sha256: str,
    render_profile: dict[str, Any] | None = None,
) -> str:
    return _canonical_json_digest(
        {
            "documentSha256": document_sha256,
            "assetManifestSha256": asset_manifest_sha256,
            "renderProfile": render_profile or {},
        }
    )


def asset_id_from_object_key(object_key: str) -> str:
    """Stable, readable, collision-free asset id derived from objectKey.

    旧实现把非 ASCII（如中文实体名）整段塌缩成一长串下划线，导致 assetId 看不出
    对应哪张图 / 哪个实体（评审痛点）。新实现：保留可读 token（含中文实体名），
    把连续非法字符折叠为单个 `_`，再追加 objectKey 的 sha1 前 8 位保证唯一。
    系统内 entityRefs/tagRefs 本就大量使用中文路径，assetId 含中文与之一致，且
    asset:// 仅在 manifest/markdown 内部闭环（由 verify_asset_refs 校验）。
    """
    readable = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", object_key).strip("_")
    digest = hashlib.sha1(object_key.encode("utf-8")).hexdigest()[:8]
    return f"data_asset_{readable}_{digest}" if readable else f"data_asset_{digest}"


def compute_post_asset_id(
    *,
    entity_name: str,
    role: str,
    global_batch_seq: int | str,
    ref: str = "",
    nonce: int = 0,
) -> str:
    """成品图统一命名：实体_角色_全局批次号_hash。"""
    return _compute_post_asset_id(
        entity_name=entity_name,
        role=role,
        global_batch_seq=global_batch_seq,
        ref=ref,
        nonce=nonce,
    )


def post_asset_id(
    *,
    entity_name: str,
    role: str,
    global_batch_seq: int | str,
    ref: str = "",
    nonce: int = 0,
) -> str:
    return compute_post_asset_id(
        entity_name=entity_name,
        role=role,
        global_batch_seq=global_batch_seq,
        ref=ref,
        nonce=nonce,
    )


def parse_post_asset_id(asset_id: str) -> dict[str, Any]:
    return _parse_post_asset_id(asset_id)


# 图片角色 → 语义说明词（gallery caption 兜底用，避免直接堆实体名/文件名）。
_ROLE_CAPTION_WORDS = {"cover": "封面", "closing": "回望", "node": "实景"}


def semantic_asset_caption(item: dict[str, Any]) -> str:
    """图片语义说明：优先用创作时写的 caption；否则按 实体名·角色 兜底，绝不退回文件名。"""
    caption = str(item.get("caption") or "").strip()
    name = str(item.get("entityName") or "").strip()
    role = str(item.get("role") or "").strip()
    # caption 若只是裸实体名（旧行为），用角色补一层语义；agent 写的真实说明原样保留。
    if caption and caption != name:
        return caption
    role_word = _ROLE_CAPTION_WORDS.get(role, "实景")
    if name:
        return f"{name} · {role_word}"
    return caption or "配图"


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
        caption = semantic_asset_caption(item)
        lines.append(f"- **{caption}**: `asset://{aid}`\n")
    return "".join(lines)


def build_article_asset_manifest(
    article_markdown: str,
    assets: list[dict[str, Any]],
    *,
    render_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document_sha256 = compute_document_sha256(article_markdown)
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
        if item.get("mimeType"):
            entry["mimeType"] = item["mimeType"]
        if item.get("durationMs"):
            entry["durationMs"] = item["durationMs"]
        manifest_assets.append(entry)
    asset_manifest_sha256 = compute_asset_manifest_sha256(manifest_assets)
    document_version_sha256 = compute_document_version_sha256(
        document_sha256=document_sha256,
        asset_manifest_sha256=asset_manifest_sha256,
        render_profile=render_profile,
    )
    return {
        "schemaVersion": 1,
        "articleMarkdownVersion": MARKDOWN_VERSION,
        "articleMarkdownDigest": document_sha256,
        "documentSha256": document_sha256,
        "assetManifestSha256": asset_manifest_sha256,
        "documentVersionSha256": document_version_sha256,
        "assets": manifest_assets,
    }


def copy_asset_files(
    assets: list[dict[str, Any]],
    assets_dir: Path,
    download_images_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Copy image files into post assets/ and fill sha256.

    Fail closed: manifest must never declare an asset that is not present on disk.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for item in assets:
        file_name = item.get("fileName") or f"{item['assetId']}.jpg"
        dest = assets_dir / file_name
        src_path = item.get("sourcePath")
        copied = False
        if src_path:
            src = Path(src_path)
            if src.is_file():
                shutil.copy2(src, dest)
                copied = True
            else:
                raise FileNotFoundError(f"asset sourcePath missing: {src_path} (assetId={item.get('assetId')})")
        elif download_images_dir and download_images_dir.is_dir():
            candidate = download_images_dir / file_name
            if candidate.is_file():
                shutil.copy2(candidate, dest)
                copied = True
        else:
            raise FileNotFoundError(f"asset has no sourcePath and no download image dir: {item.get('assetId')}")
        if not copied and not dest.is_file():
            raise FileNotFoundError(f"asset file could not be resolved: {file_name} (assetId={item.get('assetId')})")
        if dest.is_file():
            item = {**item, "sha256": sha256_file(dest)}
        out.append(item)
    return out
