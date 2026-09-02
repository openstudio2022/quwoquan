from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from content.source import professional_image_supported_api_input as supported_input
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from content.source.professional_image_discovery_governed import (
    build_professional_image_governed_candidate_catalog,
)
from content.source.host_source_review import record_host_source_review_result
from content.source.professional_image_supported_api_input import (
    SOURCE_POOL_SHORTFALL,
    ProfessionalImageSupportedApiInputError,
    prepare_supported_api_inputs,
)
from content.source.professional_safety_evidence import file_sha256
from PIL import Image


def _digest(value: object, *, newline: bool = False) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + ("\n" if newline else "")
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _image_bytes() -> bytes:
    image = Image.effect_noise((800, 600), 96).convert("RGB")
    body = io.BytesIO()
    image.save(body, format="PNG")
    return body.getvalue()


def _plan_and_catalog(tmp_path: Path, *, file_title: str = "File:West Lake.jpg") -> tuple[Path, Path, dict]:
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["西湖"], category="风光", season="秋季", style="纪实",
        viewpoint="航拍", popularity="热门", output_root=tmp_path / "plans",
    )
    discovery = next(
        row for row in plan["candidates"] if row["provider"] == "wikimedia_commons"
    )
    candidate = {
        "candidateId": "wikimedia_commons:commons:1111111111111111",
        "queryId": "commons-query-1111111111111111",
        "discoveryCandidateId": discovery["candidateId"],
        "provider": "wikimedia_commons", "entityId": "西湖",
        "observedEntityId": "西湖", "entityAliases": ["西湖"],
        "providerAssetId": "1", "upstreamProvider": "wikimedia_commons",
        "fileTitle": file_title, "pageId": 1, "caption": "西湖秋日航拍风光",
        "relevance": "西湖景区秋季全景与湖岸层次",
        "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:West_Lake.jpg",
        "originalAssetUrl": "https://upload.wikimedia.org/wikipedia/commons/a/ab/west-lake.png",
        "creator": "Travel Photographer", "license": "CC BY-SA 4.0",
        "licenseVersion": "4.0",
        "attributionText": "Travel Photographer · Wikimedia Commons · CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "width": 800, "height": 600,
        "apiRequestUrl": "https://commons.wikimedia.org/w/api.php?action=query",
        "apiResponseSha256": "sha256:" + "4" * 64,
    }
    stable = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "discoveryPlanId": plan["planId"], "discoveryPlanDigest": plan["planDigest"],
        "handoffId": "handoff-test", "handoffRevision": 1,
        "handoffDigest": "sha256:" + "5" * 64,
        "entityCatalogRef": "quwoquan_data/reference/travel/entities/china",
        "requestedProviders": ["wikimedia_commons"],
        "observedAt": "2026-08-11T10:00:00Z",
        "targetCandidateCount": 1, "queryCount": 1, "completedQueryCount": 1,
        "excludedCount": 0,
        "candidateCount": 1, "candidates": [candidate],
    }
    digest = _digest(stable)
    catalog = {
        "schema": "quwoquan_data.professional_image_supported_api_metadata_catalog",
        "catalogId": f"professional-image-supported-api-metadata-{digest[7:23]}",
        "catalogDigest": digest, **stable,
    }
    return plan_path, _write(tmp_path / "metadata.json", catalog), catalog


