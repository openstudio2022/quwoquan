"""Immutable professional-video receipt verification and projection."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid

from content.source.professional_video_popularity import popularity_sort_key

ACQUISITION_ROOT = SOURCE_ACQUISITION_ROOT / "video"
ACCEPTED_DECISIONS = frozenset({"research_allowed", "commercial_allowed"})


def document_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_child(root: Path, relative_ref: str, *, label: str) -> Path:
    relative = Path(str(relative_ref or "").strip())
    if not str(relative) or relative.is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    resolved_root = root.resolve()
    path = (resolved_root / relative).resolve()
    if path == resolved_root or resolved_root not in path.parents:
        raise ValueError(f"{label} escapes professional video acquisition root")
    return path


def provider_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row["displayName"]), str(row["provider"]), str(row["platform"]))
        grouped[key].append(row)
    result: list[dict[str, Any]] = []
    for (display_name, provider, platform), assets in sorted(grouped.items()):
        rights = Counter(str(row["rightsStatus"]) for row in assets)
        accepted = sum(row["distributionDecision"] in ACCEPTED_DECISIONS for row in assets)
        result.append({
            "displayName": display_name,
            "provider": provider,
            "platform": platform,
            "plannedAssetCount": len(assets),
            "discoveredAssetCount": len(assets),
            "downloadedAssetCount": sum(row["acquisitionStatus"] == "acquired" for row in assets),
            "acceptedAssetCount": accepted,
            "rejectedAssetCount": len(assets) - accepted,
            "verifiedAssetCount": rights["verified"],
            "unverifiedAssetCount": rights["unverified"],
            "restrictedAssetCount": rights["restricted"],
            "unknownAssetCount": rights["unknown"],
            "rankingEligibleAssetCount": sum(
                row["popularitySignals"]["rankingEligible"] is True for row in assets
            ),
        })
    return result


def assert_funnel_consistent(receipt: Mapping[str, Any]) -> None:
    rows = list(receipt["assets"])
    planned = len(rows)
    if planned < 1:
        raise ValueError("professional video receipt must contain at least one asset")
    downloaded = sum(row["acquisitionStatus"] == "acquired" for row in rows)
    accepted = sum(row["distributionDecision"] in ACCEPTED_DECISIONS for row in rows)
    expected = {
        "plannedAssetCount": planned,
        "discoveredAssetCount": planned,
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": planned - accepted,
    }
    for field, value in expected.items():
        if receipt[field] != value:
            raise ValueError(f"professional video receipt {field} is inconsistent")
        if sum(int(provider[field]) for provider in receipt["providerAssetCounts"]) != value:
            raise ValueError(f"professional video provider funnel {field} is inconsistent")
    if receipt["providerAssetCounts"] != provider_counts(rows):
        raise ValueError("professional video provider rights/ranking counts are inconsistent")


def load_professional_video_acquisition_receipt(
    receipt_ref: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Verify the receipt identity, funnel and every acquired CAS object."""
    resolved_root = (root or ACQUISITION_ROOT).resolve()
    path = canonical_child(
        resolved_root, receipt_ref, label="professional video receiptRef"
    )
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("professional video acquisition receipt must be an object")
    assert_valid(
        receipt,
        "source",
        "professional_video_acquisition_receipt",
        label="professional video acquisition receipt",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt["receiptDigest"] != document_digest(stable):
        raise ValueError("professional video acquisition receipt digest mismatch")
    expected_name = f"{str(receipt['manifestDigest']).removeprefix('sha256:')}.json"
    if path.parent.name != "receipts" or path.name != expected_name:
        raise ValueError("professional video acquisition receipt path is not canonical")
    assert_funnel_consistent(receipt)
    for row in receipt["assets"]:
        if row["acquisitionStatus"] != "acquired":
            continue
        asset_path = canonical_child(
            resolved_root,
            str(row["assetRef"]),
            label="professional video assetRef",
        )
        if not asset_path.is_file():
            raise ValueError(f"professional video CAS asset is missing: {row['assetRef']}")
        if file_digest(asset_path) != row["contentSha256"]:
            raise ValueError(f"professional video CAS digest mismatch: {row['assetRef']}")
    return receipt


def assert_observed_popularity_signals(
    signals: object,
    *,
    asset_id: str,
) -> None:
    """Validate observed popularity without making ranking a release admission gate."""
    if not isinstance(signals, Mapping):
        raise TypeError(f"professional video popularity evidence is missing: {asset_id}")
    count_fields = (
        "playCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "favoriteCount",
    )
    for field in count_fields:
        value = signals.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(
                f"professional video popularity count is invalid: {asset_id}:{field}"
            )
    if any(
        not str(signals.get(field) or "").strip()
        for field in ("observedAt", "provider", "topic", "timeBucket")
    ):
        raise ValueError(
            f"professional video popularity comparison bucket is incomplete: {asset_id}"
        )
    candidate_count = signals.get("comparisonCandidateCount")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
    ):
        raise ValueError(
            f"professional video popularity comparison count is invalid: {asset_id}"
        )
    percentile = signals.get("popularityPercentile")
    score = signals.get("popularityScore")
    ranking_eligible = signals.get("rankingEligible")
    reason = str(signals.get("rankingIneligibleReason") or "").strip()
    counts_complete = all(isinstance(signals.get(field), int) for field in count_fields)
    score_is_number = not isinstance(score, bool) and isinstance(score, (int, float))
    if ranking_eligible is True:
        if (
            not counts_complete
            or candidate_count < 2
            or reason
            or isinstance(percentile, bool)
            or not isinstance(percentile, (int, float))
            or not 0 <= float(percentile) <= 1
            or not score_is_number
        ):
            raise ValueError(
                f"professional video comparable popularity evidence is invalid: {asset_id}"
            )
        return
    if ranking_eligible is not False:
        raise ValueError(
            f"professional video ranking eligibility is invalid: {asset_id}"
        )
    if reason not in {
        "asset_not_accepted",
        "incomplete_popularity_signals",
        "insufficient_comparable_candidates",
    }:
        raise ValueError(
            f"professional video ranking ineligible reason is invalid: {asset_id}"
        )
    if percentile is not None:
        raise ValueError(
            f"professional video ineligible ranking has percentile: {asset_id}"
        )
    if counts_complete != score_is_number:
        raise ValueError(
            f"professional video popularity score completeness is invalid: {asset_id}"
        )


