"""Deterministic homepage/article scale source-pool row projections.

Owned by ``scale_source_pool_homepage_article``: that module validates the
create-once catalog bytes and delegates the per-candidate row shape (identity,
composite bindings and aggregated rights) to this projection library.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from content.source.research.scale_source_pool_rights import (
    EmptyMediaRightsError,
    aggregate_media_rights,
)

PROJECTION_INVALID = "DATA.SOURCE.INVALID_EVIDENCE"
SHA256_PREFIX = "sha256:"


class ScaleSourcePoolProjectionError(ValueError):
    """Typed catalog-to-scale projection blocker."""

    def __init__(self, issues: Sequence[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("scale source-pool projection error requires an issue")
        self.code = PROJECTION_INVALID
        self.issues = normalized
        super().__init__(f"{PROJECTION_INVALID}: " + "; ".join(normalized))


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def aggregate_rights(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    try:
        return aggregate_media_rights(rows)
    except EmptyMediaRightsError as exc:
        raise ScaleSourcePoolProjectionError([str(exc)]) from exc


def composite_bindings(
    *,
    carrier: str,
    candidate_id: str,
    evidence_root_ref: str,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
    source_unit: object,
    acquisition: object,
    rights: object,
    quality: object,
) -> dict[str, Any]:
    values = {
        "sourceUnit": source_unit,
        "acquisition": acquisition,
        "rights": rights,
        "quality": quality,
    }
    result: dict[str, Any] = {}
    for prefix, value in values.items():
        result[f"{prefix}Ref"] = evidence_ref
        result[f"{prefix}Digest"] = canonical_digest(
            {
                "schema": f"quwoquan_data.{carrier}_{prefix}_composite",
                "evidenceDigest": evidence_digest,
                "candidateId": candidate_id,
                "value": value,
            }
        )
        result[f"{prefix}FileSha256"] = file_sha256
    result["sourceReadyEvidenceRootRef"] = evidence_root_ref
    return result


def homepage_row(
    candidate: Mapping[str, Any],
    *,
    evidence_root_ref: str,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidateId"])
    entity_ref = str(candidate["entityRef"])
    primary = candidate["primarySource"]
    hero = candidate["hero"]
    assert isinstance(primary, Mapping) and isinstance(hero, Mapping)
    rights_status, decision = aggregate_rights([hero])
    bindings = composite_bindings(
        carrier="homepage",
        candidate_id=candidate_id,
        evidence_root_ref=evidence_root_ref,
        evidence_digest=evidence_digest,
        evidence_ref=evidence_ref,
        file_sha256=file_sha256,
        source_unit={
            "primarySource": primary,
            "structuredFacts": candidate["structuredFacts"],
            "factEvidence": candidate["factEvidence"],
            "factConflicts": candidate["factConflicts"],
        },
        acquisition={
            key: hero[key]
            for key in (
                "assetId",
                "assetRef",
                "originalAssetUrl",
                "sourcePageUrl",
                "acquisitionStatus",
                "contentSha256",
            )
        },
        rights={
            key: hero[key]
            for key in (
                "creator",
                "license",
                "termsUrl",
                "authorizationProof",
                "authorizationRequired",
                "rightsStatus",
                "rightsIssues",
                "distributionDecision",
            )
        },
        quality={
            key: hero[key]
            for key in ("qualityStatus", "safetyStatus", "generated")
        },
    )
    return {
        "candidateId": candidate_id,
        "carrier": "homepage",
        "objectRef": "entities/" + entity_ref.removeprefix("/entity/").strip("/"),
        "entityRef": entity_ref,
        "observedEntityRef": str(candidate["observedEntityRef"]),
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": candidate["sourceDigest"],
        "entityCatalogDigest": candidate["entityCatalogDigest"],
        "sourceAttribution": dict(candidate["sourceAttribution"]),
        **bindings,
        "provider": primary["platform"],
        "contentSha256": canonical_digest(
            {
                "bodyContentSha256": primary["bodyContentSha256"],
                "heroContentSha256": hero["contentSha256"],
            }
        ),
        "acquisitionStatus": "acquired",
        "rightsStatus": rights_status,
        "distributionDecision": decision,
        "qualityStatus": "passed",
        "generated": False,
        "playabilityRef": None,
        "playabilityDigest": None,
        "playabilityFileSha256": None,
        "videoReadiness": None,
    }


def article_row(
    candidate: Mapping[str, Any],
    *,
    evidence_root_ref: str,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidateId"])
    assets = [row for row in candidate["assets"] if isinstance(row, Mapping)]
    publish_media_mode = str(candidate["publishMediaMode"])
    if assets:
        rights_status, decision = aggregate_rights(assets)
    else:
        attribution = candidate["sourceAttribution"]
        assert isinstance(attribution, Mapping)
        rights_status = (
            "verified"
            if attribution.get("commercialAuthorizationStatus") == "verified"
            else "unverified"
        )
        decision = "research_allowed"
    bindings = composite_bindings(
        carrier="article",
        candidate_id=candidate_id,
        evidence_root_ref=evidence_root_ref,
        evidence_digest=evidence_digest,
        evidence_ref=evidence_ref,
        file_sha256=file_sha256,
        source_unit={
            key: candidate[key]
            for key in (
                "sourceUnitId",
                "sourceUnitRef",
                "sourceUnitDigest",
                "sourceKind",
                "extractor",
                "sourceUrl",
                "bodyEvidenceRef",
                "bodyContentSha256",
            )
        }
        | {
            key: candidate[key]
            for key in (
                "articleCategory",
                "writingIntent",
                "topicTagRefs",
                "sourceClassification",
            )
            if key in candidate
        },
        acquisition=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "role",
                    "assetRef",
                    "originalAssetUrl",
                    "sourcePageUrl",
                    "acquisitionStatus",
                    "contentSha256",
                )
            }
            for row in assets
        ],
        rights=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "creator",
                    "license",
                    "termsUrl",
                    "authorizationProof",
                    "authorizationRequired",
                    "rightsStatus",
                    "rightsIssues",
                    "distributionDecision",
                )
            }
            for row in assets
        ],
        quality=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "role",
                    "qualityStatus",
                    "safetyStatus",
                    "generated",
                )
            }
            for row in assets
        ],
    )
    return {
        "candidateId": candidate_id,
        "carrier": "article",
        "objectRef": f"posts/article/{candidate_id}",
        "entityRef": candidate["entityRef"],
        "observedEntityRef": candidate["observedEntityRef"],
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": candidate["sourceDigest"],
        "entityCatalogDigest": candidate["entityCatalogDigest"],
        "sourceAttribution": dict(candidate["sourceAttribution"]),
        "publishMediaMode": publish_media_mode,
        **bindings,
        "provider": candidate["platform"],
        "contentSha256": canonical_digest(
            {
                "bodyContentSha256": candidate["bodyContentSha256"],
                "mediaContentSha256": sorted(
                    str(row["contentSha256"]) for row in assets
                ),
            }
        ),
        "acquisitionStatus": "acquired",
        "rightsStatus": rights_status,
        "distributionDecision": decision,
        "qualityStatus": "passed",
        "generated": False,
        "playabilityRef": None,
        "playabilityDigest": None,
        "playabilityFileSha256": None,
        "videoReadiness": None,
    }


__all__ = [
    "PROJECTION_INVALID",
    "SHA256_PREFIX",
    "ScaleSourcePoolProjectionError",
    "aggregate_rights",
    "article_row",
    "canonical_digest",
    "composite_bindings",
    "homepage_row",
]
