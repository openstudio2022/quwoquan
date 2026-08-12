"""Canonical Openverse metadata and attribution projection."""
from __future__ import annotations

import re
import urllib.parse
from collections.abc import Mapping
from typing import Any

_ALLOWED_LICENSES = frozenset({"by", "by-sa", "cc0", "pdm"})
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def openverse_search_url(query: str, *, page_size: int) -> str:
    params = urllib.parse.urlencode(
        {
            "q": " ".join(str(query or "").split()),
            "page_size": str(page_size),
            "license_type": "commercial",
            "mature": "false",
        }
    )
    return "https://api.openverse.org/v1/images/?" + params


def openverse_detail_url(asset_id: str) -> str:
    normalized = str(asset_id or "").strip().lower()
    if not _UUID.fullmatch(normalized):
        raise ValueError("Openverse asset id must be a UUID")
    return f"https://api.openverse.org/v1/images/{normalized}/"


def openverse_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    asset_id = str(value.get("id") or "").strip().lower()
    if not _UUID.fullmatch(asset_id):
        raise ValueError("Openverse result lacks a stable asset UUID")
    license_slug = str(value.get("license") or "").strip().lower()
    license_version = str(value.get("license_version") or "").strip()
    license_url = str(value.get("license_url") or "").strip()
    source_page = str(value.get("foreign_landing_url") or "").strip()
    asset_url = str(value.get("url") or "").strip()
    creator = " ".join(str(value.get("creator") or "").split())
    upstream_provider = str(value.get("provider") or value.get("source") or "").strip()
    title = " ".join(str(value.get("title") or "").split())
    width = int(value.get("width") or 0)
    height = int(value.get("height") or 0)
    if (
        license_slug not in _ALLOWED_LICENSES
        or bool(value.get("mature"))
        or not source_page.startswith("https://")
        or not asset_url.startswith("https://")
        or not license_url.startswith("https://creativecommons.org/")
        or not creator
        or not upstream_provider
        or not license_version
        or width < 1
        or height < 1
    ):
        raise ValueError("Openverse provenance/license metadata is incomplete")
    license_name = (
        "Public Domain Mark"
        if license_slug == "pdm"
        else "CC0"
        if license_slug == "cc0"
        else f"CC {license_slug.upper()} {license_version}".strip()
    )
    return {
        "providerAssetId": asset_id,
        "sourcePageUrl": source_page,
        "originalAssetUrl": asset_url,
        "creator": creator,
        "license": license_name,
        "licenseSlug": license_slug,
        "licenseVersion": license_version,
        "termsUrl": license_url,
        "upstreamProvider": upstream_provider,
        "title": title or f"Openverse image {asset_id}",
        "attributionText": " ".join(str(value.get("attribution") or "").split())
        or f"{creator} · {license_name}",
        "width": width,
        "height": height,
    }


def openverse_source_attribution(
    meta: Mapping[str, Any], *, observed_at: str,
) -> dict[str, Any]:
    return {
        "isOriginal": False,
        "originalCreatorName": str(meta["creator"]),
        "platform": "Openverse",
        "sourcePostUrl": str(meta["sourcePageUrl"]),
        "originalAssetUrl": str(meta["originalAssetUrl"]),
        "attributionText": str(meta["attributionText"]),
        "rightsBasis": str(meta["license"]),
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": str(meta["sourcePageUrl"]),
        "termsUrl": str(meta["termsUrl"]),
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "unverified",
        "collectedAt": str(observed_at),
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
    }


__all__ = [
    "openverse_detail_url",
    "openverse_metadata",
    "openverse_search_url",
    "openverse_source_attribution",
]