def _openverse_plan_and_catalog(tmp_path: Path) -> tuple[Path, Path, dict]:
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["西湖"], category="风光", season="秋季", style="纪实",
        viewpoint="航拍", popularity="热门", output_root=tmp_path / "plans",
    )
    discovery = next(row for row in plan["candidates"] if row["provider"] == "openverse")
    candidate = {
        "candidateId": "openverse:asset:1111111111111111",
        "queryId": "openverse-query-1111111111111111",
        "discoveryCandidateId": discovery["candidateId"],
        "provider": "openverse", "entityId": "西湖",
        "observedEntityId": "西湖", "entityAliases": ["西湖"],
        "providerAssetId": "00000000-0000-4000-8000-000000000001",
        "upstreamProvider": "flickr", "fileTitle": "西湖秋日航拍风光",
        "pageId": 0, "caption": "西湖秋日航拍风光",
        "relevance": "西湖景区秋季全景与湖岸层次",
        "sourcePageUrl": "https://www.flickr.com/photos/example/1",
        "originalAssetUrl": "https://live.staticflickr.com/1/west-lake.png",
        "creator": "Travel Photographer", "license": "CC BY-SA 4.0",
        "licenseVersion": "4.0",
        "attributionText": "Travel Photographer · CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "width": 800, "height": 600,
        "apiRequestUrl": (
            "https://api.openverse.org/v1/images/?q=%E8%A5%BF%E6%B9%96&page_size=1"
        ),
        "apiResponseSha256": "sha256:" + "4" * 64,
    }
    stable = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "discoveryPlanId": plan["planId"], "discoveryPlanDigest": plan["planDigest"],
        "handoffId": "handoff-test", "handoffRevision": 1,
        "handoffDigest": "sha256:" + "5" * 64,
        "entityCatalogRef": "quwoquan_data/reference/travel/entities/china",
        "requestedProviders": ["openverse"],
        "observedAt": "2026-08-11T10:00:00Z",
        "targetCandidateCount": 1, "queryCount": 1, "completedQueryCount": 1,
        "excludedCount": 0, "candidateCount": 1, "candidates": [candidate],
    }
    digest = _digest(stable)
    catalog = {
        "schema": "quwoquan_data.professional_image_supported_api_metadata_catalog",
        "catalogId": f"professional-image-supported-api-metadata-{digest[7:23]}",
        "catalogDigest": digest, **stable,
    }
    return plan_path, _write(tmp_path / "openverse-metadata.json", catalog), catalog


def _openverse_payload() -> dict:
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "title": "西湖秋日航拍风光", "creator": "Travel Photographer",
        "license": "by-sa", "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "foreign_landing_url": "https://www.flickr.com/photos/example/1",
        "url": "https://live.staticflickr.com/1/west-lake.png",
        "provider": "flickr", "source": "flickr", "width": 800, "height": 600,
        "mature": False,
        "attribution": "Travel Photographer · CC BY-SA 4.0",
    }


def _api_payload(file_title: str) -> dict:
    def value(text: str) -> dict[str, str]:
        return {"value": text}

    return {
        "query": {"pages": [{
            "title": file_title,
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/west-lake.png",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:West_Lake.jpg",
                "width": 800, "height": 600,
                "extmetadata": {
                    "Artist": value("Travel Photographer"),
                    "LicenseShortName": value("CC BY-SA 4.0"),
                    "LicenseUrl": value("https://creativecommons.org/licenses/by-sa/4.0/"),
                    "ImageDescription": value("West Lake autumn landscape"),
                },
            }],
        }]},
    }


def _api_fetch(payload: dict, calls: list[str]):
    def fetch(url: str) -> dict:
        calls.append(url)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return {
            "bytes": body,
            "payload": payload,
            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
            "transportEvidence": _transport(url, body, "application/json"),
        }
    return fetch


def _image_fetch(body: bytes, calls: list[str]):
    def fetch(url: str, **_kwargs) -> dict:
        calls.append(url)
        return {
            "bytes": body,
            "ext": ".png",
            "transportEvidence": _transport(url, body, "image/png"),
        }
    return fetch


def _transport(url: str, body: bytes, content_type: str) -> dict:
    host = str(urlparse(url).hostname)
    return {
        "schema": "quwoquan_data.professional_image_https_transport_evidence",
        "admissionRevision": "professional-image-network-admission-v1",
        "admissionMode": "public_dns",
        "requestedUrl": url,
        "finalUrl": url,
        "requestHost": host,
        "finalHost": host,
        "resolvedAddresses": ["203.0.113.8"],
        "peerAddress": "203.0.113.8",
        "tls": {
            "serverHostname": host,
            "version": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "peerCertificateSha256": "sha256:" + "9" * 64,
            "systemTrustVerified": True,
            "hostnameVerified": True,
        },
        "httpStatus": 200,
        "contentType": content_type,
        "responseBytes": len(body),
        "responseSha256": "sha256:" + hashlib.sha256(body).hexdigest(),
    }


def _identity_guard(_catalog, **_kwargs) -> dict:
    return {"ok": True}


def _inventory_check(**_kwargs) -> None:
    return None


_REVIEW_ACTOR = {
    "host": "cursor",
    "sessionId": "image-supported-api-session",
    "modelFamily": "gpt-5",
    "auditRunId": "image-supported-api-audit-001",
}


