"""Ops consumes one exact Data-owned release/environment readiness receipt."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import release_readiness as readiness_subject
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
    write_environment_release_readiness,
)
from core.io import write_json
from core.release_layout import objects_merkle, payload_digest
from core.schema import assert_valid
from core.source_digest import (
    content_source_revision,
    current_source_definition_snapshot,
)
from verify.release_environment_readiness import (
    environment_release_readiness_issues,
)

RELEASE_ID = "release-readiness-a"
ENVIRONMENT = "gamma"
IMPORT_RUN_ID = "apply-001"
VERIFY_RUN_ID = "verify-001"
ENTITY_REF = "地点/景区/测试实体"
CREATOR_ID = "creator-a"
TAG_REF = "Topic/旅行"
POSTS = (
    ("article/test-a", "post-article-a", "article"),
    ("image/test-a", "post-image-a", "image"),
    ("video/test-a", "post-video-a", "video"),
)
SOURCE_DIGEST = current_source_definition_snapshot()
ENTITY_CATALOG_DIGEST = "sha256:" + "f" * 64
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST.digest,
    entity_catalog_digest=ENTITY_CATALOG_DIGEST,
)


def _request_evidence(path: str, page_id: str, *, suffix: str) -> dict[str, object]:
    return {
        "path": path,
        "pageId": page_id,
        "status": 200,
        "requestId": f"DATA.{page_id}.{suffix}",
        "traceId": f"DATA.readiness.{page_id}.{suffix}",
        "startedAt": "2026-07-28T00:02:00.000Z",
        "endedAt": "2026-07-28T00:02:00.001Z",
        "durationMs": 1,
    }


def _image_probe(asset_id: str, digest_char: str) -> dict[str, object]:
    digest = "sha256:" + digest_char * 64
    return {
        "assetId": asset_id,
        "kind": "image",
        "publicUrl": (
            "https://cdn.gamma.example.test/media/image/s/asset/"
            f"{asset_id}/v1/source.jpg"
        ),
        "status": 200,
        "mimeType": "image/jpeg",
        "bytes": 64,
        "sha256": digest,
        "etag": f'"{asset_id}"',
        "hashVerified": True,
        "expectedBytes": 64,
        "expectedSha256": digest,
    }


def _post_media_probes(content_type: str) -> list[dict[str, object]]:
    if content_type == "article":
        return [
            _image_probe("article-cover-a", "1"),
            _image_probe("article-body-a", "2"),
        ]
    if content_type == "image":
        return [_image_probe("image-a", "e")]
    return [
        _image_probe("video-cover-a", "f"),
        {
            "assetId": "video-a",
            "kind": "video",
            "publicUrl": (
                "https://cdn.gamma.example.test/media/video/s/asset/"
                "video-a/v1/source.mp4"
            ),
            "status": 206,
            "mimeType": "video/mp4",
            "bytes": 16,
            "sha256": "",
            "etag": '"video-a"',
            "hashVerified": False,
            "expectedBytes": 128,
            "expectedSha256": "sha256:" + "c" * 64,
        },
    ]


def _paths(root: Path) -> dict[str, Path]:
    release = root / "data/releases" / RELEASE_ID
    import_run = root / f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}"
    verify_run = root / f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{VERIFY_RUN_ID}"
    return {"release": release, "import": import_run, "verify": verify_run}


def _fixture(root: Path) -> dict[str, Path]:
    paths = _paths(root)
    release = paths["release"]
    desired_refs = {
        "entities": [ENTITY_REF],
        "posts": [row[0] for row in POSTS],
        "creators": [CREATOR_ID],
        "tags": [TAG_REF],
    }
    write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 7,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 4,
            "commercialAcceptedCount": 4,
            "canonicalMerkle": "sha256:" + "a" * 64,
            "executionIds": ["20260728--travel-content--test--pilot-002"],
            "sourceRevision": SOURCE_REVISION,
            "sourceDigest": SOURCE_DIGEST.digest,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
            "sourceDigests": [SOURCE_DIGEST.to_document()],
        },
    )
    write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": RELEASE_ID,
            "desiredRefs": desired_refs,
        },
    )
    write_json(
        release / "payload/media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "assets": [
                {
                    "assetId": "entity-cover-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/image/s/asset/entity-cover-a/v1/source.jpg",
                    "sha256": "sha256:" + "a" * 64,
                    "bytes": 64,
                    "ownerRefs": [f"entities/{ENTITY_REF}"],
                    "rightsSnapshotRefs": [
                        f"objects/entities/{ENTITY_REF}/rights_snapshots/entity-cover-a.json"
                    ],
                },
                {
                    "assetId": "creator-avatar-a",
                    "kind": "avatar",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/avatar/s/asset/creator-avatar-a/v1/source.jpg",
                    "sha256": "sha256:" + "d" * 64,
                    "bytes": 64,
                    "ownerRefs": [f"creators/{CREATOR_ID}"],
                    "rightsSnapshotRefs": [
                        f"objects/creators/{CREATOR_ID}/rights_snapshots/creator-avatar-a.json"
                    ],
                },
                {
                    "assetId": "article-cover-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/image/s/asset/article-cover-a/v1/source.jpg",
                    "sha256": "sha256:" + "1" * 64,
                    "bytes": 64,
                    "ownerRefs": ["posts/article/test-a"],
                    "rightsSnapshotRefs": [
                        "objects/posts/article/test-a/rights_snapshots/article-cover-a.json"
                    ],
                },
                {
                    "assetId": "article-body-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/image/s/asset/article-body-a/v1/source.jpg",
                    "sha256": "sha256:" + "2" * 64,
                    "bytes": 64,
                    "ownerRefs": ["posts/article/test-a"],
                    "rightsSnapshotRefs": [
                        "objects/posts/article/test-a/rights_snapshots/article-body-a.json"
                    ],
                },
                {
                    "assetId": "image-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/image/s/asset/image-a/v1/source.jpg",
                    "sha256": "sha256:" + "e" * 64,
                    "bytes": 64,
                    "ownerRefs": ["posts/image/test-a"],
                    "rightsSnapshotRefs": [
                        "objects/posts/image/test-a/rights_snapshots/image-a.json"
                    ],
                },
                {
                    "assetId": "video-cover-a",
                    "kind": "image",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": (
                        "media/image/s/asset/video-cover-a/v1/source.jpg"
                    ),
                    "sha256": "sha256:" + "f" * 64,
                    "bytes": 64,
                    "ownerRefs": ["posts/video/test-a"],
                    "rightsSnapshotRefs": [
                        "objects/posts/video/test-a/rights_snapshots/video-cover-a.json"
                    ],
                },
                {
                    "assetId": "video-a",
                    "kind": "video",
                    "version": 1,
                    "contentType": "video/mp4",
                    "publicSliceKey": "media/video/s/asset/video-a/v1/source.mp4",
                    "sha256": "sha256:" + "c" * 64,
                    "bytes": 128,
                    "ownerRefs": ["posts/video/test-a"],
                    "rightsSnapshotRefs": [
                        "objects/posts/video/test-a/rights_snapshots/video-a.json"
                    ],
                }
            ],
            "issues": [],
            "counts": {"assets": 7, "issues": 0},
        },
    )
    write_json(
        release / f"payload/objects/entities/{ENTITY_REF}/_entity.json",
        {
            "schema": "quwoquan_data.entity",
            "entityRef": f"/entity/{ENTITY_REF}",
            "label": "测试实体",
            "authorId": "author-a",
            "creatorProfileId": CREATOR_ID,
            "tagRefs": [TAG_REF],
        },
    )
    write_json(
        release / f"payload/objects/entities/{ENTITY_REF}/manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "contentType": "homepage",
            "assets": [{"assetId": "entity-cover-a", "kind": "image"}],
        },
    )
    post_titles = {
        "article": "测试文章",
        "image": "测试图片",
        "video": "测试视频",
    }
    for post_ref, _post_id, content_type in POSTS:
        manifest = {
            "schema": "quwoquan_data.post_object",
            "contentIdentity": "work",
            "contentType": content_type,
            "publishTitle": post_titles[content_type],
            "authorId": "author-a",
            "creatorProfileId": CREATOR_ID,
            "tagRefs": [TAG_REF],
        }
        if content_type == "article":
            manifest["publishMediaMode"] = "illustrated"
        if content_type == "video":
            manifest["sourceAttribution"] = {"attributionText": "测试视频来源"}
        write_json(
            release / f"payload/objects/posts/{post_ref}/manifest.json",
            manifest,
        )
    write_json(
        release / f"payload/objects/creators/{CREATOR_ID}/profile.json",
        {
            "schema": "quwoquan_data.creator_profile",
            "creatorId": CREATOR_ID,
            "authorId": "author-a",
            "personaId": "author-a",
            "displayName": "测试创作者",
            "userHandle": "test_creator",
            "avatarAsset": {
                "assetId": "creator-avatar-a",
                "kind": "avatar",
                "sha256": "sha256:" + "d" * 64,
            },
        },
    )
    write_json(
        release / f"payload/objects/tags/{TAG_REF}/_definition.json",
        {"label": "旅行"},
    )
    media_manifest = json.loads(
        (release / "payload/media_manifest.json").read_text(encoding="utf-8")
    )
    for asset in media_manifest["assets"]:
        for rights_ref in asset["rightsSnapshotRefs"]:
            write_json(
                release / "payload" / rights_ref,
                {
                    "assetId": asset["assetId"],
                    "manifestAsset": {
                        "assetId": asset["assetId"],
                        "sha256": asset["sha256"],
                    },
                },
            )
    write_json(
        release / "payload/asset_admission.json",
        {
            "schema": "quwoquan_data.release_asset_admission",
            "releaseId": RELEASE_ID,
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 7,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 4,
            "commercialAcceptedCount": 4,
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "objectCount": 1,
                    "assetCount": 1,
                    "researchAcceptedCount": 1,
                    "commercialAcceptedCount": 1,
                }
                for carrier in ("homepage", "article", "image", "video")
            ],
            "articleMediaCoverage": {
                "articleCount": 1,
                "illustratedCount": 1,
                "textOnlyCount": 0,
                "illustratedRate": 1.0,
                "textOnlyRate": 0.0,
            },
            "sourceAssetCounts": [],
            "assets": [],
        },
    )
    canonical_merkle = objects_merkle(release)
    release_header_path = release / "payload/release.json"
    release_header = json.loads(release_header_path.read_text(encoding="utf-8"))
    release_header["canonicalMerkle"] = canonical_merkle
    write_json(release_header_path, release_header)
    write_json(
        release / "attestations/release.json",
        {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 7,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 4,
            "commercialAcceptedCount": 4,
            "executionIds": ["20260728--travel-content--test--pilot-002"],
            "entityCount": 1,
            "postCount": 3,
            "creatorCount": 1,
            "tagCount": 1,
            "canonicalMerkle": canonical_merkle,
            "sourceRevision": SOURCE_REVISION,
            "sourceDigest": SOURCE_DIGEST.digest,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
            "sourceDigests": [SOURCE_DIGEST.to_document()],
            "payloadSha256": payload_digest(release),
            "recordedAt": "2026-07-28T00:00:00Z",
        },
    )
    import_run = paths["import"]
    write_json(
        import_run / "import.json",
        {
            "schema": "quwoquan.content_import_report",
            "status": "imported",
            "environment": ENVIRONMENT,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "manifestDigest": payload_digest(release),
            "mode": "sync",
            "deletePolicy": "tombstone",
            "counts": {"postsLoaded": 3, "entitiesLoaded": 1},
            "postBindings": [
                {
                    "postRef": post_ref,
                    "postId": post_id,
                    "contentId": f"content-{post_id}",
                    "contentVersion": 1,
                    "usageScope": "commercial",
                    "contentType": content_type,
                    "authorId": "author-a",
                }
                for post_ref, post_id, content_type in POSTS
            ],
            "auditEvents": [],
        },
    )
    write_json(
        import_run / "creator-import.json",
        {
            "schema": "quwoquan.user_creator_import_report",
            "status": "active",
            "environment": ENVIRONMENT,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "mode": "sync",
            "projectionDatabase": "quwoquan_user",
            "counts": {
                "creatorsLoaded": 1,
                "usersUpserted": 1,
                "creatorsUpserted": 1,
                "usersRemoved": 0,
                "creatorsRemoved": 0,
            },
            "authorIds": ["author-a"],
            "verifiedCreatorIds": [CREATOR_ID],
            "generatedAt": "2026-07-28T00:01:00Z",
        },
    )
    verify_run = paths["verify"]
    write_json(
        verify_run / "tag-consumer-verification.json",
        {
            "schema": "quwoquan_data.tag_consumer_verification",
            "environment": ENVIRONMENT,
            "releaseId": RELEASE_ID,
            "runId": VERIFY_RUN_ID,
            "sourceImportReportRef": (
                f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}/tag-import.json"
            ),
            "releaseKind": "content",
            "nodeCount": 1,
            "tagRefs": [TAG_REF],
            "verifiedAt": "2026-07-28T00:02:00Z",
            "passed": True,
        },
    )
    write_json(
        verify_run / "homepage-api-verification.json",
        {
            "schema": "quwoquan_data.homepage_api_verification",
            "environment": ENVIRONMENT,
            "releaseId": RELEASE_ID,
            "runId": VERIFY_RUN_ID,
            "sourceCasesRef": (
                f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}/homepage_verification_cases.json"
            ),
            "apiBaseUrl": "https://gamma.example.test",
            "verifiedAt": "2026-07-28T00:02:00Z",
            "passed": True,
            "entities": [
                {
                    "entityRef": ENTITY_REF,
                    "homepageId": "homepage-a",
                    "title": "测试实体",
                    "detailStatus": 200,
                    "introductionStatus": 200,
                    "coverUrl": (
                        "https://cdn.gamma.example.test/media/image/s/asset/"
                        "entity-cover-a/v1/source.jpg"
                    ),
                    "sectionCount": 1,
                }
            ],
            "issues": [],
        },
    )
    feed_queries = [
        ("discovery_work", "identity=work&limit=20", [row[1] for row in POSTS]),
        ("typed_article", "identity=work&type=article&limit=20", ["post-article-a"]),
        ("typed_image", "identity=work&type=image&limit=20", ["post-image-a"]),
        ("typed_video", "identity=work&type=video&limit=20", ["post-video-a"]),
        ("homepage_recommend", "sort=recommend&channelId=recommend&limit=20", ["post-article-a"]),
        ("premium_stream", "sort=recommend&channelId=premium_stream&limit=20", ["post-video-a"]),
    ]
    write_json(
        verify_run / "post-api-verification.json",
        {
            "schema": "quwoquan_data.post_api_verification",
            "environment": ENVIRONMENT,
            "releaseId": RELEASE_ID,
            "runId": VERIFY_RUN_ID,
            "readinessPhase": "commercial",
            "sourceImportReportRef": (
                f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}/import.json"
            ),
            "creatorImportReportRef": (
                f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}/creator-import.json"
            ),
            "apiBaseUrl": "https://gamma.example.test",
            "mediaDeliveryBaseUrl": "https://cdn.gamma.example.test",
            "guestActorHash": "sha256:" + "e" * 64,
            "guestLogin": _request_evidence(
                "/auth/login/anonymous",
                "user.login.anonymous",
                suffix="login",
            ),
            "verifiedAt": "2026-07-28T00:02:00Z",
            "passed": True,
            "feedQueries": [
                {
                    "name": name,
                    "path": "/content/feed",
                    "query": query,
                    "status": 200,
                    "releaseBound": True,
                    "matchedPostIds": ids,
                    "requests": [
                        _request_evidence(
                            "/content/feed",
                            "content.feed.list",
                            suffix=name,
                        )
                    ],
                }
                for name, query, ids in feed_queries
            ],
            "searchQueries": [
                {
                    "targetType": "post",
                    "targetId": post_id,
                    "query": post_id,
                    "status": 200,
                    "matchedObjectIds": [post_id],
                    "request": _request_evidence(
                        "/search",
                        "search.global",
                        suffix=f"search-{post_id}",
                    ),
                }
                for _post_ref, post_id, _content_type in POSTS
            ]
            + [
                {
                    "targetType": "author",
                    "targetId": "author-a",
                    "query": "creator-a",
                    "status": 200,
                    "matchedObjectIds": ["author-a"],
                    "request": _request_evidence(
                        "/search",
                        "search.global",
                        suffix="search-author-a",
                    ),
                }
            ],
            "creators": [
                {
                    "creatorRef": CREATOR_ID,
                    "authorId": "author-a",
                    "personaId": "author-a",
                    "profileStatus": 200,
                    "avatarAssetId": "creator-avatar-a",
                    "avatarUrl": (
                        "https://cdn.gamma.example.test/media/avatar/s/asset/"
                        "creator-avatar-a/v1/source.jpg"
                    ),
                    "avatarMediaReady": True,
                    "avatarProbeCount": 1,
                    "avatarProbe": {
                        "publicUrl": (
                            "https://cdn.gamma.example.test/media/avatar/s/asset/"
                            "creator-avatar-a/v1/source.jpg"
                        ),
                        "status": 200,
                        "mimeType": "image/jpeg",
                        "bytes": 64,
                        "sha256": "sha256:" + "d" * 64,
                        "etag": '"avatar-a"',
                        "hashVerified": True,
                    },
                    "usesPlatformDefaultAvatar": False,
                }
            ],
            "posts": [
                {
                    "postRef": post_ref,
                    "postId": post_id,
                    "contentType": content_type,
                    "authorId": "author-a",
                    "detailStatus": 200,
                    "feedStatus": 200,
                    "mediaReady": True,
                    "mediaProbeCount": len(_post_media_probes(content_type)),
                    "mediaProbes": _post_media_probes(content_type),
                    "sourceAttributionReady": True,
                    "authorProfileStatus": 200,
                }
                for post_ref, post_id, content_type in POSTS
            ],
            "issues": [],
        },
    )
    return paths


def _resign_release(paths: dict[str, Path]) -> None:
    release = paths["release"]
    canonical_merkle = objects_merkle(release)
    header_path = release / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["canonicalMerkle"] = canonical_merkle
    write_json(header_path, header)

    attestation_path = release / "attestations/release.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["canonicalMerkle"] = canonical_merkle
    attestation["payloadSha256"] = payload_digest(release)
    write_json(attestation_path, attestation)

    import_path = paths["import"] / "import.json"
    import_report = json.loads(import_path.read_text(encoding="utf-8"))
    import_report["manifestDigest"] = payload_digest(release)
    write_json(import_path, import_report)


def _convert_fixture_to_research(paths: dict[str, Path]) -> str:
    subject_hash = "sha256:" + "9" * 64
    release = paths["release"]
    for relative in (
        "payload/release.json",
        "payload/asset_admission.json",
        "attestations/release.json",
    ):
        path = release / relative
        document = json.loads(path.read_text(encoding="utf-8"))
        document["releaseClass"] = "research"
        document["productLifecycleState"] = "research"
        write_json(path, document)
    post_path = paths["verify"] / "post-api-verification.json"
    post_report = json.loads(post_path.read_text(encoding="utf-8"))
    post_report["readinessPhase"] = "research"
    post_report["internalSubjectHash"] = subject_hash
    post_report.pop("guestActorHash", None)
    post_report.pop("guestLogin", None)
    write_json(post_path, post_report)
    _resign_release(paths)
    return subject_hash


def _convert_fixture_to_consumer(paths: dict[str, Path]) -> None:
    post_path = paths["verify"] / "post-api-verification.json"
    post_report = json.loads(post_path.read_text(encoding="utf-8"))
    post_report["readinessPhase"] = "consumer"
    post_report["feedQueries"] = [
        row
        for row in post_report["feedQueries"]
        if row["name"] != "premium_stream"
    ]
    post_report.pop("searchQueries")
    write_json(post_path, post_report)


def _write(
    root: Path,
    *,
    readiness_phase: str = "commercial",
    research_isolation_path: Path | None = None,
) -> Path:
    paths = _paths(root)
    return write_environment_release_readiness(
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
        release_root=paths["release"],
        import_report_path=paths["import"] / "import.json",
        creator_import_report_path=paths["import"] / "creator-import.json",
        tag_consumer_verification_path=paths["verify"] / "tag-consumer-verification.json",
        homepage_api_verification_path=paths["verify"] / "homepage-api-verification.json",
        post_api_verification_path=paths["verify"] / "post-api-verification.json",
        output_root=root,
        output_path=paths["verify"] / "release-readiness.json",
        research_isolation_verification_path=research_isolation_path,
        readiness_phase=readiness_phase,
    )


def _semantic_issues(
    root: Path,
    paths: dict[str, Path],
    readiness: dict[str, object],
    *,
    post_report: dict[str, object] | None = None,
) -> list[str]:
    desired = json.loads(
        (paths["release"] / "payload/desired_state.json").read_text(
            encoding="utf-8"
        )
    )["desiredRefs"]
    attestation = json.loads(
        (paths["release"] / "attestations/release.json").read_text(
            encoding="utf-8"
        )
    )
    homepage_report = json.loads(
        (paths["verify"] / "homepage-api-verification.json").read_text(
            encoding="utf-8"
        )
    )
    if post_report is None:
        post_report = json.loads(
            (paths["verify"] / "post-api-verification.json").read_text(
                encoding="utf-8"
            )
        )
    return environment_release_readiness_issues(
        readiness,
        homepage_verification=homepage_report,
        post_verification=post_report,
        release=paths["release"],
        output_root=root,
        import_run=paths["import"],
        verify_run=paths["verify"],
        attestation=attestation,
        desired_refs=desired,
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
    )


def _resign_readiness(document: dict[str, object]) -> None:
    unsigned = dict(document)
    unsigned.pop("verificationChecksum", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    document["verificationChecksum"] = (
        "sha256:" + hashlib.sha256(canonical).hexdigest()
    )


@pytest.mark.parametrize("environment", ("alpha", "beta", "gamma", "prod"))
def test_environment_release_readiness__activation_envelope_is_environment_scoped__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "ENVIRONMENT", environment)
    _fixture(tmp_path)

    readiness = json.loads(_write(tmp_path).read_text(encoding="utf-8"))

    assert readiness["environment"] == environment
    assert readiness["activationEnvelope"]["environment"] == environment
    assert readiness["activationEnvelope"]["importReportRef"].startswith(
        f"env/{environment}/runs/data-release/"
    )
