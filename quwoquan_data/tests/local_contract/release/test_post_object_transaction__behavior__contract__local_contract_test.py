"""Approved posts resolve an independently admitted Creator version."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from content.release.canonical import creator_projection, post_promotion, post_transaction
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.content_pool_record import stable_content_id
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_publish_invariants,
)
from content.release.canonical.post_transaction import (
    ObjectTransactionError,
)
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package as _build_post_object_transaction_package,
)
from core.schema import validate_result
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from core.tree_integrity import tree_integrity_stats
from governance.coverage import distribution
from governance.creators.assignment import creator_assignment_from_profile
from content.templates.registry import TemplateRegistry
from PIL import Image

EXECUTION_ID = "20260718--travel-image-cold-start--test-region-a--scale-901"
POST_REF = "image/西湖/光影"
CREATOR_REF = "qwq_creator_landscape_photographer_001"
REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_PUBLISH_ROOT = REPO_ROOT / "quwoquan_data" / "publish"
CREATOR_PROFILE_PATH = (
    REPO_ROOT
    / "quwoquan_data"
    / "control_plane"
    / "governance"
    / "creator_pool"
    / "profiles"
    / "system_builtin"
    / "landscape_photographer.creator.yaml"
)


def _copy_creator_avatar_cas(publish_root: Path) -> None:
    profile = yaml.safe_load(CREATOR_PROFILE_PATH.read_text(encoding="utf-8"))
    avatar = profile.get("avatarAsset") if isinstance(profile, dict) else None
    assert isinstance(avatar, dict)
    object_key = str(avatar.get("objectKey") or "")
    assert object_key
    source = REAL_PUBLISH_ROOT / object_key
    assert source.is_file()
    target = publish_root / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


@pytest.fixture(autouse=True)
def _isolate_creator_avatar_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the referenced creator avatar into this test's isolated CAS root."""
    isolated_publish = tmp_path / "creator-avatar-publish"
    _copy_creator_avatar_cas(isolated_publish)
    monkeypatch.setattr(creator_projection, "PUBLISH_ROOT", isolated_publish)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "Fixture Photographer",
        "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "originalAssetUrl": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
        "attributionText": "Fixture Photographer / CC BY 4.0",
        "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-07-18T04:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
    }


def build_post_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
) -> dict[str, object]:
    """Low-level transaction fixtures pass an explicit frozen intent binding."""

    canonical_ref = object_ref.removeprefix("posts/")
    object_root = execution_root / "posts" / canonical_ref
    manifest = json.loads((object_root / "manifest.json").read_text(encoding="utf-8"))
    content_id = stable_content_id(manifest, canonical_ref)
    review = object_root / "5.review/attestation.json"
    digest = "sha256:" + "a" * 64
    creator_binding = creator_assignment_from_profile(
        TemplateRegistry.load().creators[str(manifest["creatorProfileId"])]
    )
    stable = {
        "schema": "quwoquan_data.pool_delivery_intent",
        "executionId": execution_root.name,
        "carrier": str(manifest["contentType"]),
        "objectRef": canonical_ref,
        "contentObjectDir": f"posts/{canonical_ref}",
        "objectId": content_id,
        "contentId": content_id,
        "version": 1,
        "poolIdentityReservationId": digest,
        "reviewEvidenceRef": review.relative_to(execution_root).as_posix(),
        "reviewEvidenceSha256": "sha256:" + hashlib.sha256(review.read_bytes()).hexdigest(),
        "creatorBindingMode": "manifest_exact",
        "creatorBinding": creator_binding,
        "creatorBindingDigest": _sha(creator_binding),
        "entityTagBindingDigest": digest,
        "sourceAttributionDigest": digest,
        "mediaClosureDigest": digest,
        "transactionId": transaction_id,
        "transactionInputDigest": str(tree_integrity_stats(object_root)["merkleRoot"]),
    }
    intent = {"intentId": _sha(stable), **stable}
    return _build_post_object_transaction_package(
        execution_root=execution_root,
        object_ref=object_ref,
        transaction_id=transaction_id,
        package_root=package_root,
        pool_delivery_intent=intent,
    )


