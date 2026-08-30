"""Professional image-provider acquisition and rights classification.

Provider terms describe how an asset may be discovered and which evidence is
still missing; they do not prove the rights status of an individual file.
Research admission is therefore decided only after a file has been acquired
through an allowed path and its per-asset provenance has been recorded.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.content_source_registry import load_content_source_registry
from core.content_source_registry_projection import registry_sources


RIGHTS_POLICY_ACCESS_MODE: dict[str, str] = {
    "open_license_required": "open_license_conditional",
    "attribution_no_watermark": "attribution_conditional",
    "asset_level_required": "asset_rights_conditional",
    "creator_authorization_required": "creator_authorization_conditional",
    "commercial_license_required": "commercial_license_conditional",
    "reference_only": "discovery_only",
    "official_terms_required": "official_terms_conditional",
    "factual_reference_only": "discovery_only",
}

_DISCOVERY_ONLY_MODES = frozenset({"discovery_only"})
_DEFAULT_PATHS_BY_FETCH_MODE: dict[str, tuple[str, ...]] = {
    "api": ("supported_api",),
    "licensed_api": ("supported_api", "manual_file"),
    "attribution_manifest": ("public_direct", "supported_api", "manual_file"),
    "manual_authorization": ("manual_file",),
    "search": (),
    "platform_reference": (),
    "html": (),
}


def _image_provider_rows(data: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    registry = data if data is not None else load_content_source_registry()
    rows: list[dict[str, Any]] = []
    for _scope, row in registry_sources(registry):
        lanes = row.get("lanes")
        if isinstance(lanes, list) and "image" in {str(item).strip() for item in lanes}:
            rows.append(dict(row))
    return rows


def access_mode_for_rights_policy(rights_policy: str) -> str:
    return RIGHTS_POLICY_ACCESS_MODE.get(
        str(rights_policy or "").strip(),
        "creator_authorization_conditional",
    )


def _acquisition_paths(row: Mapping[str, Any]) -> list[str]:
    explicit = row.get("researchAcquisitionPaths")
    if isinstance(explicit, list):
        return sorted({str(item).strip() for item in explicit if str(item).strip()})
    return list(_DEFAULT_PATHS_BY_FETCH_MODE.get(str(row.get("fetchMode") or ""), ()))


def open_license_publishable_providers(data: Mapping[str, Any] | None = None) -> list[str]:
    """Providers whose exact assets can become commercial after license verification."""
    ids: list[str] = []
    for row in _image_provider_rows(data):
        if str(row.get("rightsPolicy") or "") == "open_license_required":
            source_id = str(row.get("sourceId") or "").strip()
            if source_id:
                ids.append(source_id)
    return ids


def classify_image_provider(
    *,
    source_id: str = "",
    platform: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve discovery/acquisition capability without inventing asset rights."""
    registry = data if data is not None else load_content_source_registry()
    rows = _image_provider_rows(registry)
    wanted_id = str(source_id or "").strip().casefold()
    wanted_platform = str(platform or "").strip().casefold()
    matched: dict[str, Any] | None = None
    for row in rows:
        row_id = str(row.get("sourceId") or "").strip().casefold()
        row_platform = str(row.get("platform") or "").strip().casefold()
        if wanted_id and row_id == wanted_id:
            matched = row
            break
        if wanted_platform and row_platform == wanted_platform:
            matched = row
            break
    if matched is None and wanted_platform:
        for row in rows:
            row_platform = str(row.get("platform") or "").strip().casefold()
            if row_platform and (row_platform in wanted_platform or wanted_platform in row_platform):
                matched = row
                break
    row = matched or {}
    rights_policy = str(row.get("rightsPolicy") or "").strip()
    access_mode = access_mode_for_rights_policy(rights_policy)
    paths = _acquisition_paths(row)
    research_eligible = bool(paths) and access_mode not in _DISCOVERY_ONLY_MODES
    return {
        "sourceId": str(row.get("sourceId") or source_id or "").strip(),
        "platform": str(row.get("platform") or platform or "").strip(),
        "sourceClass": str(row.get("sourceClass") or "").strip(),
        "rightsPolicy": rights_policy,
        "fetchMode": str(row.get("fetchMode") or "").strip(),
        "defaultRole": str(row.get("defaultRole") or "").strip(),
        "accessMode": access_mode,
        "acquisitionPaths": paths,
        "researchEligible": research_eligible,
        "commercialEvidenceRequired": rights_policy != "open_license_required",
        "restricted": access_mode in _DISCOVERY_ONLY_MODES or not paths,
        "registered": matched is not None,
    }


def image_provider_restriction(
    *,
    source_id: str = "",
    platform: str = "",
    query: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return an acquisition blocker, not a commercial-rights judgement."""
    info = classify_image_provider(source_id=source_id, platform=platform, data=data)
    if info["researchEligible"]:
        return None
    record: dict[str, Any] = {
        **info,
        "restrictionKind": "no_supported_acquisition_path",
        "reason": (
            "该来源当前仅可发现/参考，未声明公开直链、平台支持 API 或人工文件取得路径；"
            "不得绕过登录、验证码、付费墙或访问控制。"
        ),
        "bypassAttempted": False,
    }
    if str(query or "").strip():
        record["query"] = str(query).strip()
    return record


def restricted_image_providers(data: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    registry = data if data is not None else load_content_source_registry()
    records: list[dict[str, Any]] = []
    for row in _image_provider_rows(registry):
        source_id = str(row.get("sourceId") or "").strip()
        record = image_provider_restriction(source_id=source_id, data=registry)
        if record is not None:
            records.append(record)
    return records


def professional_library_compliance_summary(
    provider_ids: list[str] | tuple[str, ...] | None = None,
    *,
    query: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose research acquisition capability separately from rights proof."""
    registry = data if data is not None else load_content_source_registry()
    targets = (
        [str(row.get("sourceId") or "").strip() for row in _image_provider_rows(registry)]
        if provider_ids is None
        else [str(item).strip() for item in provider_ids]
    )
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for source_id in targets:
        if not source_id:
            continue
        info = classify_image_provider(source_id=source_id, data=registry)
        if info["researchEligible"]:
            eligible.append(info)
        else:
            record = image_provider_restriction(
                source_id=source_id,
                query=query,
                data=registry,
            )
            if record is not None:
                blocked.append(record)
    return {
        "policy": "acquisition_separate_from_distribution_rights",
        "bypassAttempted": False,
        "researchEligibleProviders": eligible,
        "acquisitionBlockedProviders": blocked,
        "note": (
            "公开直链、平台支持 API 或人工文件只证明取得成功；每个文件仍需记录逐资产来源、"
            "Creator、rightsStatus 和 rightsIssues。unverified/unknown 仅可进入 research release。"
        ),
    }


__all__ = [
    "RIGHTS_POLICY_ACCESS_MODE",
    "access_mode_for_rights_policy",
    "classify_image_provider",
    "image_provider_restriction",
    "open_license_publishable_providers",
    "professional_library_compliance_summary",
    "restricted_image_providers",
]
