"""Immutable professional-video receipt verification and projection."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid

from content.source.acquisition_body_state import (
    AcquiredBody,
    ReclaimedBody,
    assert_unit_reclamation_is_total,
)
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
    require_bodies: bool = True,
    _verified_asset_digests: dict[Path, str] | None = None,
) -> dict[str, Any]:
    """Verify the receipt identity, funnel and every acquired CAS object.

    ``require_bodies=False`` admits a receipt whose bodies were all reclaimed
    after their object adopted them; the receipt itself is still verified in
    full. A partially reclaimed unit is refused either way.
    """
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
    token = str(receipt["manifestDigest"]).removeprefix("sha256:")
    # Attempt 1 is receipts/<token>.json; retries after retryable acquisition
    # failures append receipts/<token>-attempt-NNN.json without rewriting
    # historical receipts.
    if path.parent.name != "receipts" or not re.fullmatch(
        rf"{re.escape(token)}(-attempt-\d{{3,}})?\.json", path.name
    ):
        raise ValueError("professional video acquisition receipt path is not canonical")
    assert_funnel_consistent(receipt)
    verified_asset_digests = (
        _verified_asset_digests
        if _verified_asset_digests is not None
        else {}
    )
    bodies: list[AcquiredBody] = []
    for row in receipt["assets"]:
        if row["acquisitionStatus"] != "acquired":
            continue
        asset_ref = str(row["assetRef"])
        asset_path = canonical_child(
            resolved_root,
            asset_ref,
            label="professional video assetRef",
        )
        if not asset_path.is_file():
            if require_bodies:
                raise ValueError(
                    f"professional video CAS asset is missing: {asset_ref}"
                )
            bodies.append(ReclaimedBody(asset_ref=asset_ref))
            continue
        bodies.append(asset_path)
        expected_digest = str(row["contentSha256"])
        already_verified = verified_asset_digests.get(asset_path)
        if already_verified is not None:
            if already_verified != expected_digest:
                raise ValueError(
                    f"professional video CAS declaration conflicts: {row['assetRef']}"
                )
            continue
        if file_digest(asset_path) != expected_digest:
            raise ValueError(f"professional video CAS digest mismatch: {row['assetRef']}")
        verified_asset_digests[asset_path] = expected_digest
    assert_unit_reclamation_is_total(
        bodies,
        label="professional video acquisition receipt",
    )
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
    reason = str(signals.get("ineligibleReason") or "").strip()
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
        or bool(str(signals.get("ineligibleReason") or "").strip())
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


@dataclass(frozen=True, slots=True)
class AcquiredVideoSpecIndex:
    """Immutable projection built after one fail-closed receipt/CAS verification."""

    _encoded_specs_by_entity: Mapping[str, tuple[str, ...]]
    entity_names: tuple[str, ...]
    accepted_asset_count: int
    _encoded_exclusions: tuple[str, ...] = ()
    _encoded_work_unit_candidates: tuple[str, ...] = ()

    def specs_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        encoded = self._encoded_specs_by_entity.get(str(entity_id).strip(), ())
        return [json.loads(payload) for payload in encoded]

    def specs_for_names(self, entity_names: tuple[str, ...]) -> list[dict[str, Any]]:
        """Resolve canonical name then aliases without re-reading frozen bytes."""
        for entity_name in dict.fromkeys(
            str(value).strip() for value in entity_names if str(value).strip()
        ):
            specs = self.specs_for_entity(entity_name)
            if specs:
                return specs
        return []

    @property
    def exclusions(self) -> tuple[dict[str, str], ...]:
        return tuple(json.loads(payload) for payload in self._encoded_exclusions)

    @property
    def work_unit_candidates(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(payload) for payload in self._encoded_work_unit_candidates)


def build_acquired_video_spec_index(
    receipt_refs: list[str],
    *,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
    work_unit_bindings: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> AcquiredVideoSpecIndex:
    """Verify each frozen receipt once and index accepted assets by entity/alias."""
    normalized_refs = tuple(str(ref).strip() for ref in receipt_refs)
    if any(not ref for ref in normalized_refs):
        raise ValueError("professional video receipt refs must be non-empty")
    if len(normalized_refs) != len(set(normalized_refs)):
        raise ValueError("professional video receipt refs must not contain duplicates")

    specs_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_content_digests: set[str] = set()
    entity_names: list[str] = []
    exclusions: list[dict[str, str]] = []
    work_unit_candidates: list[dict[str, Any]] = []
    verified_asset_digests: dict[Path, str] = {}
    for receipt_ref in normalized_refs:
        receipt = load_professional_video_acquisition_receipt(
            receipt_ref,
            root=root,
            _verified_asset_digests=verified_asset_digests,
        )
        for row in receipt["assets"]:
            if row["distributionDecision"] not in ACCEPTED_DECISIONS:
                continue
            try:
                _assert_publish_grade_video(
                    row,
                    require_popularity_ranking=require_popularity_ranking,
                )
                spec = row["planVideoSpec"]
                if not isinstance(spec, Mapping):
                    raise TypeError(
                        "accepted professional video lacks planVideoSpec: "
                        f"{row['assetId']}"
                    )
            except (TypeError, ValueError) as exc:
                if require_popularity_ranking:
                    raise
                exclusions.append(
                    {
                        "assetId": str(row.get("assetId") or ""),
                        "entityId": str(row.get("entityId") or ""),
                        "code": "DATA.SOURCE.PLAN_SPEC_INVALID",
                        "reason": str(exc),
                    }
                )
                continue
            digest = str(row["contentSha256"])
            if digest in seen_content_digests:
                exclusions.append(
                    {
                        "assetId": str(row.get("assetId") or ""),
                        "entityId": str(row.get("entityId") or ""),
                        "code": "DATA.SOURCE.DUPLICATE_ASSET",
                        "reason": f"professional video cross-receipt duplicate: {digest}",
                    }
                )
                continue
            seen_content_digests.add(digest)
            binding = (
                work_unit_bindings.get((receipt_ref, str(row["assetId"])))
                if work_unit_bindings is not None
                else None
            )
            if work_unit_bindings is not None and binding is None:
                raise ValueError(
                    "accepted professional video is absent from its frozen manifest"
                )
            if binding is not None and str(binding.get("sourceEntityId") or "") != str(
                row.get("entityId") or ""
            ):
                raise ValueError("professional video manifest/receipt entity identity drift")
            frozen_names = [
                str(row.get("entityId") or "").strip(),
                *(
                    str(value).strip()
                    for value in (
                        binding.get("sourceEntityAliases")
                        if binding is not None
                        else row.get("entityAliases") or []
                    )
                    if str(value).strip()
                ),
            ]
            frozen_names = list(dict.fromkeys(name for name in frozen_names if name))
            if not frozen_names:
                raise ValueError(
                    f"accepted professional video lacks entity identity: {row['assetId']}"
                )
            for entity_name in frozen_names:
                if entity_name not in specs_by_entity:
                    entity_names.append(entity_name)
                specs_by_entity[entity_name].append(dict(spec))
            if binding is not None:
                work_unit_candidates.append(
                    {
                        "carrier": "video",
                        "manifestRef": str(binding["manifestRef"]),
                        "manifestDigest": str(binding["manifestDigest"]),
                        "receiptRef": receipt_ref,
                        "receiptDigest": str(binding["receiptDigest"]),
                        "assetId": str(row["assetId"]),
                        "contentSha256": digest,
                        "sourceEntityId": frozen_names[0],
                        "sourceEntityAliases": frozen_names[1:],
                    }
                )

    encoded = {
        entity_name: tuple(
            json.dumps(
                spec,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for spec in sorted(specs, key=popularity_sort_key)
        )
        for entity_name, specs in specs_by_entity.items()
    }
    return AcquiredVideoSpecIndex(
        _encoded_specs_by_entity=MappingProxyType(encoded),
        entity_names=tuple(entity_names),
        accepted_asset_count=len(seen_content_digests),
        _encoded_exclusions=tuple(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in exclusions
        ),
        _encoded_work_unit_candidates=tuple(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in work_unit_candidates
        ),
    )


def acquired_video_specs_for_entity(
    receipt_refs: list[str],
    *,
    entity_id: str,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
) -> list[dict[str, Any]]:
    """Project playable research assets; scale callers can require real ranking."""
    return build_acquired_video_spec_index(
        receipt_refs,
        root=root,
        require_popularity_ranking=require_popularity_ranking,
    ).specs_for_entity(entity_id)


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
    "AcquiredVideoSpecIndex",
    "acquired_video_specs_for_entity",
    "assert_funnel_consistent",
    "assert_observed_popularity_signals",
    "assert_publishable_media_probe",
    "assert_publishable_popularity_signals",
    "build_acquired_video_spec_index",
    "document_digest",
    "file_digest",
    "load_professional_video_acquisition_receipt",
    "provider_counts",
    "resolve_professional_video_candidate",
]