def _force_commercial_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    research_policy = distribution.load_content_distribution_policy()
    commercial_policy = replace(
        research_policy,
        product_lifecycle_state=distribution.ProductLifecycleState.COMMERCIAL,
        release_class=distribution.ReleaseClass.COMMERCIAL,
    )
    monkeypatch.setattr(
        distribution,
        "load_content_distribution_policy",
        lambda: commercial_policy,
    )


def _admit_packaged_creator(package_root: Path, publish_root: Path) -> None:
    package = json.loads(
        (package_root / "object_transaction_package.json").read_text(encoding="utf-8")
    )
    for row in package["closure"]["creatorObjects"]:
        source = package_root / row["packageRef"]
        target = publish_root / "creators" / row["creatorRef"]
        shutil.copytree(source, target)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    execution = tmp_path / "tasks" / EXECUTION_ID
    post = execution / "posts" / POST_REF
    source_asset = post / "assets/cover.jpg"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(30, 80, 140)).save(source_asset)
    digest = "sha256:" + hashlib.sha256(source_asset.read_bytes()).hexdigest()
    transaction_id = (
        f"{EXECUTION_ID}--post-"
        f"{hashlib.sha256(POST_REF.encode('utf-8')).hexdigest()[:12]}"
    )
    target_set = {
        "executionId": EXECUTION_ID,
        "entityCatalogDigest": "sha256:" + "4" * 64,
    }
    target_set_digest = hashlib.sha256(
        json.dumps(
            target_set,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(execution / "0.plan/target_set.json", target_set)
    _write_json(
        execution / "execution_manifest.json",
        {
            "executionId": EXECUTION_ID,
            "createdAt": "2026-07-18T04:00:00Z",
            "sourceDigest": current_source_definition_snapshot().to_document(),
            "executionBundle": current_execution_bundle_identity().to_document(),
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": target_set_digest,
        },
    )
    _write_json(
        execution / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "west-lake-cover",
                    "fileName": "cover.jpg",
                    "url": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                    "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-18T04:00:00Z",
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "licensed_adaptation",
            "researchLane": "image",
        },
    )
    _write_json(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_manifest",
            "vertical": "travel",
            "topicId": "西湖__image_1",
            "contentIdentity": "work",
            "contentId": "qwq_data_west_lake_image_fixture",
            "version": 1,
            "contentType": "image",
            "carrier": "image",
            "title": "西湖光影",
            "caption": "湖岸与长桥的光影",
            "creatorProfileId": CREATOR_REF,
            "sourceAttribution": _source_attribution(),
            "sourceUrls": ["https://commons.wikimedia.org/wiki/File:Example.jpg"],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "assets": [
                {
                    "assetId": "west-lake-cover",
                    "fileName": "assets/cover.jpg",
                    "sourceAssetId": "west-lake-cover",
                    "sourceAssetRef": "sources/commons/assets/cover.jpg",
                    "caption": "西湖光影",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                    "sha256": digest,
                }
            ],
        },
    )
    _write_json(
        post / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "sourceAssetRef": "sources/commons/assets/cover.jpg",
                }
            ]
        },
    )
    _write_json(
        post / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    _write_json(post / "5.review/evidence_index.json", {"evidence": []})
    publish = tmp_path / "publish"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    _copy_creator_avatar_cas(publish)
    package = execution / "evidence/object-transactions" / transaction_id
    return execution, package, publish, transaction_id


def test_post_transaction_resolves_independently_admitted_creator(
    tmp_path: Path,
) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    output = tmp_path / "output"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )

    assert (publish / "posts" / POST_REF / "manifest.json").is_file()
    assert (publish / "creators" / CREATOR_REF / "_creator.json").is_file()
    published_manifest = json.loads(
        (publish / "posts" / POST_REF / "manifest.json").read_text(encoding="utf-8")
    )
    assert datetime.fromisoformat(published_manifest["publishedAt"]).tzinfo is not None
    assert published_manifest["sourceTaskId"] == EXECUTION_ID
    assert published_manifest["payloadDigest"].startswith("sha256:")
    assert published_manifest["sourceIdentity"]["executionId"] == EXECUTION_ID
    assert (
        published_manifest["sourceDigest"]
        == current_source_definition_snapshot().to_document()
    )
    assert (
        published_manifest["executionBundle"]
        == current_execution_bundle_identity().to_document()
    )
    assert validate_publish_invariants(publish)["status"] == "passed"


