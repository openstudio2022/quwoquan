"""Object-reference closure helpers for canonical campaign scale evidence."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
)


def canonical_lane_refs(carrier: str, publish: Mapping[str, Any]) -> list[str]:
    refs = publish.get("publishedRefs")
    if not isinstance(refs, Mapping):
        raise CampaignScaleEvidenceError(f"{carrier} publish_ref publishedRefs invalid")
    entities = list(refs.get("entities") or [])
    posts = list(refs.get("posts") or [])
    if carrier == "homepage":
        if posts:
            raise CampaignScaleEvidenceError("homepage lane wrote post refs")
        return [f"entities/{str(ref).strip('/')}" for ref in entities]
    if entities:
        raise CampaignScaleEvidenceError(f"{carrier} lane wrote entity refs")
    return [f"posts/{str(ref).strip('/')}" for ref in posts]


def duplicate_asset_count(admission: Mapping[str, Any]) -> int:
    assets = [row for row in admission.get("assets") or [] if isinstance(row, Mapping)]
    asset_ids = Counter(str(row.get("assetId") or "") for row in assets)
    content = Counter(str(row.get("contentSha256") or "") for row in assets)
    return sum(max(0, count - 1) for key, count in asset_ids.items() if key) + sum(
        max(0, count - 1) for key, count in content.items() if key
    )


__all__ = ["canonical_lane_refs", "duplicate_asset_count"]
