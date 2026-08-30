"""Normalize the many upstream image-spec shapes into one row shape.

计划、auto_research、专业采集与人工清单写出的 image spec 形态各不相同：有的是
裸 URL 字符串，有的是带权利、归因、版式与页面证据的完整对象。下游的相关性门、
像素门、caption 与权利分级都只认一种行形状，所以规范化必须集中在一处，否则每
个消费方都会各自补一套键名兜底，形成同一事实的多份记录。

本模块只做形状规范化：认识的键原样透传，`distributionDecision` 交给
`rights_decision_projection` 区分缺席与在场，不认识的键在这里就消失——这是白名
单投影的既定语义，新增字段必须显式登记才能穿过这一层。
"""

from __future__ import annotations

from typing import Any

from content.source.rights_decision_projection import projected_distribution_decision


def normalize_image_specs(raw: Any) -> list[dict[str, Any]]:
    """Project one upstream image-spec list into deduplicated canonical rows."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            spec = {"url": item, "license": "", "credit": ""}
        elif isinstance(item, dict):
            url = item.get("url") or item.get("link") or ""
            spec = {
                "url": url,
                "license": item.get("license", ""),
                "credit": item.get("credit") or item.get("author") or "",
                "sourceUrl": item.get("sourceUrl") or url,
                "termsUrl": item.get("termsUrl", ""),
                "licenseSnapshot": item.get("licenseSnapshot", ""),
                "usageScope": item.get("usageScope", ""),
                "platform": item.get("platform") or item.get("sourcePlatform") or "",
                "modelReleaseRequired": item.get("modelReleaseRequired", ""),
                "modelReleaseStatus": item.get("modelReleaseStatus", ""),
                "authorizationProof": item.get("authorizationProof", ""),
                "generationModel": item.get("generationModel", ""),
                "generationPromptHash": item.get("generationPromptHash", ""),
                "generatedAt": item.get("generatedAt", ""),
                "syntheticDisclosure": item.get("syntheticDisclosure", ""),
                # 相关性/说明/类型/尺寸：供 relevance 门、caption 与像素门消费。
                "caption": item.get("caption", ""),
                "relevance": item.get("relevance") or item.get("caption") or "",
                "contentType": item.get("contentType", ""),
                "width": item.get("width", ""),
                "height": item.get("height", ""),
                "sourceCollectionId": item.get("sourceCollectionId", ""),
                "sourceId": item.get("sourceId", ""),
                "creator": item.get("creator") or item.get("author") or "",
                "collectionPageUrl": item.get("collectionPageUrl") or item.get("sourceUrl") or "",
                "placeholderId": item.get("placeholderId", ""),
                "placementType": item.get("placementType", ""),
                "groupId": item.get("groupId", ""),
                "sectionSlug": item.get("sectionSlug", ""),
                "sourceOrder": item.get("sourceOrder", 0),
                "coverCandidateRank": item.get("coverCandidateRank", 0),
                "subjectKey": item.get("subjectKey", ""),
                "isMapLike": bool(item.get("isMapLike")),
                "fileTitle": item.get("fileTitle", ""),
                "pageResolvedTitle": item.get("pageResolvedTitle", ""),
                "pageId": item.get("pageId", 0),
                "pageRevisionId": item.get("pageRevisionId", 0),
                "pageContentSha256": item.get("pageContentSha256", ""),
                "renderedImageCount": item.get("renderedImageCount", 0),
                "originalAssetUrl": item.get("originalAssetUrl", ""),
                "capturedAt": item.get("capturedAt", ""),
                "contentSha256": item.get("contentSha256", ""),
                "acquisitionStatus": item.get("acquisitionStatus", ""),
                "rightsStatus": item.get("rightsStatus", ""),
                "authorizationRequired": item.get("authorizationRequired"),
                **projected_distribution_decision(item),
                "rightsAuditStatus": item.get("rightsAuditStatus") or item.get("rightsStatus") or "",
                "rightsIssues": list(item.get("rightsIssues") or []),
                "acquisitionReceiptRef": item.get("acquisitionReceiptRef", ""),
                "professionalAssetId": item.get("professionalAssetId", ""),
                "professionalContentSha256": item.get(
                    "professionalContentSha256", ""
                ),
            }
        else:
            continue
        url = spec["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(spec)
    return out


__all__ = ["normalize_image_specs"]
