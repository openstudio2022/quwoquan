"""Create-once evidence contract for homepage/article source-ready capsules."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
EVIDENCE_SCHEMA = (
    "quwoquan_data.homepage_article_source_ready_acquisition_evidence"
)


class SourceReadyAcquisitionEvidenceError(ValueError):
    """Typed invalid-evidence or create-once collision blocker."""

    def __init__(self, issues: Sequence[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("source-ready acquisition evidence requires an issue")
        self.code = SOURCE_INVALID_EVIDENCE
        self.issues = normalized
        super().__init__(f"{self.code}: " + "; ".join(normalized))


def canonical_digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(value.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )


def validate_source_ready_acquisition_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate schema and content digest without reading external files."""

    try:
        assert_valid(
            dict(evidence),
            "source",
            "homepage_article_source_ready_acquisition_evidence",
            label="homepage/article source-ready acquisition evidence",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise SourceReadyAcquisitionEvidenceError([str(exc)]) from exc
    stable = {
        key: value for key, value in evidence.items() if key != "evidenceDigest"
    }
    if evidence.get("evidenceDigest") != canonical_digest(stable):
        raise SourceReadyAcquisitionEvidenceError(
            ["source-ready acquisition evidenceDigest mismatch"]
        )
    return dict(evidence)


def _candidate_assets(
    carrier: str,
    candidate: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    if carrier == "homepage":
        hero = candidate.get("hero")
        return [hero] if isinstance(hero, Mapping) else []
    assets = candidate.get("assets")
    return [row for row in assets if isinstance(row, Mapping)] if isinstance(assets, list) else []


def assert_source_ready_evidence_matches_capsule(
    evidence: Mapping[str, Any],
    capsule: Mapping[str, Any],
) -> None:
    """Cross-check acquisition truth against the frozen candidate capsule."""

    validated = validate_source_ready_acquisition_evidence(evidence)
    candidate = capsule.get("candidate")
    if not isinstance(candidate, Mapping):
        raise SourceReadyAcquisitionEvidenceError(
            ["candidate capsule lacks candidate object"]
        )
    carrier = str(capsule.get("carrier") or "")
    if any(
        (
            validated.get("carrier") != carrier,
            validated.get("candidateId") != candidate.get("candidateId"),
            validated.get("entityRef") != candidate.get("entityRef"),
            _identity(validated) != _identity(capsule),
        )
    ):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence/candidate capsule identity drift"]
        )
    source = validated["sourceUnit"]
    assert isinstance(source, Mapping)
    expected_source = (
        candidate.get("primarySource") if carrier == "homepage" else candidate
    )
    if not isinstance(expected_source, Mapping):
        raise SourceReadyAcquisitionEvidenceError(
            ["candidate capsule lacks source-unit binding"]
        )
    source_fields = (
        "sourceUnitId",
        "sourceUnitRef",
        "sourceUnitDigest",
        "sourceUrl",
        "extractor",
        "bodyEvidenceRef",
        "bodyContentSha256",
        "accessEvidence",
    )
    if any(source.get(field) != expected_source.get(field) for field in source_fields):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence/source-unit candidate drift"]
        )
    provenance = capsule.get("provenance")
    selection_origin = str(
        validated.get("sourceSelectionOrigin") or "coverage_source"
    )
    if not isinstance(provenance, Mapping) or selection_origin != str(
        provenance.get("sourceSelectionOrigin") or "coverage_source"
    ):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence source-selection origin drift"]
        )
    if carrier == "homepage":
        source_kind_matches = source.get("sourceKind") == expected_source.get(
            "sourceKind"
        )
    elif selection_origin == "site_frontier":
        try:
            from content.source.research.article_frontier_profile import (
                resolve_article_source_binding,
            )

            resolve_article_source_binding(
                str(candidate.get("sourceUrl") or ""),
                site_id=str(candidate.get("articleSiteId") or ""),
                profile_digest=str(
                    candidate.get("sourceDiscoveryProfileDigest") or ""
                ),
            )
            source_kind_matches = source.get("sourceKind") == candidate.get(
                "sourceKind"
            )
        except ValueError:
            source_kind_matches = False
    else:
        source_kind_matches = (
            candidate.get("articleSiteId") == "wikipedia_zh"
            and source.get("sourceKind") == "wikipedia"
        )
    if not source_kind_matches:
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence/source-unit provider drift"]
        )
    expected_media_mode = (
        "illustrated"
        if carrier == "homepage"
        else str(candidate["publishMediaMode"])
    )
    if (
        validated.get("publishMediaMode") != expected_media_mode
        or validated.get("sourceAttribution") != candidate.get("sourceAttribution")
    ):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence attribution/media-mode drift"]
        )
    seed = validated.get("seed")
    if not isinstance(seed, Mapping) or not isinstance(provenance, Mapping):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence seed binding is missing"]
        )
    if (
        any(seed.get(field) != provenance.get(field) for field in ("seedOrigin", "seedId", "coverageKey"))
        or not isinstance(seed.get("coverageKey"), Mapping)
        or seed["coverageKey"].get("entityRef") != candidate.get("entityRef")
        or seed["coverageKey"].get("carrier") != carrier
        or (
            selection_origin == "coverage_source"
            and seed["coverageKey"].get("sourceUrl") != source.get("sourceUrl")
        )
    ):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence exact seed binding drift"]
        )
    historical_comparison = validated.get("historicalComparison")
    provenance_comparison = provenance.get("historicalComparison")
    if seed.get("seedOrigin") == "historical_capsule_hint":
        if not isinstance(historical_comparison, Mapping):
            raise SourceReadyAcquisitionEvidenceError(
                ["historical-capsule acquisition evidence lacks historical comparison"]
            )
        expected_comparison = (
            "same"
            if historical_comparison.get("bodyContentSha256")
            == source.get("bodyContentSha256")
            else "changed"
        )
        if (
            historical_comparison != provenance_comparison
            or historical_comparison.get("bodyComparison") != expected_comparison
        ):
            raise SourceReadyAcquisitionEvidenceError(
                ["acquisition evidence historical body comparison drift"]
            )
    elif historical_comparison is not None or provenance_comparison is not None:
        raise SourceReadyAcquisitionEvidenceError(
            ["current coverage seed must not manufacture historical comparison"]
        )
    allowed_fact_refs = {
        str(source.get("bodyEvidenceRef") or ""),
        str(source.get("rawEvidenceRef") or ""),
    }
    fact_evidence = candidate.get("factEvidence") if carrier == "homepage" else []
    if isinstance(fact_evidence, list) and any(
        not isinstance(row, Mapping)
        or str(row.get("evidenceRef") or "") not in allowed_fact_refs
        for row in fact_evidence
    ):
        raise SourceReadyAcquisitionEvidenceError(
            ["candidate fact evidence is outside the frozen source unit"]
        )
    evidence_assets = {
        str(row.get("assetId") or ""): row
        for row in validated["assets"]
        if isinstance(row, Mapping)
    }
    candidate_assets = {
        str(row.get("assetId") or ""): row
        for row in _candidate_assets(carrier, candidate)
    }
    if set(evidence_assets) != set(candidate_assets):
        raise SourceReadyAcquisitionEvidenceError(
            ["acquisition evidence/candidate asset set drift"]
        )
    shared_fields = (
        "assetRef",
        "originalAssetUrl",
        "sourcePageUrl",
        "platform",
        "provider",
        "creator",
        "capturedAt",
        "license",
        "termsUrl",
        "authorizationProof",
        "authorizationRequired",
        "rightsStatus",
        "rightsIssues",
        "acquisitionStatus",
        "distributionDecision",
        "contentSha256",
        "qualityStatus",
        "safetyStatus",
        "generated",
    )
    if carrier == "homepage":
        shared_fields += ("accessEvidence",)
    for asset_id, acquired in evidence_assets.items():
        frozen = candidate_assets[asset_id]
        if any(acquired.get(field) != frozen.get(field) for field in shared_fields):
            raise SourceReadyAcquisitionEvidenceError(
                [f"acquisition evidence/candidate asset drift: {asset_id}"]
            )


