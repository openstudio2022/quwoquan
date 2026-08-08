from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.source.professional_image_discovery_governed import (
    build_professional_image_governed_candidate_catalog,
)
from content.source.research.scale_source_pool_image_video import (
    PROJECTION_INVALID,
    PROJECTION_SHORTFALL,
    ScaleSourcePoolProjectionError,
    project_scale_source_pool_image_video,
)

D_REV = "sha256:" + "a" * 64
D_SRC = "sha256:" + "b" * 64
D_CAT = "sha256:" + "c" * 64
D_PLAN = "sha256:" + "d" * 64
D_IMAGE = "sha256:" + "1" * 64
D_VIDEO = "sha256:" + "2" * 64


def _digest(value: dict) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write(root: Path, ref: str, document: dict) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _file_sha(root: Path, ref: str) -> str:
    return "sha256:" + hashlib.sha256((root / ref).read_bytes()).hexdigest()


def _catalog(root: Path) -> dict:
    evidence_ref = "evidence/pinterest-manual.json"
    evidence = {
        "schema": "quwoquan_data.professional_image_manual_file_evidence",
        "provider": "pinterest",
        "acquisitionPath": "manual_file",
        "discoveryCandidateId": "pinterest:1111111111111111",
        "sourcePageUrl": "https://www.pinterest.com/pin/1/",
        "assetUrl": "",
        "manualFile": "image.jpg",
        "apiEvidence": "",
        "creator": "Photographer A",
        "title": "Image One",
        "observedAt": "2026-08-08T00:00:00Z",
        "contentSha256": D_IMAGE,
        "originalAssetCandidate": True,
        "generated": False,
    }
    _write(root, evidence_ref, evidence)
    candidates = [{
        "candidateId": "pinterest:1111111111111111",
        "provider": "pinterest",
        "acquisitionPath": "manual_file",
        "sourcePageUrl": "https://www.pinterest.com/pin/1/",
        "creator": "Photographer A",
        "title": "Image One",
        "observedAt": "2026-08-08T00:00:00Z",
        "originalAssetCandidate": True,
        "generated": False,
        "originalAssetIdentity": {
            "contentSha256": D_IMAGE,
            "sourceUrl": "https://www.pinterest.com/pin/1/",
            "assetUrl": "",
            "manualFile": "image.jpg",
            "apiEvidence": "",
        },
        "pathEvidence": {
            "kind": "manual_file",
            "ref": evidence_ref,
            "digest": _digest(evidence),
            "fileSha256": _file_sha(root, evidence_ref),
        },
    }]
    core = {
        "catalogRevision": "governed-professional-image-candidates-v1",
        "discoveryPlanId": "professional-image-discovery-1111111111111111",
        "discoveryPlanDigest": D_PLAN,
        "createdAt": "2026-08-08T00:00:00Z",
        "providerCounts": [
            {"provider": "pinterest", "displayName": "Pinterest", "acquisitionPath": "manual_file", "candidateCount": 1},
        ],
        "candidateCount": 1,
        "candidates": candidates,
    }
    digest = _digest(core)
    return {"schema": "quwoquan_data.professional_image_governed_candidate_catalog", "catalogId": f"professional-image-governed-{digest[7:23]}", "catalogDigest": digest, **core}


def _safety() -> dict:
    return {"status": "passed", "entityMatch": "matched", "privacyRisk": "none", "minorRisk": "none", "maliciousMediaRisk": "none", "watermarkStatus": "absent", "reviewedAt": "2026-08-08T00:01:00Z", "reviewer": "fixture-reviewer", "evidenceRef": "evidence/safety.json"}


