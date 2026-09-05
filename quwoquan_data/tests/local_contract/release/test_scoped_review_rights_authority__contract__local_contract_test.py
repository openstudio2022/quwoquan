from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from content.release.canonical.content_pool_handoff import project_content_pool_handoff
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
    is_pool_record_admitted,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import source_identity_digest
from core.source_digest import content_source_revision
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.review_rights_binding import validate_review_authority
from core.schema import assert_valid

EXECUTION_ID = "20260903--travel-image-rights--test--pilot-001"
TARGET_REF = "posts/image/画报/西湖/1"
ASSET_REF = "sources/commons/assets/cover.jpg"


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _rights_row(*, passed: bool = True, issues: list[str] | None = None) -> dict[str, object]:
    return {
        "assetRef": ASSET_REF,
        "sourceUrl": "https://example.test/cover.jpg",
        "license": "CC BY 4.0",
        "termsUrl": "https://example.test/terms",
        "authorizationProof": "https://example.test/proof",
        "usageScope": "commercial",
        "passed": passed,
        "issues": list(issues or []),
    }


def _review(root: Path, *, extra_rows: list[dict[str, object]] | None = None) -> tuple[dict[str, object], dict[str, object]]:
    media = {
        "schema": "quwoquan_data.media_ref_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "passed": True,
        "mediaIssues": [],
        "referenceIssues": [],
        "rightsReviews": [_rights_row(), *(extra_rows or [])],
    }
    media_path = _write(root / "5.review/media_ref_review.json", media)
    attestation = {
        "schema": "quwoquan_data.review_attestation",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "executionBinding": "frozen",
        "objectRef": TARGET_REF,
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {
            "status": "passed",
            "actor": {
                "host": "cursor",
                "sessionId": "review-session",
                "modelFamily": "gpt",
                "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "review-run"},
            },
        },
        "mediaRefReview": {
            "status": "passed",
            "issues": [],
            "ref": "5.review/media_ref_review.json",
            "digest": _digest(media_path),
        },
        "repair": {"status": "not_required"},
    }
    _write(root / "5.review/attestation.json", attestation)
    return media, attestation


def test_passed_media_review_requires_empty_issues_per_asset() -> None:
    media = {
        "schema": "quwoquan_data.media_ref_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "passed": True,
        "mediaIssues": [],
        "referenceIssues": [],
        "rightsReviews": [_rights_row(passed=False, issues=["unresolved rights"])],
    }
    with pytest.raises(ValueError):
        assert_valid(media, "content", "media_ref_review")


def test_review_authority_requires_exact_unique_asset_set_and_digest(tmp_path: Path) -> None:
    _media, attestation = _review(tmp_path)
    source_asset = {
        "sourceUrl": "https://example.test/cover.jpg",
        "license": "CC BY 4.0",
        "termsUrl": "https://example.test/terms",
        "authorizationProof": "https://example.test/proof",
    }
    binding = validate_review_authority(
        review_root=tmp_path / "5.review",
        manifest={"contentType": "image", "topicId": TARGET_REF, "assets": [{"assetId": "cover", "sourceAssetRef": ASSET_REF}]},
        object_kind="posts",
        execution_id=EXECUTION_ID,
        object_ref=TARGET_REF,
        attestation=attestation,
        source_assets={ASSET_REF: source_asset},
    )
    assert binding["digest"] == attestation["mediaRefReview"]["digest"]
    assert binding["usageScope"] == "commercial"

    duplicate = _rights_row()
    duplicate_media = {**_media, "rightsReviews": [_rights_row(), duplicate]}
    duplicate_path = _write(tmp_path / "5.review/media_ref_review.json", duplicate_media)
    duplicate_attestation = {
        **attestation,
        "mediaRefReview": {
            "status": "passed", "issues": [],
            "ref": "5.review/media_ref_review.json", "digest": _digest(duplicate_path),
        },
    }
    with pytest.raises(ObjectTransactionError, match="unique"):
        validate_review_authority(
            review_root=tmp_path / "5.review",
            manifest={"contentType": "image", "assets": [{"assetId": "cover", "sourceAssetRef": ASSET_REF}]},
            object_kind="posts",
            execution_id=EXECUTION_ID,
            object_ref=TARGET_REF,
            attestation=duplicate_attestation,
            source_assets={ASSET_REF: source_asset},
        )


