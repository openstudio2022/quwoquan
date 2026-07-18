"""媒体公开交付清单与环境端点组合的唯一 Python 边界。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "quwoquan_ops" / "environments" / "media_delivery_manifest.json"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MEDIA_BASE_KEY = {
    "avatar": "mediaAvatar",
    "image": "mediaImage",
    "background": "mediaImage",
    "video": "mediaVideo",
    "attachment": "mediaImage",
}


def load_media_delivery_manifest(
    path: Path = MANIFEST_PATH,
) -> list[dict[str, Any]]:
    """加载并严格校验环境无关的逻辑媒体资产清单。"""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 media delivery manifest: {path}: {exc}") from exc
    if document.get("schema") != "media-delivery-manifest":
        raise ValueError(f"{path} schema 必须是 media-delivery-manifest")
    assets = document.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError(f"{path} assets 必须是非空数组")

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(assets):
        if not isinstance(raw, dict):
            raise ValueError(f"{path} assets[{index}] 必须是对象")
        logical_id = str(raw.get("logicalAssetId") or "").strip()
        media_type = str(raw.get("mediaType") or "").strip()
        public_slice_key = str(raw.get("publicSliceKey") or "").strip().lstrip("/")
        sha256 = str(raw.get("sha256") or "").strip().lower()
        version = raw.get("version")
        mime_type = str(raw.get("mimeType") or "").strip().lower()
        if not logical_id or logical_id in seen_ids:
            raise ValueError(f"{path} assets[{index}] logicalAssetId 缺失或重复")
        if media_type not in _MEDIA_BASE_KEY:
            raise ValueError(f"{path} assets[{index}] mediaType 非法: {media_type!r}")
        if not _is_canonical_public_slice_key(public_slice_key):
            raise ValueError(
                f"{path} assets[{index}] publicSliceKey 不是 canonical 公共路径"
            )
        if public_slice_key in seen_keys:
            raise ValueError(f"{path} assets[{index}] publicSliceKey 重复")
        if not isinstance(version, int) or version <= 0:
            raise ValueError(f"{path} assets[{index}] version 必须是正整数")
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError(f"{path} assets[{index}] sha256 必须是 sha256:hex")
        if "/" not in mime_type:
            raise ValueError(f"{path} assets[{index}] mimeType 非法")
        seen_ids.add(logical_id)
        seen_keys.add(public_slice_key)
        validated.append(
            {
                "logicalAssetId": logical_id,
                "mediaType": media_type,
                "publicSliceKey": public_slice_key,
                "version": version,
                "sha256": sha256,
                "mimeType": mime_type,
            }
        )
    return validated


def build_media_delivery_url(
    public_bases: dict[str, Any],
    asset: dict[str, Any],
    *,
    require_https: bool = True,
) -> str:
    """按当前 target 注入的 endpoint 构建唯一媒体 URL，不进行 host/path 回退。"""
    media_type = str(asset["mediaType"])
    base_key = _MEDIA_BASE_KEY[media_type]
    raw_base = str(public_bases.get(base_key) or "").strip().rstrip("/")
    parsed = urlsplit(raw_base)
    allowed_schemes = {"https"} if require_https else {"http", "https"}
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        scheme_label = "HTTPS" if require_https else "HTTP(S)"
        raise ValueError(
            f"{base_key} 必须是无 query/fragment 的 {scheme_label} public base"
        )
    public_slice_key = str(asset["publicSliceKey"]).lstrip("/")
    return f"{raw_base}/{public_slice_key}?v={int(asset['version'])}"


def _is_canonical_public_slice_key(value: str) -> bool:
    if not value or value.startswith("/") or "://" in value or "?" in value or "#" in value:
        return False
    segments = value.split("/")
    return all(
        segment and segment not in {".", ".."} and "\\" not in segment
        for segment in segments
    )
