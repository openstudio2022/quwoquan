"""场景组：readiness receipt 绑定 release payload、媒体探针与导入摘要。

从 test_environment_release_readiness__receipt__contract__local_contract_test.py
按场景拆出；测试逐字搬移，共享 helper 常量留在承接模块。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.release.environment import release_readiness as readiness_subject
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
)
from core.io import write_json
from core.release_layout import payload_digest

from quwoquan_data.tests.local_contract.release.test_environment_release_readiness__receipt_environment_scope__contract__local_contract_test import (
    ENTITY_CATALOG_DIGEST,
    ENVIRONMENT,
    IMPORT_RUN_ID,
    POSTS,
    RELEASE_ID,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    VERIFY_RUN_ID,
    _convert_fixture_to_consumer,
    _fixture,
    _image_probe,
    _resign_readiness,
    _resign_release,
    _semantic_issues,
    _write,
)


def test_environment_release_readiness__binds_full_payload_and_feed_ids__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    output = _write(tmp_path)

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["manifestDigest"] == payload_digest(paths["release"])
    assert receipt["sourceRevision"] == SOURCE_REVISION
    assert receipt["sourceDigest"] == SOURCE_DIGEST.digest
    assert receipt["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    media_bytes = (paths["release"] / "payload/media_manifest.json").read_bytes()
    assert receipt["mediaManifestDigest"] == (
        "sha256:" + hashlib.sha256(media_bytes).hexdigest()
    )
    assert receipt["postIds"] == sorted(row[1] for row in POSTS)
    assert receipt["counts"]["discoveryPosts"] == 3
    assert receipt["counts"]["premiumPlayableVideos"] == 1
    assert receipt["counts"]["avatarAssets"] == 1
    assert receipt["counts"]["imageAssets"] == 4
    assert receipt["guestActorHash"] == "sha256:" + "e" * 64
    assert receipt["guestLogin"]["pageId"] == "user.login.anonymous"
    premium = next(row for row in receipt["feedQueries"] if row["name"] == "premium_stream")
    assert premium["matchedPostIds"] == ["post-video-a"]
    assert receipt["appUatEnvelope"] == {
        "releaseId": RELEASE_ID,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "homepageId": "homepage-a",
        "homepageTitle": "测试实体",
        "articleWorkId": "post-article-a",
        "articleTitle": "测试文章",
        "imageWorkId": "post-image-a",
        "imageTitle": "测试图片",
        "videoWorkId": "post-video-a",
        "videoTitle": "测试视频",
        "creatorName": "测试创作者",
        "creatorUserHandle": "test_creator",
        "creatorPersonaId": "author-a",
        "creatorAvatarAssetId": "creator-avatar-a",
        "tagLabel": "旅行",
        "videoAttribution": "测试视频来源",
    }
    assert receipt["appUatEnvelopeDigest"].startswith("sha256:")
    activation = receipt["activationEnvelope"]
    assert activation == {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": ENVIRONMENT,
        "releaseId": RELEASE_ID,
        "manifestDigest": payload_digest(paths["release"]),
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST.digest,
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "readinessPhase": "commercial",
        "importRunId": IMPORT_RUN_ID,
        "verifyRunId": VERIFY_RUN_ID,
        "importReportRef": (
            f"env/{ENVIRONMENT}/runs/data-release/{RELEASE_ID}/"
            f"{IMPORT_RUN_ID}/import.json"
        ),
        "importReportDigest": (
            "sha256:"
            + hashlib.sha256((paths["import"] / "import.json").read_bytes()).hexdigest()
        ),
        "appUatEnvelopeDigest": receipt["appUatEnvelopeDigest"],
    }
    assert receipt["activationEnvelopeDigest"].startswith("sha256:")


def test_environment_release_readiness__selects_canonical_source_identity_mode__local_contract() -> None:
    assert readiness_subject._release_source_identity_fields(
        {
            "targetEnvironment": "alpha",
            "releaseMode": "research",
            "sourceIdentities": [
                {
                    "sourceRevision": "sha256:" + "5" * 64,
                    "sourceDigest": "sha256:" + "6" * 64,
                    "entityCatalogDigest": "sha256:" + "7" * 64,
                    "executionIds": ["execution-001"],
                }
            ],
            "sourceIdentitySetDigest": "sha256:" + "1" * 64,
        }
    ) == ("sourceIdentities", "sourceIdentitySetDigest")
    assert readiness_subject._release_source_identity_fields(
        {
            "sourceRevision": "sha256:" + "2" * 64,
            "sourceDigest": "sha256:" + "3" * 64,
            "entityCatalogDigest": "sha256:" + "4" * 64,
        }
    ) == ("sourceRevision", "sourceDigest", "entityCatalogDigest")


def test_environment_release_readiness__consumer_projects_typed_video_app_uat_envelope__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _convert_fixture_to_consumer(paths)

    report = _write(tmp_path, readiness_phase="consumer")
    receipt = json.loads(report.read_text(encoding="utf-8"))

    assert receipt["readinessPhase"] == "consumer"
    assert receipt["counts"]["premiumPlayableVideos"] == 0
    assert {
        row["name"] for row in receipt["feedQueries"]
    } == {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
    }
    assert receipt["appUatEnvelope"] == {
        "releaseId": RELEASE_ID,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "homepageId": "homepage-a",
        "homepageTitle": "测试实体",
        "articleWorkId": "post-article-a",
        "articleTitle": "测试文章",
        "imageWorkId": "post-image-a",
        "imageTitle": "测试图片",
        "videoWorkId": "post-video-a",
        "videoTitle": "测试视频",
        "creatorName": "测试创作者",
        "creatorUserHandle": "test_creator",
        "creatorPersonaId": "author-a",
        "creatorAvatarAssetId": "creator-avatar-a",
        "tagLabel": "旅行",
        "videoAttribution": "测试视频来源",
    }


def test_environment_release_readiness__consumer_app_uat_tamper_cannot_hide_behind_checksum__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _convert_fixture_to_consumer(paths)
    readiness = json.loads(
        _write(tmp_path, readiness_phase="consumer").read_text(encoding="utf-8")
    )
    app_uat_envelope = readiness["appUatEnvelope"]
    assert isinstance(app_uat_envelope, dict)
    app_uat_envelope["videoWorkId"] = "foreign-video"
    _resign_readiness(readiness)

    issues = _semantic_issues(tmp_path, paths, readiness)

    assert any(
        "appUatEnvelope drifts from immutable release closure" in issue
        for issue in issues
    )
    assert all("verificationChecksum drift" not in issue for issue in issues)


def test_environment_release_readiness__app_uat_envelope_requires_release_object_title__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    manifest_path = (
        paths["release"]
        / "payload/objects/posts/article/test-a/manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publishTitle"] = ""
    write_json(manifest_path, manifest)
    _resign_release(paths)

    with pytest.raises(EnvironmentReleaseReadinessError, match="release article title"):
        _write(tmp_path)


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


def test_environment_release_readiness__video_image_probes_cannot_masquerade_as_playable__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    report_path = paths["verify"] / "post-api-verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    video = next(row for row in report["posts"] if row["contentType"] == "video")
    video["mediaProbes"][1] = _image_probe("video-a", "c")
    write_json(report_path, report)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="media probe drifts from release authority: video-a",
    ):
        _write(tmp_path)


def test_environment_release_readiness__creator_avatar_must_bind_release_profile__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    report_path = paths["verify"] / "post-api-verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["creators"][0]["avatarAssetId"] = "image-a"
    write_json(report_path, report)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="creator/avatar readback drifts from release object",
    ):
        _write(tmp_path)


def test_environment_release_readiness__homepage_cover_must_bind_entity_media__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    report_path = paths["verify"] / "homepage-api-verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["entities"][0]["coverUrl"] = (
        "https://cdn.gamma.example.test/media/image/s/asset/image-a/v1/source.jpg"
    )
    write_json(report_path, report)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="homepage cover does not bind one release media asset",
    ):
        _write(tmp_path)


def test_environment_release_readiness__rights_snapshot_must_bind_media_identity__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    rights_path = (
        paths["release"]
        / "payload/objects/posts/video/test-a/rights_snapshots/video-a.json"
    )
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["manifestAsset"]["sha256"] = "sha256:" + "0" * 64
    write_json(rights_path, rights)
    _resign_release(paths)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="release media rights identity drifts: video-a",
    ):
        _write(tmp_path)


def test_environment_release_readiness__attestation_must_project_one_release_identity__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    attestation_path = paths["release"] / "attestations/release.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["executionIds"] = ["foreign-execution"]
    write_json(attestation_path, attestation)

    with pytest.raises(
        EnvironmentReleaseReadinessError,
        match="release attestation/header projection drift: executionIds",
    ):
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
