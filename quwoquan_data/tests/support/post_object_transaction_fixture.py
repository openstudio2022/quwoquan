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
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package as _build_post_object_transaction_package,
)
from governance.coverage import distribution
from PIL import Image

from support.media_fixture import seed_system_creator_avatar_holding

EXECUTION_ID = "20260718--travel-image-cold-start--test-region-a--scale-901"
POST_REF = "image/西湖/光影/1"
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


def _seed_creator_avatar_holding() -> None:
    seed_system_creator_avatar_holding(CREATOR_REF)


@pytest.fixture(autouse=True)
def _isolate_creator_avatar_cas() -> None:
    """Stand up the referenced creator avatar in the isolated content library.

    Projecting a creator resolves its avatar by digest against the library, so
    the holding has to exist before the projection runs; canonical publish never
    carries the body and cannot supply it.
    """
    _seed_creator_avatar_holding()


def make_text_only_article(execution_root: Path) -> None:
    """Turn the fixture post into a text-only article that publishes a document.

    A text-only post carries no media, so its prose is the only surface canonical
    publish can name as final content. Writing ``article.md`` here is what makes
    these fixtures describe a post that is actually publishable without bytes,
    rather than one that leans on a stray asset file to have something to point at.
    """

    post = execution_root / "posts" / POST_REF
    manifest_path = post / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        contentType="article",
        carrier="article",
        publishMediaMode="text_only",
        assets=[],
    )
    _write_json(manifest_path, manifest)
    (post / "article.md").write_text(
        "# 西湖光影\n\n文本 post 的正文，不依赖任何媒体字节。\n",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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
        "derivedModifications": [],
    }


def build_post_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
) -> dict[str, object]:
    return _build_post_object_transaction_package(
        execution_root=execution_root,
        object_ref=object_ref,
        transaction_id=transaction_id,
        package_root=package_root,
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


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> tuple[Path, Path, Path, str]:
    execution = tmp_path / "output/data/tasks" / EXECUTION_ID
    if monkeypatch is not None:
        from content.release.canonical import post_transaction
        from core import paths as core_paths

        monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path / "output")
        monkeypatch.setattr(
            post_transaction,
            "canonical_asset_manifest_row",
            lambda raw, **kwargs: {
                **dict(raw),
                "objectKey": kwargs["object_key"],
                "sha256": _file_digest(kwargs["asset_source"]),
                "bytes": kwargs["asset_source"].stat().st_size,
                "mimeType": kwargs["mime_type"],
                "perceptualHash": "0" * 16,
            },
        )
    post = execution / "posts" / POST_REF
    source_asset = post / "assets/cover.jpg"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(30, 80, 140)).save(source_asset)
    digest = "sha256:" + hashlib.sha256(source_asset.read_bytes()).hexdigest()
    transaction_id = (
        f"{EXECUTION_ID}--post-"
        f"{hashlib.sha256(POST_REF.encode('utf-8')).hexdigest()[:12]}"
    )
    output_root = tmp_path / "output"
    demand_path = output_root / "inputs/demand.json"
    bindings_path = output_root / "inputs/bindings.json"
    demand = {
        "schema": "quwoquan_data.carrier_demand",
        "status": "confirmed",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "familyRef": "content/travel/image/image",
        "quota": 1,
        "retryOf": None,
    }
    bindings = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "candidateCount": 1,
        "targets": [
            {
                "name": "西湖",
                "entityType": "地点/景区",
                "publishAngle": "西湖",
                "publishTitle": "光影",
                "publishSeq": 1,
            }
        ],
    }
    _write_json(demand_path, demand)
    _write_json(bindings_path, bindings)
    demand_binding = {
        "scope": "output",
        "ref": "inputs/demand.json",
        "digest": _file_digest(demand_path),
    }
    candidate_binding = {
        "scope": "output",
        "ref": "inputs/bindings.json",
        "digest": _file_digest(bindings_path),
    }
    submitted_inputs = {
        "carrierDemand": demand,
        "immutableCandidateBindings": bindings,
    }
    request = {
        "schema": "quwoquan_data.task_init_request",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "familyRef": "content/travel/image/image",
        "quota": 1,
        "candidateCount": 1,
        "carrierDemand": demand_binding,
        "immutableCandidateBindings": candidate_binding,
        "submittedInputs": submitted_inputs,
        "retryOf": None,
    }
    target_set = {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "candidateBinding": {**candidate_binding, "candidateCount": 1},
        "targetCount": 1,
        "targetRefs": [f"posts/{POST_REF}"],
        "targets": bindings["targets"],
    }
    request_path = execution / "0.plan/request.json"
    target_path = execution / "0.plan/target_set.json"
    _write_json(request_path, request)
    _write_json(target_path, target_set)
    family_path = (
        REPO_ROOT
        / "quwoquan_data/control_plane/families/content/travel/image/image.recipe.yaml"
    )
    _write_json(
        execution / "execution_manifest.json",
        {
            "schema": "quwoquan_data.content_execution_manifest",
            "executionId": EXECUTION_ID,
            "carrier": "image",
            "familyRef": {
                "ref": "content/travel/image/image",
                "digest": _file_digest(family_path),
            },
            "initInputs": {
                "carrierDemand": demand_binding,
                "immutableCandidateBindings": candidate_binding,
            },
            "submittedInputs": submitted_inputs,
            "request": {
                "ref": "0.plan/request.json",
                "digest": _file_digest(request_path),
            },
            "targetSet": {
                "ref": "0.plan/target_set.json",
                "digest": _file_digest(target_path),
            },
            "retryOf": None,
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
                    "distributionDecision": "research_allowed",
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
                    "distributionDecision": "research_allowed",
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
    for review_name in (
        "rubric_review.json",
        "reviewer_result.json",
        "media_ref_review.json",
    ):
        _write_json(post / "5.review" / review_name, {})
    _write_json(post / "5.review/evidence_index.json", {"evidence": []})
    publish = tmp_path / "publish"
    for relative in ("creators", "entities", "posts", "tags"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    _seed_creator_avatar_holding()
    package = execution / "evidence/object-transactions" / transaction_id
    return execution, package, publish, transaction_id
