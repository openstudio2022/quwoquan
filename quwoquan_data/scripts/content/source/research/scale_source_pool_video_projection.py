"""Optional-ranking video projection for rolling Research source pools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from content.source import professional_video_catalog_binding as popular_binding

_ACCEPTED = frozenset({"research_allowed", "commercial_allowed"})
_GENERATED_MARKERS = ("generated", "synthetic", "text_to_video", "ai_video")


def _popularity_ready(signals: Mapping[str, Any]) -> bool:
    percentile = signals.get("popularityPercentile")
    return bool(
        signals.get("rankingEligible") is True
        and not isinstance(percentile, bool)
        and isinstance(percentile, (int, float))
        and 0 <= float(percentile) <= 1
        and int(signals.get("comparisonCandidateCount") or 0) >= 2
        and all(
            not isinstance(signals.get(field), bool)
            and isinstance(signals.get(field), int)
            and int(signals[field]) >= 0
            for field in popular_binding.POPULAR_COUNT_FIELDS
        )
        and all(
            str(signals.get(field) or "").strip()
            for field in ("observedAt", "provider", "topic", "timeBucket")
        )
    )


def _catalog_candidate(
    *,
    asset: Mapping[str, Any],
    candidates: Mapping[str, tuple[Mapping[str, Any], dict[str, Any]]],
    fail: Callable[..., None],
) -> tuple[Mapping[str, Any] | None, dict[str, Any] | None]:
    binding = tuple(
        str(asset.get(field) or "").strip()
        for field in popular_binding.POPULAR_BINDING_FIELDS
    )
    if not any(binding):
        return None, None
    if not all(binding):
        fail(f"video popular-catalog binding is partial: {asset.get('assetId')}")
    candidate_id, catalog_ref, catalog_digest, catalog_sha = binding
    try:
        candidate, catalog_input = candidates[candidate_id]
    except KeyError:
        fail(f"video popular-catalog candidate is missing: {candidate_id}")
    if (
        catalog_ref != catalog_input["ref"]
        or catalog_digest != catalog_input["documentDigest"]
        or catalog_sha != catalog_input["fileSha256"]
    ):
        fail(f"video popular-catalog document binding drift: {asset.get('assetId')}")
    if (
        str(candidate.get("provider") or "") != str(asset.get("provider") or "")
        or str(candidate.get("entityId") or "") != str(asset.get("entityId") or "")
        or str(candidate.get("observedEntityId") or "")
        != str(asset.get("observedEntityId") or "")
        or str(candidate.get("sourcePageUrl") or "")
        != str(asset.get("sourceUrl") or "")
        or str(candidate.get("title") or "") != str(asset.get("title") or "")
        or str(candidate.get("creator") or "") != str(asset.get("creator") or "")
        or str(candidate.get("manualFileRef") or "")
        != str(asset.get("manualFile") or "")
        or str(candidate.get("manualFileSha256") or "")
        != str(asset.get("contentSha256") or "")
    ):
        fail(f"video popular-catalog source/bytes drift: {asset.get('assetId')}")
    return candidate, catalog_input


def _readiness(
    *,
    asset: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    fail: Callable[..., None],
) -> dict[str, Any]:
    probe = snapshot.get("mediaProbe")
    signals = snapshot.get("popularitySignals")
    if not isinstance(probe, Mapping) or not all(
        (
            probe.get("playable") is True,
            probe.get("motionVideo") is True,
            probe.get("staticImageSequence") is False,
        )
    ):
        fail(f"video is not real playable motion media: {asset.get('assetId')}")
    if not isinstance(signals, Mapping):
        fail(f"video popularity observation is missing: {asset.get('assetId')}")
    ranking_eligible = _popularity_ready(signals)
    if candidate is not None:
        expected = {
            **dict(candidate["popularity"]),
            "observedAt": str(candidate["observedAt"]),
            "provider": str(candidate["provider"]),
            "topic": str(candidate["topic"]),
            "timeBucket": str(candidate["timeBucket"]),
            "rankingEligible": ranking_eligible,
            "ineligibleReason": (
                "" if ranking_eligible else "incomplete_popularity_signals"
            ),
        }
        if dict(signals) != expected:
            fail(f"video popular-catalog popularity drift: {asset.get('assetId')}")
    percentile = signals.get("popularityPercentile")
    return {
        "playable": True,
        "motion": True,
        "premiumEligible": probe.get("premiumPlayableEligible") is True,
        **{
            field: (
                int(signals[field])
                if not isinstance(signals.get(field), bool)
                and isinstance(signals.get(field), int)
                and int(signals[field]) >= 0
                else None
            )
            for field in popular_binding.POPULAR_COUNT_FIELDS
        },
        "observedAt": str(signals.get("observedAt") or "") or None,
        "popularityPercentile": float(percentile) if ranking_eligible else None,
        "comparisonBucket": (
            {
                "provider": str(signals["provider"]),
                "topic": str(signals["topic"]),
                "timeBucket": str(signals["timeBucket"]),
                "candidateCount": int(signals["comparisonCandidateCount"]),
            }
            if ranking_eligible
            else None
        ),
    }


def project_video_rows(
    *,
    catalogs: list[dict[str, Any]],
    acquisitions: list[dict[str, Any]],
    reviews: Mapping[tuple[str, str], dict[str, Any]],
    identity: tuple[str, str, str],
    fail: Callable[..., None],
    assert_identity: Callable[..., None],
    one_review: Callable[..., dict[str, Any]],
    accepted_review: Callable[..., tuple[Mapping[str, Any], Mapping[str, Any]]],
    common_row: Callable[..., dict[str, Any]],
    entity_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project physical Research videos; ranking catalog remains optional."""

    candidates: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
    for catalog_input in catalogs:
        catalog = catalog_input["document"]
        assert_identity(catalog, identity, label="popular-video catalog")
        for candidate in catalog["candidates"]:
            candidate_id = str(candidate["candidateId"])
            if candidate_id in candidates:
                fail(f"duplicate popular-video candidate: {candidate_id}")
            candidates[candidate_id] = (candidate, catalog_input)
    rows: list[dict[str, Any]] = []
    for acquisition_input in acquisitions:
        acquisition = acquisition_input["document"]
        assert_identity(acquisition, identity, label="video acquisition")
        for asset in acquisition["assets"]:
            if asset.get("distributionDecision") not in _ACCEPTED:
                continue
            if asset.get("acquisitionStatus") != "acquired" or not asset.get(
                "contentSha256"
            ):
                fail(f"video candidate was not acquired: {asset.get('assetId')}")
            source_kind = str(asset.get("sourceKind") or "").strip().casefold()
            if any(marker in source_kind for marker in _GENERATED_MARKERS):
                fail(f"generated video is forbidden: {asset.get('assetId')}")
            candidate, catalog_input = _catalog_candidate(
                asset=asset,
                candidates=candidates,
                fail=fail,
            )
            review_input = one_review(
                reviews,
                kind="video",
                asset_id=str(asset["assetId"]),
            )
            snapshot, _judgment = accepted_review(
                review_input,
                acquisition_input,
                asset,
                expected_identity=identity,
            )
            row = common_row(
                carrier="video",
                object_ref=str(review_input["document"]["objectRef"]),
                asset=asset,
                source_input=catalog_input or acquisition_input,
                acquisition_input=acquisition_input,
                review_input=review_input,
                identity=identity,
                entity_index=entity_index,
            )
            row.update(
                playabilityRef=review_input["ref"],
                playabilityDigest=review_input["documentDigest"],
                playabilityFileSha256=review_input["fileSha256"],
                videoReadiness=_readiness(
                    asset=asset,
                    snapshot=snapshot,
                    candidate=candidate,
                    fail=fail,
                ),
            )
            rows.append(row)
    return rows


__all__ = ["project_video_rows"]
