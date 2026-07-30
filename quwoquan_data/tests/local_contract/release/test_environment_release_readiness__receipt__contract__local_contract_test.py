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

from content.release.environment.release_readiness import (  # noqa: E402
    EnvironmentReleaseReadinessError,
    write_environment_release_readiness,
)
from core.io import write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402


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
            "canonicalMerkle": "sha256:" + "a" * 64,
            "executionIds": ["20260728--travel-content--test--pilot-002"],
            "sourceDigests": [
                {
                    "algorithm": "sha256",
                    "digest": "sha256:" + "b" * 64,
                    "inputs": ["canonical/test"],
                }
            ],
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
                    "assetId": "creator-avatar-a",
                    "kind": "avatar",
                    "version": 1,
                    "contentType": "image/jpeg",
                    "publicSliceKey": "media/avatar/s/asset/creator-avatar-a/v1/source.jpg",
                    "sha256": "sha256:" + "d" * 64,
                    "bytes": 64,
                    "ownerRefs": [f"creators/{CREATOR_ID}"],
                    "rightsSnapshotRefs": ["rights/creator-avatar-a.json"],
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
                    "rightsSnapshotRefs": ["rights/image-a.json"],
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
                    "rightsSnapshotRefs": ["rights/video-cover-a.json"],
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
                    "rightsSnapshotRefs": ["rights/video-a.json"],
                }
            ],
            "issues": [],
            "counts": {"assets": 4, "issues": 0},
        },
    )
    write_json(
        release / "attestations/release.json",
        {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "executionIds": ["20260728--travel-content--test--pilot-002"],
            "entityCount": 1,
            "postCount": 3,
            "creatorCount": 1,
            "tagCount": 1,
            "canonicalMerkle": "sha256:" + "a" * 64,
            "sourceDigests": [
                {
                    "algorithm": "sha256",
                    "digest": "sha256:" + "b" * 64,
                    "inputs": ["canonical/test"],
                }
            ],
            "payloadSha256": payload_digest(release),
            "recordedAt": "2026-07-28T00:00:00Z",
        },
    )
    import_run = paths["import"]
    write_json(
        import_run / "import.json",
        {
            "schema": "quwoquan.content_import_report",
            "status": "active",
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
                    "coverUrl": "https://media.example.test/cover.jpg",
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
                    "mediaProbeCount": (
                        0 if content_type == "article" else (2 if content_type == "video" else 1)
                    ),
                    "mediaProbes": (
                        []
                        if content_type == "article"
                        else (
                            [
                                {
                                    "assetId": "image-a",
                                    "kind": "image",
                                    "publicUrl": (
                                        "https://cdn.gamma.example.test/media/image/s/"
                                        "asset/image-a/v1/source.jpg"
                                    ),
                                    "status": 200,
                                    "mimeType": "image/jpeg",
                                    "bytes": 64,
                                    "sha256": "sha256:" + "e" * 64,
                                    "etag": '"image-a"',
                                    "hashVerified": True,
                                    "expectedBytes": 64,
                                    "expectedSha256": "sha256:" + "e" * 64,
                                }
                            ]
                            if content_type == "image"
                            else [
                                {
                                    "assetId": "video-cover-a",
                                    "kind": "image",
                                    "publicUrl": (
                                        "https://cdn.gamma.example.test/media/image/s/"
                                        "asset/video-cover-a/v1/source.jpg"
                                    ),
                                    "status": 200,
                                    "mimeType": "image/jpeg",
                                    "bytes": 64,
                                    "sha256": "sha256:" + "f" * 64,
                                    "etag": '"video-cover-a"',
                                    "hashVerified": True,
                                    "expectedBytes": 64,
                                    "expectedSha256": "sha256:" + "f" * 64,
                                },
                                {
                                    "assetId": "video-a",
                                    "kind": "video",
                                    "publicUrl": (
                                        "https://cdn.gamma.example.test/media/video/s/"
                                        "asset/video-a/v1/source.mp4"
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
                        )
                    ),
                    "sourceAttributionReady": True,
                    "authorProfileStatus": 200,
                }
                for post_ref, post_id, content_type in POSTS
            ],
            "issues": [],
        },
    )
    return paths


def _write(root: Path) -> Path:
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
    )


def test_environment_release_readiness__binds_full_payload_and_feed_ids__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    output = _write(tmp_path)

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["manifestDigest"] == payload_digest(paths["release"])
    media_bytes = (paths["release"] / "payload/media_manifest.json").read_bytes()
    assert receipt["mediaManifestDigest"] == (
        "sha256:" + hashlib.sha256(media_bytes).hexdigest()
    )
    assert receipt["postIds"] == sorted(row[1] for row in POSTS)
    assert receipt["counts"]["discoveryPosts"] == 3
    assert receipt["counts"]["premiumPlayableVideos"] == 1
    assert receipt["counts"]["avatarAssets"] == 1
    assert receipt["counts"]["imageAssets"] == 2
    assert receipt["guestActorHash"] == "sha256:" + "e" * 64
    assert receipt["guestLogin"]["pageId"] == "user.login.anonymous"
    premium = next(row for row in receipt["feedQueries"] if row["name"] == "premium_stream")
    assert premium["matchedPostIds"] == ["post-video-a"]


def test_environment_release_readiness__premium_must_bind_release_post__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    report_path = paths["verify"] / "post-api-verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    next(row for row in report["feedQueries"] if row["name"] == "premium_stream")[
        "matchedPostIds"
    ] = ["foreign-post"]
    write_json(report_path, report)

    with pytest.raises(EnvironmentReleaseReadinessError, match="premium_stream"):
        _write(tmp_path)


def test_environment_release_readiness__import_digest_must_bind_payload__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    report_path = paths["import"] / "import.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["manifestDigest"] = "sha256:" + "0" * 64
    write_json(report_path, report)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="content import manifestDigest drift",
    ):
        _write(tmp_path)