def _image_acquisition(*, path: str = "manual_file", accepted: bool = True) -> dict:
    decision = "research_allowed" if accepted else "blocked"
    status = "acquired" if accepted else "failed"
    spec = None
    if accepted:
        spec = {
            "url": "file:///fixture/image.jpg", "sourceUrl": "https://www.pinterest.com/pin/1/",
            "collectionPageUrl": "https://www.pinterest.com/pin/1/", "originalAssetUrl": "https://i.pinimg.com/originals/aa/bb/image.jpg",
            "platform": "Pinterest", "sourceId": "pinterest", "discoveryCandidateId": "pinterest:1111111111111111",
            "discoveryUrl": "https://www.pinterest.com/search/pins/", "creator": "Photographer A", "credit": "Photographer A",
            "capturedAt": "2026-08-08T00:00:00Z", "contentSha256": D_IMAGE, "acquisitionStatus": "acquired",
            "rightsStatus": "unverified", "authorizationRequired": True, "distributionDecision": decision,
            "rightsAuditStatus": "unverified", "rightsIssues": ["authorization pending"], "license": "unknown",
            "licenseSnapshot": "captured", "usageScope": "internal_reference", "modelReleaseStatus": "not_required",
            "termsUrl": "https://policy.pinterest.com/terms", "authorizationProof": "", "caption": "Landscape",
            "relevance": "entity landscape", "width": 1000, "height": 800,
        }
    asset = {
        "assetId": "image-1", "entityId": "entity-1", "observedEntityId": "entity-1", "entityAliases": ["Entity One"],
        "displayName": "Image One", "discoveryCandidateId": "pinterest:1111111111111111",
        "discoveryUrl": "https://www.pinterest.com/search/pins/", "provider": "pinterest", "platform": "Pinterest",
        "acquisitionPath": path, "assetUrl": "https://i.pinimg.com/originals/aa/bb/image.jpg" if path != "manual_file" else "",
        "manualFile": "image.jpg" if path == "manual_file" else "", "apiEvidence": "api/v1" if path == "supported_api" else "",
        "accessEvidence": {"anonymousAssetAccess": False, "loginRequired": False, "captchaRequired": False, "paywallRequired": False, "drmProtected": False, "accessControlBypass": False},
        "acquisitionStatus": status, "rightsStatus": "unverified", "authorizationRequired": True, "distributionDecision": decision,
        "sourceUrl": "https://www.pinterest.com/pin/1/", "creator": "Photographer A", "capturedAt": "2026-08-08T00:00:00Z",
        "contentSha256": D_IMAGE if accepted else "", "assetRef": "cas/sha256/11/" + "1" * 64 + ".jpg" if accepted else "",
        "bytes": 5000 if accepted else 0, "width": 1000 if accepted else 0, "height": 800 if accepted else 0,
        "license": "unknown", "licenseSnapshot": "captured", "usageScope": "internal_reference", "modelReleaseStatus": "not_required",
        "termsUrl": "https://policy.pinterest.com/terms", "authorizationProof": "", "rightsIssues": ["authorization pending"],
        "caption": "Landscape", "relevance": "entity landscape", "safetyReview": _safety(), "withdrawalRequired": True,
        "failureCode": "" if accepted else "DATA.SOURCE.ACQUISITION_FAILED", "failure": "" if accepted else "failed", "planImageSpec": spec,
    }
    provider = {"displayName": "Pinterest", "provider": "pinterest", "plannedAssetCount": 1, "discoveredAssetCount": 1,
                "downloadedAssetCount": int(accepted), "acceptedAssetCount": int(accepted), "rejectedAssetCount": int(not accepted),
                "verifiedAssetCount": 0, "unverifiedAssetCount": 1, "restrictedAssetCount": 0, "unknownAssetCount": 0}
    stable = {"schema": "quwoquan_data.professional_image_acquisition_receipt", "manifestId": "image-manifest",
              "manifestDigest": D_IMAGE, "sourceRevision": D_REV, "sourceDigest": D_SRC, "entityCatalogDigest": D_CAT,
              "discoveryPlanRef": "plans/image.json", "discoveryPlanDigest": D_PLAN, "plannedAssetCount": 1,
              "discoveredAssetCount": 1, "downloadedAssetCount": int(accepted), "acceptedAssetCount": int(accepted),
              "rejectedAssetCount": int(not accepted), "providerAssetCounts": [provider], "assets": [asset]}
    return {**stable, "receiptDigest": _digest(stable)}


def _probe() -> dict:
    return {"width": 1280, "height": 720, "frameCount": 120, "framesPerSecond": 30.0, "durationMs": 4000,
            "codec": "h264", "hasAudio": True, "sampleCount": 12, "distinctFrameCount": 12,
            "movingTransitionCount": 11, "meanTransitionDelta": 0.4, "playable": True, "motionVideo": True,
            "staticImageSequence": False, "premiumPlayableEligible": True}


