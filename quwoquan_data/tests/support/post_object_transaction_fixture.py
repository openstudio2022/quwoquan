"""post object transaction 合约测试共享常量、fixture 与包装器。

由 test_post_object_transaction__behavior_* 场景组测试文件共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
``_isolate_creator_avatar_cas`` 是模块级 autouse fixture，场景测试文件
必须显式 import 它以保持 autouse 语义。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from content.release.canonical import creator_projection
from content.release.canonical.content_pool_record import stable_content_id
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package as _build_post_object_transaction_package,
)
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
# 原测试文件位于 tests/local_contract/release/（parents[4]）；本 support 模块
# 位于 tests/support/，仓库根对应 parents[3]。
REPO_ROOT = Path(__file__).resolve().parents[3]
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