def test_post_transaction_same_key_requires_same_payload_digest(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    first = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    replay = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    assert replay == first

    content_path = execution / "posts" / POST_REF / "content.md"
    content_path.write_text("# changed payload\n", encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="IDEMPOTENCY_CONFLICT"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_applied_post_pool_digest_repair_appends_record_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(post_transaction, "PUBLISH_ROOT", tmp_path / "identity-publish")
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    canonical = publish / "posts" / POST_REF
    shutil.copytree(package / "object", canonical)
    for root in (package / "object", canonical):
        record_path = root / "_pool/versions/1.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["payloadDigest"] = record["canonicalObjectDigest"] = (
            "sha256:" + "0" * 64
        )
        _write_json(record_path, record)

    assert post_promotion._repair_applied_pool_record_drift(
        package_root=package,
        canonical_post=canonical,
        canonical_ref=POST_REF,
    )
    from content.release.canonical.content_pool_record import latest_pool_record

    repaired = latest_pool_record(canonical, "content")
    assert repaired is not None
    assert repaired["recordSequence"] == 2
    assert repaired["contentVersion"] == 1


def test_text_only_post_transaction_does_not_require_media_asset(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contentType"] = "article"
    manifest["carrier"] = "article"
    manifest["publishMediaMode"] = "text_only"
    manifest["assets"] = []
    _write_json(manifest_path, manifest)

    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    asset_refs = json.loads(
        (package / "object/asset.refs.json").read_text(encoding="utf-8")
    )
    assert asset_refs == {"assets": []}
    assert transaction["publishMediaMode"] == "text_only"
    assert transaction["closure"]["casRefs"] == []
    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    assert rights == {
        "schema": "quwoquan_data.asset_rights_closure",
        "publishMediaMode": "text_only",
        "assets": [],
    }
    _admit_packaged_creator(package, publish)
    from content.release.canonical.object_transaction_contract import _verify_package

    verified = _verify_package(
        package,
        canonical_root=publish,
        require_target_absent=False,
    )
    assert verified["rights"]["assets"] == []


def test_pre_audit_text_only_package_adds_missing_media_mode_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        contentType="article",
        carrier="article",
        publishMediaMode="text_only",
        assets=[],
    )
    _write_json(manifest_path, manifest)
    first = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    package_path = package / "object_transaction_package.json"
    legacy = json.loads(package_path.read_text(encoding="utf-8"))
    legacy.pop("publishMediaMode")
    _write_json(package_path, legacy)
    rights_path = package / "object/rights.json"
    legacy_rights = json.loads(rights_path.read_text(encoding="utf-8"))
    legacy_rights.pop("publishMediaMode")
    _write_json(rights_path, legacy_rights)
    monkeypatch.setattr(post_transaction, "OUTPUT_ROOT", tmp_path / "output")

    resumed = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    assert {
        key: value
        for key, value in resumed.items()
        if key != "objectClosureDigest"
    } == {
        key: value
        for key, value in first.items()
        if key != "objectClosureDigest"
    }
    assert json.loads(package_path.read_text(encoding="utf-8")) == resumed
    assert json.loads(rights_path.read_text(encoding="utf-8"))["publishMediaMode"] == "text_only"
    from content.release.canonical.content_pool_record import latest_pool_record

    record = latest_pool_record(package / "object", "content")
    assert record is not None
    assert record["payloadDigest"] == record["canonicalObjectDigest"]


def test_media_post_transaction_rejects_empty_cas_closure(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    assert transaction["publishMediaMode"] == "embedded_media"
    document_path = package / "object_transaction_package.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["closure"]["casRefs"] = []
    _write_json(document_path, document)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="casRefs"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_media_post_transaction_rejects_empty_rights_closure(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    rights_path = package / "object/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"] = []
    _write_json(rights_path, rights)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="minItems 1"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_text_only_package_rejects_media_mode_drift(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        contentType="article",
        carrier="article",
        publishMediaMode="text_only",
        assets=[],
    )
    _write_json(manifest_path, manifest)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    document_path = package / "object_transaction_package.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    packaged_manifest_path = package / "object/manifest.json"
    packaged_manifest = json.loads(
        packaged_manifest_path.read_text(encoding="utf-8")
    )
    packaged_manifest.pop("publishMediaMode")
    _write_json(packaged_manifest_path, packaged_manifest)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="publishMediaMode"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_text_only_package_rejects_missing_rights_media_mode(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        contentType="article",
        carrier="article",
        publishMediaMode="text_only",
        assets=[],
    )
    _write_json(manifest_path, manifest)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    rights_path = package / "object/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights.pop("publishMediaMode")
    _write_json(rights_path, rights)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="publishMediaMode"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda manifest: manifest.pop("executionBundle"),
        lambda manifest: manifest["executionBundle"].update(
            inputs=["quwoquan_data/scripts/other"]
        ),
        lambda manifest: manifest["sourceDigest"].update(
            inputs=["quwoquan_data/control_plane/other"]
        ),
    ),
)
def test_post_transaction_v2_source_identity_requires_exact_snapshot_and_bundle_inputs(
    tmp_path: Path,
    mutate,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        ObjectTransactionError,
        match="valid frozen sourceDigest",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_travel_commercial_asset_blocks_unverified_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_commercial_lifecycle(monkeypatch)
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    asset["creator"] = ""
    asset["license"] = ""
    asset["termsUrl"] = ""
    asset["authorizationProof"] = ""
    asset["rightsAuditStatus"] = "unverified"
    asset["rightsAuditIssues"] = [
        "imageRights: missing required field license",
        "imageRights: missing required field credit",
    ]
    _write_json(manifest_path, manifest)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_asset = source_index["assets"][0]
    source_asset["authorizationProof"] = ""
    source_asset["termsUrl"] = ""
    source_asset["creator"] = ""
    source_asset["license"] = ""
    source_asset["rightsAuditStatus"] = "unverified"
    source_asset["rightsAuditIssues"] = list(asset["rightsAuditIssues"])
    _write_json(source_index_path, source_index)

    with pytest.raises(
        ObjectTransactionError,
        match="权利审计仍有未关闭问题",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_travel_commercial_asset_blocks_unverified_collection_page_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_commercial_lifecycle(monkeypatch)
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceUrls"] = ["https://content.example.test/article/landscape"]
    asset = manifest["assets"][0]
    asset.pop("sourceAssetId", None)
    asset["collectionPageUrl"] = "https://travel.example.test/article/landscape"
    asset["creator"] = ""
    asset["license"] = ""
    asset["termsUrl"] = ""
    asset["authorizationProof"] = ""
    asset["rightsAuditStatus"] = "unverified"
    asset["rightsAuditIssues"] = ["imageRights: source terms not yet verified"]
    _write_json(manifest_path, manifest)
    source_refs_path = execution / "posts" / POST_REF / "1.download/source_refs.json"
    source_refs = json.loads(source_refs_path.read_text(encoding="utf-8"))
    source_refs["sources"][0]["sourceUrl"] = (
        "https://content.example.test/article/landscape"
    )
    _write_json(source_refs_path, source_refs)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_asset = source_index["assets"][0]
    source_asset.update(
        {
            "authorizationProof": "",
            "termsUrl": "",
            "creator": "",
            "license": "",
            "rightsAuditStatus": "unverified",
            "rightsAuditIssues": ["imageRights: source terms not yet verified"],
        }
    )
    _write_json(source_index_path, source_index)

    with pytest.raises(
        ObjectTransactionError,
        match="权利审计仍有未关闭问题",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_canonical_source_catalog_preserves_factual_reference_only_truth(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "factual_reference_only",
            "researchLane": "image",
        },
    )

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    catalog = json.loads(
        (package / "object/source_catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["sources"] == [
        {
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "sourceUseMode": "factual_reference_only",
        }
    ]
    rights = json.loads(
        (package / "object/rights.json").read_text(encoding="utf-8")
    )
    assert rights["assets"][0]["sourceUseMode"] == "factual_reference_only"
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_verified_research_asset_projects_final_editorial_rights(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "rights_audit_only",
            "rightsMode": "rights_audit_only",
            "researchLane": "video",
        },
    )
    index_path = execution / "sources/commons/assets/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["assets"][0]["usageScope"] = "internal_reference"
    _write_json(index_path, index)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["usageScope"] = "internal_reference"
    _write_json(manifest_path, manifest)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    assert rights["assets"][0]["sourceUseMode"] == "licensed_adaptation"
    assert rights["assets"][0]["usageScope"] == "editorial"
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_research_asset_without_authorization_proof_stays_audit_only(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "rights_audit_only",
            "rightsMode": "rights_audit_only",
            "researchLane": "video",
        },
    )
    index_path = execution / "sources/commons/assets/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["assets"][0]["authorizationProof"] = ""
    _write_json(index_path, index)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["authorizationProof"] = ""
    _write_json(manifest_path, manifest)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    asset = rights["assets"][0]
    assert asset["sourceUseMode"] == "rights_audit_only"
    assert asset["rightsAuditStatus"] == "unverified"
    assert asset["authorizationProof"] == ""
    assert asset["rightsAuditIssues"] == [
        "authorizationProof: not independently verified for research distribution"
    ]
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_canonical_transaction_rejects_source_use_mode_upgrade(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "factual_reference_only",
            "researchLane": "image",
        },
    )
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceUseMode"] = "licensed_adaptation"
    _write_json(manifest_path, manifest)

    with pytest.raises(
        ObjectTransactionError,
        match="sourceUseMode 与 source unit 真值冲突",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_canonical_transaction_rejects_rights_policy_as_source_use_mode(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "attribution_no_watermark",
            "rightsMode": "attribution_no_watermark",
            "researchLane": "video",
        },
    )

    with pytest.raises(
        ObjectTransactionError,
        match="sourceUseMode 非法或缺失",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_video_transaction_closes_poster_cas_and_path_bound_source_rights(
    tmp_path: Path,
) -> None:
    execution_id = "20260718--travel-video-cold-start--test-region-a--scale-902"
    post_ref = "video/西湖/光影短片"
    execution = tmp_path / "tasks" / execution_id
    post = execution / "posts" / post_ref
    source_dir = execution / "sources/wiki/assets"
    source_dir.mkdir(parents=True)
    frame = source_dir / "frame-1.jpg"
    Image.new("RGB", (1280, 720), color=(35, 90, 150)).save(frame)
    _write_json(
        source_dir / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "001_001",
                    "fileName": frame.name,
                    "url": "https://upload.wikimedia.org/wikipedia/commons/frame-1.jpg",
                    "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-18T04:00:00Z",
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        execution / "sources/wiki/meta.json",
        {
            "sourceUseMode": "licensed_adaptation",
            "researchLane": "video",
        },
    )
    assets = post / "assets"
    assets.mkdir(parents=True)
    video = assets / "video.mp4"
    video.write_bytes(b"fixture-video-payload")
    poster = assets / "poster.webp"
    Image.new("RGB", (1080, 1920), color=(25, 75, 125)).save(poster, format="WEBP")
    frame_ref = frame.relative_to(execution).as_posix()
    video_id = "west-lake-video"
    poster_id = "west-lake-video-cover"
    target_set = {
        "executionId": execution_id,
        "entityCatalogDigest": "sha256:" + "4" * 64,
    }
    target_set_digest = hashlib.sha256(
        json.dumps(
            target_set,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write_json(execution / "0.plan/target_set.json", target_set)
    _write_json(
        execution / "execution_manifest.json",
        {
            "executionId": execution_id,
            "createdAt": "2026-07-18T04:00:00Z",
                "sourceDigest": current_source_definition_snapshot().to_document(),
                "executionBundle": current_execution_bundle_identity().to_document(),
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": target_set_digest,
        },
    )
    _write_json(
        post / "manifest.json",
        {
                "schema": "quwoquan_data.post_manifest",
                "vertical": "travel",
                "topicId": "西湖__video_1",
                    "contentIdentity": "work",
                    "contentId": "qwq_data_west_lake_video_fixture",
                    "version": 1,
                    "contentType": "video",
            "carrier": "video",
            "title": "西湖光影短片",
            "caption": "湖岸与长桥的光影",
                "creatorProfileId": CREATOR_REF,
                "sourceAttribution": _source_attribution(),
            "sourceUrls": ["https://commons.wikimedia.org/wiki/File:Frame-1.jpg"],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "generator": "agent",
            "createdAt": "2026-07-18T04:00:00Z",
            "updatedAt": "2026-07-18T04:00:00Z",
            "assets": [
                {
                    "assetId": video_id,
                    "fileName": "assets/video.mp4",
                    "kind": "video",
                    "posterAssetId": poster_id,
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(video.read_bytes()).hexdigest(),
                    "mimeType": "video/mp4",
                    "width": 1080,
                        "height": 1920,
                        "usageScope": "app_publish",
                        "modelReleaseStatus": "not_required",
                        "rightsAuditStatus": "verified",
                        "rightsAuditIssues": [],
                },
                {
                    "assetId": poster_id,
                    "fileName": "assets/poster.webp",
                    "kind": "image",
                    "role": "cover",
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(poster.read_bytes()).hexdigest(),
                        "mimeType": "image/webp",
                        "usageScope": "app_publish",
                        "modelReleaseStatus": "not_required",
                        "rightsAuditStatus": "verified",
                        "rightsAuditIssues": [],
                },
            ],
        },
    )
    _write_json(
        post / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "sourceAssetRef": frame_ref,
                }
            ]
        },
    )
    _write_json(
        post / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    _write_json(post / "5.review/evidence_index.json", {"evidence": []})
    transaction_id = (
        f"{execution_id}--post-"
        f"{hashlib.sha256(post_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    package_root = execution / "evidence/object-transactions" / transaction_id

    package = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=post_ref,
        transaction_id=transaction_id,
        package_root=package_root,
    )

    assert len(package["closure"]["casRefs"]) == 2
    rights = json.loads((package_root / "object/rights.json").read_text(encoding="utf-8"))
    assert {row["assetId"] for row in rights["assets"]} == {video_id, poster_id}
    assert all(row["source"] == "https://commons.wikimedia.org/wiki/File:Frame-1.jpg" for row in rights["assets"])
    manifest = json.loads((package_root / "object/manifest.json").read_text(encoding="utf-8"))
    canonical_assets = {row["assetId"]: row for row in manifest["assets"]}
    assert canonical_assets[video_id]["posterAssetId"] == poster_id
    assert canonical_assets[poster_id]["role"] == "cover"

    publish = tmp_path / "publish-video"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    _copy_creator_avatar_cas(publish)
    _admit_packaged_creator(package_root, publish)
    output = tmp_path / "output-video"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )
    assert validate_publish_invariants(publish)["status"] == "passed"
