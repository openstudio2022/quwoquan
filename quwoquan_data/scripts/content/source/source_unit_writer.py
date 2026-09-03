"""来源单元 + 对象证据链统一读写（真相源：object-homepage-coverage-scaling/design.md）。

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
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.source.source_unit_asset_entry import build_source_asset_entry
from core.content_library import link_bytes_from_library, link_from_library
from core.image_decode import probe_image_bytes
from core.image_variants import build_local_variants
from core.io import write_json
from core.paths import (
    execution_source_unit_dir,
    object_source_unit_dir,
    relative_execution_ref,
)
from core.source_attribution import source_attribution_fragment

from content.execution.runtime_contract import stage_execution_context
from content.source.source_snapshot_redaction import redact_raw_source_snapshot
from content.source.source_unit_attribution import (
    resolve_source_unit_attribution,
    resolve_source_unit_kind,
)
from content.source.source_unit_manifest_media import (
    apply_image_collection_manifest_defaults,
)

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")
OBJECT_SOURCE_REFS = "1.download/source_refs.json"


def _is_representative_visual(
    execution_id: str,
    image: Mapping[str, Any],
) -> bool:
    if bool(image.get("isMapLike")):
        return False
    if str(image.get("placementType") or "") == "locatorMap":
        return False
    from governance.content_supply_policy import load_content_supply_policy

    from content.execution.identity import parse_execution_id

    vertical = parse_execution_id(execution_id).vertical
    indicator = load_content_supply_policy(vertical).media_subject.prohibited_indicator(
        image.get("caption"),
        image.get("relevance"),
        image.get("visualSubject"),
        image.get("sourceUrl"),
    )
    return not indicator


from content.source.source_unit import (
    _execution_root_for_object_dir,
    _ext_from_name,
    _record_object_source_ref,
    _relative_ref_for_execution_root,
    bind_inline_source_placeholders,
    slugify,
    source_unit_raw_snapshot_name,
)


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
    source_kind: str = "",
    extractor: str = "",
    policy_revision: str = "",
    source_use_mode: str = "",
    rights_mode: str = "",
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
    execution_id: str = "",
    build_variants: bool = True,
    source: Mapping[str, Any] | None = None,
    frozen_source_unit_id: str = "",
) -> dict[str, Any]:
    """写一个来源单元，返回其 manifest（含 assets.index 摘要）。

    images 每项：{bytes|sourcePath, url, license, credit, caption, relevance, contentType}
    图片落 assets/{NNN}_{slug}.{ext}，并写 assets/index.json（含 sha256/relevance）。
    生产 download 主链路可传 build_variants=False，把 WebP 物理变体延后到
    media/release 阶段；原图、尺寸、hash、授权链仍在本阶段闭合。
    """
    from core.baike_source_contract import (
        HOMEPAGE_SOURCE_POLICY_REVISION,
        SOURCE_USE_MODES,
        source_identity_matches_contract,
    )
    from core.paths import ensure_object_stages

    snapshot_hash = "sha256:" + hashlib.sha256(source_md.encode("utf-8")).hexdigest()
    source_payload = source or {}
    rejected_unit = str((quality or {}).get("quality") or "").strip() == "Reject"
    resolved_source_kind = resolve_source_unit_kind(
        source_kind=source_kind,
        source_payload=source_payload,
        source_category=source_category,
        platform=platform,
    )
    resolved_extractor = str(
        extractor or source_payload.get("extractor") or ""
    ).strip()
    resolved_policy_revision = str(
        policy_revision or source_payload.get("policyRevision") or ""
    ).strip()
    canonical_url = str(source_payload.get("canonicalUrl") or url).strip()
    final_url = str(source_payload.get("finalUrl") or url).strip()
    if research_lane == "homepage" and not (
        title.strip()
        and canonical_url == final_url
        and source_identity_matches_contract(
            source_kind=resolved_source_kind,
            url=canonical_url,
            extractor=resolved_extractor,
            policy_revision=resolved_policy_revision,
        )
    ):
        raise ValueError(
            "homepage source unit requires explicit encyclopedia-primary "
            "sourceKind/extractor/title and matching canonical/final URL"
        )
    if research_lane == "homepage" and not source_use_mode:
        source_use_mode = SOURCE_USE_MODES[resolved_source_kind]
    # 可读命名契约（spec §3）：目录名 = {实体名}__{sourceKind}__{hash8}；
    # 实体名取对象目录名（entities/{d}/{t}/{name}），sourceKind 与 manifest 同源。
    source_unit_id = str(frozen_source_unit_id or "").strip()
    if source_unit_id:
        if "/" in source_unit_id or source_unit_id in {".", ".."}:
            raise ValueError("frozen sourceUnitId must be one safe path segment")
    else:
        from core.source_identity import source_unit_id as stable_source_unit_id

        source_unit_id = stable_source_unit_id(
            canonical_url=canonical_url,
            snapshot_hash=snapshot_hash,
            source_ref=f"{ordinal:02d}.{source_id}",
            entity_name=object_dir.name,
            source_kind=resolved_source_kind,
        )
    inferred_execution_root = _execution_root_for_object_dir(object_dir) if not execution_id else None
    # 组件调用只传 object_dir 时，目录本身已经处于唯一 execution 工作包内。
    if inferred_execution_root is not None:
        execution_id = inferred_execution_root.name
    unit = (
        execution_source_unit_dir(execution_id, source_unit_id)
        if execution_id
        else (
            inferred_execution_root / "sources" / source_unit_id
            if inferred_execution_root is not None
            else object_source_unit_dir(object_dir, ordinal, source_id)
        )
    )
    ensure_object_stages(object_dir)
    unit.mkdir(parents=True, exist_ok=True)
    (unit / "source.md").write_text(source_md, encoding="utf-8")
    if clean_md:
        (unit / "source.clean.md").write_text(clean_md, encoding="utf-8")
    persisted_snapshot_bytes = (
        redact_raw_source_snapshot(html_bytes, raw_format=raw_format)
        if html_bytes is not None
        else None
    )
    if persisted_snapshot_bytes is not None:
        # 原始快照按真实格式命名：MediaWiki API 返回 JSON，不能再误命名为 page.html。
        link_bytes_from_library(
            persisted_snapshot_bytes,
            unit / source_unit_raw_snapshot_name(raw_format),
            kind="source",
        )
    if quality is not None:
        write_json(unit / "source.quality.json", dict(quality))
    if layout is not None:
        # 统一结构化 IR 真相源（含 rejected IR：解析失败原因可审计，禁静默降级）。
        from core.source_layout import write_source_layout

        write_source_layout(unit, layout)

    asset_index: list[dict[str, Any]] = []
    assets_dir = unit / "assets"
    # RC3：内联图占位 → 真实 sourceAssetId 的绑定表（仅就地同源下载成功的内联图入表）。
    placeholder_to_asset: dict[str, str] = {}
    from content.execution.identity import parse_execution_id
    from content.source.contracts import MediaProvenance

    vertical = parse_execution_id(execution_id).vertical
    for k, img in enumerate(images or [], start=1):
        provenance = MediaProvenance.from_mapping(img, vertical=vertical)
        ext = str(img.get("ext") or _ext_from_name(img.get("fileName") or img.get("url") or "") or ".jpg")
        slug = slugify(img.get("slug") or img.get("role") or source_id)
        base_name = f"{k:03d}_{slug}"
        file_name = f"{base_name}{ext}"
        dest = assets_dir / file_name
        body = img.get("bytes")
        if body is not None:
            assets_dir.mkdir(parents=True, exist_ok=True)
            link_bytes_from_library(body, dest, kind="media")
        elif img.get("sourcePath"):
            src = Path(str(img["sourcePath"]))
            if not src.is_file():
                raise FileNotFoundError(f"source asset missing: {src}")
            assets_dir.mkdir(parents=True, exist_ok=True)
            link_from_library(src, dest, kind="media")
            body = dest.read_bytes()
        else:
            continue
        probe = probe_image_bytes(body or b"")
        if not probe.succeeded:
            raise ValueError(
                f"source asset rejected by image decode boundary: {probe.failure.value}"
            )
        sha = "sha256:" + hashlib.sha256(dest.read_bytes()).hexdigest()
        # 像素尺寸（清晰度门 + 变体源尺寸）。
        width = img.get("width")
        height = img.get("height")
        if (not width or not height) and body is not None:
            width, height = probe.width, probe.height
        variants_meta: list[dict[str, Any]] = []
        if build_variants:
            # 多变体格式化：按 IMAGE_VARIANT_PROFILES 物理压 webp（仅缩小），落同名 .variants/ 子目录。
            for var in build_local_variants(body or b"", base_name=base_name):
                var_bytes = var.pop("bytes")
                var_path = assets_dir / var["fileName"]
                var_path.parent.mkdir(parents=True, exist_ok=True)
                link_bytes_from_library(var_bytes, var_path, kind="media")
                variants_meta.append(var)
        professional_identity = (
            str(img.get("acquisitionReceiptRef") or "").strip(),
            str(img.get("professionalAssetId") or "").strip(),
            str(img.get("professionalContentSha256") or "").strip(),
        )
        if any(professional_identity) and not all(professional_identity):
            raise ValueError(
                "professional source image requires receipt, assetId, and contentSha256"
            )
        if professional_identity[0] and professional_identity[2] != sha:
            raise ValueError("professional source image contentSha256 drift")
        entry = build_source_asset_entry(
            img,
            execution_id=execution_id,
            ordinal=ordinal,
            k=k,
            file_name=file_name,
            sha=sha,
            width=width,
            height=height,
            dest_bytes=dest.stat().st_size,
            provenance=provenance,
            variants_meta=variants_meta,
            build_variants=build_variants,
            relevance=relevance or "",
            resolved_source_kind=resolved_source_kind,
            is_representative_visual=_is_representative_visual(execution_id, img),
        )
        asset_index.append(entry)
        placeholder_id = str(img.get("placeholderId") or "").strip()
        if placeholder_id:
            placeholder_to_asset[placeholder_id] = entry["sourceAssetId"]
    if not asset_index and assets_dir.exists():
        # 本轮没有图片通过权利/抓取/像素/安全/相关性门时，旧图片不能继续作为
        # 可消费证据；但空 index 仍必须保留，保证每个 accepted source unit 自包含。
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    index_payload: dict[str, Any] = {"assets": asset_index}
    if asset_funnel:
        # 候选/丢弃可审计：记录原始候选数、保留数、按原因聚合的丢弃明细与去重数。
        index_payload["funnel"] = dict(asset_funnel)
    write_json(unit / SOURCE_UNIT_ASSET_INDEX, index_payload)

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
    if execution_id:
        try:
            source_ref = relative_execution_ref(unit / "source.md", execution_id)
        except Exception:  # noqa: BLE001
            source_ref = ""
    elif inferred_execution_root is not None:
        try:
            source_ref = _relative_ref_for_execution_root(unit / "source.md", inferred_execution_root)
        except Exception:  # noqa: BLE001
            source_ref = ""
    manifest = {
        "schema": "quwoquan_data.source_unit",
        "stage": "1.download",
        **stage_execution_context(execution_id),
        "sourceUnitId": source_unit_id,
        "sourceId": source_id,
        "ordinal": ordinal,
        "sourceKind": resolved_source_kind,
        "extractor": resolved_extractor,
        "entityName": object_dir.name,
        "category": source_category or platform or "web",
        "platform": platform or "web",
        "sourceUseMode": source_use_mode,
        "imageEvidenceMode": image_evidence_mode,
        "researchLane": research_lane,
        # P3 三类解耦：来源页是否含内联视频（文章类含视频则放弃，不强行图文化视频内容）。
        "hasVideo": bool(has_video),
        "license": license_value,
        "url": url,
        "canonicalUrl": canonical_url,
        "finalUrl": final_url,
        "fetchedAt": str(
            (source or {}).get("fetchedAt")
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "rawSha256": (
            "sha256:" + hashlib.sha256(persisted_snapshot_bytes).hexdigest()
            if persisted_snapshot_bytes is not None
            else snapshot_hash
        ),
        "cleanSha256": "sha256:"
        + hashlib.sha256((clean_md or source_md).encode("utf-8")).hexdigest(),
        "policyRevision": (
            resolved_policy_revision
            or (HOMEPAGE_SOURCE_POLICY_REVISION if research_lane == "homepage" else "")
        ),
        "rightsMode": str(rights_mode or source_use_mode or "blocked").strip(),
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
    manifest.update(source_attribution_fragment(source_payload))
    if "sourceAttribution" not in manifest and not rejected_unit:
        # 只有可交付的来源单元才受 attribution fail-closed 约束；被判 Reject 的单元
        # 是隔离后的审计证据，永远不会进入 post manifest 或 pool delivery。
        attribution = resolve_source_unit_attribution(
            source_payload,
            research_lane=research_lane,
            resolved_source_kind=resolved_source_kind,
            source_url=canonical_url or url,
            captured_at=str(manifest["fetchedAt"]),
        )
        if attribution is not None:
            manifest["sourceAttribution"] = attribution
    # 未声明发布媒体形态或来源角色的单元（例如只做事实底稿的 homepage 主源）不写这两个
    # 键：空串不是它们枚举之外的第三种取值，落成空串只会让写盘撞契约。
    if str(publish_media_mode or "").strip():
        manifest["publishMediaMode"] = str(publish_media_mode).strip()
    if str(source_role or "").strip():
        manifest["sourceRole"] = str(source_role).strip()
    article_site_id = str(source_payload.get("articleSiteId") or "").strip()
    article_profile_digest = str(
        source_payload.get("sourceDiscoveryProfileDigest") or ""
    ).strip()
    article_admission = str(
        source_payload.get("articleCommercialAdmission") or ""
    ).strip()
    if article_site_id:
        manifest["articleSiteId"] = article_site_id
    if article_profile_digest:
        manifest["sourceDiscoveryProfileDigest"] = article_profile_digest
    if article_admission:
        manifest["articleCommercialAdmission"] = article_admission
    article_category = str(source_payload.get("articleCategory") or "").strip()
    if article_category:
        manifest["articleCategory"] = article_category
        manifest["writingIntent"] = str(source_payload.get("writingIntent") or "")
        manifest["topicTagRefs"] = [
            str(item) for item in source_payload.get("topicTagRefs") or []
        ]
        manifest["sourceClassification"] = dict(
            source_payload.get("sourceClassification") or {}
        )
    requested_title = str(source_payload.get("requestedTitle") or "").strip()
    resolved_title = str(source_payload.get("resolvedTitle") or "").strip()
    redirect_chain = source_payload.get("redirectChain")
    if requested_title:
        manifest["requestedTitle"] = requested_title
    if resolved_title:
        manifest["resolvedTitle"] = resolved_title
    qualified_authority_title = str(
        source_payload.get("qualifiedAuthorityTitle") or ""
    ).strip()
    if qualified_authority_title:
        manifest["qualifiedAuthorityTitle"] = qualified_authority_title
    if isinstance(redirect_chain, list):
        manifest["redirectChain"] = [str(item) for item in redirect_chain if str(item).strip()]
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
        from core.section_outline import (
            SOURCE_OUTLINE_MIN_BODY_CHARS,
            outline_required_sections,
            outline_to_dicts,
            parse_section_outline,
        )
        from core.wiki_wikitext import placements_from_layout

        manifest["sectionOutline"] = outline_to_dicts(
            outline_required_sections(
                parse_section_outline(source_md),
                min_body_chars=SOURCE_OUTLINE_MIN_BODY_CHARS,
            )
        )
        manifest["imagePlacements"] = placements_from_layout(dict(layout))
    try:
        from core.qunar_template import qunar_template_metadata

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
    # 实体聚焦度落盘（单一真相源 core.entity_focus）：仅文本 article 底稿需要，
    # 供选源弃稿门、content_plan 门与 scale_readiness 准出口径共同消费。图片相关性
    # 另有图像门把关，不在此落 verdict 以免误伤。
    if str(research_lane or "").strip() == "article":
        from core.entity_focus import classify_entity_focus

        entity_name = str(target_ref or "").rstrip("/").rsplit("/", 1)[-1]
        focus_score, focus_verdict = classify_entity_focus(
            source_md, entity_name, title=title
        )
        manifest["entityFocusScore"] = focus_score
        manifest["entityFocusVerdict"] = focus_verdict
    if asset_funnel:
        manifest["assetFunnel"] = dict(asset_funnel)
    apply_image_collection_manifest_defaults(
        manifest,
        source_kind=resolved_source_kind,
        asset_index=asset_index,
    )
    # A video lane has two distinct admissible material types: direct-video
    # source units and rights-cleared still-frame collections.  The strict
    # direct-video contract applies only to the former.  Applying it to a
    # frame collection makes an otherwise valid fallback impossible before
    # the media gate can assemble its image sequence.
    if research_lane == "video" and has_video:
        from content.source.video_source_unit_contract import (
            assert_video_source_unit_invariants,
        )

        assert_video_source_unit_invariants(manifest)
    if research_lane in {"homepage", "article", "video"}:
        from core.schema import assert_valid

        assert_valid(
            manifest,
            "source",
            "source_unit_meta",
            label=f"source_unit_meta:{source_unit_id}",
        )
    write_json(unit / SOURCE_UNIT_MANIFEST, manifest)
    if source_ref and (execution_id or inferred_execution_root is not None):
        meta_ref = (
            relative_execution_ref(unit / SOURCE_UNIT_MANIFEST, execution_id)
            if execution_id
            else _relative_ref_for_execution_root(unit / SOURCE_UNIT_MANIFEST, inferred_execution_root or unit.parent)
        )
        _record_object_source_ref(
            object_dir,
            execution_id=execution_id,
            source_ref=source_ref,
            meta_ref=meta_ref,
            execution_root_path=inferred_execution_root,
            manifest=manifest,
        )
    return manifest
