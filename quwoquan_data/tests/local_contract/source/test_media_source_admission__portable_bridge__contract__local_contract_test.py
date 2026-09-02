from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

import content.source.research.scale_source_pool_image_video as media_projection
from content.source.host_source_review import (
    prepare_host_source_review_request,
    record_host_source_review_result,
)
from content.source.media_source_admission import (
    MEDIA_SOURCE_ADMISSION_INVALID,
    MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED,
    MediaSourceAdmissionCommandWriter,
    MediaSourceAdmissionError,
    MediaSourceAdmissionQuery,
)
from content.source.research.scale_source_pool import build_scale_source_pool_plan
from content.source.research.scale_source_pool_image_video import (
    project_scale_source_pool_image_video,
)


IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}
REVIEW_IDENTITY = {
    **IDENTITY,
    "executionBundleDigest": "sha256:" + "d" * 64,
    "handoffDigest": "sha256:" + "e" * 64,
}
ENTITY_CATALOG_REF = "quwoquan_data/reference/travel/entities/china"


def _digest_bytes(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write_json(root: Path, ref: str, value: object) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_attribution(kind: str) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "source-author",
        "platform": f"{kind}-provider",
        "sourcePostUrl": f"https://source.example/{kind}/post",
        "originalAssetUrl": f"https://source.example/{kind}/asset",
        "attributionText": f"source-author / {kind}-provider",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": None,
        "termsUrl": f"https://source.example/{kind}/terms",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-20T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "derivedModifications": [],
    }


def _video_probe() -> dict[str, object]:
    return {
        "width": 3840,
        "height": 2160,
        "frameCount": 240,
        "framesPerSecond": 30.0,
        "durationMs": 8000,
        "codec": "h264",
        "hasAudio": True,
        "sampleCount": 12,
        "distinctFrameCount": 12,
        "movingTransitionCount": 11,
        "meanTransitionDelta": 0.4,
        "playable": True,
        "motionVideo": True,
        "staticImageSequence": False,
        "premiumPlayableEligible": True,
    }


def _popularity() -> dict[str, object]:
    return {
        "playCount": 100,
        "likeCount": 20,
        "commentCount": 3,
        "shareCount": 2,
        "favoriteCount": 5,
        "observedAt": "2026-08-20T00:00:00Z",
        "provider": "video-provider",
        "topic": "entity-travel",
        "timeBucket": "2026-W34",
        "popularityScore": 400,
        "popularityPercentile": 0.8,
        "rankingEligible": True,
        "ineligibleReason": "",
        "comparisonCandidateCount": 2,
    }


def _portable_evidence(
    root: Path,
    *,
    kind: str,
    entity_match: str = "matched",
) -> tuple[str, dict[str, str]]:
    extension = "jpg" if kind == "image" else "mp4"
    asset_id = f"{kind}-asset-1"
    body = (f"real-{kind}-asset-bytes" * 300).encode("utf-8")
    content_sha256 = _digest_bytes(body)
    asset_ref = f"cas/{asset_id}.{extension}"
    asset_path = root / asset_ref
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(body)

    catalog_ref = f"catalog/{kind}.json"
    acquisition_ref = f"acquisition/{kind}.json"
    probe_ref = f"probe/{kind}.json"
    rights_ref = f"rights/{kind}.json"
    common = {
        "assetId": asset_id,
        "entityId": "entity-1",
        "observedEntityId": "entity-1",
        "contentSha256": content_sha256,
    }
    catalog = {
        "schema": "quwoquan_data.fixture_media_catalog",
        **IDENTITY,
        "candidates": [
            {
                **common,
                "provider": f"{kind}-provider",
                "sourcePageUrl": f"https://source.example/{kind}/post",
                "creator": "source-author",
            }
        ],
    }
    acquisition_asset = {
        **common,
        "provider": f"{kind}-provider",
        "platform": f"{kind}-provider",
        "sourceUrl": f"https://source.example/{kind}/post",
        "creator": "source-author",
        "capturedAt": "2026-08-20T00:00:00Z",
        "assetRef": asset_ref,
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "sourceAttribution": _source_attribution(kind),
        **(
            {"width": 1600, "height": 1200}
            if kind == "image"
            else {
                "mediaProbe": _video_probe(),
                "popularitySignals": _popularity(),
                "sourceKind": "tourism_video_site",
            }
        ),
    }
    acquisition = {
        "schema": "quwoquan_data.fixture_media_acquisition",
        **IDENTITY,
        "assets": [acquisition_asset],
    }
    probe = {
        "schema": "quwoquan_data.fixture_media_probe",
        **common,
        **(
            {"width": 1600, "height": 1200}
            if kind == "image"
            else {"mediaProbe": _video_probe(), "popularitySignals": _popularity()}
        ),
    }
    rights = {
        "schema": "quwoquan_data.fixture_media_rights_attribution",
        **common,
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "sourceAttribution": _source_attribution(kind),
    }
    safety_scan = {
        "schema": "quwoquan_data.fixture_media_safety_scan",
        **common,
        "watermarkDetected": False,
    }
    safety_ref = f"safety/{kind}.json"
    for ref, value in (
        (catalog_ref, catalog),
        (acquisition_ref, acquisition),
        (probe_ref, probe),
        (rights_ref, rights),
        (safety_ref, safety_scan),
    ):
        _write_json(root, ref, value)
    review_ref = _record_host_review(
        root,
        kind=kind,
        asset_id=asset_id,
        asset_ref=asset_ref,
        content_sha256=content_sha256,
        entity_match=entity_match,
        evidence_refs={
            "acquisition": acquisition_ref,
            "media_probe": probe_ref,
            "safety_scan": safety_ref,
            "rights_attribution": rights_ref,
        },
    )
    return asset_id, {
        "catalog": catalog_ref,
        "acquisition": acquisition_ref,
        "media_probe": probe_ref,
        "rights_attribution": rights_ref,
        "source_semantic_review": review_ref,
    }


