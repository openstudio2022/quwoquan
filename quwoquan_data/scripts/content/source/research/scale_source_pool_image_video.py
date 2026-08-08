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

from content.source import professional_video_catalog_binding as popular_binding

PROJECTION_INVALID = "DATA.SOURCE.POOL_INVALID"
PROJECTION_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCALES = frozenset({"M100", "M1000", "M10000"})
_ACCEPTED = frozenset({"research_allowed", "commercial_allowed"})
_PIN = frozenset({"pinterest", "pinterest.com", "www.pinterest.com"})
_TUCHONG = frozenset({"tuchong", "tuchong.com", "www.tuchong.com", "图虫", "图虫社区"})
_SUPPLEMENTAL_IMAGE_PROVIDERS = frozenset({"wikimedia_commons", "openverse"})
_GENERATED_MARKERS = ("generated", "synthetic", "text_to_video", "ai_video")
_REQUIRED = {"M100": (180, 180, 180, 18), "M1000": (1620, 1620, 1620, 162),
             "M10000": (16200, 16200, 16200, 1620)}


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


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_path(root: Path, ref: object, *, label: str) -> tuple[Path, str]:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail(f"{label} must be a safe relative reference")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{label} must not traverse a symlink")
    if not current.is_file():
        _fail(f"{label} is missing: {relative.as_posix()}")
    return current, relative.as_posix()


def _document_digest(document: Mapping[str, Any], *, kind: str) -> str:
    if kind == "image_catalog":
        if document.get("schema") == "quwoquan_data.professional_image_public_candidate_catalog":
            fields = (
                "catalogRevision", "discoveryPlanId", "discoveryPlanDigest",
                "observedAt", "sourceResponses", "providerCounts", "candidateCount",
                "rejectedAssetCount", "candidates", "rejections",
            )
        elif document.get("schema") == "quwoquan_data.professional_image_governed_candidate_catalog":
            fields = (
                "catalogRevision", "discoveryPlanId", "discoveryPlanDigest",
                "createdAt", "providerCounts", "candidateCount", "candidates",
            )
        else:
            _fail("image catalog schema is not governed")
        return _digest({field: document[field] for field in fields})
    if kind == "video_catalog":
        return _digest({
            key: value for key, value in document.items()
            if key not in {"catalogId", "catalogDigest"}
        })
    digest_field = "receiptDigest"
    return _digest({key: value for key, value in document.items() if key != digest_field})


def _validate_governed_catalog_evidence(
    document: Mapping[str, Any], *, root: Path,
) -> None:
    if document.get("schema") != "quwoquan_data.professional_image_governed_candidate_catalog":
        return
    for candidate in document["candidates"]:
        binding = candidate["pathEvidence"]
        path, ref = _safe_path(root, binding["ref"], label="imageCandidateEvidenceRef")
        if _file_digest(path) != binding["fileSha256"]:
            _fail(f"image candidate evidence file drift: {ref}")
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            _fail(f"image candidate evidence is not readable JSON: {ref}: {exc}")
        if not isinstance(evidence, dict) or _digest(evidence) != binding["digest"]:
            _fail(f"image candidate evidence digest drift: {ref}")


def _load_documents(
    refs: Iterable[str], *, root: Path, kind: str,
    schema_name: str | Mapping[str, str],
) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    seen: set[str] = set()
    digest_field = (
        "catalogDigest"
        if kind in {"image_catalog", "video_catalog"}
        else "receiptDigest"
    )
    for raw_ref in sorted(str(ref).strip() for ref in refs):
        path, ref = _safe_path(root, raw_ref, label=f"{kind}Ref")
        if ref in seen:
            _fail(f"duplicate {kind} reference: {ref}")
        seen.add(ref)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            _fail(f"{kind} is not readable JSON: {ref}: {exc}")
        if not isinstance(document, dict):
            _fail(f"{kind} must be an object: {ref}")
        selected_schema = schema_name
        if isinstance(schema_name, Mapping):
            selected_schema = schema_name.get(str(document.get("schema") or ""), "")
            if not selected_schema:
                _fail(f"{kind} schema is not an accepted catalog type: {ref}")
        try:
            assert_valid(document, "source", selected_schema, label=kind)
        except (FileNotFoundError, TypeError, ValueError) as exc:
            _fail(f"{kind} schema failure: {ref}: {exc}")
        semantic = _document_digest(document, kind=kind)
        if document.get(digest_field) != semantic:
            _fail(f"{kind} document digest drift: {ref}")
        if kind == "image_catalog":
            _validate_governed_catalog_evidence(document, root=root)
        loaded.append(
            {
                "kind": kind,
                "ref": ref,
                "documentDigest": semantic,
                "fileSha256": _file_digest(path),
                "document": document,
            }
        )
    return loaded


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
    for field in ("mediaProbe", "popularitySignals", *popular_binding.POPULAR_BINDING_FIELDS):
        if snapshot.get(field) != asset.get(field):
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
) -> dict[str, Any]:
    source_revision, source_digest, entity_catalog_digest = identity
    review_digest = str(review_input["documentDigest"])
    review_sha = str(review_input["fileSha256"])
    seed = "|".join((carrier, object_ref, str(asset["assetId"]), str(asset["contentSha256"])))
    return {
        "candidateId": f"{carrier}-" + hashlib.sha256(seed.encode()).hexdigest(),
        "carrier": carrier,
        "objectRef": object_ref,
        "entityRef": str(asset["entityId"]),
        "observedEntityRef": str(asset["observedEntityId"]),
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
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
    reviews: Mapping[tuple[str, str], dict[str, Any]], identity: tuple[str, str, str]
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
            candidate_id = str(asset.get("discoveryCandidateId") or "")
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
                    or str(original.get("apiEvidence") or "")
                    != str(asset.get("apiEvidence") or "")
                ):
                    _fail(f"governed image original/path binding drift: {asset.get('assetId')}")
            review_input = _one_review(reviews, kind="image", asset_id=str(asset["assetId"]))
            _accepted_review(review_input, acquisition_input, asset, expected_identity=identity)
            row = _common_row(
                carrier="image", object_ref=str(review_input["document"]["objectRef"]),
                asset=asset, source_input=catalog_input, acquisition_input=acquisition_input,
                review_input=review_input, identity=identity,
            )
            row.update(playabilityRef=None, playabilityDigest=None,
                       playabilityFileSha256=None, videoReadiness=None)
            rows.append(row)
    return rows


