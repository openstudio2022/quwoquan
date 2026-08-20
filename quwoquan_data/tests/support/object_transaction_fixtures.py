from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from content.release.canonical import object_transaction as transaction

from support.media_fixture import admit_media_body

TRANSACTION_ID = "object-one"
RELEASE_ID = "release-one"
SOURCE_POLICY = "encyclopedia-primary"
CREATOR_ID = "creator_a"
TAG_REF = "Topic/旅行"
OBJECT_REF = "地点/景区/真实地点"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def build_canonical(root: Path) -> Path:
    # Only the roots canonical publish may own. There is no `media` root: bodies
    # belong to the content library, and a fixture that pre-creates one would
    # hand every test a tree the real contract already rejects.
    canonical = root / "publish"
    for name in ("creators", "entities", "posts"):
        (canonical / name).mkdir(parents=True, exist_ok=True)
    creator = canonical / "creators" / CREATOR_ID
    write_json(
        creator / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": CREATOR_ID,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [TAG_REF],
            "entityRefs": [],
        },
    )
    write_json(
        creator / "profile.json",
        {
            "creatorId": CREATOR_ID,
            "authorId": CREATOR_ID,
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "fixture-author-evidence.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
        },
    )
    write_json(creator / "assets.refs.json", {"assets": []})
    (creator / "works.refs.ndjson").write_text("", encoding="utf-8")
    return canonical


def _review_attestation() -> dict:
    return {
        "schema": "quwoquan_data.review_attestation",
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {
            "status": "passed",
            "provider": "cursor_sdk",
            "model": "composer-2.5",
            "modelFamily": "composer",
            "runId": "review-run",
        },
        "mediaRefReview": {"status": "passed", "issues": []},
    }


