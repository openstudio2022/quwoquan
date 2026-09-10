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
        "usageScope": "production",
        "decision": "approved" if passed else "rejected",
        "issues": list(issues or []),
    }


def _review(root: Path, *, extra_rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    review = {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "decision": "approved",
        "draft": {"ref": "4.draft/image_work.json", "digest": "sha256:" + "1" * 64},
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [_rights_row(), *(extra_rows or [])],
    }
    _write(root / "5.review/content_review.json", review)
    return review


def test_approved_content_review_keeps_asset_rights_issues_as_recorded_facts() -> None:
    """spec_ref: multi-carrier-release/GWT-020 — 逐资产权利结论是记录事实，不牵连对象 decision。"""
    review = {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "decision": "approved",
        "draft": {"ref": "4.draft/image_work.json", "digest": "sha256:" + "1" * 64},
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [_rights_row(passed=False, issues=["unresolved rights"])],
    }
    assert_valid(review, "content", "content_review")

    with pytest.raises(ValueError):
        assert_valid({**review, "blockingIssues": ["missing evidence"]}, "content", "content_review")


def test_review_authority_requires_exact_unique_asset_set_and_digest(tmp_path: Path) -> None:
    content_review = _review(tmp_path)
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
        source_assets={ASSET_REF: source_asset},
    )
    assert binding["digest"] == _digest(tmp_path / "5.review/content_review.json")
    assert binding["usageScope"] == "production"

    duplicate = _rights_row()
    duplicate_review = {**content_review, "assetRights": [_rights_row(), duplicate]}
    _write(tmp_path / "5.review/content_review.json", duplicate_review)
    with pytest.raises(ObjectTransactionError, match="unique"):
        validate_review_authority(
            review_root=tmp_path / "5.review",
            manifest={"contentType": "image", "assets": [{"assetId": "cover", "sourceAssetRef": ASSET_REF}]},
            object_kind="posts",
            execution_id=EXECUTION_ID,
            object_ref=TARGET_REF,
            source_assets={ASSET_REF: source_asset},
        )


