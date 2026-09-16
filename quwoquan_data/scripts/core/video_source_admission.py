"""分别校验视频取得、安全事实与 production 发布契约。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

VIDEO_SOURCE_KINDS = {
    "douyin",
    "tiktok",
    "weibo",
    "toutiao",
    "tourism_video_site",
}
REQUIRED_EVIDENCE = {
    "directly_downloadable_asset",
    "media_probe",
    "sampled_watermark_ocr",
    "original_creator_attribution",
    "source_post_url",
    "original_asset_url",
    "audio_rights",
    "model_release",
    "property_release",
    "notice_and_takedown",
}
VIDEO_ACQUISITION_PATHS_BY_FETCH_MODE = {
    "api": {"public_direct", "supported_api", "manual_file"},
    "attribution_manifest": {"public_direct", "manual_file"},
    "licensed_api": {"supported_api", "manual_file"},
    "platform_reference": {"manual_file"},
}

def _video_policy(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    lane_policies = registry.get("lanePolicies")
    if not isinstance(lane_policies, Mapping):
        return {}
    policy = lane_policies.get("video")
    return policy if isinstance(policy, Mapping) else {}


def _video_sources(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    common = registry.get("common")
    if isinstance(common, Mapping) and isinstance(common.get("video"), list):
        rows.extend(
            row
            for row in common["video"]
            if isinstance(row, Mapping)
        )
    verticals = registry.get("verticals")
    travel = (
        verticals.get("travel")
        if isinstance(verticals, Mapping)
        else None
    )
    if isinstance(travel, Mapping) and isinstance(travel.get("video"), list):
        rows.extend(
            row
            for row in travel["video"]
            if isinstance(row, Mapping)
        )
    return {
        str(row.get("sourceId") or "").strip(): row
        for row in rows
        if str(row.get("sourceId") or "").strip()
    }


def _video_source(
    registry: Mapping[str, Any], *, source_id: str, source_kind: str
) -> Mapping[str, Any]:
    source = _video_sources(registry).get(source_id)
    if source is None:
        raise ValueError(f"video source is not registered: {source_id}")
    declared_kind = str(source.get("sourceKind") or "").strip()
    if declared_kind and declared_kind != source_kind:
        raise ValueError(f"video sourceKind mismatch for {source_id}: {source_kind}")
    return source


def assert_video_acquisition_path_allowed(
    registry: Mapping[str, Any],
    *,
    source_id: str,
    source_kind: str,
    acquisition_path: str,
) -> None:
    """Validate only how bytes were acquired, never their release status."""
    source = _video_source(
        registry, source_id=source_id, source_kind=source_kind
    )
    paths = {
        str(value)
        for value in source.get("acquisitionPaths") or []
    }
    if acquisition_path not in paths:
        raise ValueError(
            f"video acquisition path {acquisition_path} is not allowed "
            f"for source {source_id}"
        )


def verify_video_publication_admission(
    registry: Mapping[str, Any],
) -> list[str]:
    policy = _video_policy(registry)
    issues: list[str] = []
    if policy.get("admissionPolicyRevision") != "sourced-video-attribution":
        issues.append(
            "lanePolicies.video.admissionPolicyRevision must be "
            "sourced-video-attribution"
        )
    evidence = {
        str(value)
        for value in policy.get("requiredEvidence") or []
    }
    missing_evidence = sorted(REQUIRED_EVIDENCE - evidence)
    if missing_evidence:
        issues.append(
            "lanePolicies.video.requiredEvidence missing "
            f"{missing_evidence}"
        )
    invariant = policy.get("invariant")
    expected_invariant = {
        "directDownloadRequired": True,
        "accessControlBypassAllowed": False,
        "drmAllowed": False,
        "watermarkStatusRequired": "absent",
        "attributionRequired": True,
        "audioRightsEvidenceRequired": True,
    }
    if not isinstance(invariant, Mapping) or any(
        invariant.get(field) != value
        for field, value in expected_invariant.items()
    ):
        issues.append("lanePolicies.video.invariant is incomplete or unsafe")

    sources = _video_sources(registry)
    if "publicationAdmissionMatrix" in policy:
        issues.append("lanePolicies.video.publicationAdmissionMatrix is retired")
    for source_id, source in sources.items():
        source_kind = str(source.get("sourceKind") or "").strip()
        if source_kind and source_kind not in VIDEO_SOURCE_KINDS:
            issues.append(f"video source {source_id}: invalid sourceKind")
        acquisition_paths = {str(value) for value in source.get("acquisitionPaths") or []}
        expected_acquisition_paths = VIDEO_ACQUISITION_PATHS_BY_FETCH_MODE.get(str(source.get("fetchMode") or ""))
        if acquisition_paths != expected_acquisition_paths:
            issues.append(
                f"video source {source_id}: acquisition paths must equal {sorted(expected_acquisition_paths or set())}"
            )
    return issues


__all__ = [
    "VIDEO_ACQUISITION_PATHS_BY_FETCH_MODE",
    "VIDEO_SOURCE_KINDS",
    "assert_video_acquisition_path_allowed",
    "verify_video_publication_admission",
]
