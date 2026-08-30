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
    _convert_fixture_to_research,
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
    assert "appUatEnvelope" not in receipt
    assert "appUatEnvelopeDigest" not in receipt
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
    }
    assert receipt["activationEnvelopeDigest"].startswith("sha256:")


def test_environment_release_readiness__milestone_identity_is_projected_from_header__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture(tmp_path)
    subject_hash = _convert_fixture_to_research(paths)
    identity = {
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST.digest,
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "executionIds": ["20260728--travel-content--test--pilot-002"],
    }
    header_path = paths["release"] / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        header.pop(field)
    header.update(
        {
            "sourceIdentities": [identity],
            "sourceIdentitySetDigest": "sha256:" + "9" * 64,
            "milestone": "M100",
            "selectionScope": "milestone",
            "releaseMode": "research",
            "milestoneTargets": {
                "homepage": 100,
                "article": 100,
                "image": 100,
                "video": 10,
            },
            "poolDigest": "sha256:" + "8" * 64,
            "counts": {"article": 1, "image": 1, "video": 1, "total": 3},
            "buildResult": "completed",
        }
    )
    write_json(header_path, header)
    attestation_path = paths["release"] / "attestations/release.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        attestation.pop(field)
    attestation["sourceIdentities"] = [identity]
    attestation["sourceIdentitySetDigest"] = "sha256:" + "9" * 64
    write_json(attestation_path, attestation)
    _resign_release(paths)

    isolation_path = paths["verify"] / "research-isolation-verification.json"
    write_json(isolation_path, {"frozen": True})
    isolation = {
        "subjectHash": subject_hash,
        "policyRef": "quwoquan_ops/environments/gamma/runtime.yaml",
        "policySha256": "sha256:" + "7" * 64,
        "positiveReadback": {
            "releaseId": RELEASE_ID,
            "manifestDigest": payload_digest(paths["release"]),
            "subjectHash": subject_hash,
            "entityRefs": ["entity:景区:测试实体"],
            "postIds": sorted(row[1] for row in POSTS),
            "mediaAssetIds": [
                "article-body-a",
                "article-cover-a",
                "image-a",
                "video-a",
                "video-cover-a",
            ],
        },
    }
    monkeypatch.setattr(
        readiness_subject,
        "load_research_isolation_verification",
        lambda *_args, **_kwargs: isolation,
    )
    monkeypatch.setattr(
        readiness_subject,
        "validate_release_header",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        readiness_subject,
        "previous_environment_activation_for_release",
        lambda **_kwargs: {
            "environment": "beta",
            "readinessRef": (
                f"env/beta/runs/data-release/{RELEASE_ID}/verify-beta/"
                "release-readiness.json"
            ),
            "readinessDigest": "sha256:" + "6" * 64,
            "activationEnvelopeDigest": "sha256:" + "5" * 64,
        },
    )

    receipt = json.loads(
        _write(
            tmp_path,
            readiness_phase="research",
            research_isolation_path=isolation_path,
        ).read_text(encoding="utf-8")
    )

    assert receipt["milestone"] == "M100"
    assert receipt["activationEnvelope"]["milestone"] == "M100"
    receipt["milestone"] = "M1000"
    _resign_readiness(receipt)
    assert any(
        "milestone drifts from immutable release closure" in issue
        for issue in _semantic_issues(tmp_path, paths, receipt)
    )


def test_environment_release_readiness__semantic_verifier_rejects_invented_milestone__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    receipt = json.loads(_write(tmp_path).read_text(encoding="utf-8"))
    receipt["milestone"] = "M100"
    _resign_readiness(receipt)

    assert any(
        "milestone is absent from immutable release header" in issue
        for issue in _semantic_issues(tmp_path, paths, receipt)
    )


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


def test_environment_release_readiness__consumer_keeps_data_readback_without_app_uat_authority__local_contract(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _convert_fixture_to_consumer(paths)

    report = _write(tmp_path, readiness_phase="consumer")
    receipt = json.loads(report.read_text(encoding="utf-8"))

    assert receipt["readinessPhase"] == "consumer"
    assert receipt["counts"]["premiumPlayableVideos"] == 1
    assert {row["name"] for row in receipt["feedQueries"]} == {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
        "premium_stream",
    }
    assert "appUatEnvelope" not in receipt
    assert "appUatEnvelopeDigest" not in receipt


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
