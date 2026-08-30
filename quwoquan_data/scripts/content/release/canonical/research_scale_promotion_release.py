"""Hard release-owned closure for cumulative Research milestone promotion."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_cumulative import (
    release_refs_by_carrier,
)
from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
)
from content.release.canonical.campaign_scale_object_closure import (
    duplicate_asset_count,
)
from content.release.canonical.object_transaction_contract import _read_json
from content.release.canonical.release_header import validate_release_header
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy


CARRIERS = ("homepage", "article", "image", "video")


class ResearchMilestoneReleaseError(ValueError):
    """The immutable milestone release cannot prove its own exact closure."""


@dataclass(frozen=True, slots=True)
class ResearchMilestoneRelease:
    header: dict[str, Any]
    admission: dict[str, Any]
    manifest_digest: str
    targets: dict[str, int]
    counts: dict[str, int]
    refs_by_carrier: dict[str, set[str]]


def _count(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResearchMilestoneReleaseError(
            f"{label} must be a non-negative integer"
        )
    return value


def _asset_object_refs(admission: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("objectRef") or "")
        for row in admission.get("assets") or []
        if isinstance(row, Mapping)
        and str(row.get("objectRef") or "").startswith(("entities/", "posts/"))
    }


def load_research_milestone_release(
    release: Path,
    *,
    release_id: str,
    target_scale: str,
) -> ResearchMilestoneRelease:
    """Load only release-owned facts; workflow diagnostics are intentionally absent."""

    header = _read_json(payload_file(release, "release.json"))
    admission = _read_json(payload_file(release, "asset_admission.json"))
    desired = _read_json(payload_file(release, "desired_state.json"))
    try:
        validate_release_header(
            header, label=f"research {target_scale} milestone release"
        )
        assert_valid(
            admission,
            "release",
            "release_asset_admission",
            label=f"research {target_scale} asset admission",
        )
        assert_valid(
            desired,
            "release",
            "release_desired_state",
            label=f"research {target_scale} desired state",
        )
    except (CampaignScaleEvidenceError, TypeError, ValueError) as exc:
        raise ResearchMilestoneReleaseError(str(exc)) from exc

    policy = load_content_distribution_policy()
    targets = {
        carrier: policy.scale_target(target_scale, carrier)
        for carrier in CARRIERS
    }
    if (
        header.get("releaseId") != release_id
        or admission.get("releaseId") != release_id
        or desired.get("releaseId") != release_id
        or header.get("releaseClass") != "research"
        or header.get("productLifecycleState") != "research"
        or admission.get("releaseClass") != "research"
        or admission.get("productLifecycleState") != "research"
        or header.get("milestone") != target_scale
        or header.get("targetEnvironment") is not None
        or header.get("releaseMode") != "research"
        or header.get("milestoneTargets") != targets
    ):
        raise ResearchMilestoneReleaseError(
            "research promotion requires one environment-neutral exact milestone "
            "Research release"
        )

    shared_fields = (
        "containsUnverifiedAssets",
        "rightsStatusCounts",
        "authorizationRequiredAssetIds",
        "researchAcceptedCount",
        "commercialAcceptedCount",
    )
    if any(header.get(field) != admission.get(field) for field in shared_fields):
        raise ResearchMilestoneReleaseError(
            "release header and asset admission lifecycle/count identity drift"
        )

    try:
        refs_by_carrier = release_refs_by_carrier(release)
    except (CampaignScaleEvidenceError, TypeError, ValueError) as exc:
        raise ResearchMilestoneReleaseError(str(exc)) from exc
    carrier_rows = admission.get("carrierCounts")
    if not isinstance(carrier_rows, list):
        raise ResearchMilestoneReleaseError("release carrierCounts are missing")
    rows = {
        str(row.get("carrier") or ""): row
        for row in carrier_rows
        if isinstance(row, Mapping)
    }
    if len(rows) != len(carrier_rows) or set(rows) != set(CARRIERS):
        raise ResearchMilestoneReleaseError(
            "release carrierCounts must contain each carrier exactly once"
        )

    counts: dict[str, int] = {}
    for carrier in CARRIERS:
        row = rows[carrier]
        accepted = _count(
            row.get("researchAcceptedCount"),
            label=f"{carrier} researchAcceptedCount",
        )
        object_count = _count(
            row.get("objectCount"), label=f"{carrier} objectCount"
        )
        release_count = len(refs_by_carrier[carrier])
        if accepted < targets[carrier] or not (
            accepted == object_count == release_count
        ):
            raise ResearchMilestoneReleaseError(
                "DATA.SCALE.ATTAINMENT_SHORTFALL: "
                f"{carrier} requires milestone>={targets[carrier]} with exact "
                f"immutable closure admission={accepted}/{object_count} "
                f"releaseRefs={release_count}"
            )
        counts[carrier] = accepted

    desired_refs = desired["desiredRefs"]
    desired_posts = {str(ref).strip("/") for ref in desired_refs["posts"]}
    header_posts = {
        str(row.get("postRef") or "").strip("/")
        for row in header.get("contents") or []
        if isinstance(row, Mapping)
    }
    desired_creators = {str(ref).strip("/") for ref in desired_refs["creators"]}
    header_creators = {
        str(row.get("creatorRef") or "").strip("/")
        for row in header.get("authors") or []
        if isinstance(row, Mapping)
    }
    header_counts = header.get("counts")
    if not isinstance(header_counts, Mapping):
        raise ResearchMilestoneReleaseError("release counts are missing")
    post_counts = {
        carrier: len(refs_by_carrier[carrier])
        for carrier in ("article", "image", "video")
    }
    if (
        desired_posts != header_posts
        or desired_creators != header_creators
        or any(
            _count(header_counts.get(carrier), label=f"release counts.{carrier}")
            != post_counts[carrier]
            for carrier in post_counts
        )
        or _count(header_counts.get("total"), label="release counts.total")
        != sum(post_counts.values())
        or _count(
            admission.get("researchAcceptedCount"),
            label="release researchAcceptedCount",
        )
        != sum(counts.values())
    ):
        raise ResearchMilestoneReleaseError(
            "release payload/header/object count exact closure drift"
        )

    release_object_refs = set().union(*refs_by_carrier.values())
    if not _asset_object_refs(admission).issubset(release_object_refs):
        raise ResearchMilestoneReleaseError(
            "release asset admission references objects outside release closure"
        )
    duplicates = duplicate_asset_count(admission)
    if duplicates:
        raise ResearchMilestoneReleaseError(
            f"release duplicateAssetCount must be zero, got {duplicates}"
        )

    return ResearchMilestoneRelease(
        header=header,
        admission=admission,
        manifest_digest=payload_digest(release),
        targets=targets,
        counts=counts,
        refs_by_carrier=refs_by_carrier,
    )


__all__ = [
    "CARRIERS",
    "ResearchMilestoneRelease",
    "ResearchMilestoneReleaseError",
    "load_research_milestone_release",
]
