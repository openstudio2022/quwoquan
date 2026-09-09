"""媒体权利投影：水印、衍生修改与音轨状态的资产行转录与对象级汇总。

final_surface_projection 只搬运 ingest 从 AI 申报与实际处理转录下来的事实，不做业务假定。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from content.release.canonical.object_transaction_contract import ObjectTransactionError


def asset_license_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    """许可、商业授权和发布记录逐项转录，资格取值不相互推导。"""
    attribution = source.get("sourceAttribution")
    authorization = attribution.get("commercialAuthorizationStatus", "unverified") if isinstance(attribution, Mapping) else "unverified"
    return {
        "license": str(source.get("license") or "").strip(),
        "termsUrl": str(source.get("termsUrl") or ""),
        "authorizationProof": str(source.get("authorizationProof") or ""),
        "commercialAuthorizationStatus": authorization,
        "usageScope": str(source.get("usageScope") or "app_publish"),
        "modelReleaseStatus": str(source.get("modelReleaseStatus") or "not_required"),
        "propertyReleaseStatus": str(source.get("propertyReleaseStatus") or "unverified"),
        "distributionDecision": str(source.get("distributionDecision") or ""),
        "rightsAuditStatus": str(source.get("rightsStatus") or source.get("rightsAuditStatus") or "").strip(),
        "rightsAuditIssues": [str(value) for value in source.get("rightsIssues") or source.get("rightsAuditIssues") or [] if str(value)],
    }


def commercial_authorization_rollup(assets: Sequence[Mapping[str, Any]]) -> str:
    """空集合或任一资产缺授权事实，均不能汇总为已验证。"""
    verified = bool(assets) and all(
        row.get("commercialAuthorizationStatus") == "verified"
        and str(row.get("authorizationProof") or "").startswith("https://")
        for row in assets
    )
    return "verified" if verified else "unverified"


def _attribution_source(first: Mapping[str, Any], carrier: str) -> dict[str, str]:
    fields = ("creator", "collectionPageUrl", "license", "termsUrl", "authorizationProof")
    facts = {key: str(first.get(key) or "").strip() for key in fields}
    if not all((facts["creator"], facts["collectionPageUrl"].startswith("https://"), facts["license"])):
        raise ObjectTransactionError(f"{carrier} selected assets lack attribution hard facts")
    return facts


def media_attribution(
    assets: Sequence[Mapping[str, Any]], *, carrier: str, collected_at: str
) -> dict[str, Any]:
    """由选中资产构造对象署名，商业授权只汇总精确逐资产事实。"""
    if not assets:
        raise ObjectTransactionError(f"{carrier} attribution requires selected assets")
    first = assets[0]
    facts = _attribution_source(first, carrier)
    creator, source_url, license_name = facts["creator"], facts["collectionPageUrl"], facts["license"]
    terms_url, proof = facts["termsUrl"], facts["authorizationProof"]
    authorization = commercial_authorization_rollup(assets)
    platform = str(first.get("platform") or "").strip() or urlparse(source_url).netloc
    rights = object_rights_rollup(assets, carrier)
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": platform,
        "sourcePostUrl": source_url,
        "originalAssetUrl": str(first.get("originalAssetUrl") or source_url),
        "attributionText": f"{creator} · {platform} · {license_name}",
        "rightsBasis": license_name,
        "commercialAuthorizationStatus": authorization,
        "publicationAdmission": "commercial_release" if authorization == "verified" else "research_release",
        "authorizationProofUrl": proof or None,
        "termsUrl": terms_url or None,
        **{k: rights[k] for k in ("watermarkStatus", "watermarkKind", "audioRightsStatus")},
        "modelReleaseStatus": str(first.get("modelReleaseStatus") or "not_required"),
        "propertyReleaseStatus": str(first.get("propertyReleaseStatus") or "unverified"),
        "collectedAt": collected_at,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": rights["derivedModifications"],
    }


def asset_rights_fields(source: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """单条资产行的水印三字段、衍生修改与（视频）音轨状态。"""
    fields: dict[str, Any] = {
        "watermarkStatus": str(source.get("watermarkStatus") or "unknown"),
        "watermarkKind": str(source.get("watermarkKind") or "unknown"),
        "watermarkNote": str(source.get("watermarkNote") or ""),
        "derivedModifications": sorted(
            {str(value) for value in source.get("derivedModifications") or [] if str(value)}
        ),
    }
    if str(source.get("accessPolicy") or "").strip():
        # 访问政策只搬运：缺席即缺席，不补 open。
        fields["accessPolicy"] = str(source["accessPolicy"]).strip()
    if kind == "video":
        attribution = source.get("sourceAttribution")
        declared_audio = (
            str(attribution.get("audioRightsStatus") or "").strip()
            if isinstance(attribution, Mapping)
            else ""
        )
        fields["audioRightsStatus"] = declared_audio or "unverified"
    return fields


def object_rights_rollup(assets: Sequence[Mapping[str, Any]], carrier: str) -> dict[str, Any]:
    """对象级汇总：水印取「最重」判定（present > unknown > absent），音轨缺席时保守记 unverified。"""
    statuses = [str(raw.get("watermarkStatus") or "unknown") for raw in assets]
    if "present" in statuses:
        watermark_status = "present"
        watermark_kind = next(
            (
                str(raw.get("watermarkKind") or "other")
                for raw in assets
                if str(raw.get("watermarkStatus") or "") == "present"
            ),
            "other",
        )
    elif "unknown" in statuses:
        watermark_status, watermark_kind = "unknown", "unknown"
    else:
        watermark_status, watermark_kind = "absent", "none"
    if carrier == "video":
        audio = next(
            (
                str(raw.get("audioRightsStatus"))
                for raw in assets
                if str(raw.get("kind") or "") == "video" and raw.get("audioRightsStatus")
            ),
            "unverified",
        )
    else:
        audio = "no_audio"
    return {
        "watermarkStatus": watermark_status,
        "watermarkKind": watermark_kind,
        "audioRightsStatus": audio,
        "derivedModifications": sorted(
            {str(value) for raw in assets for value in raw.get("derivedModifications") or [] if str(value)}
        ),
    }
