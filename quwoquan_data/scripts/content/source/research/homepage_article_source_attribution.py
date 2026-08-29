"""Canonical Research attribution for freshly acquired encyclopedia sources."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.source_attribution import (
    canonical_source_attribution,
    derived_modifications_value,
)

_PLATFORMS = {
    "wikipedia": "维基百科",
    "baidu_baike": "百度百科",
    "toutiao_baike": "今日头条百科",
}
_CREATORS = {
    "wikipedia": "维基百科贡献者",
    "baidu_baike": "百度百科词条贡献者",
    "toutiao_baike": "今日头条百科词条贡献者",
}


def encyclopedia_source_attribution(
    *,
    source_kind: str,
    source_url: str,
    captured_at: str,
) -> dict[str, Any]:
    """Return a complete fail-closed attribution without commercial promotion."""

    kind = str(source_kind).strip()
    url = str(source_url).strip()
    platform = _PLATFORMS.get(kind)
    creator = _CREATORS.get(kind)
    if not platform or not creator or not url.startswith("https://"):
        raise ValueError("unsupported encyclopedia source attribution identity")
    wikipedia = kind == "wikipedia"
    value: Mapping[str, Any] = {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": platform,
        "sourcePostUrl": url,
        "originalAssetUrl": url,
        "attributionText": f"正文事实来源：{platform}（{creator}）",
        "rightsBasis": "CC BY-SA 4.0" if wikipedia else "factual_reference_only",
        "commercialAuthorizationStatus": "verified" if wikipedia else "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": url if wikipedia else None,
        "termsUrl": (
            "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
            if wikipedia
            else None
        ),
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": str(captured_at).strip(),
        "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
        # 百科来源承载的是正文事实引用，本身不落媒体字节，因此没有衍生修改。
        "derivedModifications": derived_modifications_value(),
    }
    return canonical_source_attribution(value)


__all__ = ["encyclopedia_source_attribution"]
