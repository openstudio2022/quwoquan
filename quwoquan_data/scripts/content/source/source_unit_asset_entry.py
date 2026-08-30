"""Projection of one accepted source image into its asset index row.

The row is the frozen evidence downstream stages consume, so every field is
derived here from provider evidence rather than recomputed per consumer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.source.rights_decision_projection import projected_distribution_decision


def build_source_asset_entry(
    img: Mapping[str, Any],
    *,
    execution_id: str,
    ordinal: int,
    k: int,
    file_name: str,
    sha: str,
    width: Any,
    height: Any,
    dest_bytes: int,
    provenance: Any,
    variants_meta: list[dict[str, Any]],
    build_variants: bool,
    relevance: str,
    resolved_source_kind: str,
    is_representative_visual: bool,
) -> dict[str, Any]:
    return {
        "sourceAssetId": f"{ordinal:03d}_{k:03d}",
        "fileName": file_name,
        "url": str(img.get("url") or ""),
        "requestedUrl": str(img.get("requestedUrl") or img.get("url") or ""),
        "normalizedFromUrl": str(img.get("normalizedFromUrl") or ""),
        "sourceUrl": str(img.get("sourceUrl") or img.get("url") or ""),
        "contentType": str(img.get("contentType") or ""),
        "width": int(width) if width else 0,
        "height": int(height) if height else 0,
        "bytes": dest_bytes,
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
        "acquisitionReceiptRef": str(img.get("acquisitionReceiptRef") or ""),
        "professionalAssetId": str(img.get("professionalAssetId") or ""),
        "professionalContentSha256": str(
            img.get("professionalContentSha256") or ""
        ),
        "acquisitionStatus": str(img.get("acquisitionStatus") or ""),
        "rightsStatus": str(
            img.get("rightsStatus") or img.get("rightsAuditStatus") or ""
        ),
        "authorizationRequired": img.get("authorizationRequired"),
        **projected_distribution_decision(img),
        "platform": str(img.get("platform") or ""),
        "capturedAt": str(img.get("capturedAt") or ""),
        "contentSha256": sha,
        "rightsIssues": list(
            img.get("rightsIssues") or img.get("rightsAuditIssues") or []
        ),
        **provenance.audit_fields(),
        "caption": str(img.get("caption") or ""),
        "relevance": str(img.get("relevance") or relevance or ""),
        "variants": variants_meta,
        "variantGeneration": "inline" if build_variants else "deferred",
        "inlinePlaceholderId": str(img.get("placeholderId") or ""),
        # 布局/封面候选语义（来自 source.layout.json figure；非结构源为空/默认）：
        # placementType=infoboxLead|locatorMap|inline|groupMember；rank=-1 禁封面。
        "placementType": str(
            img.get("placementType")
            or (
                "infoboxLead"
                if resolved_source_kind == "image_collection" and k == 1
                else "groupMember" if resolved_source_kind == "image_collection" else ""
            )
        ),
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
        "isRepresentativeVisual": is_representative_visual,
        # provider 原图主体优先；图位 caption 仅在无独立证据时回退。
        "visualSubject": str(img.get("visualSubject") or img.get("caption") or ""),
        # Commons category -> Wikidata 多语言标签，是视觉主体别名的唯一
        # provider 证据；下游只能消费这些冻结行，不能自行翻译文件名。
        "visualSubjectEvidence": [
            dict(item)
            for item in img.get("visualSubjectEvidence") or []
            if isinstance(item, Mapping)
        ],
    }


__all__ = ["build_source_asset_entry"]