def _pending_receipt(error: ProfessionalImageSupportedApiInputError, output_root: Path) -> tuple[dict, Path]:
    receipt_path = output_root / error.receipt_ref
    return json.loads(receipt_path.read_text(encoding="utf-8")), receipt_path


def _record_host_review_result(root: Path, *, request_ref: str) -> str:
    """Record one passing host source review result against a frozen request."""
    request = json.loads((root / request_ref).read_text(encoding="utf-8"))
    _result, result_ref = record_host_source_review_result(
        evidence_root=root,
        result_input={
            "schema": "quwoquan_data.host_source_review_result_input",
            "requestRef": request_ref,
            "requestDigest": request["requestDigest"],
            "actor": dict(_REVIEW_ACTOR),
            "reviewedAt": "2026-08-11T10:05:00Z",
            "verdict": {
                "status": "passed", "entityMatch": "matched",
                "qualityStatus": "passed", "privacyRisk": "none",
                "minorRisk": "none", "maliciousMediaRisk": "none",
                "watermarkStatus": "absent", "findings": [],
            },
        },
    )
    return result_ref


def test_panoramio_provenance_blocks_before_api_or_asset_fetch(tmp_path: Path) -> None:
    plan_path, catalog_path, _catalog = _plan_and_catalog(
        tmp_path, file_title="File:Panoramio West Lake.jpg"
    )
    api_calls: list[str] = []
    image_calls: list[str] = []
    output_root = tmp_path / "output"
    with pytest.raises(ProfessionalImageSupportedApiInputError) as captured:
        prepare_supported_api_inputs(
            handoff_ref=tmp_path / "handoff.json", discovery_plan_path=plan_path,
            metadata_catalog_path=catalog_path, accepted_target=1,
            output_root=output_root, reviewer_root=tmp_path,
            api_fetcher=_api_fetch({}, api_calls),
            image_fetcher=_image_fetch(_image_bytes(), image_calls),
            identity_guard=_identity_guard, inventory_check=_inventory_check,
        )
    receipt, _path = _pending_receipt(captured.value, output_root)
    assert captured.value.code == SOURCE_POOL_SHORTFALL
    assert api_calls == image_calls == []
    assert receipt["blockedCount"] == 1
    assert receipt["items"][0]["failureCode"] == "DATA.SOURCE.WATERMARK_BLOCKED"


def test_openverse_supported_api_freezes_bytes_and_attribution_pending_review(
    tmp_path: Path,
) -> None:
    plan_path, catalog_path, _catalog = _openverse_plan_and_catalog(tmp_path)
    api_calls: list[str] = []
    image_calls: list[str] = []
    output_root = tmp_path / "output"
    with pytest.raises(ProfessionalImageSupportedApiInputError) as captured:
        prepare_supported_api_inputs(
            handoff_ref=tmp_path / "handoff.json",
            discovery_plan_path=plan_path,
            metadata_catalog_path=catalog_path,
            accepted_target=1,
            output_root=output_root,
            reviewer_root=tmp_path,
            api_fetcher=_api_fetch(_openverse_payload(), api_calls),
            image_fetcher=_image_fetch(_image_bytes(), image_calls),
            identity_guard=_identity_guard,
            inventory_check=_inventory_check,
        )
    pending, pending_path = _pending_receipt(captured.value, output_root)
    assert captured.value.code == SOURCE_POOL_SHORTFALL
    assert pending["pendingCount"] == 1
    assert api_calls == [
        "https://api.openverse.org/v1/images/00000000-0000-4000-8000-000000000001/"
    ]
    assert image_calls == ["https://live.staticflickr.com/1/west-lake.png"]
    evidence = json.loads(
        (pending_path.parent.parent / pending["items"][0]["evidenceRef"]).read_text()
    )
    assert evidence["provider"] == "openverse"
    assert evidence["providerAssetId"] == "00000000-0000-4000-8000-000000000001"
    assert evidence["upstreamProvider"] == "flickr"
    assert evidence["sourcePageUrl"] == "https://www.flickr.com/photos/example/1"
    assert evidence["license"] == "CC BY-SA 4.0"
    assert evidence["licenseVersion"] == "4.0"
    assert evidence["attributionText"] == "Travel Photographer · CC BY-SA 4.0"
    assert evidence["contentSha256"].startswith("sha256:")
    assert len(evidence["perceptualHash"]) == 16

    root = pending_path.parent.parent
    request_doc = json.loads((root / evidence["reviewRequestRef"]).read_text())
    assert request_doc["rubric"]["rubricId"] == "media-source-semantic-review"
    assert request_doc["assetBinding"]["contentSha256"] == evidence["contentSha256"]
    reviewer_ref = _record_host_review_result(
        root, request_ref=evidence["reviewRequestRef"]
    )
    ready, ready_path = prepare_supported_api_inputs(
        handoff_ref=tmp_path / "handoff.json",
        discovery_plan_path=plan_path,
        metadata_catalog_path=catalog_path,
        accepted_target=1,
        output_root=output_root,
        reviewer_root=root,
        reviewer_result_refs=(reviewer_ref,),
        api_fetcher=_api_fetch(_openverse_payload(), api_calls),
        image_fetcher=_image_fetch(_image_bytes(), image_calls),
        identity_guard=_identity_guard,
        inventory_check=_inventory_check,
    )
    accepted_ref = ready["items"][0]["evidenceRef"]
    accepted = json.loads((ready_path.parent.parent / accepted_ref).read_text())
    governed = build_professional_image_governed_candidate_catalog(
        discovery_plan_id=_catalog["discoveryPlanId"],
        discovery_plan_digest=_catalog["discoveryPlanDigest"],
        created_at="2026-08-11T10:06:00Z",
        evidence_root=ready_path.parent.parent,
        evidence_refs=[accepted_ref],
    )
    assert governed["candidates"][0]["candidateId"] == evidence["candidateId"]
    assert governed["candidates"][0]["originalAssetIdentity"]["contentSha256"] == evidence[
        "contentSha256"
    ]