def _popularity(*, percentile: float | None = 0.9) -> dict:
    return {"playCount": 1000, "likeCount": 100, "commentCount": 10, "shareCount": 8, "favoriteCount": 20,
            "observedAt": "2026-08-08T00:00:00Z", "provider": "pexels_videos", "topic": "entity-travel",
            "timeBucket": "2026-W32", "popularityScore": 4200, "popularityPercentile": percentile,
            "rankingEligible": percentile is not None, "ineligibleReason": "" if percentile is not None else "incomplete_popularity_signals",
            "comparisonCandidateCount": 2 if percentile is not None else 0}


def _video_catalog(*, content_sha: str = D_VIDEO) -> dict:
    candidates = []
    for ordinal, percentile in ((1, 0.9), (2, 0.1)):
        popularity = _popularity(percentile=percentile)
        if ordinal == 2:
            popularity = {**popularity, "playCount": 100, "popularityScore": 3300}
        candidates.append({
            "candidateId": f"popular-video:pexels_videos:{ordinal:016x}",
            "provider": "pexels_videos", "sourceId": f"video-{ordinal}",
            "entityId": "entity-1", "observedEntityId": "entity-1",
            "sourcePageUrl": f"https://videos.example.test/post/{ordinal}",
            "creator": "Video Creator" if ordinal == 1 else "Video Creator Two",
            "title": "Travel video" if ordinal == 1 else "Travel video two",
            "observedAt": popularity["observedAt"], "topic": popularity["topic"],
            "timeBucket": popularity["timeBucket"],
            "popularity": {key: popularity[key] for key in (
                "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount",
                "popularityScore", "popularityPercentile", "comparisonCandidateCount")},
            "metadataResponseDigest": D_PLAN, "manualFileRequired": True,
            "manualFileProvided": True,
            "manualFileRef": "video.mp4" if ordinal == 1 else "video-2.mp4",
            "manualFileSha256": content_sha if ordinal == 1 else "sha256:" + "8" * 64,
            "manualFileBytes": 10000, "mediaProbe": _probe(),
            "acquisitionStatus": "not_acquired",
        })
    core = {
        "catalogRevision": "popular-video-candidates-v1", 
            "sourceRevision": D_REV, "sourceDigest": D_SRC,
            "entityCatalogDigest": D_CAT
        ,
        "providerPolicyRef": "control_plane/video.yaml", "providerPolicyDigest": D_PLAN,
        "providerPolicies": [{"provider": "pexels_videos", "displayName": "Pexels",
                              "priority": 0, "manualFileRequired": True,
                              "automaticStreamParsing": False, "automaticVideoDownload": False}],
        "sourceResponses": [{"provider": "pexels_videos",
                             "sourcePageUrl": "https://videos.example.test/post/1",
                             "apiEvidenceUrl": "https://videos.example.test/api/metadata",
                             "responseDigest": D_PLAN, "candidateCount": 2}],
        "providerCounts": [{"provider": "pexels_videos", "displayName": "Pexels",
                            "candidateCount": 2, "manualFileProvidedCount": 2}],
        "candidateCount": 2, "candidates": candidates,
    }
    schema = "quwoquan_data.professional_video_popular_candidate_catalog"
    digest = _digest({"schema": schema, **core})
    return {"schema": schema,
            "catalogId": f"popular-video-candidates-{digest[7:23]}", **core,
            "catalogDigest": digest}