def assert_publishable_popularity_signals(
    signals: object,
    *,
    asset_id: str,
) -> None:
    """Require five observed metrics and one real comparable-bucket percentile."""
    if not isinstance(signals, Mapping):
        raise TypeError(f"professional video popularity evidence is missing: {asset_id}")
    count_fields = (
        "playCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "favoriteCount",
    )
    if any(
        isinstance(signals.get(field), bool)
        or not isinstance(signals.get(field), int)
        or int(signals[field]) < 0
        for field in count_fields
    ):
        raise ValueError(
            f"professional video popularity counts are incomplete: {asset_id}"
        )
    if any(
        not str(signals.get(field) or "").strip()
        for field in ("observedAt", "provider", "topic", "timeBucket")
    ):
        raise ValueError(
            f"professional video popularity comparison bucket is incomplete: {asset_id}"
        )
    percentile = signals.get("popularityPercentile")
    score = signals.get("popularityScore")
    if (
        signals.get("rankingEligible") is not True
        or int(signals.get("comparisonCandidateCount") or 0) < 2
        or bool(str(signals.get("rankingIneligibleReason") or "").strip())
        or isinstance(percentile, bool)
        or not isinstance(percentile, (int, float))
        or not 0 <= float(percentile) <= 1
        or isinstance(score, bool)
        or not isinstance(score, (int, float))
    ):
        raise ValueError(
            f"professional video lacks comparable popularity percentile: {asset_id}"
        )


def assert_publishable_media_probe(probe: object, *, asset_id: str) -> None:
    if not isinstance(probe, Mapping) or not all(
        (
            probe.get("playable") is True,
            probe.get("motionVideo") is True,
            probe.get("staticImageSequence") is False,
            probe.get("premiumPlayableEligible") is True,
        )
    ):
        raise ValueError(
            f"accepted professional video is not playable motion media: {asset_id}"
        )