def test_api_metadata_panoramio_provenance_is_defense_in_depth_block(tmp_path: Path) -> None:
    file_title = "File:West Lake.jpg"
    plan_path, catalog_path, _catalog = _plan_and_catalog(tmp_path, file_title=file_title)
    payload = _api_payload(file_title)
    payload["query"]["pages"][0]["imageinfo"][0]["extmetadata"]["ImageDescription"] = {
        "value": "Imported from Panoramio"
    }
    api_calls: list[str] = []
    image_calls: list[str] = []
    output_root = tmp_path / "output"
    with pytest.raises(ProfessionalImageSupportedApiInputError) as captured:
        prepare_supported_api_inputs(
            handoff_ref=tmp_path / "handoff.json", discovery_plan_path=plan_path,
            metadata_catalog_path=catalog_path, accepted_target=1,
            output_root=output_root, reviewer_root=tmp_path,
            api_fetcher=_api_fetch(payload, api_calls),
            image_fetcher=_image_fetch(_image_bytes(), image_calls),
            identity_guard=_identity_guard, inventory_check=_inventory_check,
        )
    receipt, _path = _pending_receipt(captured.value, output_root)
    assert len(api_calls) == 1 and image_calls == []
    assert receipt["items"][0]["failureCode"] == "DATA.SOURCE.WATERMARK_BLOCKED"


