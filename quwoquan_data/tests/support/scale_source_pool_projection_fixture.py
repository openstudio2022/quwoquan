"""scale source pool projection 合约测试共享 batch / projection helper。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1

由 test_scale_source_pool_homepage_article__catalog_projection_* 场景组
测试文件共享；从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from content.source.media_source_admission import MediaSourceAdmissionCommandWriter
from content.source.research.scale_source_pool_homepage_article import (
    project_scale_source_pool_homepage_article,
)

from support.scale_source_pool_catalog_fixture import (
    IDENTITY,
    _catalogs,
    _digest,
    _document_digest,
    _file_digest,
    _image_bytes,
    _source_attribution,
    _write_evidence_bytes,
    _write_evidence_file,
    _write_json,
)


def _source_ready_batch(
    root: Path,
    *,
    homepage_candidates: list[dict[str, object]],
    article_candidates: list[dict[str, object]],
    per_member_roots: bool = False,
) -> tuple[str, str, str]:
    coverage_ref = "coverage/projection.json"
    coverage_digest = "sha256:" + "f" * 64
    _write_json(
        root / coverage_ref,
        {"schema": "test.coverage_projection", "projectionDigest": coverage_digest},
    )
    seeds = []
    seeds_by_candidate_id: dict[str, dict[str, object]] = {}
    for carrier, candidates in (
        ("homepage", homepage_candidates),
        ("article", article_candidates),
    ):
        for candidate in candidates:
            source = candidate["primarySource"] if carrier == "homepage" else candidate
            assert isinstance(source, dict)
            entity_ref = str(candidate["entityRef"])
            candidate_name = entity_ref.rsplit("/", 1)[-1]
            coverage_key = {
                "coverageEntityIdentity": (
                    f"name_location:{candidate_name}|示例省|示例市|示例区"
                ),
                "coverageRecordDigest": _digest(
                    f"coverage:{carrier}:{entity_ref}:{source['sourceUrl']}"
                ),
                "entityRef": entity_ref,
                "carrier": carrier,
                "sourceUrl": source["sourceUrl"],
            }
            seed = {
                "seedOrigin": "current_coverage",
                "seedId": _document_digest(
                    {
                        "seedOrigin": "current_coverage",
                        "coverageKey": coverage_key,
                    }
                ),
                "coverageKey": coverage_key,
                "candidateName": entity_ref.rsplit("/", 1)[-1],
                "province": "示例省",
                "city": "杭州市",
                "district": "西湖区",
                "entityType": "/".join(entity_ref.split("/")[2:4]),
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
            }
            seeds.append(seed)
            seeds_by_candidate_id[str(candidate["candidateId"])] = seed
    stable_seed_selection = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": "projection-test-seeds",
        "counts": {
            "homepage": len(homepage_candidates),
            "article": len(article_candidates),
        },
        "seeds": seeds,
    }
    seed_selection = {
        **stable_seed_selection,
        "selectionDigest": _document_digest(stable_seed_selection),
    }
    seed_selection_ref = "seed-selection.json"
    _write_json(root / seed_selection_ref, seed_selection)
    seed_selection_binding = {
        "ref": seed_selection_ref,
        "digest": seed_selection["selectionDigest"],
        "fileSha256": _file_digest(root / seed_selection_ref),
    }
    body_values = {
        _digest(f"body:{candidate['candidateId']}"): f"body:{candidate['candidateId']}"
        for candidate in [*homepage_candidates, *article_candidates]
    }
    capsule_bindings: list[dict[str, object]] = []
    for carrier, candidates in (
        ("homepage", homepage_candidates),
        ("article", article_candidates),
    ):
        for candidate in candidates:
            candidate_id = str(candidate["candidateId"])
            member_root_ref = (
                f"members/{carrier}/{candidate_id}" if per_member_roots else "."
            )
            candidate_root = (
                root / member_root_ref if member_root_ref != "." else root
            )
            candidate_coverage_ref = (
                "shared/coverage.json" if per_member_roots else coverage_ref
            )
            if per_member_roots:
                _write_json(
                    candidate_root / candidate_coverage_ref,
                    {
                        "schema": "test.coverage_projection",
                        "projectionDigest": coverage_digest,
                    },
                )
                candidate_seed_ref = "shared/seed-selection.json"
                _write_json(candidate_root / candidate_seed_ref, seed_selection)
                candidate_seed_binding = {
                    "ref": candidate_seed_ref,
                    "digest": seed_selection["selectionDigest"],
                    "fileSha256": _file_digest(candidate_root / candidate_seed_ref),
                }
            else:
                candidate_seed_binding = seed_selection_binding
            if carrier == "homepage":
                primary = candidate["primarySource"]
                hero = candidate["hero"]
                assert isinstance(primary, dict) and isinstance(hero, dict)
                body_ref = str(primary["bodyEvidenceRef"])
                body_content = str(primary["bodyContentSha256"])
                media_rows = [{
                    "assetId": hero["assetId"],
                    "role": "hero",
                    "ref": hero["assetRef"],
                    "contentSha256": hero["contentSha256"],
                }]
            else:
                body_ref = str(candidate["bodyEvidenceRef"])
                body_content = str(candidate["bodyContentSha256"])
                media_rows = [
                    {
                        "assetId": row["assetId"],
                        "role": row["role"],
                        "ref": row["assetRef"],
                        "contentSha256": row["contentSha256"],
                    }
                    for row in candidate["assets"]
                    if isinstance(row, dict)
                ]
            body_value = body_values.get(body_content)
            if body_value is None:
                raise AssertionError(f"test body content preimage missing: {body_content}")
            body_file_sha = _write_evidence_file(
                candidate_root / body_ref,
                body_value,
            )
            materialized_media: list[dict[str, object]] = []
            for row in media_rows:
                ref = str(row["ref"])
                media_bytes = _image_bytes(f"{candidate_id}:{row['assetId']}")
                assert "sha256:" + hashlib.sha256(media_bytes).hexdigest() == row[
                    "contentSha256"
                ]
                materialized_media.append({
                    **row,
                    "fileSha256": _write_evidence_bytes(
                        candidate_root / ref, media_bytes
                    ),
                })
            raw_evidence_ref = f"raw/{carrier}/{candidate_id}.json"
            raw_evidence_sha = _write_evidence_file(
                candidate_root / raw_evidence_ref,
                json.dumps({"candidateId": candidate_id}, ensure_ascii=False),
            )
            evidence_bindings: list[dict[str, str]] = []
            for name in ("discovery", "acquisition", "rights", "quality"):
                ref = (
                    f"provenance/{name}.json"
                    if per_member_roots
                    else f"provenance/{candidate_id}-{name}.json"
                )
                evidence = (
                    {
                        "schema": (
                            "quwoquan_data."
                            "homepage_article_source_ready_acquisition_evidence"
                        ),
                        "id": candidate_id,
                        "sourceUnit": {
                            "rawEvidenceRef": raw_evidence_ref,
                            "rawEvidenceFileSha256": raw_evidence_sha,
                        },
                    }
                    if name == "discovery"
                    else {"schema": f"test.{name}", "id": candidate_id}
                )
                _write_json(candidate_root / ref, evidence)
                evidence_bindings.append({
                    "ref": ref,
                    "fileSha256": _file_digest(candidate_root / ref),
                })
            stable_capsule: dict[str, object] = {
                "schema": "quwoquan_data.homepage_article_source_ready_candidate",
                "carrier": carrier,
                **IDENTITY,
                "candidate": candidate,
                "materialization": {
                    "body": {
                        "ref": body_ref,
                        "contentSha256": body_content,
                        "fileSha256": body_file_sha,
                    },
                    "media": materialized_media,
                },
                "provenance": {
                    "coverageProjectionRef": candidate_coverage_ref,
                    "coverageProjectionDigest": coverage_digest,
                    "coverageProjectionFileSha256": _file_digest(
                        candidate_root / candidate_coverage_ref
                    ),
                    "seedSelectionRef": candidate_seed_binding["ref"],
                    "seedSelectionDigest": candidate_seed_binding["digest"],
                    "seedSelectionFileSha256": candidate_seed_binding["fileSha256"],
                    "seedOrigin": seeds_by_candidate_id[candidate_id]["seedOrigin"],
                    "seedId": seeds_by_candidate_id[candidate_id]["seedId"],
                    "coverageKey": seeds_by_candidate_id[candidate_id]["coverageKey"],
                    "discoveryEvidenceRef": evidence_bindings[0]["ref"],
                    "discoveryEvidenceFileSha256": evidence_bindings[0]["fileSha256"],
                    "acquisitionEvidenceRefs": [evidence_bindings[1]],
                    "rightsEvidenceRefs": [evidence_bindings[2]],
                    "qualityEvidenceRefs": [evidence_bindings[3]],
                },
            }
            capsule = {
                **stable_capsule,
                "capsuleDigest": _document_digest(stable_capsule),
            }
            capsule_ref = (
                "capsule.json"
                if per_member_roots
                else f"capsules/{carrier}/{candidate_id}.json"
            )
            _write_json(candidate_root / capsule_ref, capsule)
            capsule_bindings.append({
                "carrier": carrier,
                "candidateId": candidate_id,
                "evidenceRootRef": member_root_ref,
                "ref": capsule_ref,
                "digest": capsule["capsuleDigest"],
                "fileSha256": _file_digest(candidate_root / capsule_ref),
            })
    stable_batch: dict[str, object] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "sourceSetId": "projection-source-set",
        "targetScale": "M100",
        **IDENTITY,
        "createdAt": "2026-08-08T00:00:00Z",
        "coverageProjection": {
            "ref": coverage_ref,
            "digest": coverage_digest,
            "fileSha256": _file_digest(root / coverage_ref),
        },
        "seedSelection": seed_selection_binding,
        "candidateCapsules": capsule_bindings,
        "counts": {
            "homepage": len(homepage_candidates),
            "article": len(article_candidates),
        },
    }
    batch = {**stable_batch, "sourceSetDigest": _document_digest(stable_batch)}
    batch_ref = "batches/homepage-article.json"
    _write_json(root / batch_ref, batch)
    return batch_ref, str(batch["sourceSetDigest"]), _file_digest(root / batch_ref)


def _project(
    root: Path,
    *,
    per_member_roots: bool = False,
    **catalog_kwargs: object,
) -> dict[str, object]:
    homepage, article, homepage_path, article_path = _catalogs(
        root, **catalog_kwargs
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
        per_member_roots=per_member_roots,
    )
    return project_scale_source_pool_homepage_article(
        evidence_root=root,
        homepage_catalog_ref=homepage_path.relative_to(root).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(root).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )


def _media_probe() -> dict[str, object]:
    return {
        "width": 1920,
        "height": 1080,
        "frameCount": 240,
        "framesPerSecond": 30.0,
        "durationMs": 8000,
        "codec": "h264",
        "hasAudio": False,
        "sampleCount": 12,
        "distinctFrameCount": 12,
        "movingTransitionCount": 11,
        "meanTransitionDelta": 0.4,
        "playable": True,
        "motionVideo": True,
        "staticImageSequence": False,
        "premiumPlayableEligible": True,
    }


def _media_popularity(
    provider: str, index: int, *, comparison_count: int = 18
) -> dict[str, object]:
    """One video's popularity signals inside a bucket of ``comparison_count`` peers.

    The percentile is a position within the bucket it declares, so the bucket size
    has to be the caller's real candidate count: a fixture minting 100 videos against
    a hard-coded bucket of 18 emits percentiles above 1 and the receipt is refused.
    """

    return {
        "playCount": 10000 + index,
        "likeCount": 500 + index,
        "commentCount": 40 + index,
        "shareCount": 30 + index,
        "favoriteCount": 200 + index,
        "observedAt": "2026-08-08T00:00:00Z",
        "provider": provider,
        "topic": "旅行",
        "timeBucket": "2026-W32",
        "popularityScore": 10000 + index,
        "popularityPercentile": round(index / max(comparison_count - 1, 1), 6),
        "rankingEligible": True,
        "ineligibleReason": "",
        "comparisonCandidateCount": comparison_count,
    }


def _media_admission_row(
    *,
    evidence_root: Path,
    carrier: str,
    index: int,
    provider: str,
    candidate_id: str | None = None,
    object_ref: str | None = None,
    identity: Mapping[str, str] | None = None,
    comparison_count: int = 18,
) -> dict[str, object]:
    """Write one media candidate's admission evidence and return the projected row.

    ``candidate_id``/``object_ref`` are overridable because the pool revalidates the
    receipt against the candidate that cites it: `objectRef`, `assetKind`,
    `contentSha256`, `rightsStatus` and `distributionDecision` must agree. A caller
    whose candidates carry a different object shape has to mint the receipt under
    that same shape, or the projection drifts by construction.

    ``identity`` is overridable for the same reason one level up: the receipt freezes
    the source identity it was minted under, and a caller whose pool derives its own
    revision at runtime would otherwise cite receipts frozen under this module's
    constants — an identity drift that only surfaces during deep pool validation.
    """

    identity = dict(identity or IDENTITY)
    candidate_id = candidate_id or f"{carrier}-{index:05d}"
    asset_id = f"{carrier}-asset-{index:05d}"
    object_ref = object_ref or f"posts/{carrier}/{candidate_id}"
    entity_id = candidate_id
    entity_ref = f"/entity/地点/景区/{entity_id}"
    source_url = f"https://source.example/{carrier}/{index}"
    asset_ref = f"media/{carrier}/{asset_id}.{'jpg' if carrier == 'image' else 'mp4'}"
    content_sha256 = _write_evidence_bytes(
        evidence_root / asset_ref,
        (f"real-{carrier}-asset-{index}" * 300).encode("utf-8"),
    )
    attribution = _source_attribution(
        platform=provider,
        source_url=source_url,
        asset_url=f"https://source.example/{carrier}/{index}/asset",
    )
    common = {
        "assetId": asset_id,
        "entityId": entity_id,
        "observedEntityId": entity_id,
        "contentSha256": content_sha256,
    }
    probe = _media_probe() if carrier == "video" else None
    popularity = (
        _media_popularity(provider, index, comparison_count=comparison_count)
        if carrier == "video"
        else None
    )
    acquisition_asset = {
        **common,
        "provider": provider,
        "platform": provider,
        "sourceUrl": source_url,
        "creator": f"creator-{carrier}-{index}",
        "capturedAt": "2026-08-08T00:00:00Z",
        "assetRef": asset_ref,
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "sourceAttribution": attribution,
        **(
            {"width": 1600, "height": 1200}
            if carrier == "image"
            else {
                "sourceKind": "tourism_video_site",
                "mediaProbe": probe,
                "popularitySignals": popularity,
            }
        ),
    }
    evidence_dir = Path("media-admission") / carrier / f"{index:05d}"
    evidence_documents = {
        "catalog": {
            "schema": "quwoquan_data.fixture_media_catalog",
            **identity,
            "candidates": [{**common, "provider": provider}],
        },
        "acquisition": {
            "schema": "quwoquan_data.fixture_media_acquisition",
            **identity,
            "assets": [acquisition_asset],
        },
        "media_probe": {
            "schema": "quwoquan_data.fixture_media_probe",
            **common,
            **(
                {"width": 1600, "height": 1200}
                if carrier == "image"
                else {"mediaProbe": probe, "popularitySignals": popularity}
            ),
        },
        "rights_attribution": {
            "schema": "quwoquan_data.fixture_media_rights_attribution",
            **common,
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "sourceAttribution": attribution,
        },
        "source_semantic_review": {
            "schema": "quwoquan_data.fixture_media_source_semantic_review",
            **common,
            "status": "passed",
            "entityMatch": "matched",
            "qualityStatus": "passed",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "findings": [],
        },
    }
    evidence_refs: dict[str, str] = {}
    for role, document in evidence_documents.items():
        ref = (evidence_dir / f"{role}.json").as_posix()
        _write_json(evidence_root / ref, document)
        evidence_refs[role] = ref
    receipt, receipt_ref = MediaSourceAdmissionCommandWriter(evidence_root).write(
        asset_kind=carrier,
        asset_id=asset_id,
        object_ref=object_ref,
        source_revision=identity["sourceRevision"],
        source_digest=identity["sourceDigest"],
        entity_catalog_digest=identity["entityCatalogDigest"],
        evidence_refs=evidence_refs,
        recorded_at="2026-08-08T00:00:00Z",
    )
    snapshot = receipt["assetSnapshot"]
    return {
        "candidateId": candidate_id,
        "carrier": carrier,
        "objectRef": object_ref,
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **identity,
        "sourceAdmissionRef": receipt_ref,
        "sourceAdmissionDigest": receipt["receiptDigest"],
        "sourceAttribution": snapshot["sourceAttribution"],
        "provider": provider,
        "contentSha256": snapshot["contentSha256"],
        "acquisitionStatus": "acquired",
        "rightsStatus": snapshot["rightsStatus"],
        "distributionDecision": snapshot["distributionDecision"],
        "qualityStatus": "passed",
        "generated": False,
        "videoReadiness": (
            {
                "playable": True,
                "motion": True,
                "premiumEligible": True,
                **{
                    field: popularity[field]
                    for field in (
                        "playCount", "likeCount", "commentCount", "shareCount",
                        "favoriteCount", "observedAt", "popularityPercentile",
                    )
                },
                "comparisonBucket": {
                    "provider": provider,
                    "topic": "旅行",
                    "timeBucket": "2026-W32",
                    "candidateCount": comparison_count,
                },
            }
            if carrier == "video"
            else None
        ),
    }


def _clone_row(
    template: dict[str, object],
    *,
    carrier: str,
    index: int,
    provider: str,
    evidence_root: Path | None = None,
) -> dict[str, object]:
    if carrier in {"image", "video"}:
        if evidence_root is None:
            raise ValueError("media clone requires evidence_root")
        return _media_admission_row(
            evidence_root=evidence_root,
            carrier=carrier,
            index=index,
            provider=provider,
        )
    row = copy.deepcopy(template)
    entity_ref = f"/entity/地点/景区/{carrier}-{index:05d}"
    row.update(
        {
            "candidateId": f"{carrier}-{index:05d}",
            "carrier": carrier,
            "objectRef": f"{'entities' if carrier == 'homepage' else f'posts/{carrier}'}/{carrier}-{index:05d}",
            "entityRef": entity_ref,
            "observedEntityRef": entity_ref,
            "provider": provider,
            "contentSha256": _digest(f"projected:{carrier}:{index}"),
            "playabilityRef": None,
            "playabilityDigest": None,
            "playabilityFileSha256": None,
            "videoReadiness": None,
        }
    )
    return row