def _video_acquisition(*, catalog: dict, catalog_ref: str, catalog_sha: str,
                       percentile: float | None = 0.9, content_sha: str = D_VIDEO) -> dict:
    probe, popularity = _probe(), _popularity(percentile=percentile)
    spec = {"sourceId": "pexels_videos", "sourceKind": "tourism_video_site", "ordinal": 1, "title": "Travel video",
            "relevance": "entity motion", "platform": "Pexels Videos", "assetUrl": "cas://sha256/" + content_sha[7:],
            "originalAssetUrl": "https://videos.example.test/original.mp4", "sourcePostUrl": "https://videos.example.test/post/1",
            "authorizationProofUrl": "", "termsUrl": "https://videos.example.test/terms", "rightsBasis": "pending",
            "originalCreatorName": "Video Creator", "attributionText": "Video Creator / Pexels", "commercialAuthorizationStatus": "unverified",
            "rightsStatus": "unverified", "rightsIssues": ["authorization pending"], "publicationAdmission": "research_release",
            "modelReleaseStatus": "unverified", "propertyReleaseStatus": "not_required", "takedownPolicy": "remove on request",
            "durationSeconds": 4.0, "sizeBytes": 10000, "mediaProbe": probe, "popularitySignals": popularity,
            "professionalAcquisitionReceiptRef": "receipts/" + "3" * 64 + ".json", "professionalAssetId": "video-1",
            "professionalContentSha256": content_sha, "premiumPlayableEligible": True}
    asset = {"assetId": "video-1", "entityId": "entity-1", "observedEntityId": "entity-1", "provider": "pexels_videos",
             "popularCandidateId": catalog["candidates"][0]["candidateId"],
             "popularCatalogRef": catalog_ref, "popularCatalogDigest": catalog["catalogDigest"],
             "popularCatalogFileSha256": catalog_sha,
             "platform": "Pexels Videos", "displayName": "Travel Video", "sourceKind": "tourism_video_site", "acquisitionPath": "manual_file",
             "sourceUrl": "https://videos.example.test/post/1", "assetUrl": "", "manualFile": "video.mp4", "apiEvidence": "",
             "accessEvidence": {"anonymousAssetAccess": False, "loginRequired": False, "captchaRequired": False, "paywallRequired": False, "drmProtected": False, "accessControlBypass": False},
             "title": "Travel video", "relevance": "entity motion", "creator": "Video Creator", "capturedAt": "2026-08-08T00:00:00Z",
             "acquisitionStatus": "acquired", "rightsStatus": "unverified", "authorizationRequired": True,
             "distributionDecision": "research_allowed", "contentSha256": content_sha, "assetRef": "cas/sha256/video.mp4", "bytes": 10000,
             "license": "unknown", "termsUrl": "https://videos.example.test/terms", "authorizationProof": "",
             "rightsIssues": ["authorization pending"], "modelReleaseStatus": "unverified", "propertyReleaseStatus": "not_required",
             "safetyReview": _safety(), "mediaProbe": probe, "duplicateOf": "", "failureCode": "", "failure": "",
             "popularitySignals": popularity, "planVideoSpec": spec}
    counts = {"displayName": "Pexels", "provider": "pexels_videos", "platform": "Pexels Videos", "plannedAssetCount": 1,
              "discoveredAssetCount": 1, "downloadedAssetCount": 1, "acceptedAssetCount": 1, "rejectedAssetCount": 0,
              "verifiedAssetCount": 0, "unverifiedAssetCount": 1, "restrictedAssetCount": 0, "unknownAssetCount": 0,
              "rankingEligibleAssetCount": int(percentile is not None)}
    stable = {"schema": "quwoquan_data.professional_video_acquisition_receipt", "manifestId": "video-manifest", "manifestDigest": D_VIDEO,
              "sourceRevision": D_REV, "sourceDigest": D_SRC, "entityCatalogDigest": D_CAT, "plannedAssetCount": 1,
              "discoveredAssetCount": 1, "downloadedAssetCount": 1, "acceptedAssetCount": 1, "rejectedAssetCount": 0,
              "providerAssetCounts": [counts], "assets": [asset]}
    return {**stable, "receiptDigest": _digest(stable)}