def test_pending_checkpoint_resumes_without_refetch_and_binds_semantic_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_title = "File:West Lake.jpg"
    plan_path, catalog_path, catalog = _plan_and_catalog(tmp_path, file_title=file_title)
    api_calls: list[str] = []
    image_calls: list[str] = []
    source_body = _image_bytes()
    output_root = tmp_path / "output"
    options = {
        "handoff_ref": tmp_path / "handoff.json", "discovery_plan_path": plan_path,
        "metadata_catalog_path": catalog_path, "accepted_target": 1,
        "output_root": output_root, "reviewer_root": tmp_path,
        "api_fetcher": _api_fetch(_api_payload(file_title), api_calls),
        "image_fetcher": _image_fetch(source_body, image_calls),
        "identity_guard": _identity_guard, "inventory_check": _inventory_check,
    }
    with pytest.raises(ProfessionalImageSupportedApiInputError) as captured:
        prepare_supported_api_inputs(**options)
    pending, pending_path = _pending_receipt(captured.value, output_root)
    assert pending["status"] == "partial"
    assert pending["pendingCount"] == 1 and pending["acceptedCount"] == 0
    root = pending_path.parent.parent
    evidence = json.loads((root / pending["items"][0]["evidenceRef"]).read_text())
    assert evidence["status"] == "review_pending"
    reviewer_ref = _record_host_review_result(
        root, request_ref=evidence["reviewRequestRef"]
    )
    receipt, receipt_path = prepare_supported_api_inputs(
        **{**options, "reviewer_root": root}, reviewer_result_refs=(reviewer_ref,)
    )
    assert receipt["status"] == "ready"
    assert receipt["acceptedCount"] == 1 and receipt["shortfall"] == 0
    assert receipt["acquisitionManifestRef"] == "manifests/acquisition.json"
    assert receipt_path.is_file()
    assert len(api_calls) == len(image_calls) == 1
    manifest = json.loads((receipt_path.parent.parent / receipt["acquisitionManifestRef"]).read_text())
    item = manifest["items"][0]
    assert item["sourceAttribution"]["publicationAdmission"] == "research_release"
    assert item["safetyReview"]["reviewer"] == "host:" + _REVIEW_ACTOR["auditRunId"]

    from content.source import professional_image_acquisition as acquisition

    monkeypatch.setattr(
        acquisition, "guard_acquisition_source_identity", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(
        acquisition, "_network_payload",
        lambda _url, *, supported_api: {
            "bytes": source_body, "ext": ".png", "contentType": "image/png"
        },
    )
    acquired, _acquisition_path = acquisition.acquire_professional_images(
        receipt_path.parent.parent / receipt["acquisitionManifestRef"],
        handoff_ref=tmp_path / "handoff.json",
        output_root=receipt_path.parent.parent,
    )
    assert acquired["acceptedAssetCount"] == 1

    drifted_body = _image_bytes()
    assert drifted_body != source_body
    monkeypatch.setattr(
        acquisition, "_network_payload",
        lambda _url, *, supported_api: {
            "bytes": drifted_body, "ext": ".png", "contentType": "image/png"
        },
    )
    # Same manifest identity cannot replace its prior successful immutable receipt,
    # even when a later fetch would now be excluded for safety-byte drift.
    with pytest.raises(ValueError, match="acquisition receipt collision"):
        acquisition.acquire_professional_images(
            receipt_path.parent.parent / receipt["acquisitionManifestRef"],
            handoff_ref=tmp_path / "handoff.json",
            output_root=receipt_path.parent.parent,
        )


def test_incremental_adoption_freezes_new_manifest_record_without_rewriting_first(
    tmp_path: Path,
) -> None:
    """增量采纳会让 manifest 内容增长：首个 record 拥有固定路径，后续内容冻结为 content-addressed record。"""
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["西湖"], category="风光", season="秋季", style="纪实",
        viewpoint="航拍", popularity="热门", output_root=tmp_path / "plans",
    )
    discovery = next(
        row for row in plan["candidates"] if row["provider"] == "wikimedia_commons"
    )
    file_titles = ("File:West Lake.jpg", "File:West Lake Second.jpg")
    asset_urls = (
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/west-lake.png",
        "https://upload.wikimedia.org/wikipedia/commons/b/bc/west-lake-second.png",
    )
    candidates = []
    for index, (file_title, asset_url) in enumerate(zip(file_titles, asset_urls), start=1):
        candidates.append({
            "candidateId": f"wikimedia_commons:commons:{index:016d}",
            "queryId": f"commons-query-{index:016d}",
            "discoveryCandidateId": discovery["candidateId"],
            "provider": "wikimedia_commons", "entityId": "西湖",
            "observedEntityId": "西湖", "entityAliases": ["西湖"],
            "providerAssetId": str(index), "upstreamProvider": "wikimedia_commons",
            "fileTitle": file_title, "pageId": index, "caption": "西湖秋日航拍风光",
            "relevance": "西湖景区秋季全景与湖岸层次",
            "sourcePageUrl": (
                "https://commons.wikimedia.org/wiki/"
                + file_title.replace(" ", "_")
            ),
            "originalAssetUrl": asset_url,
            "creator": "Travel Photographer", "license": "CC BY-SA 4.0",
            "licenseVersion": "4.0",
            "attributionText": "Travel Photographer · Wikimedia Commons · CC BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "width": 800, "height": 600,
            "apiRequestUrl": "https://commons.wikimedia.org/w/api.php?action=query",
            "apiResponseSha256": "sha256:" + "4" * 64,
        })
    stable = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "discoveryPlanId": plan["planId"], "discoveryPlanDigest": plan["planDigest"],
        "handoffId": "handoff-test", "handoffRevision": 1,
        "handoffDigest": "sha256:" + "5" * 64,
        "entityCatalogRef": "quwoquan_data/reference/travel/entities/china",
        "requestedProviders": ["wikimedia_commons"],
        "observedAt": "2026-08-11T10:00:00Z",
        "targetCandidateCount": 2, "queryCount": 1, "completedQueryCount": 1,
        "excludedCount": 0, "candidateCount": 2, "candidates": candidates,
    }
    digest = _digest(stable)
    catalog = {
        "schema": "quwoquan_data.professional_image_supported_api_metadata_catalog",
        "catalogId": f"professional-image-supported-api-metadata-{digest[7:23]}",
        "catalogDigest": digest, **stable,
    }
    catalog_path = _write(tmp_path / "metadata.json", catalog)

    payloads = {title: _api_payload(title) for title in file_titles}
    second_info = payloads[file_titles[1]]["query"]["pages"][0]["imageinfo"][0]
    second_info["url"] = asset_urls[1]
    second_info["descriptionurl"] = candidates[1]["sourcePageUrl"]

    def api_fetch(url: str) -> dict:
        title = file_titles[1] if "Second" in url else file_titles[0]
        body = json.dumps(payloads[title], ensure_ascii=False).encode("utf-8")
        return {
            "bytes": body, "payload": payloads[title],
            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
            "transportEvidence": _transport(url, body, "application/json"),
        }

    bodies = {asset_urls[0]: _image_bytes(), asset_urls[1]: _image_bytes()}

    def image_fetch(url: str, **_kwargs) -> dict:
        return {
            "bytes": bodies[url], "ext": ".png",
            "transportEvidence": _transport(url, bodies[url], "image/png"),
        }

    output_root = tmp_path / "output"
    options = {
        "handoff_ref": tmp_path / "handoff.json", "discovery_plan_path": plan_path,
        "metadata_catalog_path": catalog_path, "accepted_target": 2,
        "output_root": output_root, "reviewer_root": tmp_path,
        "api_fetcher": api_fetch, "image_fetcher": image_fetch,
        "identity_guard": _identity_guard, "inventory_check": _inventory_check,
    }
    with pytest.raises(ProfessionalImageSupportedApiInputError) as first_wave:
        prepare_supported_api_inputs(**options)
    pending, pending_path = _pending_receipt(first_wave.value, output_root)
    root = pending_path.parent.parent
    evidences = {
        row["candidateId"]: json.loads((root / row["evidenceRef"]).read_text())
        for row in pending["items"]
    }
    options = {**options, "reviewer_root": root}
    first_ref = _record_host_review_result(
        root,
        request_ref=evidences[candidates[0]["candidateId"]]["reviewRequestRef"],
    )
    with pytest.raises(ProfessionalImageSupportedApiInputError) as second_wave:
        prepare_supported_api_inputs(**options, reviewer_result_refs=(first_ref,))
    partial, partial_path = _pending_receipt(second_wave.value, output_root)
    assert partial["acceptedCount"] == 1 and partial["pendingCount"] == 1
    assert partial["acquisitionManifestRef"] == "manifests/acquisition.json"
    first_manifest_bytes = (root / "manifests/acquisition.json").read_bytes()
    partial_receipt_bytes = partial_path.read_bytes()

    second_ref = _record_host_review_result(
        root,
        request_ref=evidences[candidates[1]["candidateId"]]["reviewRequestRef"],
    )

    ready, _ready_path = prepare_supported_api_inputs(
        **options, reviewer_result_refs=(first_ref, second_ref)
    )
    assert ready["status"] == "ready" and ready["acceptedCount"] == 2
    assert ready["acquisitionManifestRef"].startswith("manifests/acquisition-")
    grown = json.loads((root / ready["acquisitionManifestRef"]).read_text())
    assert len(grown["items"]) == 2
    assert (root / "manifests/acquisition.json").read_bytes() == first_manifest_bytes
    assert partial_path.read_bytes() == partial_receipt_bytes
    assert file_sha256(root / "manifests/acquisition.json") == partial[
        "acquisitionManifestSha256"
    ]

    replay, _replay_path = prepare_supported_api_inputs(
        **options, reviewer_result_refs=(first_ref, second_ref)
    )
    assert replay["acquisitionManifestRef"] == ready["acquisitionManifestRef"]