def test_text_only_article_allows_explicit_empty_rights_set(tmp_path: Path) -> None:
    _write(tmp_path / "5.review/content_review.json", {
        "schema": "quwoquan_data.content_review", "stage": "5.review",
        "executionId": EXECUTION_ID, "objectRef": TARGET_REF, "decision": "approved",
        "draft": {"ref": "4.draft/draft.article.md", "digest": "sha256:" + "1" * 64},
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [], "assetRights": [],
    })
    binding = validate_review_authority(
        review_root=tmp_path / "5.review",
        manifest={"contentType": "article", "publishMediaMode": "text_only", "assets": []},
        object_kind="posts", execution_id=EXECUTION_ID, object_ref=TARGET_REF,
        source_assets={},
    )
    assert binding["usageScope"] == "production"


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False, "originalCreatorName": "Creator", "platform": "Commons",
        "sourcePostUrl": "https://example.test/post", "originalAssetUrl": "https://example.test/asset",
        "attributionText": "Creator / Commons", "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "verified", "publicationAdmission": "production_release",
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
    _write(root / "manifest.json", {"assets": [{
        "assetId": "cover", "objectKey": object_key, "sha256": digest,
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
    }]})
    with pytest.raises(ObjectTransactionError, match="CONTENT_LIBRARY_BINDING_INVALID"):
        from content.release.canonical.content_pool_handoff import project_content_library_bindings

        project_content_library_bindings(
            json.loads((root / "manifest.json").read_text(encoding="utf-8"))["assets"]
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
    review = _write(root / "content_review.json", {"decision": "approved"})
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
    assets = [{
        "assetId": "cover", "objectKey": object_key, "sha256": digest, "bytes": 8,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
        "derivativeBinding": derivative,
    }]
    _write(root / "manifest.json", {
        "contentId": "content-asset-facts", "version": 1,
        "executionId": EXECUTION_ID, "contentType": "image", "generator": "agent",
        "creatorProfileId": "creator", "variantPurpose": "original", "status": "active",
        "tagRefs": [], "assets": assets,
        "sourceIdentity": {**identity, "identityDigest": source_identity_digest(identity)},
        "sourceAttribution": _attribution(),
        "admission": {
            "processResult": "completed", "qualityResult": "passed", "usageScope": "production",
            "rightsResult": "passed", "rightsAuthorityRef": f"posts/image/asset-facts/1/content_review.json",
            "rightsAuthorityDigest": _digest(review), "evidenceRef": "content_review.json",
            "evidenceDigest": _digest(review),
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
    assert content_library["bindingRef"] == query.as_document()["refs"]["manifestRef"]
    assert content_library["bindings"] == expected_bindings
    assert "bytes" not in content_library["bindings"][0]
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
    review_path = _write(root / "content_review.json", {"decision": "approved"})
    source_digest = "sha256:" + "2" * 64
    entity_digest = "sha256:" + "3" * 64
    identity = {
        "executionId": EXECUTION_ID,
        "sourceRevision": content_source_revision(source_digest=source_digest, entity_catalog_digest=entity_digest),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_digest,
    }
    asset_digest = "sha256:" + "a" * 64
    assets = [{
        "assetId": "cover",
        "objectKey": "media/objects/sha256/aa/aa/" + "a" * 64 + ".jpg",
        "sha256": asset_digest,
        "sourceAssetRefs": [ASSET_REF],
        "acquisitionReceiptRefs": ["receipts/acquired.json"],
    }]
    manifest = {
        "contentId": "content-rights", "version": 1, "executionId": EXECUTION_ID, "contentType": "image", "generator": "agent",
        "creatorProfileId": "creator", "variantPurpose": "original", "status": "active",
        "tagRefs": [], "assets": assets,
        "sourceIdentity": {**identity, "identityDigest": source_identity_digest(identity)},
        "sourceAttribution": _attribution(),
        "admission": {
            "processResult": "completed", "qualityResult": "passed", "usageScope": "production",
            "rightsResult": "passed", "rightsAuthorityRef": "posts/image/rights/1/content_review.json",
            "rightsAuthorityDigest": _digest(review_path), "evidenceRef": "content_review.json", "evidenceDigest": _digest(review_path),
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


def test_binding_projection_preserves_asset_and_source_order() -> None:
    """spec_ref: multi-carrier-release/GWT-032 — 查询只投影，不重排资产或来源。"""
    from content.release.canonical.content_pool_handoff import project_content_library_bindings

    digest = "sha256:" + "a" * 64
    assets = [{
        "assetId": asset_id,
        "objectKey": f"media/objects/sha256/aa/aa/{'a' * 64}.jpg",
        "sha256": digest, "bytes": 8, "caption": "仅展示字段",
        "sourceAssetRefs": ["sources/z.jpg", "sources/a.jpg"],
        "acquisitionReceiptRefs": ["receipts/z.json", "receipts/a.json"],
    } for asset_id in ("z-last-lexically", "a-first-lexically")]
    rows = [row.as_document() for row in project_content_library_bindings(assets)]
    assert [row["assetId"] for row in rows] == [row["assetId"] for row in assets]
    assert rows[0]["sourceAssetRefs"] == assets[0]["sourceAssetRefs"]
    assert rows[0]["acquisitionReceiptRefs"] == assets[0]["acquisitionReceiptRefs"]
    assert "caption" not in rows[0]
    assert "bytes" not in rows[0]


def test_query_creator_does_not_fall_back_to_author_id() -> None:
    """spec_ref: multi-carrier-release/GWT-032 — authorId 不替代显式 creatorProfileId。"""
    from content.release.canonical.content_pool_handoff import _creator_ref

    with pytest.raises(ObjectTransactionError, match="creatorProfileId missing"):
        _creator_ref({"authorId": "old-author"})
    assert _creator_ref({"creatorProfileId": "explicit", "authorId": "other"}) == "explicit"


@pytest.mark.parametrize("field", ["assetRefsRef", "creatorRefsRef", "tagRefsRef"])
def test_query_rejects_retired_pointer_even_with_manifest_assets(tmp_path: Path, field: str) -> None:
    """spec_ref: multi-carrier-release/GWT-032 — 普通 reader 不接受旧指针。"""
    from content.release.canonical.content_pool_handoff import _content_library_bindings

    manifest = {"contentType": "article", "publishMediaMode": "text_only", "assets": [], field: "old.json"}
    _write(tmp_path / "manifest.json", manifest)
    with pytest.raises(ObjectTransactionError, match="retired sidecar pointer"):
        _content_library_bindings(tmp_path, manifest)