def _review(kind: str, asset: dict, acquisition: dict, *, acquisition_ref: str, acquisition_sha: str) -> dict:
    snapshot = {key: asset[key] for key in ("assetId", "entityId", "observedEntityId", "contentSha256", "sourceUrl", "creator", "capturedAt", "license", "termsUrl", "authorizationProof", "rightsIssues", "acquisitionStatus", "rightsStatus", "authorizationRequired", "distributionDecision")}
    snapshot["casRef"] = asset["assetRef"]
    snapshot["platform"] = asset["platform"]
    if kind == "image":
        snapshot.update(licenseSnapshot=asset["licenseSnapshot"], usageScope=asset["usageScope"], modelReleaseStatus=asset["modelReleaseStatus"])
    else:
        snapshot.update(modelReleaseStatus=asset["modelReleaseStatus"], mediaProbe=asset["mediaProbe"], popularitySignals=asset["popularitySignals"])
        snapshot.update({field: asset[field] for field in (
            "popularCandidateId", "popularCatalogRef", "popularCatalogDigest",
            "popularCatalogFileSha256")})
    evidence = {"executionId": f"{kind}-execution", "objectRef": f"posts/{kind}/entity-1", "provider": "cursor_sdk", "model": "auto", "runId": f"{kind}-run", "evidenceRef": f"evidence/{kind}.json", "evidenceSha256": D_IMAGE}
    reviewer = {**evidence, "modelFamily": "cursor-auto", "resultHash": D_VIDEO}
    judgment = {"rightsStatus": "unverified", "authorizationRequired": True, "distributionDecision": "research_allowed", "safetyStatus": "passed",
                "entityMatch": "matched", "qualityStatus": "passed", "privacyRisk": "none", "minorRisk": "none",
                "maliciousMediaRisk": "none", "watermarkStatus": "absent", "findings": []}
    stable = {"schema": "quwoquan_data.independent_asset_review_receipt", "reviewId": "asset-review-" + ("4" if kind == "image" else "5") * 64,
              "assetKind": kind, "objectRef": f"posts/{kind}/entity-1", "sourceRevision": D_REV, "sourceDigest": D_SRC,
              "entityCatalogDigest": D_CAT, "acquisitionReceiptRef": acquisition_ref, "acquisitionReceiptDigest": acquisition["receiptDigest"],
              "acquisitionReceiptSha256": acquisition_sha, "executionManifestRef": f"tasks/{kind}/execution.json",
              "executionManifestSha256": D_CAT, "assetSnapshot": snapshot, "acquisitionExecution": evidence,
              "authorExecution": {**evidence, "runId": f"{kind}-author"}, "reviewerExecution": reviewer,
              "judgment": judgment, "reviewDecision": "accepted", "recordedAt": "2026-08-08T00:02:00Z"}
    return {**stable, "receiptDigest": _digest(stable)}


def _fixture(root: Path, *, image_path: str = "manual_file", percentile: float | None = 0.9, video_sha: str = D_VIDEO) -> dict:
    refs = {"catalog": "catalog/image.json", "image_acq": "acquisition/image.json", "image_review": "reviews/image.json",
            "video_catalog": "catalog/video.json", "video_acq": "acquisition/video.json", "video_review": "reviews/video.json"}
    catalog = _catalog(root)
    image = _image_acquisition(path=image_path)
    video_catalog = _video_catalog(content_sha=video_sha)
    _write(root, refs["catalog"], catalog)
    _write(root, refs["video_catalog"], video_catalog)
    video = _video_acquisition(
        catalog=video_catalog, catalog_ref=refs["video_catalog"],
        catalog_sha=_file_sha(root, refs["video_catalog"]), percentile=percentile,
        content_sha=video_sha,
    )
    _write(root, refs["image_acq"], image)
    _write(root, refs["video_acq"], video)
    _write(root, refs["image_review"], _review("image", image["assets"][0], image, acquisition_ref=refs["image_acq"], acquisition_sha=_file_sha(root, refs["image_acq"])))
    _write(root, refs["video_review"], _review("video", video["assets"][0], video, acquisition_ref=refs["video_acq"], acquisition_sha=_file_sha(root, refs["video_acq"])))
    return refs


def _project(root: Path, refs: dict) -> dict:
    return project_scale_source_pool_image_video(
        evidence_root=root, target_scale="M100", source_revision=D_REV, source_digest=D_SRC, entity_catalog_digest=D_CAT,
        image_catalog_refs=[refs["catalog"]], image_acquisition_refs=[refs["image_acq"]], image_review_refs=[refs["image_review"]],
        video_catalog_refs=[refs["video_catalog"]], video_acquisition_refs=[refs["video_acq"]], video_review_refs=[refs["video_review"]],
    )


