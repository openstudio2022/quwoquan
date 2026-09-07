"""Separate video acquisition, research use and commercial admission policy."""
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
PUBLICATION_ADMISSIONS = {
    "research_release",
    "commercial_release",
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
REFERENCE_ONLY_GATE_BLOCK = "GATE_BLOCK DATA.CONTRACT.INVALID"


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


def _is_reference_only_provider(source: Mapping[str, Any]) -> bool:
    return (
        str(source.get("defaultRole") or "").strip() == "reference_only"
        or str(source.get("fetchMode") or "").strip() == "platform_reference"
    )


def video_commercial_admission(
    registry: Mapping[str, Any],
    *,
    source_id: str,
) -> Mapping[str, Any]:
    matrix = _video_policy(registry).get("commercialAdmissionMatrix")
    for row in matrix if isinstance(matrix, list) else []:
        if (
            isinstance(row, Mapping)
            and str(row.get("sourceId") or "").strip() == source_id
        ):
            return row
    raise ValueError(
        f"video source is absent from commercial admission matrix: {source_id}"
    )


def _video_source_and_admission(
    registry: Mapping[str, Any],
    *,
    source_id: str,
    source_kind: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    source = _video_sources(registry).get(source_id)
    if source is None:
        raise ValueError(f"video source is not registered: {source_id}")
    row = video_commercial_admission(registry, source_id=source_id)
    if str(row.get("sourceKind") or "") != source_kind:
        raise ValueError(
            f"video sourceKind mismatch for {source_id}: {source_kind}"
        )
    return source, row


def assert_video_acquisition_path_allowed(
    registry: Mapping[str, Any],
    *,
    source_id: str,
    source_kind: str,
    acquisition_path: str,
) -> None:
    """Validate only how bytes were acquired, never their release status."""
    source, _row = _video_source_and_admission(
        registry,
        source_id=source_id,
        source_kind=source_kind,
    )
    paths = {
        str(value)
        for value in source.get("researchAcquisitionPaths") or []
    }
    if acquisition_path not in paths:
        raise ValueError(
            f"video acquisition path {acquisition_path} is not allowed "
            f"for source {source_id}"
        )


def assert_video_distribution_use_allowed(
    registry: Mapping[str, Any],
    *,
    source_id: str,
    source_kind: str,
    publication_admission: str,
) -> None:
    """Validate distribution without treating rights facts as acquisition facts.

    A protected research release is admitted from per-asset rights and safety
    evidence.  Source-level publication defaults remain authoritative for
    commercial and explicitly risk-accepted publication only.
    """
    _source, row = _video_source_and_admission(
        registry,
        source_id=source_id,
        source_kind=source_kind,
    )
    if publication_admission == "research_release":
        return
    admissions = {
        str(value)
        for value in row.get("publicationAdmissions") or []
    }
    if publication_admission not in admissions:
        raise ValueError(
            f"publication admission {publication_admission} is not allowed "
            f"for video source {source_id}"
        )


def verify_video_commercial_admission(
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
    matrix = policy.get("commercialAdmissionMatrix")
    matrix_rows = [
        row
        for row in matrix if isinstance(row, Mapping)
    ] if isinstance(matrix, list) else []
    matrix_ids = [
        str(row.get("sourceId") or "").strip()
        for row in matrix_rows
    ]
    if set(matrix_ids) != set(sources):
        issues.append(
            "lanePolicies.video.commercialAdmissionMatrix sourceIds must "
            "exactly match registered video sources"
        )
    if len(matrix_ids) != len(set(matrix_ids)):
        issues.append(
            "lanePolicies.video.commercialAdmissionMatrix has duplicate sourceId"
        )
    for row in matrix_rows:
        source_id = str(row.get("sourceId") or "").strip()
        source_kind = str(row.get("sourceKind") or "").strip()
        admissions = {
            str(value)
            for value in row.get("publicationAdmissions") or []
        }
        if source_kind not in VIDEO_SOURCE_KINDS:
            issues.append(f"video matrix {source_id}: invalid sourceKind")
        if not admissions <= PUBLICATION_ADMISSIONS:
            issues.append(
                f"video matrix {source_id}: invalid publicationAdmissions"
            )
        source = sources.get(source_id) or {}
        reference_only = _is_reference_only_provider(source)
        acquisition_paths = {
            str(value)
            for value in source.get("researchAcquisitionPaths") or []
        }
        expected_acquisition_paths = VIDEO_ACQUISITION_PATHS_BY_FETCH_MODE.get(
            str(source.get("fetchMode") or "")
        )
        if acquisition_paths != expected_acquisition_paths:
            issues.append(
                f"video source {source_id}: research acquisition paths must "
                f"equal {sorted(expected_acquisition_paths or set())}"
            )
        if reference_only:
            if admissions:
                issues.append(
                    f"{REFERENCE_ONLY_GATE_BLOCK}: video matrix {source_id} is "
                    "reference_only/platform_reference but declares release "
                    "admissions"
                )
        else:
            if not admissions:
                issues.append(
                    f"video matrix {source_id}: invalid publicationAdmissions"
                )
            if "research_release" not in admissions:
                issues.append(
                    f"video matrix {source_id}: research_release admission is required"
                )
    return issues


__all__ = [
    "VIDEO_ACQUISITION_PATHS_BY_FETCH_MODE",
    "VIDEO_SOURCE_KINDS",
    "assert_video_acquisition_path_allowed",
    "assert_video_distribution_use_allowed",
    "verify_video_commercial_admission",
    "video_commercial_admission",
]
