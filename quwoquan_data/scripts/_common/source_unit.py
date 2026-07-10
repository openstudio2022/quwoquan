"""来源单元 + 对象证据链统一读写（真相源：docs/pipeline_directory_layout_spec.md）。

替代「对象级散落 images/ + 实体目录承载来源」的旧布局。每个来源是一个自包含、
稳定 ID、带类目与相关性说明的单元；实体/作品对象只保存 `1.download/source_refs.json`
软引用索引：

    sources/{sourceUnitId}/
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
import os
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
    batch_source_unit_dir,
    batches_root,
    relative_batch_ref,
    source_unit_dir,
)
from _common.entity_extract import require_domain_etype, resolve_domain_etype

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")
OBJECT_SOURCE_REFS = "1.download/source_refs.json"


def slugify(value: str) -> str:
    """可读 slug：保留中文/字母数字，连续非法折叠为 _。"""
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return s or "asset"


# RC3：source.md 内联图占位 :::figure 块（未绑定到真实资产的悬空占位需整块剥离）。
# 图注行可选：无原图注的占位块只有图行（禁止人为补注），剥离时同样整块移除。
_INLINE_FIGURE_BLOCK_RE = re.compile(
    r"\n?:::figure\n!\[[^\]]*\]\(asset://source-inline-\d+\)\n(?:(?!:::)[^\n]*\n)?:::\n?"
)


def bind_inline_source_placeholders(text: str, placeholder_to_asset: Mapping[str, str]) -> str:
    """把 source.md 内联占位 asset://source-inline-NNN 绑定到真实 sourceAssetId。

    成功就地同源下载的内联图：占位 → asset://{ordinal_kkk}（段落锚定位置不变，
    保留图文交错）。未成功下载的 source-inline 占位：删除其整个 :::figure 块，
    杜绝悬空占位（这是九寨沟"图片对不上/缺失"的直接表征）。
    """
    from _common.figure_groups import prune_unbound_group_images

    bound = str(text or "")
    for placeholder, asset_id in placeholder_to_asset.items():
        placeholder = str(placeholder or "").strip()
        asset_id = str(asset_id or "").strip()
        if not placeholder or not asset_id:
            continue
        bound = bound.replace(f"asset://{placeholder}", f"asset://{asset_id}")
    # figuregroup（连续图组）：剔除组内未绑定图行 + 重算 count + 删空组（P2）。
    bound = prune_unbound_group_images(bound)
    # 单图内联块：未绑定的悬空 :::figure 占位整块剥离（RC3）。
    bound = _INLINE_FIGURE_BLOCK_RE.sub("\n", bound)
    return re.sub(r"\n{3,}", "\n\n", bound)


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
    markers = ("_entity.json", "page.md", "1.download")
    if not any((sibling / marker).exists() for marker in markers):
        return
    # 「same batch contains both」要求两类型目录都真实物化：读路径以默认/空
    # hint 解析出的 current 并不在磁盘上时，只是类型提示缺失（上游应做
    # canonical 校正），不构成漂移共存；否则 canonical 产物存在时任何空 hint
    # 读操作都会假阳性炸穿 audit/completion gate（WP5 舟山实测）。
    if not current.exists() or not any((current / marker).exists() for marker in markers):
        return
    raise ValueError(
        "entity type drift detected: same batch contains both "
        f"{domain}/{etype}/{name} and {domain}/{sibling_type}/{name}; "
        "must fail or explicitly correct, silent coexistence is forbidden"
    )


# ─── 写：来源单元 ──────────────────────────────────────────────────
def _batch_root_for_object_dir(object_dir: Path) -> Path | None:
    root = batches_root().resolve()
    path = object_dir.resolve()
    for parent in (path, *path.parents):
        try:
            if parent.parent.resolve() == root:
                return parent
        except OSError:
            continue
    return None


def _object_source_refs_path(object_dir: Path) -> Path:
    return object_dir / OBJECT_SOURCE_REFS


def _relative_ref_for_batch_root(target: Path, batch_root_path: Path) -> str:
    return os.path.relpath(Path(target).resolve(), Path(batch_root_path).resolve()).replace(os.sep, "/")


def _record_object_source_ref(
    object_dir: Path,
    *,
    task_id: str = "",
    batch_id: str = "",
    batch_root_path: Path | None = None,
    source_ref: str,
    meta_ref: str,
    manifest: Mapping[str, Any],
) -> None:
    path = _object_source_refs_path(object_dir)
    payload = read_json(path) if path.is_file() else {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schemaVersion", "quwoquan_data.object_source_refs/1")
    try:
        if task_id and batch_id:
            payload["objectRef"] = relative_batch_ref(object_dir, task_id, batch_id)
        elif batch_root_path is not None:
            payload["objectRef"] = _relative_ref_for_batch_root(object_dir, batch_root_path)
        else:
            payload["objectRef"] = ""
    except Exception:  # noqa: BLE001
        payload["objectRef"] = ""
    rows = [row for row in (payload.get("sources") or []) if isinstance(row, dict)]
    row = {
        "sourceUnitId": str(manifest.get("sourceUnitId") or ""),
        "sourceRef": source_ref,
        "metaRef": meta_ref,
        "sourceId": str(manifest.get("sourceId") or ""),
        "ordinal": int(manifest.get("ordinal") or 0),
        "researchLane": str(manifest.get("researchLane") or ""),
        "sourceUseMode": str(manifest.get("sourceUseMode") or ""),
        "publishMediaMode": str(manifest.get("publishMediaMode") or ""),
        "targetRefs": list((manifest.get("relevance") or {}).get("targetRefs") or []),
    }
    rows = [existing for existing in rows if str(existing.get("sourceRef") or "") != source_ref]
    rows.append(row)
    payload["sources"] = sorted(rows, key=lambda item: (int(item.get("ordinal") or 0), str(item.get("sourceRef") or "")))
    write_json(path, payload)


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
    publish_media_mode: str = "",
    source_role: str = "",
    image_evidence_mode: str = "",
    research_lane: str = "",
    license_value: str = "",
    url: str = "",
    title: str = "",
    target_ref: str = "",
    relevance: str = "",
    has_video: bool = False,
    images: Sequence[Mapping[str, Any]] | None = None,
    asset_funnel: Mapping[str, Any] | None = None,
    raw_format: str = "",
    layout: Mapping[str, Any] | None = None,
    task_id: str = "",
    batch_id: str = "",
    build_variants: bool = True,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """写一个来源单元，返回其 manifest（含 assets.index 摘要）。

    images 每项：{bytes|sourcePath, url, license, credit, caption, relevance, contentType}
    图片落 assets/{NNN}_{slug}.{ext}，并写 assets/index.json（含 sha256/relevance）。
    生产 download 主链路可传 build_variants=False，把 WebP 物理变体延后到
    media/release 阶段；原图、尺寸、hash、授权链仍在本阶段闭合。
    """
    from _common.paths import STAGE_DOWNLOAD, ensure_object_stages

    snapshot_hash = "sha256:" + hashlib.sha256(source_md.encode("utf-8")).hexdigest()
    # 可读命名契约（spec §3）：目录名 = {实体名}__{sourceKind}__{hash8}；
    # 实体名取对象目录名（entities/{d}/{t}/{name}），sourceKind 与 manifest 同源。
    source_unit_id = og.source_unit_id(
        canonical_url=url,
        snapshot_hash=snapshot_hash,
        source_ref=f"{ordinal:02d}.{source_id}",
        entity_name=object_dir.name,
        source_kind=source_category or platform or "web",
    )
    inferred_batch_root = _batch_root_for_object_dir(object_dir) if not (task_id and batch_id) else None
    unit = (
        batch_source_unit_dir(task_id, batch_id, source_unit_id)
        if task_id and batch_id
        else (inferred_batch_root / "sources" / source_unit_id if inferred_batch_root is not None else source_unit_dir(object_dir, ordinal, source_id))
    )
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
    if layout is not None:
        # 统一结构化 IR 真相源（含 rejected IR：解析失败原因可审计，禁静默降级）。
        from _common.source_layout import write_source_layout

        write_source_layout(unit, layout)

    asset_index: list[dict[str, Any]] = []
    assets_dir = unit / "assets"
    # RC3：内联图占位 → 真实 sourceAssetId 的绑定表（仅就地同源下载成功的内联图入表）。
    placeholder_to_asset: dict[str, str] = {}
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
            "inlinePlaceholderId": str(img.get("placeholderId") or ""),
            # 布局/封面候选语义（来自 source.layout.json figure；非结构源为空/默认）：
            # placementType=infoboxLead|locatorMap|inline|groupMember；rank=-1 禁封面。
            "placementType": str(img.get("placementType") or ""),
            "groupId": str(img.get("groupId") or ""),
            "sectionSlug": str(img.get("sectionSlug") or ""),
            "sourceOrder": int(img.get("sourceOrder") or 0),
            "coverCandidateRank": int(img.get("coverCandidateRank") or 0),
            "isMapLike": bool(img.get("isMapLike")),
            # 代表性实景图：非地图/定位图即可进入封面与配图选择池。
            "isRepresentativeVisual": (
                not bool(img.get("isMapLike"))
                and str(img.get("placementType") or "") != "locatorMap"
            ),
            # 视觉主体描述 = 原图注（仅原图注，无则空，禁止伪造）。
            "visualSubject": str(img.get("caption") or ""),
        }
        asset_index.append(entry)
        placeholder_id = str(img.get("placeholderId") or "").strip()
        if placeholder_id:
            placeholder_to_asset[placeholder_id] = entry["sourceAssetId"]
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

    # RC3：把 source.md / source.clean.md 的内联图占位绑定到真实 sourceAssetId；
    # 未就地下载成功的 source-inline 占位整块剥离，避免悬空占位（图文对不上）。
    if placeholder_to_asset or "asset://source-inline-" in source_md:
        bound_md = bind_inline_source_placeholders(source_md, placeholder_to_asset)
        if bound_md != source_md:
            (unit / "source.md").write_text(bound_md, encoding="utf-8")
        if clean_md and "asset://source-inline-" in clean_md:
            bound_clean = bind_inline_source_placeholders(clean_md, placeholder_to_asset)
            if bound_clean != clean_md and (unit / "source.clean.md").is_file():
                (unit / "source.clean.md").write_text(bound_clean, encoding="utf-8")

    source_ref = ""
    if task_id and batch_id:
        try:
            source_ref = relative_batch_ref(unit / "source.md", task_id, batch_id)
        except Exception:  # noqa: BLE001
            source_ref = ""
    elif inferred_batch_root is not None:
        try:
            source_ref = _relative_ref_for_batch_root(unit / "source.md", inferred_batch_root)
        except Exception:  # noqa: BLE001
            source_ref = ""
    manifest = {
        "schemaVersion": "quwoquan_data.source_unit",
        "sourceUnitId": source_unit_id,
        "sourceId": source_id,
        "ordinal": ordinal,
        "sourceKind": source_category or platform or "web",
        "category": source_category or platform or "web",
        "platform": platform or "web",
        "sourceUseMode": source_use_mode,
        "publishMediaMode": publish_media_mode,
        "sourceRole": source_role,
        "imageEvidenceMode": image_evidence_mode,
        "researchLane": research_lane,
        # P3 三类解耦：来源页是否含内联视频（文章类含视频则放弃，不强行图文化视频内容）。
        "hasVideo": bool(has_video),
        "license": license_value,
        "url": url,
        "snapshotHash": snapshot_hash,
        "title": title,
        "relevance": {
            "targetRefs": [target_ref] if target_ref else [],
            "entityTags": [target_ref] if target_ref else [],
            "semanticMentions": [target_ref.rsplit("/", 1)[-1]] if target_ref else [],
            "coverageTargets": [target_ref] if target_ref else [],
            "reason": relevance or "覆盖该对象的基础事实/交通/季节等",
        },
        "assetCount": len(asset_index),
    }
    if layout is not None:
        # meta 只保留 IR 索引摘要；结构块真相源在 source.layout.json。
        layout_blocks = layout.get("blocks") if isinstance(layout.get("blocks"), list) else []
        manifest["layoutSummary"] = {
            "parseStatus": str(layout.get("parseStatus") or ""),
            "rejectReason": str(layout.get("rejectReason") or ""),
            "blockCount": len(layout_blocks),
            "figureCount": int(layout.get("figureCount") or 0),
            "tableCount": len(layout.get("tables") or []),
        }
    try:
        from _common.qunar_template import qunar_template_metadata

        html_text = html_bytes.decode("utf-8", errors="replace") if html_bytes else ""
        site_template = qunar_template_metadata(url=url, text=source_md, html=html_text, title=title, source=source)
    except Exception:  # noqa: BLE001
        site_template = {}
    if site_template:
        manifest["siteTemplate"] = site_template
        if site_template.get("publishedAt"):
            manifest["publishedAt"] = site_template["publishedAt"]
        if site_template.get("freshnessTier"):
            manifest["sourceFreshnessTier"] = site_template["freshnessTier"]
        if site_template.get("sourceAuthorRef"):
            manifest["sourceAuthorRef"] = site_template["sourceAuthorRef"]
    if source_ref:
        manifest["sourceRef"] = source_ref
        manifest["sourceUnitRef"] = str(Path(source_ref).parent)
    if quality is not None:
        raw_quality_score = (
            quality.get("sourceQualityScore")
            or quality.get("qualityScore")
            or quality.get("score")
            or quality.get("quality_score")
        )
        try:
            quality_score = float(raw_quality_score)
        except (TypeError, ValueError):
            quality_score = 0.0
        if quality_score:
            manifest["sourceQualityScore"] = quality_score / 10.0 if quality_score > 1 else quality_score
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
    if source_ref and (task_id and batch_id or inferred_batch_root is not None):
        meta_ref = (
            relative_batch_ref(unit / SOURCE_UNIT_MANIFEST, task_id, batch_id)
            if task_id and batch_id
            else _relative_ref_for_batch_root(unit / SOURCE_UNIT_MANIFEST, inferred_batch_root or unit.parent)
        )
        _record_object_source_ref(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            source_ref=source_ref,
            meta_ref=meta_ref,
            batch_root_path=inferred_batch_root,
            manifest=manifest,
        )
    return manifest


def _ext_from_name(name: str) -> str:
    suffix = Path(str(name).split("?")[0]).suffix.lower()
    return suffix if suffix in _IMAGE_EXTS else ""


# ─── 读：来源单元与候选图（含证据链相对引用）────────────────────────
def iter_source_units(object_dir: Path) -> list[Path]:
    refs_path = _object_source_refs_path(object_dir)
    if not refs_path.is_file():
        return []
    batch_dir = _batch_root_for_object_dir(object_dir)
    if batch_dir is None:
        return []
    payload = read_json(refs_path)
    if not isinstance(payload, Mapping):
        # agent 产物是外部输入：顶层写成数组/标量时视为无可回查来源单元，
        # 契约违规由 verify 证据链负责报 issue，读路径不得崩溃。
        return []
    units: list[Path] = []
    for row in payload.get("sources") or []:
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("sourceRef") or "").strip()
        if not ref:
            continue
        source_md = batch_dir / ref
        unit = source_md.parent
        if source_md.is_file() and (unit / SOURCE_UNIT_MANIFEST).is_file():
            units.append(unit)
    return sorted(set(units), key=lambda d: d.name)


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
    for refs_path in entities_root.rglob("source_refs.json"):
        obj = refs_path.parent.parent
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

    每项：{path, sourceRef(相对), sourceAssetId, sourceAssetRef(相对), sha256, caption, relevance}。
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
                    "sourceAssetId": meta.get("sourceAssetId") or "",
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