def _rewrite_image(root: Path, refs: dict, image: dict) -> None:
    stable = {key: value for key, value in image.items() if key != "receiptDigest"}
    image = {**stable, "receiptDigest": _digest(stable)}
    _write(root, refs["image_acq"], image)
    _write(
        root,
        refs["image_review"],
        _review(
            "image",
            image["assets"][0],
            image,
            acquisition_ref=refs["image_acq"],
            acquisition_sha=_file_sha(root, refs["image_acq"]),
        ),
    )


def test_projection_recomputes_documents_and_returns_deterministic_scale_rows(tmp_path: Path) -> None:
    refs = _fixture(tmp_path)
    first = _project(tmp_path, refs)
    second = _project(tmp_path, refs)
    assert first == second
    assert [row["carrier"] for row in first["candidates"]] == ["image", "video"]
    image, video = first["candidates"]
    assert image["provider"] == "pinterest" and image["generated"] is False
    assert image["sourceUnitRef"] == refs["catalog"] and image["acquisitionRef"] == refs["image_acq"]
    assert video["videoReadiness"]["premiumEligible"] is True
    assert video["videoReadiness"]["popularityPercentile"] == 0.9
    assert all((tmp_path / item["ref"]).is_file() for item in first["inputDocuments"])
    assert all(_file_sha(tmp_path, item["ref"]) == item["fileSha256"] for item in first["inputDocuments"])


def test_projection_allows_wikimedia_as_a_governed_supplement(
    tmp_path: Path,
) -> None:
    refs = _fixture(tmp_path)
    evidence_ref = "evidence/wikimedia-manual.json"
    source_page = "https://commons.wikimedia.org/wiki/File:West_Lake.jpg"
    evidence = {
        "schema": "quwoquan_data.professional_image_manual_file_evidence",
        "provider": "wikimedia_commons",
        "acquisitionPath": "manual_file",
        "discoveryCandidateId": "wikimedia_commons:1111111111111111",
        "sourcePageUrl": source_page,
        "assetUrl": "",
        "manualFile": "manual/west-lake.jpg",
        "apiEvidence": "",
        "creator": "Commons Photographer",
        "title": "Wikimedia Original",
        "observedAt": "2026-08-08T00:00:00Z",
        "contentSha256": D_IMAGE,
        "originalAssetCandidate": True,
        "generated": False,
    }
    _write(tmp_path, evidence_ref, evidence)
    catalog = build_professional_image_governed_candidate_catalog(
        discovery_plan_id="professional-image-discovery-1111111111111111",
        discovery_plan_digest=D_PLAN,
        created_at="2026-08-08T00:00:00Z",
        evidence_root=tmp_path,
        evidence_refs=[evidence_ref],
    )
    _write(tmp_path, refs["catalog"], catalog)

    image = _image_acquisition()
    asset = image["assets"][0]
    asset.update(
        provider="wikimedia_commons",
        platform="Wikimedia Commons",
        displayName="Wikimedia Original",
        discoveryCandidateId="wikimedia_commons:1111111111111111",
        sourceUrl=source_page,
        manualFile="manual/west-lake.jpg",
        creator="Commons Photographer",
    )
    spec = asset["planImageSpec"]
    spec.update(
        sourceId="wikimedia_commons",
        platform="Wikimedia Commons",
        sourceUrl=source_page,
        collectionPageUrl=source_page,
        originalAssetUrl=source_page,
        discoveryCandidateId="wikimedia_commons:1111111111111111",
        creator="Commons Photographer",
        credit="Commons Photographer",
    )
    image["providerAssetCounts"][0].update(
        displayName="Wikimedia Commons", provider="wikimedia_commons"
    )
    _rewrite_image(tmp_path, refs, image)

    projected = _project(tmp_path, refs)
    image_row = next(
        row for row in projected["candidates"] if row["carrier"] == "image"
    )
    assert image_row["provider"] == "wikimedia_commons"


def test_projection_rejects_pinterest_automatic_public_direct_acquisition(tmp_path: Path) -> None:
    refs = _fixture(tmp_path, image_path="public_direct")
    with pytest.raises(ScaleSourcePoolProjectionError) as caught:
        _project(tmp_path, refs)
    assert caught.value.code == PROJECTION_INVALID
    assert "supported API or manual" in str(caught.value)


