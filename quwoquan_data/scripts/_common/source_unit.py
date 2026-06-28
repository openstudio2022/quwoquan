"""来源单元 + 对象证据链统一读写（真相源：docs/pipeline_directory_layout_spec.md）。

替代「对象级散落 images/ + 来源与图片分离」的旧布局。每个来源是一个自包含、
编号、带类目与相关性说明的单元（命名/文件名对齐 docs/pipeline_directory_layout_spec.md §0/§3）：

    {object}/1.download/sources/{NN}.{sourceKind}/
        meta.json            # url/title/sourceKind/relevance（与对象相关性）
        source.md            # 原文
        source.clean.md      # 清洗正文
        page.html / page.raw.json  # 原始抓取快照（HTML 存 page.html，MediaWiki API JSON 存 page.raw.json）
        source.quality.json  # 来源质量
        assets/{NNN}_{slug}.{ext}   # 该来源自带图片
        assets/index.json    # 每图 sourceAssetId/fileName/url/sha256/license/relevance/variants

证据链：source -> source asset -> writing pack asset -> article asset:// ->
post assets/{assetId} -> manifest.sourceAssetRef（相对 batch 根）。
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, write_json
from _common import ops_governance as og
from _common.image_variants import build_local_variants, image_dimensions
from _common.paths import (
    STAGE_DOWNLOAD,
    batch_entity_object_dir,
    batch_root,
    relative_batch_ref,
    source_unit_dir,
)
from _common.entity_extract import require_domain_etype, resolve_domain_etype

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")


def slugify(value: str) -> str:
    """可读 slug：保留中文/字母数字，连续非法折叠为 _。"""
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return s or "asset"


_SOURCE_RAW_SNAPSHOT_NAMES = ("page.raw.json", "page.html")


def source_unit_raw_snapshot_name(raw_format: str = "") -> str:
    """原始抓取快照文件名：MediaWiki API JSON 存 page.raw.json，其它（HTML）存 page.html。"""
    return "page.raw.json" if str(raw_format or "").strip() == "mediawiki_api_json" else "page.html"


def find_source_unit_raw_snapshot(unit: Path) -> Path | None:
    """返回来源单元已有的原始快照文件（兼容 page.raw.json 与 page.html）。"""
    for name in _SOURCE_RAW_SNAPSHOT_NAMES:
        candidate = unit / name
        if candidate.is_file():
            return candidate
    return None


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
        if etype_hint:
            domain, etype = require_domain_etype(etype_hint, context=f"entity object path for {name}")
        else:
            domain, etype = resolve_domain_etype(etype_hint)
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    _raise_if_scenic_location_type_conflict(task_id, batch_id, domain, etype, name, current=obj)
    return obj


def _raise_if_scenic_location_type_conflict(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    current: Path,
) -> None:
    if domain != "地点" or etype not in {"景区", "打卡地"}:
        return
    sibling_type = "打卡地" if etype == "景区" else "景区"
    sibling = batch_entity_object_dir(task_id, batch_id, domain, sibling_type, name)
    if sibling == current or not sibling.exists():
        return
    if not any((sibling / marker).exists() for marker in ("_entity.json", "page.md", "1.download")):
        return
    raise ValueError(
        "entity type drift detected: same batch contains both "
        f"{domain}/{etype}/{name} and {domain}/{sibling_type}/{name}; "
        "must fail or explicitly correct, silent coexistence is forbidden"
    )


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
    source_use_mode: str = "",
    source_role: str = "",
    image_evidence_mode: str = "",
    research_lane: str = "",
    license_value: str = "",
    url: str = "",
    title: str = "",
    target_ref: str = "",
    relevance: str = "",
    images: Sequence[Mapping[str, Any]] | None = None,
    asset_funnel: Mapping[str, Any] | None = None,
    raw_format: str = "",
    task_id: str = "",
    batch_id: str = "",
    build_variants: bool = True,
) -> dict[str, Any]:
    """写一个来源单元，返回其 manifest（含 assets.index 摘要）。

    images 每项：{bytes|sourcePath, url, license, credit, caption, relevance, contentType}
    图片落 assets/{NNN}_{slug}.{ext}，并写 assets/index.json（含 sha256/relevance）。
    生产 download 主链路可传 build_variants=False，把 WebP 物理变体延后到
    media/release 阶段；原图、尺寸、hash、授权链仍在本阶段闭合。
    """
    unit = source_unit_dir(object_dir, ordinal, source_id)
    from _common.paths import STAGE_DOWNLOAD, ensure_object_stages

    ensure_object_stages(object_dir, through_stage=STAGE_DOWNLOAD)
    unit.mkdir(parents=True, exist_ok=True)
    (unit / "source.md").write_text(source_md, encoding="utf-8")
    if clean_md:
        (unit / "source.clean.md").write_text(clean_md, encoding="utf-8")
    if html_bytes is not None:
        # 原始快照按真实格式命名：MediaWiki API 返回 JSON，不能再误命名为 page.html。
        (unit / source_unit_raw_snapshot_name(raw_format)).write_bytes(html_bytes)
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
        variants_meta: list[dict[str, Any]] = []
        if build_variants:
            # 多变体格式化：按 IMAGE_VARIANT_PROFILES 物理压 webp（仅缩小），落同名 .variants/ 子目录。
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
            "requestedUrl": str(img.get("requestedUrl") or img.get("url") or ""),
            "normalizedFromUrl": str(img.get("normalizedFromUrl") or ""),
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
            "generationModel": str(img.get("generationModel") or ""),
            "generationPromptHash": str(img.get("generationPromptHash") or ""),
            "generatedAt": str(img.get("generatedAt") or ""),
            "syntheticDisclosure": str(img.get("syntheticDisclosure") or ""),
            "sourceCollectionId": str(img.get("sourceCollectionId") or ""),
            "creator": str(img.get("creator") or img.get("credit") or ""),
            "collectionPageUrl": str(img.get("collectionPageUrl") or img.get("sourceUrl") or ""),
            "authorizationProof": str(img.get("authorizationProof") or ""),
            "caption": str(img.get("caption") or ""),
            "relevance": str(img.get("relevance") or relevance or ""),
            "variants": variants_meta,
            "variantGeneration": "inline" if build_variants else "deferred",
        }
        asset_index.append(entry)
    if asset_index:
        (unit / "assets").mkdir(parents=True, exist_ok=True)
        index_payload: dict[str, Any] = {"assets": asset_index}
        if asset_funnel:
            # 候选/丢弃可审计：记录原始候选数、保留数、按原因聚合的丢弃明细与去重数。
            index_payload["funnel"] = dict(asset_funnel)
        write_json(unit / SOURCE_UNIT_ASSET_INDEX, index_payload)
    elif assets_dir.exists():
        # 本轮没有图片通过权利/抓取/像素/安全/相关性门时，旧 assets 不能继续作为可消费证据。
        shutil.rmtree(assets_dir)

    source_ref = ""
    if task_id and batch_id:
        try:
            source_ref = relative_batch_ref(unit / "source.md", task_id, batch_id)
        except Exception:  # noqa: BLE001
            source_ref = ""
    snapshot_hash = "sha256:" + hashlib.sha256(source_md.encode("utf-8")).hexdigest()
    manifest = {
        "schemaVersion": "quwoquan_data.source_unit",
        "sourceUnitId": og.source_unit_id(
            canonical_url=url,
            snapshot_hash=snapshot_hash,
            source_ref=source_ref or str(unit),
        ),
        "sourceId": source_id,
        "ordinal": ordinal,
        "sourceKind": source_category or platform or "web",
        "category": source_category or platform or "web",
        "platform": platform or "web",
        "sourceUseMode": source_use_mode,
        "sourceRole": source_role,
        "imageEvidenceMode": image_evidence_mode,
        "researchLane": research_lane,
        "license": license_value,
        "url": url,
        "snapshotHash": snapshot_hash,
        "title": title,
        "relevance": {
            "targetRef": target_ref,
            "reason": relevance or "覆盖该对象的基础事实/交通/季节等",
        },
        "assetCount": len(asset_index),
    }
    # 实体聚焦度落盘（单一真相源 _common.entity_focus）：仅文本 article 底稿需要，
    # 供选源弃稿门、content_plan 门与 scale_readiness 准出口径共同消费。图片相关性
    # 另有图像门把关，不在此落 verdict 以免误伤。
    if str(research_lane or "").strip() == "article":
        from _common.entity_focus import classify_entity_focus

        entity_name = str(target_ref or "").rstrip("/").rsplit("/", 1)[-1]
        focus_score, focus_verdict = classify_entity_focus(
            source_md, entity_name, title=title
        )
        manifest["entityFocusScore"] = focus_score
        manifest["entityFocusVerdict"] = focus_verdict
    if asset_funnel:
        manifest["assetFunnel"] = dict(asset_funnel)
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


def find_entity_object_dirs(
    task_id: str,
    batch_id: str,
    name: str,
    *,
    etype_hint: str = "",
) -> list[Path]:
    """按实体名在批次 entities/** 下定位对象目录（含 1.download 来源单元者）。

    新布局来源单元在对象目录下，produce/quality 读取时无需 domain/type，
    用名字定位即可（同名跨类目极少；命中多个时全部返回，调用方合并）。
    """
    from _common.paths import batch_root

    entities_root = batch_root(task_id, batch_id) / "entities"
    if not entities_root.is_dir():
        return []
    raw = str(name or "").strip().strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        return [resolve_entity_object_dir(task_id, batch_id, raw)]
    if etype_hint:
        return [resolve_entity_object_dir(task_id, batch_id, raw, etype_hint=etype_hint)]
    out: list[Path] = []
    for src_dir in entities_root.rglob(f"{raw}/{STAGE_DOWNLOAD}/sources"):
        obj = src_dir.parent.parent
        if obj.name == raw:
            out.append(obj)
    unique = sorted(set(out))
    scenic_pairs = {
        path.relative_to(entities_root).parts[1]
        for path in unique
        if len(path.relative_to(entities_root).parts) >= 3
        and path.relative_to(entities_root).parts[0] == "地点"
        and path.relative_to(entities_root).parts[1] in {"景区", "打卡地"}
    }
    if len(scenic_pairs) > 1:
        rels = sorted(path.relative_to(batch_root(task_id, batch_id)).as_posix() for path in unique)
        raise ValueError(
            f"entity type drift detected for '{raw}': dual scenic-location trees coexist -> {rels}"
        )
    return unique


def object_image_candidates(
    object_dir: Path, task_id: str, batch_id: str
) -> list[dict[str, Any]]:
    """对象的可选图候选（新布局：来源单元 assets/）。

    每项：{path, sourceRef(相对), sourceAssetRef(相对), sha256, caption, relevance}。
    """
    out: list[dict[str, Any]] = []
    for unit in iter_source_units(object_dir):
        unit_meta_path = unit / SOURCE_UNIT_MANIFEST
        unit_meta = read_json(unit_meta_path) if unit_meta_path.is_file() else {}
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
                    "sha256": meta.get("sha256") or "",
                    "caption": meta.get("caption", ""),
                    "relevance": meta.get("relevance", ""),
                    "sourceTitle": unit_meta.get("title") or "",
                    "sourceKind": unit_meta.get("sourceKind") or unit_meta.get("category") or "",
                    "researchLane": unit_meta.get("researchLane") or "",
                    "sourceCollectionId": meta.get("sourceCollectionId") or "",
                    "creator": meta.get("creator") or meta.get("credit") or "",
                    "collectionPageUrl": meta.get("collectionPageUrl") or meta.get("sourceUrl") or "",
                    "license": meta.get("license") or "",
                    "termsUrl": meta.get("termsUrl") or "",
                    "licenseSnapshot": meta.get("licenseSnapshot") or "",
                    "authorizationProof": meta.get("authorizationProof") or "",
                    "usageScope": meta.get("usageScope") or "",
                }
            )
    return out


def source_asset_sha256(source_asset_ref: Any, task_id: str, batch_id: str) -> str:
    """Return the source-unit sha256 for an asset ref/path, falling back to file bytes."""
    raw = str(source_asset_ref or "").replace("\\", "/").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = batch_root(task_id, batch_id) / raw
    try:
        if not path.is_file():
            return ""
        idx_path = path.parent / "index.json"
        if idx_path.is_file():
            index = read_json(idx_path)
            for asset in index.get("assets") or []:
                if isinstance(asset, Mapping) and asset.get("fileName") == path.name:
                    sha = str(asset.get("sha256") or "").strip().lower()
                    if sha:
                        return sha
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError, TypeError):
        return ""


__all__ = [
    "SOURCE_UNIT_MANIFEST",
    "SOURCE_UNIT_ASSET_INDEX",
    "slugify",
    "resolve_entity_object_dir",
    "write_source_unit",
    "iter_source_units",
    "find_entity_object_dirs",
    "object_image_candidates",
    "source_asset_sha256",
]
