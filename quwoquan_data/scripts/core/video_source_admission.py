"""Video-source commercial admission matrix backed by the unified registry."""
from __future__ import annotations

from typing import Any, Mapping


VIDEO_SOURCE_KINDS = {
    "douyin",
    "tiktok",
    "weibo",
    "toutiao",
    "tourism_video_site",
}
PUBLICATION_ADMISSIONS = {
    "commercial_release",
    "risk_accepted_attribution_only",
}
RISK_ATTRIBUTION_SOURCES = {
    "douyin",
    "tiktok",
    "weibo",
    "toutiao_video",
    "travel_vlog",
    "chinese_tourism_vertical",
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


def assert_video_source_admitted(
    registry: Mapping[str, Any],
    *,
    source_id: str,
    source_kind: str,
    publication_admission: str,
) -> None:
    row = video_commercial_admission(registry, source_id=source_id)
    if str(row.get("sourceKind") or "") != source_kind:
        raise ValueError(
            f"video sourceKind mismatch for {source_id}: {source_kind}"
        )
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
        if not admissions or not admissions <= PUBLICATION_ADMISSIONS:
            issues.append(
                f"video matrix {source_id}: invalid publicationAdmissions"
            )
        source = sources.get(source_id) or {}
        if "risk_accepted_attribution_only" in admissions and (
            source.get("defaultRole") != "publish_candidate"
            or source.get("fetchMode") != "attribution_manifest"
            or source.get("rightsPolicy") != "attribution_no_watermark"
        ):
            issues.append(
                f"video matrix {source_id}: risk-attribution source wiring "
                "must be publish_candidate/attribution_manifest/"
                "attribution_no_watermark"
            )
    missing_risk_sources = sorted(
        RISK_ATTRIBUTION_SOURCES
        - {
            str(row.get("sourceId") or "")
            for row in matrix_rows
            if "risk_accepted_attribution_only"
            in (row.get("publicationAdmissions") or [])
        }
    )
    if missing_risk_sources:
        issues.append(
            "video matrix misses required attribution sources "
            f"{missing_risk_sources}"
        )
    return issues


__all__ = [
    "VIDEO_SOURCE_KINDS",
    "assert_video_source_admitted",
    "verify_video_commercial_admission",
    "video_commercial_admission",
]
