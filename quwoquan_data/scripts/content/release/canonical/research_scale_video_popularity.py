"""Validate and collect M100 video popularity observations from release objects."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from content.release.canonical.object_transaction_contract import _read_json
from content.source.independent_asset_review_contract import (
    canonical_digest,
    file_digest,
)
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


def _release_output_root(release: Path) -> Path:
    resolved = release.resolve()
    if (
        resolved.parent.name != "releases"
        or resolved.parent.parent.name != "data"
    ):
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: release is outside canonical output layout"
        )
    return resolved.parents[2]


def _execution_review_receipt(
    binding: Mapping[str, Any],
    *,
    output_root: Path,
    object_ref: str,
) -> dict[str, Any]:
    raw_ref = str(binding.get("receiptRef") or "")
    receipt_ref = Path(raw_ref)
    parts = receipt_ref.parts
    review_name = receipt_ref.name
    review_digest = review_name.removeprefix("asset-review-").removesuffix(".json")
    if (
        receipt_ref.is_absolute()
        or len(parts) != 7
        or parts[:2] != ("data", "tasks")
        or parts[3:6] != ("evidence", "asset_reviews", "receipts")
        or ".." in parts
        or not review_name.startswith("asset-review-")
        or not review_name.endswith(".json")
        or len(review_digest) != 64
        or any(character not in "0123456789abcdef" for character in review_digest)
    ):
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} review receipt must name execution evidence"
        )
    try:
        execution_id = validate_execution_id(parts[2])
    except ValueError as exc:
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} review receipt execution is invalid"
        ) from exc
    receipt_path = output_root.joinpath(*parts)
    current = output_root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ResearchScaleVideoPopularityError(
                f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
                f"{object_ref} review receipt path contains a symlink"
            )
    try:
        receipt_path.resolve().relative_to(output_root.resolve())
    except ValueError as exc:
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} review receipt escapes the output root"
        ) from exc
    if not receipt_path.is_file():
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} execution review receipt is missing"
        )
    if file_digest(receipt_path) != binding.get("receiptFileSha256"):
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} execution review receipt bytes drift"
        )
    try:
        receipt = _read_json(receipt_path)
    except RuntimeError as exc:
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} execution review receipt is invalid"
        ) from exc
    receipt_digest = canonical_digest(receipt, excluded="receiptDigest")
    snapshot = receipt.get("assetSnapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    author = receipt.get("authorExecution")
    author = author if isinstance(author, Mapping) else {}
    reviewer = receipt.get("reviewerExecution")
    reviewer = reviewer if isinstance(reviewer, Mapping) else {}
    expected_manifest_ref = f"data/tasks/{execution_id}/execution_manifest.json"
    signals = snapshot.get("popularitySignals")
    if (
        receipt.get("reviewId") != receipt_ref.stem
        or receipt.get("assetKind") != "video"
        or receipt.get("reviewDecision") != "accepted"
        or receipt.get("objectRef") != binding.get("objectRef")
        or receipt.get("receiptDigest") != binding.get("receiptDigest")
        or receipt.get("receiptDigest") != receipt_digest
        or receipt.get("executionManifestRef") != expected_manifest_ref
        or author.get("executionId") != execution_id
        or reviewer.get("executionId") != execution_id
        or snapshot.get("assetId") != binding.get("acquisitionAssetId")
        or snapshot.get("contentSha256") != binding.get("contentSha256")
        or receipt.get("sourceRevision") != binding.get("sourceRevision")
        or receipt.get("sourceDigest") != binding.get("sourceDigest")
        or receipt.get("entityCatalogDigest")
        != binding.get("entityCatalogDigest")
        or not isinstance(signals, Mapping)
        or canonical_digest(signals) != binding.get("popularitySignalsDigest")
    ):
        raise ResearchScaleVideoPopularityError(
            f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: "
            f"{object_ref} execution review binding drift"
        )
    return receipt


def collect_m100_video_popularity_observations(
    release: Path,
    *,
    expected_video_count: int,
) -> list[dict[str, Any]]:
    output_root = _release_output_root(release)
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
            receipt = _execution_review_receipt(
                binding,
                output_root=output_root,
                object_ref=str(raw_ref),
            )
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