def _record_host_review(
    root: Path,
    *,
    kind: str,
    asset_id: str,
    asset_ref: str,
    content_sha256: str,
    entity_match: str,
    evidence_refs: dict[str, str],
) -> str:
    request, request_ref = prepare_host_source_review_request(
        evidence_root=root,
        source_identity=REVIEW_IDENTITY,
        asset_kind=kind,
        asset_id=asset_id,
        asset_ref=asset_ref,
        content_sha256=content_sha256,
        entity_id="entity-1",
        observed_entity_id="entity-1",
        content_ref="entity:entity-1",
        evidence_refs=evidence_refs,
    )
    passed = entity_match == "matched"
    _result, result_ref = record_host_source_review_result(
        evidence_root=root,
        result_input={
            "schema": "quwoquan_data.host_source_review_result_input",
            "requestRef": request_ref,
            "requestDigest": request["requestDigest"],
            "actor": {
                "host": "cursor",
                "sessionId": "portable-bridge-session",
                "modelFamily": "gpt-5",
                "auditRunId": "portable-bridge-audit-001",
            },
            "reviewedAt": "2026-08-20T00:00:30Z",
            "verdict": {
                "status": "passed" if passed else "blocked",
                "entityMatch": entity_match,
                "qualityStatus": "passed",
                "privacyRisk": "none",
                "minorRisk": "none",
                "maliciousMediaRisk": "none",
                "watermarkStatus": "absent",
                "findings": [] if passed else ["entity mismatch"],
            },
        },
    )
    return result_ref


def _admit(
    root: Path,
    *,
    kind: str,
    entity_match: str = "matched",
) -> tuple[dict[str, object], str, dict[str, str]]:
    asset_id, refs = _portable_evidence(
        root,
        kind=kind,
        entity_match=entity_match,
    )
    receipt, receipt_ref = MediaSourceAdmissionCommandWriter(root).write(
        asset_kind=kind,
        asset_id=asset_id,
        object_ref=f"posts/{kind}/{asset_id}",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        evidence_refs=refs,
        recorded_at="2026-08-20T00:01:00Z",
    )
    return receipt, receipt_ref, refs