def _video_rows(
    catalogs: list[dict[str, Any]], acquisitions: list[dict[str, Any]],
    reviews: Mapping[tuple[str, str], dict[str, Any]],
    identity: tuple[str, str, str]
) -> list[dict[str, Any]]:
    candidates: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
    for catalog_input in catalogs:
        catalog = catalog_input["document"]
        _assert_identity(catalog, identity, label="popular-video catalog")
        for candidate in catalog["candidates"]:
            candidate_id = str(candidate["candidateId"])
            if candidate_id in candidates:
                _fail(f"duplicate popular-video candidate: {candidate_id}")
            candidates[candidate_id] = (candidate, catalog_input)
    rows: list[dict[str, Any]] = []
    for acquisition_input in acquisitions:
        acquisition = acquisition_input["document"]
        _assert_identity(acquisition, identity, label="video acquisition")
        for asset in acquisition["assets"]:
            if asset.get("distributionDecision") not in _ACCEPTED:
                continue
            if asset.get("acquisitionStatus") != "acquired" or not asset.get("contentSha256"):
                _fail(f"video candidate was not acquired: {asset.get('assetId')}")
            source_kind = str(asset.get("sourceKind") or "").strip().casefold()
            if any(marker in source_kind for marker in _GENERATED_MARKERS):
                _fail(f"generated video is forbidden: {asset.get('assetId')}")
            binding = tuple(str(asset.get(field) or "").strip()
                            for field in popular_binding.POPULAR_BINDING_FIELDS)
            if not all(binding):
                _fail(
                    f"M100+ video lacks popular-catalog binding: {asset.get('assetId')}",
                    shortfall=True,
                )
            candidate_id, catalog_ref, catalog_digest, catalog_sha = binding
            try:
                candidate, catalog_input = candidates[candidate_id]
            except KeyError:
                _fail(f"video popular-catalog candidate is missing: {candidate_id}")
            if (
                catalog_ref != catalog_input["ref"]
                or catalog_digest != catalog_input["documentDigest"]
                or catalog_sha != catalog_input["fileSha256"]
            ):
                _fail(f"video popular-catalog document binding drift: {asset.get('assetId')}")
            candidate_drift = (
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
            )
            if candidate_drift:
                _fail(f"video popular-catalog source/bytes drift: {asset.get('assetId')}")
            review_input = _one_review(reviews, kind="video", asset_id=str(asset["assetId"]))
            snapshot, _judgment = _accepted_review(
                review_input, acquisition_input, asset, expected_identity=identity
            )
            probe = snapshot.get("mediaProbe")
            signals = snapshot.get("popularitySignals")
            count_fields = popular_binding.POPULAR_COUNT_FIELDS
            if not isinstance(probe, Mapping) or not all((
                probe.get("playable") is True, probe.get("motionVideo") is True,
                probe.get("staticImageSequence") is False,
                probe.get("premiumPlayableEligible") is True,
            )):
                _fail(f"video is not real playable motion Premium media: {asset.get('assetId')}")
            if not isinstance(signals, Mapping) or any(
                isinstance(signals.get(field), bool)
                or not isinstance(signals.get(field), int)
                or int(signals[field]) < 0 for field in count_fields
            ):
                _fail(f"video five-signal popularity is incomplete: {asset.get('assetId')}")
            percentile = signals.get("popularityPercentile")
            if (
                signals.get("rankingEligible") is not True
                or isinstance(percentile, bool)
                or not isinstance(percentile, (int, float))
                or not 0 <= float(percentile) <= 1
                or int(signals.get("comparisonCandidateCount") or 0) < 2
                or any(not str(signals.get(field) or "").strip() for field in ("observedAt", "provider", "topic", "timeBucket"))
            ):
                _fail(f"video popularity percentile is not comparable: {asset.get('assetId')}")
            catalog_popularity = candidate["popularity"]
            expected_popularity = {
                **dict(catalog_popularity),
                "observedAt": str(candidate["observedAt"]),
                "provider": str(candidate["provider"]),
                "topic": str(candidate["topic"]),
                "timeBucket": str(candidate["timeBucket"]),
                "rankingEligible": True,
                "ineligibleReason": "",
            }
            if dict(signals) != expected_popularity:
                _fail(f"video popular-catalog popularity drift: {asset.get('assetId')}")
            row = _common_row(
                carrier="video", object_ref=str(review_input["document"]["objectRef"]),
                asset=asset, source_input=catalog_input, acquisition_input=acquisition_input,
                review_input=review_input, identity=identity,
            )
            row.update(
                playabilityRef=review_input["ref"],
                playabilityDigest=review_input["documentDigest"],
                playabilityFileSha256=review_input["fileSha256"],
                videoReadiness={
                    "playable": True, "motion": True, "premiumEligible": True,
                    **{field: int(signals[field]) for field in count_fields},
                    "observedAt": str(signals["observedAt"]),
                    "popularityPercentile": float(percentile),
                    "comparisonBucket": {
                        "provider": str(signals["provider"]), "topic": str(signals["topic"]),
                        "timeBucket": str(signals["timeBucket"]),
                        "candidateCount": int(signals["comparisonCandidateCount"]),
                    },
                },
            )
            rows.append(row)
    return rows