def write_create_once_json(destination: Path, document: Mapping[str, Any]) -> Path:
    """Atomically create one JSON file and permit only byte-equivalent replay."""

    body = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != body:
                raise SourceReadyAcquisitionEvidenceError(
                    [f"create-once JSON collision: {destination}"]
                )
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return destination


def write_create_once_bytes(
    destination: Path,
    body: bytes,
    *,
    allow_empty: bool = False,
) -> Path:
    """Create one immutable byte object and reject path/content collisions."""

    if not body and not allow_empty:
        raise SourceReadyAcquisitionEvidenceError(
            [f"create-once byte object must be non-empty: {destination}"]
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != body:
                raise SourceReadyAcquisitionEvidenceError(
                    [f"create-once byte collision: {destination}"]
                )
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return destination


def load_source_ready_acquisition_evidence(path: Path) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SourceReadyAcquisitionEvidenceError(
            [f"source-ready acquisition evidence is unreadable: {exc}"]
        ) from exc
    if not isinstance(value, dict):
        raise SourceReadyAcquisitionEvidenceError(
            ["source-ready acquisition evidence must be one object"]
        )
    return validate_source_ready_acquisition_evidence(value)


__all__ = [
    "EVIDENCE_SCHEMA",
    "SOURCE_INVALID_EVIDENCE",
    "SourceReadyAcquisitionEvidenceError",
    "assert_source_ready_evidence_matches_capsule",
    "canonical_digest",
    "file_sha256",
    "load_source_ready_acquisition_evidence",
    "validate_source_ready_acquisition_evidence",
    "write_create_once_bytes",
    "write_create_once_json",
]
