"""Strict SourceAttribution completeness checks for pool admission."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_REQUIRED_FIELDS = (
    "originalCreatorName",
    "platform",
    "sourcePostUrl",
    "originalAssetUrl",
    "attributionText",
    "rightsBasis",
    "commercialAuthorizationStatus",
    "publicationAdmission",
    "watermarkStatus",
    "audioRightsStatus",
    "modelReleaseStatus",
    "propertyReleaseStatus",
    "collectedAt",
    "takedownPolicy",
)


def source_attribution_complete(document: Mapping[str, Any]) -> bool:
    attribution = document.get("sourceAttribution")
    return bool(
        isinstance(attribution, Mapping)
        and isinstance(attribution.get("isOriginal"), bool)
        and all(
            str(attribution.get(field) or "").strip()
            for field in _REQUIRED_FIELDS
        )
    )


__all__ = ["source_attribution_complete"]
