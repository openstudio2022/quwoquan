"""Project audited professional media into scale source-pool candidate rows.

The projection is offline and pure: it verifies caller-owned evidence files and
returns deterministic rows.  Discovery is never treated as acquisition.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.schema import assert_valid

from content.source.professional_image_supported_api_metadata_entities import (
    load_entity_bindings,
    resolve_entity_ref,
)
from content.source.professional_image_source_attribution import (
    bound_image_source_attribution,
)
from content.source.research.scale_source_pool_projection_documents import (
    load_documents as _load_documents,
)
from content.source.research.scale_source_pool_video_projection import (
    project_video_rows,
)

PROJECTION_INVALID = "DATA.SOURCE.POOL_INVALID"
PROJECTION_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCALES = frozenset({"WORKLOAD", "M100", "M1000", "M10000"})
_ACCEPTED = frozenset({"research_allowed", "commercial_allowed"})
_PIN = frozenset({"pinterest", "pinterest.com", "www.pinterest.com"})
_TUCHONG = frozenset({"tuchong", "tuchong.com", "www.tuchong.com", "图虫", "图虫社区"})
_SUPPLEMENTAL_IMAGE_PROVIDERS = frozenset({"wikimedia_commons", "openverse"})


class ScaleSourcePoolProjectionError(ValueError):
    """Typed projection blocker."""

    def __init__(self, code: str, issue: str) -> None:
        self.code = code
        self.issue = str(issue).strip()
        super().__init__(f"{code}: {self.issue}")


def _fail(issue: str, *, shortfall: bool = False) -> None:
    code = PROJECTION_SHORTFALL if shortfall else PROJECTION_INVALID
    raise ScaleSourcePoolProjectionError(code, issue)


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _provider(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in _PIN:
        return "pinterest"
    if normalized in _TUCHONG:
        return "tuchong"
    return normalized


def _assert_identity(document: Mapping[str, Any], expected: tuple[str, str, str], *, label: str) -> None:
    actual = tuple(
        str(document.get(field) or "").strip()
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if actual != expected:
        _fail(f"{label} source identity drift")


def _one_review(
    reviews: Mapping[tuple[str, str], dict[str, Any]], *, kind: str, asset_id: str
) -> dict[str, Any]:
    try:
        return reviews[(kind, asset_id)]
    except KeyError:
        _fail(f"{kind} asset lacks independent rights/quality review: {asset_id}", shortfall=True)
    raise AssertionError("unreachable")


def _accepted_review(
    review_input: Mapping[str, Any],
    acquisition_input: Mapping[str, Any],
    asset: Mapping[str, Any],
    *,
    expected_identity: tuple[str, str, str],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    review = review_input["document"]
    _assert_identity(review, expected_identity, label="independent review")
    snapshot = review.get("assetSnapshot")
    judgment = review.get("judgment")
    if not isinstance(snapshot, Mapping) or not isinstance(judgment, Mapping):
        _fail("independent review lacks snapshot/judgment")
    if (
        review.get("reviewDecision") != "accepted"
        or review.get("acquisitionReceiptDigest") != acquisition_input["documentDigest"]
        or review.get("acquisitionReceiptSha256") != acquisition_input["fileSha256"]
        or snapshot.get("assetId") != asset.get("assetId")
        or snapshot.get("contentSha256") != asset.get("contentSha256")
        or snapshot.get("entityId") != asset.get("entityId")
        or snapshot.get("observedEntityId") != asset.get("observedEntityId")
        or snapshot.get("rightsStatus") != asset.get("rightsStatus")
        or snapshot.get("distributionDecision") != asset.get("distributionDecision")
        or judgment.get("qualityStatus") != "passed"
        or judgment.get("safetyStatus") != "passed"
        or judgment.get("entityMatch") != "matched"
        or judgment.get("rightsStatus") != asset.get("rightsStatus")
        or judgment.get("distributionDecision") != asset.get("distributionDecision")
    ):
        _fail(f"independent review binding is not publishable: {asset.get('assetId')}")
    for field in ("mediaProbe", "popularitySignals"):
        if snapshot.get(field) != asset.get(field):
            _fail(
                f"independent review snapshot drift for {field}: {asset.get('assetId')}"
            )
    for field in (
        "popularCandidateId",
        "popularCatalogRef",
        "popularCatalogDigest",
        "popularCatalogFileSha256",
    ):
        if str(snapshot.get(field) or "") != str(asset.get(field) or ""):
            _fail(
                f"independent review snapshot drift for {field}: {asset.get('assetId')}"
            )
    return snapshot, judgment


def _common_row(
    *,
    carrier: str,
    object_ref: str,
    asset: Mapping[str, Any],
    source_input: Mapping[str, Any],
    acquisition_input: Mapping[str, Any],
    review_input: Mapping[str, Any],
    identity: tuple[str, str, str],
    entity_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_revision, source_digest, entity_catalog_digest = identity
    review_digest = str(review_input["documentDigest"])
    review_sha = str(review_input["fileSha256"])
    seed = "|".join((carrier, object_ref, str(asset["assetId"]), str(asset["contentSha256"])))
    source_attribution: dict[str, Any] | None = None
    if carrier == "image":
        source_attribution = bound_image_source_attribution(
            asset,
            platform=str(asset["platform"]),
            distribution_decision=str(asset["distributionDecision"]),
        )
    try:
        canonical_entity_ref = resolve_entity_ref(
            asset["entityId"],
            index=entity_index,
        )
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"asset entity identity is absent from frozen catalog: {exc}")
    return {
        "candidateId": f"{carrier}-" + hashlib.sha256(seed.encode()).hexdigest(),
        "carrier": carrier,
        "objectRef": object_ref,
        "entityRef": canonical_entity_ref,
        "observedEntityRef": canonical_entity_ref,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        **(
            {"sourceAttribution": source_attribution}
            if source_attribution is not None
            else {}
        ),
        "sourceUnitRef": source_input["ref"],
        "sourceUnitDigest": source_input["documentDigest"],
        "sourceUnitFileSha256": source_input["fileSha256"],
        "provider": _provider(asset.get("provider") or asset.get("platform")),
        "contentSha256": str(asset["contentSha256"]),
        "acquisitionStatus": "acquired",
        "acquisitionRef": acquisition_input["ref"],
        "acquisitionDigest": acquisition_input["documentDigest"],
        "acquisitionFileSha256": acquisition_input["fileSha256"],
        "rightsStatus": str(asset["rightsStatus"]),
        "distributionDecision": str(asset["distributionDecision"]),
        "rightsRef": review_input["ref"],
        "rightsDigest": review_digest,
        "rightsFileSha256": review_sha,
        "qualityStatus": "passed",
        "qualityRef": review_input["ref"],
        "qualityDigest": review_digest,
        "qualityFileSha256": review_sha,
        "generated": False,
    }


def _image_rows(
    catalogs: list[dict[str, Any]], acquisitions: list[dict[str, Any]],
    reviews: Mapping[tuple[str, str], dict[str, Any]], identity: tuple[str, str, str],
    entity_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: dict[str, tuple[Mapping[str, Any], Mapping[str, Any], str]] = {}
    for catalog_input in catalogs:
        catalog_schema = str(catalog_input["document"]["schema"])
        expected_path = (
            "public_direct"
            if catalog_schema == "quwoquan_data.professional_image_public_candidate_catalog"
            else ""
        )
        for candidate in catalog_input["document"]["candidates"]:
            candidate_id = str(candidate["candidateId"])
            if candidate_id in candidates:
                _fail(f"duplicate image discovery candidate: {candidate_id}")
            candidate_path = expected_path or str(candidate.get("acquisitionPath") or "")
            candidates[candidate_id] = (candidate, catalog_input, candidate_path)
    rows: list[dict[str, Any]] = []
    for acquisition_input in acquisitions:
        acquisition = acquisition_input["document"]
        _assert_identity(acquisition, identity, label="image acquisition")
        for asset in acquisition["assets"]:
            if asset.get("distributionDecision") not in _ACCEPTED:
                continue
            if asset.get("acquisitionStatus") != "acquired" or not asset.get("contentSha256"):
                _fail(f"image discovery was not acquired: {asset.get('assetId')}")
            provider = _provider(asset.get("provider") or asset.get("platform"))
            if provider not in {"pinterest", "tuchong", *_SUPPLEMENTAL_IMAGE_PROVIDERS}:
                _fail(f"image provider is not governed for scale: {asset.get('provider')}")
            acquisition_path = str(asset.get("acquisitionPath") or "")
            if provider == "pinterest" and acquisition_path not in {
                "supported_api", "manual_file"
            }:
                _fail("Pinterest scale acquisition requires supported API or manual file")
            discovery_candidate_id = str(asset.get("discoveryCandidateId") or "")
            asset_candidate_id = str(asset.get("assetId") or "")
            candidate_id = (
                asset_candidate_id
                if asset_candidate_id in candidates
                else discovery_candidate_id
            )
            try:
                candidate, catalog_input, catalog_path = candidates[candidate_id]
            except KeyError:
                _fail(f"acquired image lacks path-governed candidate binding: {candidate_id}")
            if catalog_path != acquisition_path:
                _fail(f"image candidate acquisitionPath drift: {asset.get('assetId')}")
            common_drift = (
                candidate.get("originalAssetCandidate") is not True
                or candidate.get("generated") is True
                or _provider(candidate.get("provider")) != provider
                or acquisition.get("discoveryPlanDigest")
                != catalog_input["document"].get("discoveryPlanDigest")
                or str(candidate.get("creator") or "").strip()
                != str(asset.get("creator") or "").strip()
            )
            if common_drift:
                _fail(f"image original/source binding drift: {asset.get('assetId')}")
            if catalog_path == "public_direct":
                if (
                    str(candidate.get("sourcePageUrl") or "")
                    != str(asset.get("discoveryUrl") or "")
                    or str(candidate.get("assetUrl") or "")
                    != str(asset.get("assetUrl") or "")
                ):
                    _fail(f"public image candidate binding drift: {asset.get('assetId')}")
            else:
                original = candidate.get("originalAssetIdentity")
                if not isinstance(original, Mapping):
                    _fail(f"governed image candidate lacks original identity: {candidate_id}")
                if (
                    str(candidate.get("sourcePageUrl") or "")
                    != str(asset.get("sourceUrl") or "")
                    or str(candidate.get("title") or "").strip()
                    != str(asset.get("displayName") or "").strip()
                    or str(original.get("contentSha256") or "")
                    != str(asset.get("contentSha256") or "")
                    or str(original.get("sourceUrl") or "")
                    != str(asset.get("sourceUrl") or "")
                    or str(original.get("assetUrl") or "")
                    != str(asset.get("assetUrl") or "")
                    or str(original.get("manualFile") or "")
                    != str(asset.get("manualFile") or "")
                    or not (
                        str(original.get("apiEvidence") or "")
                        == str(asset.get("apiEvidence") or "")
                        or (
                            acquisition_path == "supported_api"
                            and str(original.get("apiEvidence") or "").endswith(
                                "/" + str(asset.get("apiEvidence") or "")
                            )
                        )
                    )
                ):
                    _fail(f"governed image original/path binding drift: {asset.get('assetId')}")
            review_input = _one_review(reviews, kind="image", asset_id=str(asset["assetId"]))
            _accepted_review(review_input, acquisition_input, asset, expected_identity=identity)
            row = _common_row(
                carrier="image", object_ref=str(review_input["document"]["objectRef"]),
                asset=asset, source_input=catalog_input, acquisition_input=acquisition_input,
                review_input=review_input, identity=identity, entity_index=entity_index,
            )
            row.update(playabilityRef=None, playabilityDigest=None,
                       playabilityFileSha256=None, videoReadiness=None)
            rows.append(row)
    return rows


def project_scale_source_pool_image_video(
    *,
    evidence_root: Path,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    entity_catalog_ref: str,
    image_catalog_refs: Iterable[str] | None,
    image_acquisition_refs: Iterable[str] | None,
    image_review_refs: Iterable[str] | None,
    video_catalog_refs: Iterable[str] | None,
    video_acquisition_refs: Iterable[str] | None,
    video_review_refs: Iterable[str] | None,
) -> dict[str, Any]:
    """Return verified rows for the media carriers active in one wave."""
    if target_scale not in _SCALES:
        _fail(f"unsupported targetScale={target_scale!r}")
    identity = (source_revision, source_digest, entity_catalog_digest)
    if any(not _SHA256.fullmatch(value) for value in identity):
        _fail("sourceRevision/sourceDigest/entityCatalogDigest must be sha256")
    try:
        resolved_catalog_ref, resolved_catalog_digest, entity_index = (
            load_entity_bindings(Path(entity_catalog_ref))
        )
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"entity catalog binding is unavailable: {exc}")
    if resolved_catalog_ref != str(entity_catalog_ref).strip().strip("/"):
        _fail("entity catalog ref drift")
    if resolved_catalog_digest != entity_catalog_digest:
        _fail("entity catalog digest drift")
    root = evidence_root.expanduser().resolve()
    refs = {
        "image_catalog": tuple(image_catalog_refs or ()),
        "image_acquisition": tuple(image_acquisition_refs or ()),
        "image_review": tuple(image_review_refs or ()),
        "video_catalog": tuple(video_catalog_refs or ()),
        "video_acquisition": tuple(video_acquisition_refs or ()),
        "video_review": tuple(video_review_refs or ()),
    }
    image_requested = any(refs[kind] for kind in (
        "image_catalog", "image_acquisition", "image_review"
    ))
    video_requested = any(refs[kind] for kind in (
        "video_catalog", "video_acquisition", "video_review"
    ))
    if not image_requested and not video_requested:
        _fail("at least one media carrier evidence set is required", shortfall=True)
    groups = {
        "image_catalog": _load_documents(
            refs["image_catalog"],
            root=root,
            kind="image_catalog",
            schema_name={
                "quwoquan_data.professional_image_public_candidate_catalog":
                    "professional_image_public_candidate_catalog",
                "quwoquan_data.professional_image_governed_candidate_catalog":
                    "professional_image_governed_candidate_catalog",
            },
            fail=_fail,
        ),
        "image_acquisition": _load_documents(
            refs["image_acquisition"],
            root=root,
            kind="image_acquisition",
            schema_name="professional_image_acquisition_receipt",
            fail=_fail,
        ),
        "image_review": _load_documents(
            refs["image_review"],
            root=root,
            kind="image_review",
            schema_name="independent_asset_review_receipt",
            fail=_fail,
        ),
        "video_catalog": _load_documents(
            refs["video_catalog"],
            root=root,
            kind="video_catalog",
            schema_name="professional_video_popular_candidate_catalog",
            fail=_fail,
        ),
        "video_acquisition": _load_documents(
            refs["video_acquisition"],
            root=root,
            kind="video_acquisition",
            schema_name="professional_video_acquisition_receipt",
            fail=_fail,
        ),
        "video_review": _load_documents(
            refs["video_review"],
            root=root,
            kind="video_review",
            schema_name="independent_asset_review_receipt",
            fail=_fail,
        ),
    }
    required_kinds = []
    if image_requested:
        required_kinds.extend(("image_catalog", "image_acquisition", "image_review"))
    if video_requested:
        required_kinds.extend(("video_acquisition", "video_review"))
    if any(not groups[kind] for kind in required_kinds):
        _fail("active media carrier requires every evidence class", shortfall=True)
    review_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in groups["image_review"] + groups["video_review"]:
        review = item["document"]
        key = (str(review["assetKind"]), str(review["assetSnapshot"]["assetId"]))
        if key in review_index:
            _fail(f"duplicate independent review for {key[0]} asset {key[1]}")
        review_index[key] = item
    rows: list[dict[str, Any]] = []
    if image_requested:
        rows.extend(_image_rows(
            groups["image_catalog"], groups["image_acquisition"], review_index, identity,
            entity_index,
        ))
    if video_requested:
        rows.extend(project_video_rows(
            catalogs=groups["video_catalog"],
            acquisitions=groups["video_acquisition"],
            reviews=review_index,
            identity=identity,
            fail=_fail,
            assert_identity=_assert_identity,
            one_review=_one_review,
            accepted_review=_accepted_review,
            common_row=_common_row,
            entity_index=entity_index,
        ))
    for carrier, requested in (("image", image_requested), ("video", video_requested)):
        if requested and not any(row["carrier"] == carrier for row in rows):
            _fail(
                f"no acquired reviewed {carrier} rows were projected",
                shortfall=True,
            )
    content = [str(row["contentSha256"]) for row in rows]
    if len(content) != len(set(content)):
        _fail("duplicate contentSha256 across projected image/video rows")
    rows.sort(key=lambda row: (str(row["carrier"]), str(row["objectRef"]), str(row["candidateId"])))
    inputs = [
        {key: item[key] for key in ("kind", "ref", "documentDigest", "fileSha256")}
        for kind in sorted(groups) for item in groups[kind]
    ]
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
    carriers = ("homepage", "article", "image", "video")
    active = tuple(
        carrier
        for carrier in carriers
        if any(str(row.get("carrier") or "") == carrier for row in rows)
    )
    physical_workloads = {
        carrier: sum(str(row.get("carrier") or "") == carrier for row in rows)
        for carrier in active
    }
    shape_probe = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "projection-shape-probe",
        "targetScale": target_scale,
        "workloadMode": (
            "milestone_preset"
            if target_scale != "WORKLOAD" and active == carriers
            else "explicit"
        ),
        "activeCarriers": list(active),
        "workloadTargets": physical_workloads,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": "projection-only",
        "waveCandidateCounts": [
            {
                "carrier": carrier,
                "minimumCandidateCount": sum(
                    str(row.get("carrier") or "") == carrier for row in rows
                ),
            }
            for carrier in active
        ],
        "candidates": rows,
    }
    shape_probe["planDigest"] = _digest(shape_probe)
    try:
        assert_valid(shape_probe, "source", "scale_source_pool", label="image/video projection")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(f"projected scale source-pool row is invalid: {exc}")
    return {**stable, "projectionDigest": _digest(stable)}

__all__ = [
    "PROJECTION_INVALID", "PROJECTION_SHORTFALL", "ScaleSourcePoolProjectionError",
    "project_scale_source_pool_image_video",
]