def test_text_only_article_allows_explicit_empty_rights_set(tmp_path: Path) -> None:
    media_path = _write(tmp_path / "5.review/media_ref_review.json", {
        "schema": "quwoquan_data.media_ref_review", "stage": "5.review",
        "executionId": EXECUTION_ID, "objectRef": TARGET_REF, "passed": True,
        "mediaIssues": [], "referenceIssues": [], "rightsReviews": [],
    })
    attestation = {
        "mediaRefReview": {"status": "passed", "issues": [], "ref": "5.review/media_ref_review.json", "digest": _digest(media_path)}
    }
    binding = validate_review_authority(
        review_root=tmp_path / "5.review",
        manifest={"contentType": "article", "publishMediaMode": "text_only", "assets": []},
        object_kind="posts", execution_id=EXECUTION_ID, object_ref=TARGET_REF,
        attestation=attestation, source_assets={},
    )
    assert binding["usageScope"] == "research"


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False, "originalCreatorName": "Creator", "platform": "Commons",
        "sourcePostUrl": "https://example.test/post", "originalAssetUrl": "https://example.test/asset",
        "attributionText": "Creator / Commons", "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "verified", "publicationAdmission": "commercial_release",
        "watermarkStatus": "absent", "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required", "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-09-03T00:00:00Z", "takedownPolicy": "notice_and_takedown",
        "derivedModifications": [], "authorizationProofUrl": "https://example.test/proof",
        "termsUrl": "https://example.test/terms",
    }


def test_content_pool_query_rejects_asset_binding_missing_source_refs(tmp_path: Path) -> None:
    root = tmp_path / "publish/posts/image/missing-source/1"
    digest = "sha256:" + "a" * 64
    object_key = f"media/objects/sha256/aa/aa/{'a' * 64}.jpg"
    _write(root / "asset.refs.json", {"assets": [{
        "assetId": "cover", "objectKey": object_key, "sha256": digest,
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
    }]})
    with pytest.raises(ObjectTransactionError, match="CONTENT_LIBRARY_BINDING_INVALID"):
        from content.release.canonical.content_pool_handoff import project_content_library_bindings

        project_content_library_bindings(
            json.loads((root / "asset.refs.json").read_text(encoding="utf-8"))["assets"]
        )


