"""Deterministic provider funnel counts for image acquisition receipts."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any


def provider_counts(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["displayName"]), str(row["provider"]))].append(row)
    result: list[dict[str, Any]] = []
    for (display_name, provider), assets in sorted(grouped.items()):
        rights = Counter(str(row["rightsStatus"]) for row in assets)
        downloaded = sum(row["acquisitionStatus"] == "acquired" for row in assets)
        accepted = sum(
            row["distributionDecision"]
            in {"research_allowed", "commercial_allowed"}
            for row in assets
        )
        result.append(
            {
                "displayName": display_name,
                "provider": provider,
                "plannedAssetCount": len(assets),
                "discoveredAssetCount": len(assets),
                "downloadedAssetCount": downloaded,
                "acceptedAssetCount": accepted,
                "rejectedAssetCount": len(assets) - accepted,
                "verifiedAssetCount": rights["verified"],
                "unverifiedAssetCount": rights["unverified"],
                "restrictedAssetCount": rights["restricted"],
                "unknownAssetCount": rights["unknown"],
            }
        )
    return result


__all__ = ["provider_counts"]