def test_same_raw_bytes_require_fresh_handoff_review_before_governed_rebind(
    tmp_path: Path,
) -> None:
    plan_path, catalog_path, catalog = _plan_and_catalog(tmp_path)
    output_root = tmp_path / "output"
    source_body = _image_bytes()
    # 真实 handoff 文件使 source review identity 生效：跨 handoff 的旧结果必须被拒绝。
    handoff_path = _write(tmp_path / "handoff.json", {"handoffId": "handoff-test"})
    first_options = {
        "handoff_ref": handoff_path,
        "discovery_plan_path": plan_path,
        "metadata_catalog_path": catalog_path,
        "accepted_target": 1,
        "output_root": output_root,
        "reviewer_root": tmp_path,
        "api_fetcher": _api_fetch(_api_payload("File:West Lake.jpg"), []),
        "image_fetcher": _image_fetch(source_body, []),
        "identity_guard": _identity_guard,
        "inventory_check": _inventory_check,
    }
    with pytest.raises(ProfessionalImageSupportedApiInputError) as first_error:
        prepare_supported_api_inputs(**first_options)
    first_pending, first_receipt_path = _pending_receipt(first_error.value, output_root)
    first_root = first_receipt_path.parent.parent
    first_evidence = json.loads(
        (first_root / first_pending["items"][0]["evidenceRef"]).read_text()
    )
    first_request = first_root / first_evidence["reviewRequestRef"]
    old_result_ref = _record_host_review_result(
        first_root, request_ref=first_evidence["reviewRequestRef"]
    )

    fresh = dict(catalog)
    fresh.update(
        sourceRevision="sha256:" + "6" * 64,
        sourceDigest="sha256:" + "7" * 64,
        entityCatalogDigest="sha256:" + "8" * 64,
    )
    stable = {
        key: value
        for key, value in fresh.items()
        if key not in {"schema", "catalogId", "catalogDigest"}
    }
    fresh["catalogDigest"] = _digest(stable)
    fresh["catalogId"] = "professional-image-supported-api-metadata-" + fresh["catalogDigest"][7:23]
    fresh_catalog_path = _write(tmp_path / "metadata-rebind.json", fresh)
    rebound_options = {
        **first_options,
        "metadata_catalog_path": fresh_catalog_path,
        "api_fetcher": _api_fetch(_api_payload("File:West Lake.jpg"), []),
        "image_fetcher": _image_fetch(source_body, []),
    }
    with pytest.raises(
        ProfessionalImageSupportedApiInputError,
        match="identity differs from handoff",
    ):
        prepare_supported_api_inputs(
            **{**rebound_options, "reviewer_root": first_root},
            reviewer_result_refs=(old_result_ref,),
        )
    first_asset = first_root / first_evidence["originalAssetRef"]
    first_asset.write_bytes(b"tampered")
    with pytest.raises(ProfessionalImageSupportedApiInputError) as sha_drift:
        prepare_supported_api_inputs(**rebound_options)
    sha_drift_receipt, _sha_drift_path = _pending_receipt(
        sha_drift.value, output_root
    )
    assert sha_drift_receipt["items"][0]["failureCode"] == "DATA.SOURCE.REBIND_ASSET_SHA_DRIFT"
    first_asset.write_bytes(source_body)
    with pytest.raises(ProfessionalImageSupportedApiInputError) as rebound_error:
        prepare_supported_api_inputs(**rebound_options)
    rebound_pending, rebound_receipt_path = _pending_receipt(
        rebound_error.value, output_root
    )
    rebound_root = rebound_receipt_path.parent.parent
    rebound_evidence = json.loads(
        (rebound_root / rebound_pending["items"][0]["evidenceRef"]).read_text()
    )
    rebound_request = rebound_root / rebound_evidence["reviewRequestRef"]
    assert rebound_evidence["contentSha256"] == first_evidence["contentSha256"]
    assert rebound_request != first_request
    assert file_sha256(rebound_request) != file_sha256(first_request)
    new_result_ref = _record_host_review_result(
        rebound_root, request_ref=rebound_evidence["reviewRequestRef"]
    )
    rebound, _rebound_path = prepare_supported_api_inputs(
        **{**rebound_options, "reviewer_root": rebound_root},
        reviewer_result_refs=(new_result_ref,),
    )
    assert rebound["acceptedCount"] == 1
    assert rebound["pendingCount"] == rebound["blockedCount"] == 0


