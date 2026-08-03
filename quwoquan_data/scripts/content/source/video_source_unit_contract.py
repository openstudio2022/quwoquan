"""Fail-closed invariants for commercially publishable video source units."""
from __future__ import annotations

from typing import Any, Mapping

from core.video_source_admission import VIDEO_SOURCE_KINDS


def assert_video_source_unit_invariants(manifest: Mapping[str, Any]) -> None:
    expected = {
        "extractor": "sourced_video_direct_download",
        "policyRevision": "sourced-video-attribution",
        "researchLane": "video",
        "hasVideo": True,
    }
    issues = [
        f"{field}={manifest.get(field)!r} expected={value!r}"
        for field, value in expected.items()
        if manifest.get(field) != value
    ]
    source_kind = str(manifest.get("sourceKind") or "").strip()
    if source_kind not in VIDEO_SOURCE_KINDS:
        issues.append(f"sourceKind={source_kind!r} is not a video source kind")
    use_mode = str(manifest.get("sourceUseMode") or "")
    rights_mode = str(manifest.get("rightsMode") or "")
    allowed_modes = {
        ("licensed_adaptation", "attribution_no_watermark"),
        ("rights_audit_only", "rights_audit_only"),
    }
    if (use_mode, rights_mode) not in allowed_modes:
        issues.append(
            "sourceUseMode/rightsMode must be one governed commercial or research pair"
        )
    if issues:
        raise ValueError("video source unit invariant failed: " + "; ".join(issues))


__all__ = ["assert_video_source_unit_invariants"]