def test_content_pool_query_rejects_empty_acquisition_receipts(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    object_key = f"media/objects/sha256/aa/aa/{'a' * 64}.jpg"
    from content.release.canonical.content_pool_handoff import (
        project_content_library_bindings,
    )

    with pytest.raises(ObjectTransactionError, match="CONTENT_LIBRARY_BINDING_INVALID"):
        project_content_library_bindings([{
            "assetId": "cover",
            "objectKey": object_key,
            "sha256": digest,
            "sourceAssetRefs": [ASSET_REF],
            "acquisitionReceiptRefs": [],
        }])


def test_content_pool_query_projects_complete_asset_hard_facts(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    root = publish / "posts/image/asset-facts/1"
    attestation = _write(root / "attestation.json", {"decision": "approved"})
    review = _write(root / "5.review/media_ref_review.json", {"passed": True})
    digest = "sha256:" + "a" * 64
    source_digest = "sha256:" + "2" * 64
    entity_digest = "sha256:" + "3" * 64
    identity = {
        "executionId": EXECUTION_ID,
        "sourceRevision": content_source_revision(
            source_digest=source_digest, entity_catalog_digest=entity_digest
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_digest,
    }
    derivative = {
        "originalSha256": "sha256:" + "b" * 64,
        "originalBytes": 10,
        "originalMimeType": "image/jpeg",
        "policy": "source_unit_asset_budget",
        "profile": "image",
        "derivedSha256": digest,
        "derivedBytes": 8,
        "derivedMimeType": "image/webp",
        "derivedExtension": ".webp",
    }
    object_key = f"media/objects/sha256/{'a' * 2}/{'a' * 2}/{'a' * 64}.webp"
    _write(root / "asset.refs.json", {"assets": [{
        "assetId": "cover", "objectKey": object_key, "sha256": digest, "bytes": 8,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
        "derivativeBinding": derivative,
    }]})
    _write(root / "manifest.json", {
        "contentId": "content-asset-facts", "version": 1,
        "executionId": EXECUTION_ID, "contentType": "image", "generator": "agent",
        "authorId": "creator", "variantPurpose": "original", "status": "active",
        "assetRefsRef": "asset.refs.json", "assets": [],
        "sourceIdentity": {**identity, "identityDigest": source_identity_digest(identity)},
        "sourceAttribution": _attribution(),
        "admission": {
            "processResult": "completed", "qualityResult": "passed", "usageScope": "commercial",
            "rightsResult": "passed", "rightsAuthorityRef": f"posts/image/asset-facts/1/5.review/media_ref_review.json",
            "rightsAuthorityDigest": _digest(review), "evidenceRef": "attestation.json",
            "evidenceDigest": _digest(attestation),
        },
    })
    record = build_canonical_pool_record(
        object_root=root, object_type="content", object_ref="image/asset-facts/1"
    )
    append_pool_record(object_root=root, record=record)

    query = project_content_pool_handoff(
        publish_root=publish, object_type="content", object_ref="image/asset-facts/1"
    )
    assert query is not None
    content_library = query.as_document()["contentLibrary"]
    expected_bindings = [{
        "assetId": "cover", "objectKey": object_key, "sha256": digest,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
        "derivativeBinding": derivative,
    }]
    assert content_library["bindings"] == expected_bindings
    expected_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            expected_bindings,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert content_library["bindingDigest"] == expected_digest

    changed_hard_facts = json.loads(json.dumps(expected_bindings))
    changed_hard_facts[0]["acquisitionReceiptRefs"] = ["receipts/other.json"]
    changed_hard_facts[0]["derivativeBinding"]["originalSha256"] = (
        "sha256:" + "c" * 64
    )
    changed_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            changed_hard_facts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert changed_digest != content_library["bindingDigest"]


def test_content_pool_query_rejects_derivative_binding_tamper(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    raw_bindings = [{
        "assetId": "cover",
        "objectKey": f"media/objects/sha256/aa/aa/{'a' * 64}.webp",
        "sha256": digest,
        "bytes": 8,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
        "derivativeBinding": {
            "originalSha256": "sha256:" + "b" * 64,
            "originalBytes": 10,
            "originalMimeType": "image/jpeg",
            "policy": "source_unit_asset_budget",
            "profile": "image",
            "derivedSha256": "sha256:" + "c" * 64,
            "derivedBytes": 8,
            "derivedMimeType": "image/webp",
            "derivedExtension": ".webp",
        },
    }]
    from content.release.canonical.content_pool_handoff import (
        project_content_library_bindings,
    )

    with pytest.raises(ObjectTransactionError, match="CONTENT_LIBRARY_BINDING_INVALID"):
        project_content_library_bindings(raw_bindings)


def test_pool_record_and_query_project_bound_rights_authority(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    root = publish / "posts/image/rights/1"
    review_path = _write(root / "5.review/media_ref_review.json", {"passed": True})
    attestation = _write(root / "attestation.json", {"decision": "approved"})
    source_digest = "sha256:" + "2" * 64
    entity_digest = "sha256:" + "3" * 64
    identity = {
        "executionId": EXECUTION_ID,
        "sourceRevision": content_source_revision(source_digest=source_digest, entity_catalog_digest=entity_digest),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_digest,
    }
    asset_digest = "sha256:" + "a" * 64
    _write(root / "asset.refs.json", {"assets": [{
        "assetId": "cover",
        "objectKey": "media/objects/sha256/aa/aa/" + "a" * 64 + ".jpg",
        "sha256": asset_digest,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
    }]})
    manifest = {
        "contentId": "content-rights", "version": 1, "executionId": EXECUTION_ID, "contentType": "image", "generator": "agent",
        "authorId": "creator", "variantPurpose": "original", "status": "active",
        "assetRefsRef": "asset.refs.json", "assets": [{"assetId": "cover", "sourceAssetRef": ASSET_REF}],
        "sourceIdentity": {**identity, "identityDigest": source_identity_digest(identity)},
        "sourceAttribution": _attribution(),
        "admission": {
            "processResult": "completed", "qualityResult": "passed", "usageScope": "commercial",
            "rightsResult": "passed", "rightsAuthorityRef": f"{TARGET_REF}/5.review/media_ref_review.json",
            "rightsAuthorityDigest": _digest(review_path), "evidenceRef": "attestation.json", "evidenceDigest": _digest(attestation),
        },
    }
    _write(root / "manifest.json", manifest)
    record = build_canonical_pool_record(object_root=root, object_type="content", object_ref="image/rights/1")
    append_pool_record(object_root=root, record=record)
    assert is_pool_record_admitted(record)
    query = project_content_pool_handoff(publish_root=publish, object_type="content", object_ref="image/rights/1")
    assert query is not None
    assert query.as_document()["admission"]["rightsAuthorityDigest"] == _digest(review_path)

    bad = dict(record, rightsResult="pending")
    assert not is_pool_record_admitted(bad)