def build_package(
    root: Path,
    canonical: Path,
    *,
    entity_extra: dict | None = None,
) -> Path:
    package_root = root / "package"
    object_root = package_root / "object"
    image = package_root / "cas/image.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"licensed-real-image")
    # 采集阶段就把字节交给内容库，封缄闭包时的存储预算准入才解析得到这条引用；
    # 少了这一步，事务包只能靠上一轮跑剩的库内容才封得住。
    digest = admit_media_body(image.read_bytes())
    digest_hex = digest.removeprefix("sha256:")
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
        f"{digest_hex}.jpg"
    )
    write_json(
        object_root / "_entity.json",
        {
            **(entity_extra or {}),
            "label": "真实地点",
            "domain": "地点",
            "type": "景区",
            "originTaskId": "旅行/地域/测试",
            "entityRef": "/entity/地点/景区/真实地点",
            "tagRefs": [TAG_REF],
            "geoTagRef": TAG_REF,
            "sourceUrls": ["https://zh.wikipedia.org/wiki/真实地点"],
            "primarySource": {
                "sourceKind": "wikipedia",
                "entityName": "真实地点",
                "extractor": "wikipedia_api",
                "canonicalUrl": "https://zh.wikipedia.org/wiki/真实地点",
                "sourceUrl": "https://zh.wikipedia.org/wiki/真实地点",
                "title": "真实地点",
                "fetchedAt": "2026-07-11T00:00:00Z",
                "snapshotHash": "sha256:" + "1" * 64,
                "policyRevision": SOURCE_POLICY,
                "sourceUseMode": "licensed_adaptation",
            },
        },
    )
    write_json(
        object_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_object",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "evidence/source_catalog.json",
            "rightsRef": "evidence/rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": image.stat().st_size,
                }
            ],
        },
    )
    (object_root / "page.md").write_text(
        "# 真实地点\n\n真实正文。\n",
        encoding="utf-8",
    )
    write_json(
        object_root / "evidence/source_catalog.json",
        {
            "sources": [
                {
                    "sourceKind": "wikipedia",
                    "sourceUrl": "https://zh.wikipedia.org/wiki/真实地点",
                }
            ]
        },
    )
    snapshot = object_root / "evidence/rights/commons_file_page.html"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"canonical commons author and license snapshot")
    snapshot_digest = "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
    write_json(
        object_root / "evidence/rights.json",
        {
            "schema": "quwoquan_data.asset_rights_closure",
            "publishMediaMode": "not_applicable",
            "assets": [
                {
                    "assetId": "cover",
                    "sourceKind": "wikipedia",
                    "sourceUseMode": "licensed_adaptation",
                    "canonicalFilePage": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "snapshotUrl": (
                        "https://commons.wikimedia.org/w/index.php?"
                        "title=File:Example.jpg&oldid=1"
                    ),
                    "pageRevision": "1",
                    "originalAssetUrl": (
                        "https://upload.wikimedia.org/example.jpg"
                    ),
                    "author": "真实作者",
                    "source": "Own work",
                    "licenseName": (
                        "Creative Commons Attribution-ShareAlike 4.0 International"
                    ),
                    "licenseShortName": "CC BY-SA 4.0",
                    "licenseUrl": (
                        "https://creativecommons.org/licenses/by-sa/4.0/"
                    ),
                    "usageScope": "app_publish",
                    "attribution": "真实地点，摄影：真实作者，CC BY-SA 4.0",
                    "caption": "真实地点",
                    "captionSource": "Commons file page Chinese description",
                    "modifications": "none",
                    "fetchedAt": "2026-07-11T00:00:00Z",
                    "snapshot": {
                        "ref": "object/evidence/rights/commons_file_page.html",
                        "sha256": snapshot_digest,
                        "bytes": snapshot.stat().st_size,
                    },
                    "asset": {
                        "ref": "cas/image.jpg",
                        "sha256": digest,
                        "bytes": image.stat().st_size,
                        "mimeType": "image/jpeg",
                        "width": 1280,
                        "height": 720,
                    },
                    "authorizationProof": (
                        "https://commons.wikimedia.org/w/index.php?"
                        "title=File:Example.jpg&oldid=1"
                    ),
                    "distributionDecision": "commercial_allowed",
                    "modelReleaseStatus": "not_required",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                }
            ],
        },
    )
    write_json(object_root / "creator.refs.json", {"creatorRefs": [CREATOR_ID]})
    write_json(object_root / "tag.refs.json", {"tagRefs": [TAG_REF]})
    write_json(
        object_root / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": image.stat().st_size,
                }
            ]
        },
    )
    write_json(object_root / "attestation.json", _review_attestation())
    write_json(
        object_root / "evidence_index.json",
        {"schema": "quwoquan_data.release_evidence_index", "refs": []},
    )
    creator_package_ref = Path("creators") / CREATOR_ID
    creator_package_root = package_root / creator_package_ref
    shutil.copytree(canonical / "creators" / CREATOR_ID, creator_package_root)
    closure = {
        "creatorRefs": [CREATOR_ID],
        "creatorObjects": [
            {
                "creatorRef": CREATOR_ID,
                "packageRef": creator_package_ref.as_posix(),
                "treeDigest": transaction._tree_digest(creator_package_root),
            }
        ],
        "tagRefs": [TAG_REF],
        "sourceCatalogRef": "evidence/source_catalog.json",
        "rightsRef": "evidence/rights.json",
        "casRefs": [
            {
                "sourceRef": "cas/image.jpg",
                "objectKey": object_key,
                "sha256": digest,
                "bytes": image.stat().st_size,
            }
        ],
    }
    review = {
        "attestationRef": "attestation.json",
        "evidenceIndexRef": "evidence_index.json",
    }
    review_binding = transaction._review_binding(object_root, {"review": review})
    closure_digest = transaction._closure_digest(
        object_root=object_root,
        object_kind="entities",
        object_ref=OBJECT_REF,
        target_schema="quwoquan_data.entity_object",
        source_policy_revision=SOURCE_POLICY,
        closure=closure,
        cas_rows=[dict(closure["casRefs"][0])],
        review=review_binding,
    )
    write_json(
        package_root / "object_transaction_package.json",
        {
            "schema": transaction.PACKAGE_SCHEMA,
            "transactionId": TRANSACTION_ID,
            "executionId": "20260711--travel-homepage-coverage--cn-test--pilot-001",
            "publishMediaMode": "not_applicable",
            "sourcePolicyRevision": SOURCE_POLICY,
            "target": {
                "layoutSchema": transaction.LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": OBJECT_REF,
                "objectSchema": "quwoquan_data.entity_object",
                "packageObjectRef": "object",
            },
            "closure": closure,
            "review": review,
            "objectClosureDigest": closure_digest,
        },
    )
    return package_root