@pytest.fixture(autouse=True)
def _entity_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_projection,
        "load_entity_bindings",
        lambda _path: (
            ENTITY_CATALOG_REF,
            IDENTITY["entityCatalogDigest"],
            {
                "entity-1": {
                    "entityId": "entity-1",
                    "entityType": "地点/景区",
                    "entityAliases": ["entity-1"],
                }
            },
        ),
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t1
def test_source_admission_is_create_once_and_revalidates_one_portable_root(
    tmp_path: Path,
) -> None:
    receipt, receipt_ref, _refs = _admit(tmp_path, kind="image")
    replay, replay_ref, _ = _admit(tmp_path, kind="image")

    assert replay == receipt
    assert replay_ref == receipt_ref
    assert receipt["admissionDecision"] == "accepted"
    assert receipt["evidenceRootDigest"].startswith("sha256:")
    assert {row["role"] for row in receipt["evidenceBindings"]} == {
        "catalog",
        "acquisition",
        "media_probe",
        "rights_attribution",
        "source_semantic_review",
    }
    result = MediaSourceAdmissionQuery(tmp_path).read(receipt_ref)
    assert result["status"] == "accepted"
    assert result["receiptDigest"] == receipt["receiptDigest"]


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t1
def test_source_admission_rejects_root_drift_absolute_parent_and_symlink_refs(
    tmp_path: Path,
) -> None:
    _receipt, receipt_ref, refs = _admit(tmp_path, kind="image")
    rights_path = tmp_path / refs["rights_attribution"]
    rights_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(MediaSourceAdmissionError) as drift:
        MediaSourceAdmissionQuery(tmp_path).read(receipt_ref)
    assert drift.value.code == MEDIA_SOURCE_ADMISSION_INVALID

    for unsafe in ("../rights.json", str((tmp_path / "rights.json").resolve())):
        _asset_id, unsafe_refs = _portable_evidence(tmp_path / unsafe.replace("/", "_"), kind="image")
        unsafe_refs["rights_attribution"] = unsafe
        with pytest.raises(MediaSourceAdmissionError) as blocked:
            MediaSourceAdmissionCommandWriter(
                tmp_path / unsafe.replace("/", "_")
            ).write(
                asset_kind="image",
                asset_id="image-asset-1",
                object_ref="posts/image/image-asset-1",
                source_revision=IDENTITY["sourceRevision"],
                source_digest=IDENTITY["sourceDigest"],
                entity_catalog_digest=IDENTITY["entityCatalogDigest"],
                evidence_refs=unsafe_refs,
                recorded_at="2026-08-20T00:01:00Z",
            )
        assert blocked.value.code == MEDIA_SOURCE_ADMISSION_INVALID

    symlink_root = tmp_path / "symlink-root"
    asset_id, symlink_refs = _portable_evidence(symlink_root, kind="image")
    target = symlink_root / symlink_refs["rights_attribution"]
    link = symlink_root / "rights/link.json"
    link.symlink_to(target)
    symlink_refs["rights_attribution"] = "rights/link.json"
    with pytest.raises(MediaSourceAdmissionError) as symlinked:
        MediaSourceAdmissionCommandWriter(symlink_root).write(
            asset_kind="image",
            asset_id=asset_id,
            object_ref=f"posts/image/{asset_id}",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            evidence_refs=symlink_refs,
            recorded_at="2026-08-20T00:01:00Z",
        )
    assert symlinked.value.code == MEDIA_SOURCE_ADMISSION_INVALID


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t2
def test_media_projection_accepts_only_source_admission_and_has_no_review_fallback(
    tmp_path: Path,
) -> None:
    image_receipt, image_ref, _ = _admit(tmp_path, kind="image")
    video_receipt, video_ref, _ = _admit(tmp_path, kind="video")
    projected = project_scale_source_pool_image_video(
        evidence_root=tmp_path,
        target_scale="WORKLOAD",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        entity_catalog_ref=ENTITY_CATALOG_REF,
        image_source_admission_refs=[image_ref],
        video_source_admission_refs=[video_ref],
    )

    assert [row["carrier"] for row in projected["candidates"]] == ["image", "video"]
    by_carrier = {row["carrier"]: row for row in projected["candidates"]}
    assert by_carrier["image"]["sourceAdmissionDigest"] == image_receipt["receiptDigest"]
    assert by_carrier["video"]["sourceAdmissionDigest"] == video_receipt["receiptDigest"]
    retired = {
        "sourceUnitRef",
        "acquisitionRef",
        "rightsRef",
        "qualityRef",
        "playabilityRef",
        "independentAssetReviewRef",
    }
    assert all(not retired.intersection(row) for row in projected["candidates"])
    parameters = inspect.signature(project_scale_source_pool_image_video).parameters
    assert "image_review_refs" not in parameters
    assert "video_review_refs" not in parameters

    plan = build_scale_source_pool_plan(
        pool_id="media-source-admission-pool",
        target_scale="WORKLOAD",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        created_at="2026-08-20T00:02:00Z",
        candidates=projected["candidates"],
        workload_targets={"image": 1, "video": 1},
    )
    assert plan["candidates"] == projected["candidates"]


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t4
def test_video_entity_mismatch_remains_typed_source_safety_blocker(
    tmp_path: Path,
) -> None:
    receipt, receipt_ref, _ = _admit(
        tmp_path,
        kind="video",
        entity_match="mismatch",
    )
    assert receipt["admissionDecision"] == "blocked"
    result = MediaSourceAdmissionQuery(tmp_path).read(receipt_ref)
    assert result["status"] == "blocked"
    with pytest.raises(MediaSourceAdmissionError) as blocked:
        MediaSourceAdmissionQuery(tmp_path).require_accepted(receipt_ref)
    assert blocked.value.code == MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t5
def test_source_admission_same_identity_different_bytes_collides_before_write(
    tmp_path: Path,
) -> None:
    receipt, _receipt_ref, refs = _admit(tmp_path, kind="image")
    path = tmp_path / refs["source_semantic_review"]
    review = json.loads(path.read_text(encoding="utf-8"))
    review["findings"] = ["different source judgment bytes"]
    _write_json(tmp_path, refs["source_semantic_review"], review)

    with pytest.raises(MediaSourceAdmissionError) as collision:
        MediaSourceAdmissionCommandWriter(tmp_path).write(
            asset_kind="image",
            asset_id=str(receipt["assetSnapshot"]["assetId"]),
            object_ref=str(receipt["objectRef"]),
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            evidence_refs=refs,
            recorded_at="2026-08-20T00:01:00Z",
        )
    assert collision.value.code == MEDIA_SOURCE_ADMISSION_INVALID