def _assert_publish_grade_video(
    row: Mapping[str, Any],
    *,
    require_popularity_ranking: bool,
) -> None:
    """Validate research media admission, optionally adding the scale rank gate."""
    asset_id = str(row.get("assetId") or "<missing>")
    probe = row.get("mediaProbe")
    assert_publishable_media_probe(probe, asset_id=asset_id)
    assert isinstance(probe, Mapping)
    signals = row.get("popularitySignals")
    if require_popularity_ranking:
        assert_publishable_popularity_signals(signals, asset_id=asset_id)
    else:
        assert_observed_popularity_signals(signals, asset_id=asset_id)
    assert isinstance(signals, Mapping)
    plan_spec = row.get("planVideoSpec")
    if (
        not isinstance(plan_spec, Mapping)
        or plan_spec.get("mediaProbe") != dict(probe)
        or plan_spec.get("popularitySignals") != dict(signals)
        or plan_spec.get("premiumPlayableEligible") is not True
    ):
        raise ValueError(
            f"professional video plan does not bind publish-grade evidence: {asset_id}"
        )


def acquired_video_specs_for_entity(
    receipt_refs: list[str],
    *,
    entity_id: str,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
) -> list[dict[str, Any]]:
    """Project playable research assets; scale callers can require real ranking."""
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for receipt_ref in receipt_refs:
        receipt = load_professional_video_acquisition_receipt(receipt_ref, root=root)
        for row in receipt["assets"]:
            if (
                str(row["entityId"]) != entity_id
                or row["distributionDecision"] not in ACCEPTED_DECISIONS
            ):
                continue
            _assert_publish_grade_video(
                row,
                require_popularity_ranking=require_popularity_ranking,
            )
            spec = row["planVideoSpec"]
            if not isinstance(spec, Mapping):
                raise TypeError(
                    f"accepted professional video lacks planVideoSpec: {row['assetId']}"
                )
            digest = str(row["contentSha256"])
            if digest in seen:
                raise ValueError(f"professional video cross-receipt duplicate: {digest}")
            seen.add(digest)
            specs.append(dict(spec))
    return sorted(specs, key=popularity_sort_key)


def resolve_professional_video_candidate(
    candidate: Mapping[str, Any],
    *,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
) -> Path:
    """Resolve a plan candidate only after binding it back to receipt and CAS."""
    receipt_ref = str(candidate.get("professionalAcquisitionReceiptRef") or "")
    asset_id = str(candidate.get("professionalAssetId") or "")
    receipt = load_professional_video_acquisition_receipt(receipt_ref, root=root)
    matches = [row for row in receipt["assets"] if str(row["assetId"]) == asset_id]
    if len(matches) != 1:
        raise ValueError(
            f"professional video asset binding is missing or ambiguous: {asset_id}"
        )
    row = matches[0]
    _assert_publish_grade_video(
        row,
        require_popularity_ranking=require_popularity_ranking,
    )
    if (
        row["distributionDecision"] not in ACCEPTED_DECISIONS
        or row["planVideoSpec"] != dict(candidate)
    ):
        raise ValueError("professional video plan candidate does not match immutable receipt")
    digest = str(row["contentSha256"])
    expected_cas_url = f"cas://sha256/{digest.removeprefix('sha256:')}"
    if (
        candidate.get("professionalContentSha256") != digest
        or candidate.get("assetUrl") != expected_cas_url
    ):
        raise ValueError("professional video plan candidate digest binding mismatch")
    resolved_root = (root or ACQUISITION_ROOT).resolve()
    return canonical_child(
        resolved_root, str(row["assetRef"]), label="professional video assetRef"
    )


__all__ = [
    "ACCEPTED_DECISIONS",
    "ACQUISITION_ROOT",
    "acquired_video_specs_for_entity",
    "assert_funnel_consistent",
    "assert_observed_popularity_signals",
    "assert_publishable_media_probe",
    "assert_publishable_popularity_signals",
    "document_digest",
    "file_digest",
    "load_professional_video_acquisition_receipt",
    "provider_counts",
    "resolve_professional_video_candidate",
]
