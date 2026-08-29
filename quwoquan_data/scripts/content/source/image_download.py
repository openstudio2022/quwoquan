"""Download image, source-unit cache and rejection helpers."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode
from core.image_decode import probe_image_bytes
from core.image_rules import pixel_size_issue, relevance_issue
from core.image_safety import dedupe_image_payloads
from core.image_variants import derive_budget_compliant_variant
from core.object_storage_budget import source_unit_asset_budget_bytes
from core.page_media import (
    DownloadedPageAsset,
    PageImageDropCode,
    PageImagePlacement,
    PageImagePlacementType,
)
from governance.coverage.distribution import (
    AcquisitionStatus,
    RightsStatus,
    image_distribution_decision,
)
from governance.coverage.license import (
    normalize_rights_payload,
)

from content.source.contracts import MediaProvenance
from content.source.fetch_images import fetch_image_payload, fetch_page_image_payload
from content.source.handler_images import (
    _assess_source_image,
    _cached_source_image_payload,
    _cleanup_image_check_temp_file,
    _write_image_check_temp_file,
)
from content.source.handler_plan import (
    SOURCE_UNIT_MAX_IMAGE_BYTES,
)
from content.source.source_asset_identity import (
    stable_source_image_collection_id,
)


def _acquired_asset_contract(
    asset: Mapping[str, Any],
    *,
    provenance: MediaProvenance,
    captured_at: str,
) -> dict[str, Any]:
    """Project one successful download through the governed asset policy."""

    acquisition_status = AcquisitionStatus.ACQUIRED
    rights_status = RightsStatus(provenance.rights_audit_status.value)
    authorization_proof = str(asset.get("authorizationProof") or "").strip()
    return {
        "acquisitionStatus": acquisition_status.value,
        "rightsStatus": rights_status.value,
        "authorizationRequired": (
            rights_status is not RightsStatus.VERIFIED or not authorization_proof
        ),
        "distributionDecision": image_distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=rights_status,
            authorization_proof=authorization_proof,
            usage_scope=str(asset.get("usageScope") or ""),
            model_release_status=str(asset.get("modelReleaseStatus") or ""),
        ).value,
        "capturedAt": captured_at,
        "contentSha256": "sha256:"
        + hashlib.sha256(bytes(asset["bytes"])).hexdigest(),
        "rightsIssues": list(provenance.rights_audit_issues),
    }

def _budget_admitted_payload(
    payload: dict[str, Any],
    *,
    budget_bytes: int,
) -> tuple[dict[str, Any] | None, str]:
    """把一个已下载候选收敛到其载体的对象存储预算之内。

    返回 (payload, derivation)：预算内原样返回且 derivation 为空串；超预算时就地派生
    一个合规交付档并按新字节身份重写 `bytes`/`ext`/`sha256`/`contentType`、附上派生体的
    `width`/`height`，derivation 描述派生结果；逐档降采样后仍装不进预算时返回 (None, 原因)。
    derivation 非空是「读 `width`/`height`」的唯一许可条件——预算内的原体不带这两个键，
    它的几何由调用方自己的 probe 负责。

    判定放在这里而不是 publish：publish 侧把「单资产自身即超过整个对象预算」判为对象级
    blocked，落在下载放行上限与该预算之间的候选会走完 `2.quality`→`5.review` 全程创作与
    评审成本才被拒，而一个超尺寸 hero 还会连带让引用该实体的成品 article 因引用闭包不成立
    被长期排除。
    """

    body = bytes(payload["bytes"])
    if len(body) <= budget_bytes:
        return payload, ""
    derived = derive_budget_compliant_variant(body, budget_bytes=budget_bytes)
    if derived is None:
        return None, (
            f"{len(body)}B exceeds the {budget_bytes}B carrier object storage "
            "budget and every declared delivery profile still exceeds it"
        )
    admitted = dict(payload)
    admitted["bytes"] = derived["bytes"]
    admitted["ext"] = derived["ext"]
    admitted["contentType"] = derived["mimeType"]
    admitted["sha256"] = derived["sha256"]
    admitted["width"] = derived["width"]
    admitted["height"] = derived["height"]
    return admitted, (
        f"budget_compliant_variant:{derived['profile']}"
        f":{derived['width']}x{derived['height']}"
        f":{len(body)}B->{derived['byteSize']}B"
    )


def _download_source_unit_images(
    source: Mapping[str, Any],
    *,
    execution_id: str,
    entity_id: str,
    object_dir: Path,
    ordinal: int,
    vertical: str,
    research_lane: str,
    extra_candidates: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Download and gate images that belong to the same text source unit.

    Article/homepage source images are part of that source's draft evidence.
    They must stay attached to the source unit instead of being mixed into the
    independent image-work collection lane.

    下载该来源 imageUrls 中所有与底稿相符、且通过 权利→抓取→像素→预算→安全→相关性 六道门、
    再经感知去重的真实图（广告/图标/占位/视频在这些门里被排除），而不是只留 1 张。
    返回 (images, issues, funnel)：funnel 记录候选数、保留数、按原因聚合的丢弃明细与去重数，
    用于写入 assets/index.json 做候选/丢弃可审计。

    `research_lane` 是必需参数：它是来源单元上的显式声明位，决定这些资产落到哪个发布载体，
    载体再决定字节预算。缺席或落在闭集之外时在此判否，不替它挑一个预算。
    """
    asset_budget_bytes = source_unit_asset_budget_bytes(research_lane)
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    drops: list[dict[str, object]] = []
    fetch_failures: list[dict[str, object]] = []
    budget_derivations: list[dict[str, object]] = []

    def _record_drop(
        code: PageImageDropCode,
        *,
        slug: str,
        reason: str,
        url: str = "",
        status_code: int | None = None,
    ) -> None:
        row: dict[str, object] = {
            "slug": slug,
            "code": code.value,
            "reason": reason,
        }
        if url:
            row["url"] = url
        if status_code is not None:
            row["statusCode"] = status_code
        drops.append(row)

    def _funnel(candidate_count: int, dedupe_removed: int) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        for drop in drops:
            key = str(drop.get("code") or "unknown")
            reason_counts[key] = reason_counts.get(key, 0) + 1
        return {
            "candidateCount": candidate_count,
            "keptCount": len(images),
            "droppedCount": len(drops),
            "dedupeRemoved": dedupe_removed,
            "quotaMode": "complete_source_page",
            "assetBudgetBytes": asset_budget_bytes,
            "dropReasonCounts": reason_counts,
            "drops": drops,
            "fetchFailures": fetch_failures,
            # 就地降采样过的候选：交付的不是源体，审计必须能看出这一跳。
            "budgetDerivations": budget_derivations,
        }

    raw_images = source.get("imageUrls") or []
    if not isinstance(raw_images, list):
        msg = f"{source.get('source_id') or '?'} imageUrls must be a list"
        return images, [msg], _funnel(0, 0)
    # RC3：同源内联 <img> 候选与计划 imageUrls 合并，走同一套五道硬门（不绕许可），
    # 经 placeholderId 把通过门的内联图回连 source.md 段落占位。
    all_candidates = list(raw_images) + list(extra_candidates or [])
    source_id = str(source.get("source_id") or "")
    candidate_count = len(all_candidates)
    for idx_img, raw in enumerate(all_candidates, start=1):
        candidate_group = str(raw.get("groupId") or "") if isinstance(raw, Mapping) else ""
        if not isinstance(raw, Mapping):
            issues.append(f"{source_id} image[{idx_img}] invalid payload")
            _record_drop(
                PageImageDropCode.INVALID_PAYLOAD,
                slug=f"{source_id}#{idx_img}",
                reason="image candidate payload is not an object",
            )
            continue
        spec = {
            "license": source.get("license") or "",
            "credit": source.get("credit") or "",
            "termsUrl": source.get("termsUrl") or "",
            "licenseSnapshot": source.get("licenseSnapshot") or "",
            "authorizationProof": source.get("authorizationProof") or "",
            "usageScope": source.get("usageScope") or "",
            "modelReleaseStatus": source.get("modelReleaseStatus") or "not_required",
            "sourceUrl": source.get("url") or "",
            "platform": source.get("platform") or "",
            "sourceCollectionId": "",
            "creator": source.get("credit") or "",
            "collectionPageUrl": source.get("url") or "",
            **{k: v for k, v in raw.items() if v not in ("", None)},
        }
        spec["sourceCollectionId"] = stable_source_image_collection_id(
            entity_id=entity_id,
            source_id=source_id,
            spec=spec,
        )
        label = f"{entity_id}/{source_id}#{idx_img}"
        spec_url = str(spec.get("url") or "")
        provenance = MediaProvenance.from_mapping(spec, vertical=vertical)
        payload = _cached_source_image_payload(
            object_dir,
            ordinal=ordinal,
            source_id=source_id,
            spec=spec,
        )
        if payload is None:
            placement_type = str(spec.get("placementType") or "")
            is_structured_page_image = placement_type in {
                item.value for item in PageImagePlacementType
            }
            if is_structured_page_image:
                page_fetch = fetch_page_image_payload(
                    str(spec.get("url") or ""),
                    max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
                )
                if page_fetch.succeeded:
                    assert page_fetch.payload is not None
                    payload = page_fetch.payload.to_asset_mapping()
                else:
                    assert page_fetch.failure is not None
                    issues.append(
                        f"{label}: page image fetch {page_fetch.failure.value} "
                        f"(status={page_fetch.status_code}, attempts={page_fetch.attempt_count})"
                    )
                    _record_drop(
                        PageImageDropCode.FETCH_FAILURE,
                        slug=label,
                        url=spec_url,
                        reason=page_fetch.failure.value,
                        status_code=page_fetch.status_code,
                    )
                    fetch_failures.append(
                        page_fetch.as_failure_evidence(
                            source_order=int(spec.get("sourceOrder") or 0)
                        )
                    )
                    continue
            else:
                payload = fetch_image_payload(
                    str(spec.get("url") or ""),
                    max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
                )
        if payload is None:
            size_note = (
                f"/too large >{SOURCE_UNIT_MAX_IMAGE_BYTES} bytes"
                if SOURCE_UNIT_MAX_IMAGE_BYTES
                else ""
            )
            issues.append(f"{label}: imageFetch failed/non-image/too small{size_note} ({spec.get('url')})")
            _record_drop(
                PageImageDropCode.FETCH_FAILURE,
                slug=label,
                url=spec_url,
                reason="generic image fetch failed",
            )
            continue
        image_probe = probe_image_bytes(payload["bytes"])
        if not image_probe.succeeded:
            reason = f"image_decode:{image_probe.failure.value}"
            issues.append(f"{label}: {reason}")
            _record_drop(
                PageImageDropCode.DECODE_POLICY,
                slug=label,
                url=spec_url,
                reason=reason,
            )
            continue
        width, height = image_probe.width, image_probe.height
        px_issue = pixel_size_issue(width, height, asset_id=label)
        if px_issue:
            issues.append(px_issue)
            _record_drop(
                PageImageDropCode.PIXEL_POLICY,
                slug=label,
                url=spec_url,
                reason=px_issue,
            )
            continue
        admitted, budget_note = _budget_admitted_payload(
            payload, budget_bytes=asset_budget_bytes
        )
        if admitted is None:
            reason = (
                f"{DataIssueCode.MEDIA_ASSET_OVER_BUDGET.value}: {label} "
                f"({spec_url}) {budget_note}"
            )
            issues.append(reason)
            _record_drop(
                PageImageDropCode.BUDGET_POLICY,
                slug=label,
                url=spec_url,
                reason=reason,
            )
            continue
        if budget_note:
            # 派生档换了字节身份与像素几何：安全评估、去重、写盘与权利摘要之后
            # 一律看派生体，原体不再随流程流转。
            payload = admitted
            width, height = int(admitted["width"]), int(admitted["height"])
            derived_px_issue = pixel_size_issue(width, height, asset_id=label)
            if derived_px_issue:
                reason = (
                    f"{DataIssueCode.MEDIA_ASSET_OVER_BUDGET.value}: {label} "
                    f"({spec_url}) {budget_note} but the derived variant fails the "
                    f"pixel gate: {derived_px_issue}"
                )
                issues.append(reason)
                _record_drop(
                    PageImageDropCode.BUDGET_POLICY,
                    slug=label,
                    url=spec_url,
                    reason=reason,
                )
                continue
            budget_derivations.append(
                {"slug": label, "url": spec_url, "derivation": budget_note}
            )
        temp_file = _write_image_check_temp_file(
            execution_id,
            subdir="tmp_source_unit_image_checks",
            payload=payload,
        )
        try:
            verdict = _assess_source_image(temp_file, spec, execution_id=execution_id)
        finally:
            _cleanup_image_check_temp_file(temp_file)
        if verdict.blocks_image_publish:
            issues.append(f"{label}: imageSafety blocked ({verdict.status}) reasons={list(verdict.reasons)}")
            _record_drop(
                PageImageDropCode.SAFETY_POLICY,
                slug=label,
                url=spec_url,
                reason=f"{verdict.status} {list(verdict.reasons)}",
            )
            continue
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=label)
        if rel_issue:
            issues.append(rel_issue)
            _record_drop(
                PageImageDropCode.RELEVANCE_POLICY,
                slug=label,
                url=spec_url,
                reason=rel_issue,
            )
            continue
        rights = normalize_rights_payload(spec)
        captured_at = str(
            spec.get("capturedAt")
            or spec.get("collectedAt")
            or source.get("fetchedAt")
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ).strip()
        asset_payload = {
                "bytes": payload["bytes"],
                "ext": payload["ext"],
                "url": payload.get("url") or spec.get("url") or "",
                "requestedUrl": payload.get("requestedUrl") or spec.get("url") or "",
                "normalizedFromUrl": payload.get("normalizedFromUrl") or "",
                "sourceUrl": spec.get("sourceUrl") or spec.get("url") or "",
                "contentType": payload.get("contentType") or "",
                "width": width,
                "height": height,
                "license": rights.get("license") or spec.get("license") or "",
                "credit": rights.get("credit") or spec.get("credit") or "",
                "termsUrl": rights.get("termsUrl") or spec.get("termsUrl") or "",
                "licenseSnapshot": rights.get("licenseSnapshot") or spec.get("licenseSnapshot") or "",
                "usageScope": rights.get("usageScope") or spec.get("usageScope") or "",
                "generationModel": rights.get("generationModel") or "",
                "generationPromptHash": rights.get("generationPromptHash") or "",
                "generatedAt": rights.get("generatedAt") or "",
                "syntheticDisclosure": rights.get("syntheticDisclosure") or "",
                "sourceCollectionId": spec.get("sourceCollectionId") or "",
                "creator": spec.get("creator") or spec.get("credit") or "",
                "platform": spec.get("platform") or source.get("platform") or "",
                "collectionPageUrl": spec.get("collectionPageUrl") or spec.get("sourceUrl") or "",
                "authorizationProof": spec.get("authorizationProof") or "",
                **provenance.audit_fields(),
                "caption": str(spec.get("caption") or relevance),
                "relevance": relevance,
                "slug": f"{source_id}_{idx_img}",
                # RC3：内联同源图回连 source.md 段落占位（非内联候选为空字符串）。
                "placeholderId": str(spec.get("placeholderId") or ""),
                # 布局/封面候选语义透传（source.layout.json figure 同源；无结构源为默认值）。
                "placementType": str(spec.get("placementType") or ""),
                "groupId": candidate_group,
                "sectionSlug": str(spec.get("sectionSlug") or ""),
                "sourceOrder": int(spec.get("sourceOrder") or 0),
                "coverCandidateRank": int(spec.get("coverCandidateRank") or 0),
                "subjectKey": str(spec.get("subjectKey") or ""),
                "isMapLike": bool(spec.get("isMapLike")),
                "fileTitle": str(spec.get("fileTitle") or ""),
                "pageResolvedTitle": str(spec.get("pageResolvedTitle") or ""),
                "pageId": int(spec.get("pageId") or 0),
                "pageRevisionId": int(spec.get("pageRevisionId") or 0),
                "pageContentSha256": str(spec.get("pageContentSha256") or ""),
                "renderedImageCount": int(spec.get("renderedImageCount") or 0),
            }
        placement_type_raw = str(spec.get("placementType") or "")
        if placement_type_raw in {item.value for item in PageImagePlacementType}:
            file_title = str(spec.get("fileTitle") or "").strip()
            if not file_title:
                file_title = str(spec.get("url") or "").split("?", 1)[0].rsplit("/", 1)[-1]
            placement = PageImagePlacement(
                file_title=file_title or f"page-image-{idx_img}.jpg",
                caption=str(spec.get("caption") or relevance),
                section_slug=str(spec.get("sectionSlug") or ""),
                paragraph_index=int(spec.get("paragraphIndex") or 0),
                source_order=int(spec.get("sourceOrder") or 0),
                placement_type=PageImagePlacementType(placement_type_raw),
                group_id=candidate_group,
                cover_rank=int(spec.get("coverCandidateRank") or 0),
                placeholder_id=str(spec.get("placeholderId") or ""),
                subject_key=str(spec.get("subjectKey") or ""),
                is_map_like=bool(spec.get("isMapLike")),
            )
            typed_asset = DownloadedPageAsset(
                placement=placement,
                content=payload["bytes"],
                ext=str(payload["ext"]),
                url=str(payload.get("url") or spec.get("url") or ""),
                requested_url=str(payload.get("requestedUrl") or spec.get("url") or ""),
                source_url=str(spec.get("sourceUrl") or spec.get("url") or ""),
                content_type=str(payload.get("contentType") or ""),
                width=width,
                height=height,
                license_name=str(rights.get("license") or spec.get("license") or ""),
                credit=str(rights.get("credit") or spec.get("credit") or ""),
                terms_url=str(rights.get("termsUrl") or spec.get("termsUrl") or ""),
                authorization_proof=str(
                    spec.get("authorizationProof")
                    or rights.get("termsUrl")
                    or spec.get("termsUrl")
                    or spec.get("sourceUrl")
                    or ""
                ),
            )
            asset_payload.update(typed_asset.as_dict())
        asset_payload.update(
            _acquired_asset_contract(
                asset_payload,
                provenance=provenance,
                captured_at=captured_at,
            )
        )
        images.append(asset_payload)
    downloaded_images = images
    images, duplicates = dedupe_image_payloads(downloaded_images)
    if duplicates:
        issues.append(f"{source_id}: source image dedupe removed {len(duplicates)} near-duplicate image(s)")
        for duplicate_index in duplicates:
            duplicate = downloaded_images[duplicate_index]
            _record_drop(
                PageImageDropCode.DUPLICATE,
                slug=str(duplicate.get("slug") or f"{source_id}#duplicate-{duplicate_index + 1}"),
                url=str(duplicate.get("url") or ""),
                reason="near-duplicate source image",
            )
    funnel = _funnel(candidate_count, len(duplicates))
    structured_page_images = any(
        str(spec.get("placementType") or "")
        in {"lead", "infoboxLead", "inline", "groupMember", "locatorMap"}
        for spec in all_candidates
        if isinstance(spec, Mapping)
    )
    incomplete_downloads = [
        row
        for row in drops
        if str(row.get("code") or "") == PageImageDropCode.FETCH_FAILURE.value
    ]
    if structured_page_images and incomplete_downloads:
        return (
            images,
            [
                (
                    "DATA.MEDIA.DOWNLOAD_INCOMPLETE: "
                    f"{len(incomplete_downloads)} structured page image(s) failed to download"
                )
            ],
            funnel,
        )
    # 策略排除（许可/像素/安全/去重）保留在 funnel；结构化页面的网络下载漏失必须阻断。
    if images:
        return images, [], funnel
    return images, issues, funnel
