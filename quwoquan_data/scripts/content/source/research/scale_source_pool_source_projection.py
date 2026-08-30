"""冻结候选到 source plan/source unit 的投影与幂等重放校验（拆分自 scale_source_pool_runtime）。"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from core.io import read_json

from content.source.research.scale_source_pool_runtime_blockers import _fail


def _candidate_source(candidate: Mapping[str, Any], carrier: str) -> dict[str, Any]:
    source = (
        candidate["primarySource"] if carrier == "homepage" else candidate
    )
    assert isinstance(source, Mapping)
    publish_media_mode = (
        "illustrated"
        if carrier == "homepage"
        else str(candidate["publishMediaMode"])
    )
    result = {
        "source_id": str(source["sourceUnitId"]),
        "platform": str(source["platform"]),
        "url": str(source["sourceUrl"]),
        "canonicalUrl": str(source["sourceUrl"]),
        "finalUrl": str(source["sourceUrl"]),
        "sourceKind": str(source["sourceKind"]),
        "sourceTitle": str(source["platform"]),
        "qualifiedAuthorityTitle": str(source["platform"]),
        "extractor": str(source["extractor"]),
        "policyRevision": str(source["policyRevision"]),
        "sourceUseMode": "factual_reference_only",
        "publishMediaMode": publish_media_mode,
        "category": str(source["sourceKind"]),
        "discoveryProvider": "frozen_scale_source_pool",
        "matchConfidence": 1.0,
        "evidenceReason": "immutable source-ready candidate capsule",
        "sourceRole": "base",
        "imageEvidenceMode": (
            "" if candidate.get("publishMediaMode") == "text_only" else "same_source"
        ),
        "entityMatch": "accepted",
        "researchLane": carrier,
        "articleCommercialAdmission": (
            "commercial_release" if carrier == "article" else ""
        ),
        "articleSiteId": str(source.get("articleSiteId") or ""),
        "sourceDiscoveryProfileDigest": str(
            source.get("sourceDiscoveryProfileDigest") or ""
        ),
        "runtimeInputMode": "frozen_scale_source_pool",
        "sourcePoolCandidateId": str(candidate["candidateId"]),
        "sourceAttribution": dict(candidate["sourceAttribution"]),
    }
    if carrier == "article" and candidate.get("articleCategory"):
        result.update(
            {
                "articleCategory": str(candidate["articleCategory"]),
                "writingIntent": str(candidate["writingIntent"]),
                "topicTagRefs": list(candidate["topicTagRefs"]),
                "sourceClassification": dict(candidate["sourceClassification"]),
            }
        )
    return result


def _existing_source_unit(
    execution_id: str,
    source_unit_id: str,
    *,
    body_sha256: str,
    media_sha256: list[str],
    carrier: str,
    source_url: str,
    source_attribution: Mapping[str, Any],
    publish_media_mode: str,
    image_placements: list[dict[str, Any]] | None,
    asset_funnel: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    from content.source import source_unit_writer

    unit = source_unit_writer.execution_source_unit_dir(execution_id, source_unit_id)
    if not unit.exists():
        return None
    try:
        meta = read_json(unit / "meta.json")
        index = read_json(unit / "assets/index.json")
        source_path = unit / "source.md"
        actual_body = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
        actual_media = sorted(
            str(row["sha256"])
            for row in index["assets"]
            if isinstance(row, Mapping)
        )
        if (
            not isinstance(meta, dict)
            or meta.get("sourceUnitId") != source_unit_id
            or meta.get("researchLane") != carrier
            or meta.get("url") != source_url
            or meta.get("sourceAttribution") != dict(source_attribution)
            or meta.get("publishMediaMode") != publish_media_mode
            or (
                image_placements is not None
                and meta.get("imagePlacements") != image_placements
            )
            or (
                asset_funnel is not None
                and meta.get("assetFunnel") != dict(asset_funnel)
            )
            or actual_body != body_sha256
            or actual_media != sorted(media_sha256)
        ):
            raise ValueError("existing source unit bytes differ from frozen candidate")
        return meta
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"existing frozen source unit is not replayable: {exc}") from exc