def test_projection_rejects_governed_catalog_path_evidence_creator_and_content_drift(
    tmp_path: Path,
) -> None:
    path_root = tmp_path / "path"
    path_refs = _fixture(path_root)
    _rewrite_image(path_root, path_refs, _image_acquisition(path="supported_api"))
    with pytest.raises(ScaleSourcePoolProjectionError, match="acquisitionPath drift"):
        _project(path_root, path_refs)

    evidence_root = tmp_path / "evidence"
    evidence_refs = _fixture(evidence_root)
    evidence_path = evidence_root / "evidence/pinterest-manual.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["title"] = "drifted evidence"
    _write(evidence_root, "evidence/pinterest-manual.json", evidence)
    with pytest.raises(ScaleSourcePoolProjectionError, match="evidence file drift"):
        _project(evidence_root, evidence_refs)

    creator_root = tmp_path / "creator"
    creator_refs = _fixture(creator_root)
    creator_image = _image_acquisition()
    creator_image["assets"][0]["creator"] = "Drifted Creator"
    creator_image["assets"][0]["planImageSpec"]["creator"] = "Drifted Creator"
    creator_image["assets"][0]["planImageSpec"]["credit"] = "Drifted Creator"
    _rewrite_image(creator_root, creator_refs, creator_image)
    with pytest.raises(ScaleSourcePoolProjectionError, match="original/source binding drift"):
        _project(creator_root, creator_refs)

    content_root = tmp_path / "content"
    content_refs = _fixture(content_root)
    content_image = _image_acquisition()
    content_image["assets"][0]["contentSha256"] = "sha256:" + "9" * 64
    content_image["assets"][0]["planImageSpec"]["contentSha256"] = "sha256:" + "9" * 64
    _rewrite_image(content_root, content_refs, content_image)
    with pytest.raises(ScaleSourcePoolProjectionError, match="original/path binding drift"):
        _project(content_root, content_refs)


def test_projection_rejects_discovery_without_acquired_image(tmp_path: Path) -> None:
    refs = _fixture(tmp_path)
    image = _image_acquisition(accepted=False)
    _write(tmp_path, refs["image_acq"], image)
    with pytest.raises(ScaleSourcePoolProjectionError) as caught:
        _project(tmp_path, refs)
    assert caught.value.code == PROJECTION_SHORTFALL


def test_projection_rejects_null_video_popularity_percentile(tmp_path: Path) -> None:
    refs = _fixture(tmp_path, percentile=None)
    with pytest.raises(ScaleSourcePoolProjectionError) as caught:
        _project(tmp_path, refs)
    assert caught.value.code == PROJECTION_INVALID
    assert "percentile" in str(caught.value)


def test_projection_rejects_identity_drift_duplicate_content_and_symlink(tmp_path: Path) -> None:
    refs = _fixture(tmp_path)
    with pytest.raises(ScaleSourcePoolProjectionError, match="identity drift"):
        project_scale_source_pool_image_video(
            evidence_root=tmp_path, target_scale="M100", source_revision=D_REV, source_digest="sha256:" + "f" * 64,
            entity_catalog_digest=D_CAT, image_catalog_refs=[refs["catalog"]], image_acquisition_refs=[refs["image_acq"]],
            image_review_refs=[refs["image_review"]], video_catalog_refs=[refs["video_catalog"]], video_acquisition_refs=[refs["video_acq"]], video_review_refs=[refs["video_review"]],
        )
    duplicate_refs = _fixture(tmp_path / "duplicate", video_sha=D_IMAGE)
    with pytest.raises(ScaleSourcePoolProjectionError, match="duplicate contentSha256"):
        _project(tmp_path / "duplicate", duplicate_refs)
    link = tmp_path / "catalog-link.json"
    link.symlink_to(tmp_path / refs["catalog"])
    with pytest.raises(ScaleSourcePoolProjectionError, match="symlink"):
        project_scale_source_pool_image_video(
            evidence_root=tmp_path, target_scale="M100", source_revision=D_REV, source_digest=D_SRC,
            entity_catalog_digest=D_CAT, image_catalog_refs=[link.name], image_acquisition_refs=[refs["image_acq"]],
            image_review_refs=[refs["image_review"]], video_catalog_refs=[refs["video_catalog"]], video_acquisition_refs=[refs["video_acq"]], video_review_refs=[refs["video_review"]],
        )
