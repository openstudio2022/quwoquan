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
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.io import read_json, write_json
from content.execution.runtime_contract import stage_execution_context
from core import ops_governance as og
from core.image_decode import probe_image_bytes
from core.image_variants import build_local_variants, image_dimensions
from core.paths import (
    STAGE_DOWNLOAD,
    execution_entity_object_dir,
    execution_root,
    execution_source_unit_dir,
    executions_root,
    relative_execution_ref,
    object_source_unit_dir,
)
from governance.coverage.entity_extract import require_domain_etype, resolve_domain_etype

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")
OBJECT_SOURCE_REFS = "1.download/source_refs.json"
_RAW_SNAPSHOT_BEARER = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    flags=re.IGNORECASE,
)
_RAW_SNAPSHOT_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:access[_-]?token|api[_-]?key|authcode|authorization|credential|"
    r"password|private[_-]?key|secret|signature|token|x-amz-credential|"
    r"x-amz-signature)s?\b\s*=\s*)([^&#\s\"'<>\\]+)"
)
_RAW_SNAPSHOT_EMPTY_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:access[_-]?token|api[_-]?key|authcode|authorization|credential|"
    r"password|private[_-]?key|secret|signature|token|x-amz-credential|"
    r"x-amz-signature)s?\b\s*=\s*)(?=[&#\s\"'<>\\]|$)"
)
_RAW_SNAPSHOT_SECRET_KEY_SUFFIXES = (
    "apikey",
    "credential",
    "password",
    "privatekey",
    "secret",
    "signature",
    "token",
)


def _redact_embedded_snapshot_secrets(value: str) -> str:
    redacted = _RAW_SNAPSHOT_BEARER.sub("Bearer <redacted>", value)
    redacted = _RAW_SNAPSHOT_SECRET_ASSIGNMENT.sub(
        r"\1<redacted>",
        redacted,
    )
    return _RAW_SNAPSHOT_EMPTY_SECRET_ASSIGNMENT.sub(
        r"\1<redacted>",
        redacted,
    )


def _snapshot_key_is_secret(value: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    return normalized.endswith(_RAW_SNAPSHOT_SECRET_KEY_SUFFIXES)


def _redact_snapshot_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _snapshot_key_is_secret(key)
                else _redact_snapshot_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_snapshot_json(item) for item in value]
    if isinstance(value, str):
        return _redact_embedded_snapshot_secrets(value)
    return value


def redact_raw_source_snapshot(raw: bytes, *, raw_format: str = "") -> bytes:
    """Remove credential-like values before an untrusted source snapshot persists."""
    text = raw.decode("utf-8", errors="replace")
    if str(raw_format or "").strip() == "mediawiki_api_json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(
                _redact_snapshot_json(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
    return _redact_embedded_snapshot_secrets(text).encode("utf-8")


def _is_representative_visual(
    execution_id: str,
    image: Mapping[str, Any],
) -> bool:
    if bool(image.get("isMapLike")):
        return False
    if str(image.get("placementType") or "") == "locatorMap":
        return False
    from content.execution.identity import parse_execution_id
    from governance.content_supply_policy import load_content_supply_policy

    vertical = parse_execution_id(execution_id).vertical
    indicator = load_content_supply_policy(vertical).media_subject.prohibited_indicator(
        image.get("caption"),
        image.get("relevance"),
        image.get("visualSubject"),
        image.get("sourceUrl"),
    )
    return not indicator


from content.source.source_unit import (
    _execution_root_for_object_dir, _ext_from_name, _record_object_source_ref,
    _relative_ref_for_execution_root, bind_inline_source_placeholders,
    slugify, source_unit_raw_snapshot_name,
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
) -> dict[str, Any]:
    """写一个来源单元，返回其 manifest（含 assets.index 摘要）。

    images 每项：{bytes|sourcePath, url, license, credit, caption, relevance, contentType}
    图片落 assets/{NNN}_{slug}.{ext}，并写 assets/index.json（含 sha256/relevance）。
    生产 download 主链路可传 build_variants=False，把 WebP 物理变体延后到
    media/release 阶段；原图、尺寸、hash、授权链仍在本阶段闭合。
    """
    from core.paths import STAGE_DOWNLOAD, ensure_object_stages

    from core.baike_source_contract import (
        HOMEPAGE_SOURCE_POLICY_REVISION,
        SOURCE_USE_MODES,
        source_identity_matches_contract,
    )

    snapshot_hash = "sha256:" + hashlib.sha256(source_md.encode("utf-8")).hexdigest()
    source_payload = source or {}
    resolved_source_kind = (
        str(source_kind or "").strip()
        or str(source_payload.get("sourceKind") or "").strip()
        or source_category
        or platform
        or "web"
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
    source_unit_id = og.source_unit_id(
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
    ensure_object_stages(object_dir, through_stage=STAGE_DOWNLOAD)
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
        (unit / source_unit_raw_snapshot_name(raw_format)).write_bytes(
            persisted_snapshot_bytes
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
            **provenance.audit_fields(),
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
            "subjectKey": str(img.get("subjectKey") or ""),
            "isMapLike": bool(img.get("isMapLike")),
            "pageResolvedTitle": str(img.get("pageResolvedTitle") or ""),
            "pageId": int(img.get("pageId") or 0),
            "pageRevisionId": int(img.get("pageRevisionId") or 0),
            "pageContentSha256": str(img.get("pageContentSha256") or ""),
            "renderedImageCount": int(img.get("renderedImageCount") or 0),
            # 代表性实景图同时受地图和垂类媒体主体规则约束。
            "isRepresentativeVisual": _is_representative_visual(
                execution_id,
                img,
            ),
            # 视觉主体描述 = 原图注（仅原图注，无则空，禁止伪造）。
            "visualSubject": str(img.get("caption") or ""),
        }
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
        "publishMediaMode": publish_media_mode,
        "sourceRole": source_role,
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
        "rightsMode": source_use_mode or "blocked",
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
    if research_lane == "homepage":
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
