"""Project accepted media source-admission facts into scale SourcePool rows."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.schema import assert_valid

from content.source.media_source_admission import (
    MediaSourceAdmissionError,
    MediaSourceAdmissionQuery,
)
from content.source.professional_image_supported_api_metadata_entities import (
    load_entity_bindings,
    resolve_entity_ref,
)
from content.source.research.scale_source_pool_evidence_path import (
    compute_evidence_file_sha256,
    resolve_evidence_file,
)

PROJECTION_INVALID = "DATA.SOURCE.POOL_INVALID"
PROJECTION_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCALES = frozenset({"WORKLOAD", "M100", "M1000", "M10000"})
_PIN = frozenset({"pinterest", "pinterest.com", "www.pinterest.com"})
_TUCHONG = frozenset({"tuchong", "tuchong.com", "www.tuchong.com", "图虫", "图虫社区"})
_POPULAR_COUNT_FIELDS = (
    "playCount",
    "likeCount",
    "commentCount",
    "shareCount",
    "favoriteCount",
)


class ScaleSourcePoolProjectionError(ValueError):
    """Typed projection blocker."""

    def __init__(self, code: str, issue: str) -> None:
        self.code = code
        self.issue = str(issue).strip()
        self.issues = (self.issue,)
        super().__init__(f"{code}: {self.issue}")


def _fail(issue: str, *, shortfall: bool = False) -> None:
    code = PROJECTION_SHORTFALL if shortfall else PROJECTION_INVALID
    raise ScaleSourcePoolProjectionError(code, issue)


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _provider(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in _PIN:
        return "pinterest"
    if normalized in _TUCHONG:
        return "tuchong"
    return normalized


def _ranking_eligible(signals: Mapping[str, Any]) -> bool:
    percentile = signals.get("popularityPercentile")
    return bool(
        signals.get("rankingEligible") is True
        and not isinstance(percentile, bool)
        and isinstance(percentile, int | float)
        and 0 <= float(percentile) <= 1
        and int(signals.get("comparisonCandidateCount") or 0) >= 2
        and all(
            not isinstance(signals.get(field), bool)
            and isinstance(signals.get(field), int)
            and int(signals[field]) >= 0
            for field in _POPULAR_COUNT_FIELDS
        )
        and all(
            str(signals.get(field) or "").strip()
            for field in ("observedAt", "provider", "topic", "timeBucket")
        )
    )


def _video_readiness(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    probe = snapshot.get("mediaProbe")
    signals = snapshot.get("popularitySignals")
    if not isinstance(probe, Mapping) or not all(
        (
            probe.get("playable") is True,
            probe.get("motionVideo") is True,
            probe.get("staticImageSequence") is False,
        )
    ):
        _fail(f"video is not real playable motion media: {snapshot.get('assetId')}")
    if not isinstance(signals, Mapping):
        _fail(f"video popularity observation is missing: {snapshot.get('assetId')}")
    eligible = _ranking_eligible(signals)
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
            for field in _POPULAR_COUNT_FIELDS
        },
        "observedAt": str(signals.get("observedAt") or "") or None,
        "popularityPercentile": float(percentile) if eligible else None,
        "comparisonBucket": (
            {
                "provider": str(signals["provider"]),
                "topic": str(signals["topic"]),
                "timeBucket": str(signals["timeBucket"]),
                "candidateCount": int(signals["comparisonCandidateCount"]),
            }
            if eligible
            else None
        ),
    }


def _accepted_source_admission(
    *,
    query: MediaSourceAdmissionQuery,
    evidence_root: Path,
    receipt_ref: str,
    asset_kind: str,
    identity: tuple[str, str, str],
    entity_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        result = query.require_accepted(receipt_ref)
    except MediaSourceAdmissionError:
        raise
    receipt = result["receipt"]
    if receipt.get("assetKind") != asset_kind:
        _fail(f"{asset_kind} source admission assetKind drift: {receipt_ref}")
    actual_identity = tuple(
        str(receipt.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if actual_identity != identity:
        _fail(f"{asset_kind} source admission source identity drift: {receipt_ref}")
    snapshot = receipt.get("assetSnapshot")
    if not isinstance(snapshot, Mapping):
        _fail(f"{asset_kind} source admission lacks asset snapshot: {receipt_ref}")
    try:
        entity_ref = resolve_entity_ref(snapshot["entityId"], index=entity_index)
        observed_entity_ref = resolve_entity_ref(
            snapshot["observedEntityId"],
            index=entity_index,
        )
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"source-admitted asset entity is absent from frozen catalog: {exc}")
    if entity_ref != observed_entity_ref:
        _fail(f"source-admitted asset observed entity mismatch: {snapshot.get('assetId')}")
    provider = _provider(snapshot.get("provider") or snapshot.get("platform"))
    seed = "|".join(
        (
            asset_kind,
            str(receipt["objectRef"]),
            str(snapshot["assetId"]),
            str(snapshot["contentSha256"]),
        )
    )
    row: dict[str, Any] = {
        "candidateId": f"{asset_kind}-" + hashlib.sha256(seed.encode()).hexdigest(),
        "carrier": asset_kind,
        "objectRef": str(receipt["objectRef"]),
        "entityRef": entity_ref,
        "observedEntityRef": observed_entity_ref,
        "sourceRevision": identity[0],
        "sourceDigest": identity[1],
        "entityCatalogDigest": identity[2],
        "sourceAdmissionRef": str(result["receiptRef"]),
        "sourceAdmissionDigest": str(result["receiptDigest"]),
        "provider": provider,
        "contentSha256": str(snapshot["contentSha256"]),
        "acquisitionStatus": "acquired",
        "rightsStatus": str(snapshot["rightsStatus"]),
        "distributionDecision": str(snapshot["distributionDecision"]),
        "qualityStatus": "passed",
        "generated": False,
        "videoReadiness": (
            _video_readiness(snapshot) if asset_kind == "video" else None
        ),
    }
    attribution = snapshot.get("sourceAttribution")
    if isinstance(attribution, Mapping):
        row["sourceAttribution"] = dict(attribution)
    try:
        receipt_path = resolve_evidence_file(
            evidence_root,
            result["receiptRef"],
            label=f"{asset_kind}SourceAdmissionRef",
        )
        file_sha256 = compute_evidence_file_sha256(receipt_path)
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"{asset_kind} source admission bytes are unavailable: {exc}")
    input_document = {
        "kind": f"{asset_kind}_source_admission",
        "ref": str(result["receiptRef"]),
        "documentDigest": str(result["receiptDigest"]),
        "fileSha256": file_sha256,
    }
    return row, input_document


def project_scale_source_pool_image_video(
    *,
    evidence_root: Path,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    entity_catalog_ref: str,
    image_source_admission_refs: Iterable[str] | None,
    video_source_admission_refs: Iterable[str] | None,
) -> dict[str, Any]:
    """Return media rows from accepted source-admission receipts only."""

    if target_scale not in _SCALES:
        _fail(f"unsupported targetScale={target_scale!r}")
    identity = (source_revision, source_digest, entity_catalog_digest)
    if any(not _SHA256.fullmatch(value) for value in identity):
        _fail("sourceRevision/sourceDigest/entityCatalogDigest must be sha256")
    try:
        resolved_catalog_ref, resolved_catalog_digest, entity_index = load_entity_bindings(
            Path(entity_catalog_ref)
        )
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"entity catalog binding is unavailable: {exc}")
    if resolved_catalog_ref != str(entity_catalog_ref).strip().strip("/"):
        _fail("entity catalog ref drift")
    if resolved_catalog_digest != entity_catalog_digest:
        _fail("entity catalog digest drift")
    root = evidence_root.expanduser().absolute()
    refs = {
        "image": tuple(str(ref).strip() for ref in image_source_admission_refs or ()),
        "video": tuple(str(ref).strip() for ref in video_source_admission_refs or ()),
    }
    if not any(refs.values()):
        _fail("at least one media source admission is required", shortfall=True)
    query = MediaSourceAdmissionQuery(root)
    rows: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    for asset_kind in ("image", "video"):
        seen: set[str] = set()
        for receipt_ref in sorted(refs[asset_kind]):
            if not receipt_ref or receipt_ref in seen:
                _fail(f"duplicate or empty {asset_kind} source admission ref")
            seen.add(receipt_ref)
            row, input_document = _accepted_source_admission(
                query=query,
                evidence_root=root,
                receipt_ref=receipt_ref,
                asset_kind=asset_kind,
                identity=identity,
                entity_index=entity_index,
            )
            rows.append(row)
            inputs.append(input_document)
    for asset_kind in ("image", "video"):
        if refs[asset_kind] and not any(row["carrier"] == asset_kind for row in rows):
            _fail(f"no accepted {asset_kind} source admissions were projected", shortfall=True)
    content = [str(row["contentSha256"]) for row in rows]
    if len(content) != len(set(content)):
        _fail("duplicate contentSha256 across projected image/video rows")
    rows.sort(
        key=lambda row: (
            str(row["carrier"]),
            str(row["objectRef"]),
            str(row["candidateId"]),
        )
    )
    inputs.sort(key=lambda row: (str(row["kind"]), str(row["ref"])))
    stable = {
        "schema": "quwoquan_data.scale_source_pool_image_video_projection",
        "targetScale": target_scale,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "inputDocuments": inputs,
        "candidateCount": len(rows),
        "candidates": rows,
    }
    active = tuple(
        carrier
        for carrier in ("image", "video")
        if any(str(row.get("carrier") or "") == carrier for row in rows)
    )
    workloads = {
        carrier: sum(str(row.get("carrier") or "") == carrier for row in rows)
        for carrier in active
    }
    shape_probe = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "projection-shape-probe",
        "targetScale": target_scale,
        "workloadMode": "explicit",
        "activeCarriers": list(active),
        "workloadTargets": workloads,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": "projection-only",
        "waveCandidateCounts": [
            {
                "carrier": carrier,
                "minimumCandidateCount": workloads[carrier],
            }
            for carrier in active
        ],
        "candidates": rows,
    }
    shape_probe["planDigest"] = _digest(shape_probe)
    try:
        assert_valid(
            shape_probe,
            "source",
            "scale_source_pool",
            label="image/video source admission projection",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(f"projected scale source-pool row is invalid: {exc}")
    return {**stable, "projectionDigest": _digest(stable)}


__all__ = [
    "PROJECTION_INVALID",
    "PROJECTION_SHORTFALL",
    "ScaleSourcePoolProjectionError",
    "project_scale_source_pool_image_video",
]
