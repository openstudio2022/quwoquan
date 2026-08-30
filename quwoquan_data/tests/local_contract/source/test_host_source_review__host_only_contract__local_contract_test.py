from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from content.source.host_source_review import (
    HOST_SOURCE_REVIEW_CONFLICT,
    HOST_SOURCE_REVIEW_INVALID,
    HostSourceReviewError,
    HostSourceReviewPending,
    prepare_host_source_review_request,
    read_host_source_review_result,
    record_host_source_review_result,
)
from content.source.media_source_admission import (
    MEDIA_SOURCE_ADMISSION_INVALID,
    MediaSourceAdmissionCommandWriter,
    MediaSourceAdmissionError,
    MediaSourceAdmissionQuery,
    canonical_digest,
)
from verify.legacy_runtime_entries import scan_live_python_import_graph

IDENTITY = {
    "sourceRevision": "sha256:" + "1" * 64,
    "sourceDigest": "sha256:" + "2" * 64,
    "entityCatalogDigest": "sha256:" + "3" * 64,
    "executionBundleDigest": "sha256:" + "4" * 64,
    "handoffDigest": "sha256:" + "5" * 64,
}


def _sha(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write(root: Path, ref: str, value: object) -> str:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    return ref


def _physical(root: Path, *, kind: str = "video") -> dict[str, object]:
    asset_id = f"{kind}-host-review-1"
    body = (f"physical-{kind}-bytes" * 400).encode()
    asset_ref = f"cas/{asset_id}.{'mp4' if kind == 'video' else 'jpg'}"
    asset = root / asset_ref
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(body)
    content_sha = _sha(body)
    common = {"assetId": asset_id, "entityId": "entity-1", "contentSha256": content_sha}
    acquisition = {
        "schema": "fixture.acquisition",
        **common,
        "observedEntityId": "entity-1",
        "assetRef": asset_ref,
        "provider": "fixture-provider",
        "platform": "fixture-platform",
        "sourceUrl": "https://example.test/source",
        "creator": "creator",
        "capturedAt": "2026-08-31T00:00:00Z",
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        **(
            {
                "sourceKind": "tourism_video_site",
                "mediaProbe": {
                    "width": 1920, "height": 1080, "frameCount": 90,
                    "framesPerSecond": 30.0, "durationMs": 3000, "codec": "h264",
                    "hasAudio": False, "sampleCount": 8, "distinctFrameCount": 8,
                    "movingTransitionCount": 7, "meanTransitionDelta": 0.4,
                    "motionVideo": True, "staticImageSequence": False,
                    "playable": True, "premiumPlayableEligible": True,
                },
                "popularitySignals": {
                    "playCount": 10, "likeCount": 2, "commentCount": 0,
                    "shareCount": 0, "favoriteCount": 1,
                    "observedAt": "2026-08-31T00:00:00Z", "provider": "fixture-provider",
                    "topic": "entity-1", "timeBucket": "2026-W35",
                    "popularityScore": 10, "popularityPercentile": 0.5,
                    "rankingEligible": True, "ineligibleReason": "",
                    "comparisonCandidateCount": 2,
                },
            }
            if kind == "video"
            else {
                "width": 1600, "height": 1200,
                "sourceAttribution": {
                    "isOriginal": False, "originalCreatorName": "creator",
                    "platform": "fixture-platform", "sourcePostUrl": "https://example.test/source",
                    "originalAssetUrl": "https://example.test/asset", "attributionText": "creator",
                    "rightsBasis": "research", "commercialAuthorizationStatus": "unverified",
                    "publicationAdmission": "research_release", "authorizationProofUrl": None,
                    "termsUrl": "https://example.test/terms", "riskAcceptanceId": None,
                    "watermarkStatus": "absent", "audioRightsStatus": "no_audio",
                    "modelReleaseStatus": "not_required", "propertyReleaseStatus": "not_required",
                    "collectedAt": "2026-08-31T00:00:00Z", "takedownPolicy": "remove",
                    "derivedModifications": [],
                },
            }
        ),
    }
    probe = {
        "schema": "fixture.probe", **common,
        **(
            {"mediaProbe": acquisition["mediaProbe"], "popularitySignals": acquisition["popularitySignals"]}
            if kind == "video" else {"width": 1600, "height": 1200}
        ),
    }
    scan = {"schema": "fixture.safety", **common, "watermarkDetected": False}
    rights = {
        "schema": "fixture.rights", **common, "rightsStatus": "unverified",
        "authorizationRequired": True, "distributionDecision": "research_allowed",
    }
    if kind == "image":
        rights["sourceAttribution"] = acquisition["sourceAttribution"]
    refs = {
        "acquisition": _write(root, "evidence/acquisition.json", acquisition),
        "media_probe": _write(root, "evidence/probe.json", probe),
        "safety_scan": _write(root, "evidence/safety.json", scan),
        "rights_attribution": _write(root, "evidence/rights.json", rights),
    }
    return {
        "assetId": asset_id, "assetRef": asset_ref, "contentSha256": content_sha,
        "refs": refs, "acquisition": acquisition, "probe": probe, "rights": rights,
    }


def _prepare(root: Path, *, kind: str = "video") -> tuple[dict, str, dict]:
    physical = _physical(root, kind=kind)
    request, ref = prepare_host_source_review_request(
        evidence_root=root, source_identity=IDENTITY, asset_kind=kind,
        asset_id=physical["assetId"], asset_ref=physical["assetRef"],
        content_sha256=physical["contentSha256"], entity_id="entity-1",
        observed_entity_id="entity-1", content_ref="entity:entity-1",
        evidence_refs=physical["refs"],
    )
    return request, ref, physical


def _input(request: dict, request_ref: str, *, passed: bool = True) -> dict:
    return {
        "schema": "quwoquan_data.host_source_review_result_input",
        "contractVersion": "host-source-review/v1",
        "requestRef": request_ref,
        "requestDigest": request["requestDigest"],
        "actor": {
            "host": "cursor", "sessionId": "cursor-session-current",
            "modelFamily": "gpt-5", "auditRunId": "source-audit-run-001",
            "runtimeAudit": {"provider": "opaque-host-provider", "model": "opaque-host-model"},
        },
        "reviewedAt": "2026-08-31T00:01:00Z",
        "verdict": {
            "status": "passed" if passed else "blocked",
            "entityMatch": "matched" if passed else "mismatch",
            "qualityStatus": "passed",
            "privacyRisk": "none", "minorRisk": "none",
            "maliciousMediaRisk": "none", "watermarkStatus": "absent",
            "findings": [] if passed else ["not the requested entity"],
        },
    }


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t1
def test_prepare_is_deterministic_and_has_no_semantic_or_runtime_selection(tmp_path: Path) -> None:
    first, first_ref, _ = _prepare(tmp_path)
    second, second_ref = prepare_host_source_review_request(
        evidence_root=tmp_path, source_identity=IDENTITY, asset_kind="video",
        asset_id=first["assetBinding"]["assetId"], asset_ref=first["assetBinding"]["assetRef"],
        content_sha256=first["assetBinding"]["contentSha256"], entity_id="entity-1",
        observed_entity_id="entity-1", content_ref="entity:entity-1",
        evidence_refs={row["role"]: row["ref"] for row in first["evidenceBindings"]},
    )
    assert second == first and second_ref == first_ref
    serialized = json.dumps(first, sort_keys=True)
    for forbidden in ("provider", "model", "cursor_sdk", "codex_sdk", "verdict", "status"):
        assert forbidden not in serialized
    with pytest.raises(HostSourceReviewPending) as pending:
        read_host_source_review_result(evidence_root=tmp_path, request_ref=first_ref)
    assert pending.value.next_action == "record_host_source_review_result"
    assert pending.value.reentry_ref == first["requestDigest"]


@pytest.mark.parametrize("mutation", ["missing_actor", "request_digest", "asset_drift", "evidence_drift"])
def test_record_fails_closed_for_missing_actor_request_or_exact_evidence_drift(
    tmp_path: Path, mutation: str,
) -> None:
    request, request_ref, physical = _prepare(tmp_path)
    payload = _input(request, request_ref)
    if mutation == "missing_actor":
        payload.pop("actor")
    elif mutation == "request_digest":
        payload["requestDigest"] = "sha256:" + "9" * 64
    elif mutation == "asset_drift":
        (tmp_path / physical["assetRef"]).write_bytes(b"drift")
    else:
        (tmp_path / physical["refs"]["rights_attribution"]).write_text("{}\n")
    with pytest.raises(HostSourceReviewError) as captured:
        record_host_source_review_result(evidence_root=tmp_path, result_input=payload)
    assert captured.value.code == HOST_SOURCE_REVIEW_INVALID


def test_record_validates_pass_and_blocked_and_is_create_once(tmp_path: Path) -> None:
    request, request_ref, _ = _prepare(tmp_path)
    passed, result_ref = record_host_source_review_result(
        evidence_root=tmp_path, result_input=_input(request, request_ref)
    )
    replay, replay_ref = record_host_source_review_result(
        evidence_root=tmp_path, result_input=_input(request, request_ref)
    )
    assert replay == passed and replay_ref == result_ref
    assert passed["verdict"]["status"] == "passed"
    changed = _input(request, request_ref, passed=False)
    with pytest.raises(HostSourceReviewError) as collision:
        record_host_source_review_result(evidence_root=tmp_path, result_input=changed)
    assert collision.value.code == HOST_SOURCE_REVIEW_CONFLICT

    other_root = tmp_path / "blocked"
    blocked_request, blocked_ref, _ = _prepare(other_root)
    blocked, _ = record_host_source_review_result(
        evidence_root=other_root,
        result_input=_input(blocked_request, blocked_ref, passed=False),
    )
    assert blocked["verdict"]["status"] == "blocked"


def _admission_documents(root: Path, physical: dict, result_ref: str) -> dict[str, str]:
    acquisition = dict(physical["acquisition"])
    acquisition.update({
        "sourceRevision": IDENTITY["sourceRevision"],
        "sourceDigest": IDENTITY["sourceDigest"],
        "entityCatalogDigest": IDENTITY["entityCatalogDigest"],
    })
    refs = {
        "catalog": _write(root, "admission/catalog.json", {
            "schema": "fixture.catalog",
            "sourceRevision": IDENTITY["sourceRevision"],
            "sourceDigest": IDENTITY["sourceDigest"],
            "entityCatalogDigest": IDENTITY["entityCatalogDigest"],
            "candidates": [{
                "assetId": physical["assetId"], "entityId": "entity-1",
                "contentSha256": physical["contentSha256"],
            }],
        }),
        "acquisition": _write(root, "admission/acquisition.json", {
            "schema": "fixture.admission-acquisition", "assets": [acquisition],
            "sourceRevision": IDENTITY["sourceRevision"],
            "sourceDigest": IDENTITY["sourceDigest"],
            "entityCatalogDigest": IDENTITY["entityCatalogDigest"],
        }),
        "media_probe": physical["refs"]["media_probe"],
        "rights_attribution": physical["refs"]["rights_attribution"],
        "source_semantic_review": result_ref,
    }
    return refs


def test_legacy_unversioned_admission_remains_read_only_but_cannot_be_rewritten(
    tmp_path: Path,
) -> None:
    request, request_ref, physical = _prepare(tmp_path, kind="image")
    _result, result_ref = record_host_source_review_result(
        evidence_root=tmp_path, result_input=_input(request, request_ref)
    )
    refs = _admission_documents(tmp_path, physical, result_ref)
    receipt, receipt_ref = MediaSourceAdmissionCommandWriter(tmp_path).write(
        asset_kind="image", asset_id=physical["assetId"],
        object_ref=f"posts/image/{physical['assetId']}",
        source_revision=IDENTITY["sourceRevision"], source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"], evidence_refs=refs,
        recorded_at="2026-08-31T00:02:00Z",
    )
    legacy = copy.deepcopy(receipt)
    legacy.pop("sourceReviewContractVersion")
    legacy["sourceReview"] = dict(legacy["verdict"]) if "verdict" in legacy else {
        key: legacy["sourceReview"][key] for key in (
            "status", "entityMatch", "qualityStatus", "privacyRisk", "minorRisk",
            "maliciousMediaRisk", "watermarkStatus", "findings",
        )
    }
    stable = {key: value for key, value in legacy.items() if key != "receiptDigest"}
    legacy["receiptDigest"] = canonical_digest(stable)
    path = tmp_path / receipt_ref
    path.write_text(json.dumps(legacy, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    historical = MediaSourceAdmissionQuery(tmp_path).read(receipt_ref)
    assert historical["contractVersion"] == "legacy-v0-read-only"
    with pytest.raises(MediaSourceAdmissionError) as ineligible:
        MediaSourceAdmissionQuery(tmp_path).require_accepted(receipt_ref)
    assert ineligible.value.code == MEDIA_SOURCE_ADMISSION_INVALID
    with pytest.raises(MediaSourceAdmissionError) as collision:
        MediaSourceAdmissionCommandWriter(tmp_path).write(
            asset_kind="image", asset_id=physical["assetId"],
            object_ref=f"posts/image/{physical['assetId']}",
            source_revision=IDENTITY["sourceRevision"], source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"], evidence_refs=refs,
            recorded_at="2026-08-31T00:02:00Z",
        )
    assert collision.value.code == MEDIA_SOURCE_ADMISSION_INVALID


def test_new_admission_accepts_only_validated_host_result_and_rejects_legacy_sdk(tmp_path: Path) -> None:
    request, request_ref, physical = _prepare(tmp_path, kind="video")
    result, result_ref = record_host_source_review_result(
        evidence_root=tmp_path, result_input=_input(request, request_ref)
    )
    refs = _admission_documents(tmp_path, physical, result_ref)
    receipt, _ = MediaSourceAdmissionCommandWriter(tmp_path).write(
        asset_kind="video", asset_id=physical["assetId"],
        object_ref=f"posts/video/{physical['assetId']}",
        source_revision=IDENTITY["sourceRevision"], source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"], evidence_refs=refs,
        recorded_at="2026-08-31T00:02:00Z",
    )
    assert receipt["admissionDecision"] == "accepted"
    assert receipt["sourceReviewContractVersion"] == "host-source-review/v1"
    assert receipt["sourceReview"]["resultDigest"] == result["resultDigest"]
    assert "provider" not in receipt["sourceReview"]
    assert "model" not in receipt["sourceReview"]

    legacy_root = tmp_path / "legacy"
    _request, _request_ref, legacy_physical = _prepare(legacy_root, kind="video")
    legacy_ref = _write(legacy_root, "legacy/cursor-sdk-result.json", {
        "schema": "quwoquan_data.professional_image_supported_api_reviewer_result",
        "provider": "cursor_sdk", "model": "grok-old", "runId": "old",
        "candidateId": legacy_physical["assetId"],
    })
    legacy_refs = _admission_documents(legacy_root, legacy_physical, legacy_ref)
    with pytest.raises(MediaSourceAdmissionError) as rejected:
        MediaSourceAdmissionCommandWriter(legacy_root).write(
            asset_kind="video", asset_id=legacy_physical["assetId"],
            object_ref=f"posts/video/{legacy_physical['assetId']}",
            source_revision=IDENTITY["sourceRevision"], source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"], evidence_refs=legacy_refs,
            recorded_at="2026-08-31T00:02:00Z",
        )
    assert rejected.value.code == MEDIA_SOURCE_ADMISSION_INVALID


def test_source_review_live_graph_has_no_sdk_runtime_after_cutover() -> None:
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    scan = scan_live_python_import_graph(
        scripts_root=scripts,
        entry_modules=(
            "content.source.host_source_review",
            "content.source.research.host_source_review_cli",
            "content.source.media_source_admission",
            "content.source.professional_commons_video_input",
            "content.source.professional_video_provider_batch",
            "content.source.professional_video_rebind",
            "content.source.professional_image_supported_api_input",
        ),
    )
    assert not any("forbidden runtime import" in ref for ref in scan.legacy_entry_refs)
    assert not scan.scan_errors
