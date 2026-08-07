"""Validate and collect M100 video popularity observations from release objects."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import _read_json
from content.source.professional_video_receipt import (
    assert_observed_popularity_signals,
)
from core.release_layout import payload_file

VIDEO_POPULARITY_EVIDENCE_ERROR = (
    "DATA.RELEASE.VIDEO_POPULARITY_EVIDENCE_INVALID"
)
VIDEO_POPULARITY_SIGNALS = (
    ("play", "playCount"),
    ("like", "likeCount"),
    ("comment", "commentCount"),
    ("share", "shareCount"),
    ("favorite", "favoriteCount"),
)


class ResearchScaleVideoPopularityError(RuntimeError):
    pass


def collect_m100_video_popularity_observations(
    release: Path,
    *,
    expected_video_count: int,
) -> list[dict[str, Any]]:
    desired = _read_json(payload_file(release, "desired_state.json"))
    desired_refs = desired.get("desiredRefs")
    post_refs = desired_refs.get("posts") if isinstance(desired_refs, Mapping) else None
    if not isinstance(post_refs, list):
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: release desired video refs are missing"
        )
    objects_root = payload_file(release, "objects")
    video_count = 0
    observations: list[dict[str, Any]] = []
    for raw_ref in post_refs:
        post_ref = Path(str(raw_ref or ""))
        if post_ref.is_absolute() or not post_ref.parts or ".." in post_ref.parts:
            raise ResearchScaleVideoPopularityError(
                f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: release post ref is unsafe"
            )
        object_root = objects_root / "posts" / post_ref
        manifest = _read_json(object_root / "manifest.json")
        if str(manifest.get("contentType") or "").strip() != "video":
            continue
        video_count += 1
        rights = _read_json(object_root / "rights.json")
        rights_assets = rights.get("assets")
        if not isinstance(rights_assets, list):
            raise ResearchScaleVideoPopularityError(
                f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
                f"{raw_ref} rights assets are missing"
            )
        reviewed_video_assets = 0
        for raw_asset in rights_assets:
            if not isinstance(raw_asset, Mapping):
                continue
            binding = raw_asset.get("independentAssetReview")
            if not isinstance(binding, Mapping) or binding.get("assetKind") != "video":
                continue
            receipt_ref = Path(str(binding.get("receiptRef") or ""))
            if (
                receipt_ref.is_absolute()
                or not receipt_ref.parts
                or ".." in receipt_ref.parts
            ):
                raise ResearchScaleVideoPopularityError(
                    f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
                    f"{raw_ref} review receipt ref is unsafe"
                )
            receipt = _read_json(object_root / receipt_ref)
            snapshot = receipt.get("assetSnapshot")
            if (
                receipt.get("assetKind") != "video"
                or receipt.get("reviewDecision") != "accepted"
                or not isinstance(snapshot, Mapping)
                or snapshot.get("assetId") != binding.get("acquisitionAssetId")
            ):
                raise ResearchScaleVideoPopularityError(
                    f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
                    f"{raw_ref} review binding is invalid"
                )
            asset_id = str(snapshot.get("assetId") or "<missing>")
            signals = snapshot.get("popularitySignals")
            try:
                assert_observed_popularity_signals(signals, asset_id=asset_id)
            except (TypeError, ValueError) as exc:
                raise ResearchScaleVideoPopularityError(
                    f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: {exc}"
                ) from exc
            assert isinstance(signals, Mapping)
            observations.append(
                {
                    "objectRef": f"posts/{post_ref.as_posix()}",
                    "assetId": asset_id,
                    **{
                        field: signals.get(field)
                        for _signal, field in VIDEO_POPULARITY_SIGNALS
                    },
                    "observedAt": str(signals["observedAt"]),
                    "comparisonBucket": {
                        "provider": str(signals["provider"]),
                        "topic": str(signals["topic"]),
                        "timeBucket": str(signals["timeBucket"]),
                        "candidateCount": int(signals["comparisonCandidateCount"]),
                    },
                    "popularityScore": signals.get("popularityScore"),
                    "popularityPercentile": signals.get("popularityPercentile"),
                    "rankingEligible": signals["rankingEligible"],
                    "ineligibleReason": str(signals["ineligibleReason"]),
                }
            )
            reviewed_video_assets += 1
        if reviewed_video_assets < 1:
            raise ResearchScaleVideoPopularityError(
                f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
                f"{raw_ref} has no accepted video review"
            )
    if video_count != expected_video_count:
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: release video object count "
            f"{video_count} != admitted {expected_video_count}"
        )
    if len(observations) < video_count:
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            "release video observations do not cover every video object"
        )
    return observations