def project_scale_source_pool_image_video(
    *,
    evidence_root: Path,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    image_catalog_refs: Iterable[str],
    image_acquisition_refs: Iterable[str],
    image_review_refs: Iterable[str],
    video_catalog_refs: Iterable[str],
    video_acquisition_refs: Iterable[str],
    video_review_refs: Iterable[str],
) -> dict[str, Any]:
    """Return verified deterministic image/video scale-source candidate rows."""
    if target_scale not in _SCALES:
        _fail(f"unsupported targetScale={target_scale!r}")
    identity = (source_revision, source_digest, entity_catalog_digest)
    if any(not _SHA256.fullmatch(value) for value in identity):
        _fail("sourceRevision/sourceDigest/entityCatalogDigest must be sha256")
    root = evidence_root.expanduser().resolve()
    groups = {
        "image_catalog": _load_documents(
            image_catalog_refs,
            root=root,
            kind="image_catalog",
            schema_name={
                "quwoquan_data.professional_image_public_candidate_catalog":
                    "professional_image_public_candidate_catalog",
                "quwoquan_data.professional_image_governed_candidate_catalog":
                    "professional_image_governed_candidate_catalog",
            },
        ),
        "image_acquisition": _load_documents(image_acquisition_refs, root=root, kind="image_acquisition", schema_name="professional_image_acquisition_receipt"),
        "image_review": _load_documents(image_review_refs, root=root, kind="image_review", schema_name="independent_asset_review_receipt"),
        "video_catalog": _load_documents(video_catalog_refs, root=root, kind="video_catalog", schema_name="professional_video_popular_candidate_catalog"),
        "video_acquisition": _load_documents(video_acquisition_refs, root=root, kind="video_acquisition", schema_name="professional_video_acquisition_receipt"),
        "video_review": _load_documents(video_review_refs, root=root, kind="video_review", schema_name="independent_asset_review_receipt"),
    }
    if any(not rows for rows in groups.values()):
        _fail("image/video projection requires every evidence class", shortfall=True)
    review_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in groups["image_review"] + groups["video_review"]:
        review = item["document"]
        key = (str(review["assetKind"]), str(review["assetSnapshot"]["assetId"]))
        if key in review_index:
            _fail(f"duplicate independent review for {key[0]} asset {key[1]}")
        review_index[key] = item
    rows = _image_rows(groups["image_catalog"], groups["image_acquisition"], review_index, identity)
    rows += _video_rows(
        groups["video_catalog"], groups["video_acquisition"], review_index, identity
    )
    if not any(row["carrier"] == "image" for row in rows) or not any(
        row["carrier"] == "video" for row in rows
    ):
        _fail("no acquired reviewed image/video rows were projected", shortfall=True)
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
    shape_probe = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "projection-shape-probe",
        "targetScale": target_scale,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": "projection-only",
        "requiredNewCandidateCounts": [
            {"carrier": carrier, "minimumCandidateCount": count}
            for carrier, count in zip(carriers, _REQUIRED[target_scale], strict=True)
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
