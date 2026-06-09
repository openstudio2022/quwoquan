"""来源单元 + 对象证据链统一读写（真相源：docs/pipeline_directory_layout_spec.md）。

替代「对象级散落 images/ + 来源与图片分离」的旧布局。每个来源是一个自包含、
编号、带类目与相关性说明的单元（命名/文件名对齐 docs/pipeline_directory_layout_spec.md §0/§3）：

    {object}/1.download/sources/{NN}.{sourceKind}/
        meta.json            # url/title/sourceKind/relevance（与对象相关性）
        source.md            # 原文
        source.clean.md      # 清洗正文
        page.html            # 存档（可选）
        source.quality.json  # 来源质量
        assets/{NNN}_{slug}.{ext}   # 该来源自带图片
        assets/index.json    # 每图 sourceAssetId/fileName/url/sha256/license/relevance/variants

证据链：source -> source asset -> writing pack asset -> article asset:// ->
post assets/{assetId} -> manifest.sourceAssetRef（相对 batch 根）。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, write_json
from _common.image_variants import build_local_variants, image_dimensions
from _common.paths import (
    STAGE_DOWNLOAD,
    batch_entity_object_dir,
    relative_batch_ref,
    source_unit_dir,
)
from _common.entity_extract import resolve_domain_etype

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")


def slugify(value: str) -> str:
    """可读 slug：保留中文/字母数字，连续非法折叠为 _。"""
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return s or "asset"


def resolve_entity_object_dir(
    task_id: str,
    batch_id: str,
    ref_or_name: str,
    *,
    etype_hint: str = "",
) -> Path:
    """从 entityRef（/entity/{domain}/{type}/{name} 或 {domain}/{type}/{name}）
    或裸名 + etype_hint 解析实体对象目录（与 publish DataRoot 同构）。"""
    raw = str(ref_or_name or "").strip().strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        domain, etype, name = parts[0], parts[1], parts[-1]
    else:
        name = parts[-1] if parts else raw
        domain, etype = resolve_domain_etype(etype_hint)
    return batch_entity_object_dir(task_id, batch_id, domain, etype, name)


# ─── 写：来源单元 ──────────────────────────────────────────────────
def write_source_unit(
    object_dir: Path,
    *,
    ordinal: int,
    source_id: str,
    source_md: str,
    clean_md: str = "",
    html_bytes: bytes | None = None,
    quality: Mapping[str, Any] | None = None,
    platform: str = "",
    source_category: str = "",
    url: str = "",
    title: str = "",
    target_ref: str = "",
    relevance: str = "",
    images: Sequence[Mapping[str, Any]] | None = None,
    task_id: str = "",
    batch_id: str = "",
) -> dict[str, Any]:
    """写一个来源单元，返回其 manifest（含 assets.index 摘要）。

    images 每项：{bytes|sourcePath, url, license, credit, caption, relevance, contentType}
    图片落 assets/{NNN}_{slug}.{ext}，并写 assets/index.json（含 sha256/relevance）。
    """
    unit = source_unit_dir(object_dir, ordinal, source_id)
    unit.mkdir(parents=True, exist_ok=True)
    (unit / "source.md").write_text(source_md, encoding="utf-8")
    if clean_md:
        (unit / "source.clean.md").write_text(clean_md, encoding="utf-8")
    if html_bytes is not None:
        (unit / "page.html").write_bytes(html_bytes)
    if quality is not None:
        write_json(unit / "source.quality.json", dict(quality))

    asset_index: list[dict[str, Any]] = []
    assets_dir = unit / "assets"
    for k, img in enumerate(images or [], start=1):
        ext = str(img.get("ext") or _ext_from_name(img.get("fileName") or img.get("url") or "") or ".jpg")
        slug = slugify(img.get("slug") or img.get("role") or source_id)
        base_name = f"{k:03d}_{slug}"
        file_name = f"{base_name}{ext}"
        dest = assets_dir / file_name
        body = img.get("bytes")
        if body is not None:
            assets_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
        elif img.get("sourcePath"):
            src = Path(str(img["sourcePath"]))
            if not src.is_file():
                raise FileNotFoundError(f"source asset missing: {src}")
            assets_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            body = dest.read_bytes()
        else:
            continue
        sha = "sha256:" + hashlib.sha256(dest.read_bytes()).hexdigest()
        # 像素尺寸（清晰度门 + 变体源尺寸）。
        width = img.get("width")
        height = img.get("height")
        if (not width or not height) and body is not None:
            dims = image_dimensions(body)
            if dims:
                width, height = dims
        # 多变体格式化：按 IMAGE_VARIANT_PROFILES 物理压 webp（仅缩小），落同名 .variants/ 子目录。
        variants_meta: list[dict[str, Any]] = []
        for var in build_local_variants(body or b"", base_name=base_name):
            var_bytes = var.pop("bytes")
            var_path = assets_dir / var["fileName"]
            var_path.parent.mkdir(parents=True, exist_ok=True)
            var_path.write_bytes(var_bytes)
            variants_meta.append(var)
        entry = {
            "sourceAssetId": f"{ordinal:03d}_{k:03d}",
            "fileName": file_name,
            "url": str(img.get("url") or ""),
            "sourceUrl": str(img.get("sourceUrl") or img.get("url") or ""),
            "contentType": str(img.get("contentType") or ""),
            "width": int(width) if width else 0,
            "height": int(height) if height else 0,
            "bytes": dest.stat().st_size,
            "sha256": sha,
            "license": str(img.get("license") or ""),
            "credit": str(img.get("credit") or ""),
            "termsUrl": str(img.get("termsUrl") or ""),
            "licenseSnapshot": str(img.get("licenseSnapshot") or ""),
            "usageScope": str(img.get("usageScope") or ""),
            "caption": str(img.get("caption") or ""),
            "relevance": str(img.get("relevance") or relevance or ""),
            "variants": variants_meta,
        }
        asset_index.append(entry)
    if asset_index:
        (unit / "assets").mkdir(parents=True, exist_ok=True)
        write_json(unit / SOURCE_UNIT_ASSET_INDEX, {"assets": asset_index})

    manifest = {
        "schemaVersion": "quwoquan_data.source_unit",
        "sourceId": source_id,
        "ordinal": ordinal,
        "sourceKind": source_category or platform or "web",
        "platform": platform or "web",
        "url": url,
        "title": title,
        "relevance": {
            "targetRef": target_ref,
            "reason": relevance or "覆盖该对象的基础事实/交通/季节等",
        },
        "assetCount": len(asset_index),
    }
    write_json(unit / SOURCE_UNIT_MANIFEST, manifest)
    return manifest


def _ext_from_name(name: str) -> str:
    suffix = Path(str(name).split("?")[0]).suffix.lower()
    return suffix if suffix in _IMAGE_EXTS else ""


# ─── 读：来源单元与候选图（含证据链相对引用）────────────────────────
def iter_source_units(object_dir: Path) -> list[Path]:
    base = object_dir / STAGE_DOWNLOAD / "sources"
    if not base.is_dir():
        return []
    units = [d for d in base.iterdir() if d.is_dir() and _UNIT_RE.match(d.name)]
    return sorted(units, key=lambda d: d.name)


def find_entity_object_dirs(task_id: str, batch_id: str, name: str) -> list[Path]:
    """按实体名在批次 entities/** 下定位对象目录（含 1.download 来源单元者）。

    新布局来源单元在对象目录下，produce/quality 读取时无需 domain/type，
    用名字定位即可（同名跨类目极少；命中多个时全部返回，调用方合并）。
    """
    from _common.paths import batch_root

    entities_root = batch_root(task_id, batch_id) / "entities"
    if not entities_root.is_dir():
        return []
    out: list[Path] = []
    for src_dir in entities_root.rglob(f"{name}/{STAGE_DOWNLOAD}/sources"):
        obj = src_dir.parent.parent
        if obj.name == name:
            out.append(obj)
    return sorted(set(out))


def object_image_candidates(
    object_dir: Path, task_id: str, batch_id: str
) -> list[dict[str, Any]]:
    """对象的可选图候选（新布局：来源单元 assets/）。

    每项：{path, sourceRef(相对), sourceAssetRef(相对), caption, relevance}。
    """
    out: list[dict[str, Any]] = []
    for unit in iter_source_units(object_dir):
        index = {}
        idx_path = unit / SOURCE_UNIT_ASSET_INDEX
        if idx_path.is_file():
            by_name = {a.get("fileName"): a for a in (read_json(idx_path).get("assets") or [])}
            index = by_name
        assets_dir = unit / "assets"
        if not assets_dir.is_dir():
            continue
        source_md = unit / "source.md"
        source_ref = relative_batch_ref(source_md, task_id, batch_id) if source_md.is_file() else ""
        for asset in sorted(assets_dir.iterdir()):
            if not asset.is_file() or asset.suffix.lower() not in _IMAGE_EXTS:
                continue
            meta = index.get(asset.name, {})
            out.append(
                {
                    "path": asset,
                    "sourceRef": source_ref,
                    "sourceAssetRef": relative_batch_ref(asset, task_id, batch_id),
                    "caption": meta.get("caption", ""),
                    "relevance": meta.get("relevance", ""),
                }
            )
    return out


__all__ = [
    "SOURCE_UNIT_MANIFEST",
    "SOURCE_UNIT_ASSET_INDEX",
    "slugify",
    "resolve_entity_object_dir",
    "write_source_unit",
    "iter_source_units",
    "find_entity_object_dirs",
    "object_image_candidates",
]