def test_rebind_rejects_source_rights_entity_and_prior_asset_sha_drift(
    tmp_path: Path,
) -> None:
    prior_evidence = {
        "provider": "wikimedia_commons",
        "providerAssetId": "1",
        "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:West_Lake.jpg",
        "originalAssetUrl": "https://upload.wikimedia.org/west-lake.png",
        "creator": "Travel Photographer",
        "license": "CC BY-SA 4.0",
        "licenseVersion": "4.0",
        "attributionText": "Travel Photographer · Wikimedia Commons · CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    }
    prior_request = {
        "entityBinding": {
            "entityId": "西湖",
            "observedEntityId": "西湖",
        },
    }
    candidate = {
        "provider": "wikimedia_commons",
        "providerAssetId": "1",
        "entityId": "西湖",
        "observedEntityId": "西湖",
    }
    meta = {
        key: value
        for key, value in prior_evidence.items()
        if key not in {"provider", "providerAssetId"}
    }
    for field, value in (
        ("entityId", "杭州"),
        ("license", "CC BY-ND 4.0"),
        ("sourcePageUrl", "https://commons.wikimedia.org/wiki/File:Drift.jpg"),
    ):
        changed_candidate = dict(candidate)
        changed_meta = dict(meta)
        if field in changed_candidate:
            changed_candidate[field] = value
        else:
            changed_meta[field] = value
        with pytest.raises(
            ProfessionalImageSupportedApiInputError, match="REBIND_IDENTITY_DRIFT"
        ):
            supported_input._assert_rebindable_provenance(
                candidate=changed_candidate,
                meta=changed_meta,
                evidence=prior_evidence,
                request=prior_request,
            )


def test_reviewer_result_cannot_drift_from_frozen_request(tmp_path: Path) -> None:
    file_title = "File:West Lake.jpg"
    plan_path, catalog_path, _catalog = _plan_and_catalog(tmp_path, file_title=file_title)
    output_root = tmp_path / "output"
    options = {
        "handoff_ref": tmp_path / "handoff.json", "discovery_plan_path": plan_path,
        "metadata_catalog_path": catalog_path, "accepted_target": 1,
        "output_root": output_root, "reviewer_root": tmp_path,
        "api_fetcher": _api_fetch(_api_payload(file_title), []),
        "image_fetcher": _image_fetch(_image_bytes(), []),
        "identity_guard": _identity_guard, "inventory_check": _inventory_check,
    }
    with pytest.raises(ProfessionalImageSupportedApiInputError) as captured:
        prepare_supported_api_inputs(**options)
    pending, pending_path = _pending_receipt(captured.value, output_root)
    root = pending_path.parent.parent
    evidence = json.loads((root / pending["items"][0]["evidenceRef"]).read_text())
    reviewer_ref = _record_host_review_result(
        root, request_ref=evidence["reviewRequestRef"]
    )
    result_path = root / reviewer_ref
    result = json.loads(result_path.read_text())
    result["requestDigest"] = "sha256:" + "f" * 64
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(ProfessionalImageSupportedApiInputError, match="resultDigest drift"):
        prepare_supported_api_inputs(
            **{**options, "reviewer_root": root}, reviewer_result_refs=(reviewer_ref,)
        )


def test_task_cli_exposes_only_physical_inputs_without_semantic_verdicts() -> None:
    from content.execution.handler import register_parser

    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="root", required=True))
    args = parser.parse_args([
        "task", "acquire-images",
        "--manifest", "/tmp/manifest.json",
        "--handoff-ref", "/tmp/handoff.json",
    ])
    assert args.manifest == "/tmp/manifest.json"
    assert args.handoff_ref == "/tmp/handoff.json"
    assert not hasattr(args, "verdict")
    assert not hasattr(args, "watermark_status")
    # 语义准备/复核不再挂在公开 task 面：宿主只能经 host source review 单轨录结果。
    with pytest.raises(SystemExit):
        parser.parse_args([
            "task", "prepare-image-supported-api-input",
            "--handoff-ref", "/tmp/handoff.json",
        ])
