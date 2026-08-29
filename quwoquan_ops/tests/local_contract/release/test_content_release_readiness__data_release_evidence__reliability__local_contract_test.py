"""data release readiness / lifecycle exit 证据绑定与防篡改契约。

由 1000 行硬顶拆分自
test_content_release_readiness__policy__reliability__local_contract_test.py；
测试逐字搬移，_write_data_readiness_fixture 等构造 helper 只被本场景组使用，
随组保留在本文件。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl


def _operation_evidence(path: str, page_id: str, *, suffix: str) -> dict[str, object]:
    return {
        "path": path,
        "pageId": page_id,
        "status": 200,
        "requestId": f"DATA.{page_id}.{suffix}",
        "traceId": f"DATA.readiness.{page_id}.{suffix}",
        "startedAt": "2026-07-28T00:00:00.000Z",
        "endedAt": "2026-07-28T00:00:00.001Z",
        "durationMs": 1,
    }


def _write_data_readiness_fixture(
    *,
    output_root: Path,
    environment: str = "gamma",
    release_id: str = "pilot-002",
    verify_run_id: str = "verify-001",
) -> tuple[Path, str]:
    release_root = output_root / "data" / "releases" / release_id
    media_path = release_root / "payload" / "media_manifest.json"
    media_path.parent.mkdir(parents=True)
    media_path.write_text('{"assets":[{"assetId":"video-asset"}]}\n', encoding="utf-8")
    manifest_digest = "sha256:" + "2" * 64
    source_revision = "sha256:" + "a" * 64
    source_digest = "sha256:" + "b" * 64
    entity_catalog_digest = "sha256:" + "c" * 64
    attestation_path = release_root / "attestations" / "release.json"
    attestation_path.parent.mkdir(parents=True)
    attestation_path.write_text(
        json.dumps(
            {
                "releaseId": release_id,
                "sourceOwner": "qwq_data",
                "payloadSha256": manifest_digest,
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "sourceRevision": source_revision,
                "sourceDigest": source_digest,
                "entityCatalogDigest": entity_catalog_digest,
            }
        ),
        encoding="utf-8",
    )
    evidence_root = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / verify_run_id
    )
    evidence_root.mkdir(parents=True)
    refs: dict[str, str] = {}
    for key, filename in (
        ("contentImportReportRef", "content-import-report.json"),
        ("creatorAttributionRef", "creator-attribution.json"),
        ("tagAttributionRef", "tag-attribution.json"),
        ("homepageApiVerificationRef", "homepage-api-verification.json"),
        ("postApiVerificationRef", "post-api-verification.json"),
    ):
        path = evidence_root / filename
        if key != "postApiVerificationRef":
            path.write_text("{}\n", encoding="utf-8")
        refs[key] = path.relative_to(output_root).as_posix()
    feed_queries = [
        (
            "discovery_work",
            "identity=work&limit=20",
            ["post-article", "post-image", "post-video"],
        ),
        ("typed_article", "identity=work&type=article&limit=20", ["post-article"]),
        ("typed_image", "identity=work&type=image&limit=20", ["post-image"]),
        ("typed_video", "identity=work&type=video&limit=20", ["post-video"]),
        (
            "homepage_recommend",
            "sort=recommend&channelId=recommend&limit=20",
            ["post-video"],
        ),
        (
            "premium_stream",
            "sort=recommend&channelId=premium_stream&limit=20",
            ["post-video"],
        ),
    ]
    guest_login = _operation_evidence(
        "/auth/login/anonymous",
        "user.login.anonymous",
        suffix="login",
    )
    feed_query_evidence = [
        {
            "name": name,
            "path": "/content/feed",
            "query": query,
            "status": 200,
            "releaseBound": True,
            "matchedPostIds": post_ids,
            "requests": [
                _operation_evidence(
                    "/content/feed",
                    "content.feed.list",
                    suffix=name,
                )
            ],
        }
        for name, query, post_ids in feed_queries
    ]
    guest_actor_hash = "sha256:" + "3" * 64
    app_uat_envelope = {
        "releaseId": release_id,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "homepageId": "homepage-west-lake",
        "homepageTitle": "西湖",
        "articleWorkId": "post-article",
        "articleTitle": "西湖文章",
        "imageWorkId": "post-image",
        "imageTitle": "西湖图片",
        "videoWorkId": "post-video",
        "videoTitle": "西湖视频",
        "creatorName": "西湖创作者",
        "creatorUserHandle": "west_lake_creator",
        "creatorPersonaId": "persona-west-lake",
        "creatorAvatarAssetId": "creator-avatar-1",
        "tagLabel": "西湖",
        "videoAttribution": "测试来源",
    }
    post_verification_path = output_root / refs["postApiVerificationRef"]
    post_verification_path.write_text(
        json.dumps(
            {
                "guestActorHash": guest_actor_hash,
                "guestLogin": guest_login,
                "feedQueries": feed_query_evidence,
                "creators": [
                    {
                        "creatorRef": f"creator-{index}",
                        "avatarAssetId": f"creator-avatar-{index}",
                        "profileStatus": 200,
                        "avatarMediaReady": True,
                        "avatarProbeCount": 1,
                        "avatarUrl": (
                            "https://cdn.gamma.quwoquan.com/media/avatar/s/asset/"
                            f"creator-avatar-{index}/v1/source.jpg"
                        ),
                        "avatarProbe": {
                            "publicUrl": (
                                "https://cdn.gamma.quwoquan.com/media/avatar/s/asset/"
                                f"creator-avatar-{index}/v1/source.jpg"
                            ),
                            "status": 200,
                            "mimeType": "image/jpeg",
                            "bytes": 64,
                            "sha256": "sha256:" + f"{index}" * 64,
                            "etag": f'"creator-avatar-{index}"',
                            "hashVerified": True,
                        },
                    }
                    for index in range(1, 5)
                ],
                "posts": [
                    {
                        "mediaProbeCount": 1,
                        "mediaProbes": [
                            {
                                "assetId": "image-asset",
                                "kind": "image",
                                "status": 200,
                                "mimeType": "image/jpeg",
                                "bytes": 64,
                                "expectedBytes": 64,
                                "sha256": "sha256:" + "8" * 64,
                                "expectedSha256": "sha256:" + "8" * 64,
                                "hashVerified": True,
                            }
                        ]
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 3,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 3,
        "commercialAcceptedCount": 3,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "readinessPhase": "commercial",
        "manifestDigest": manifest_digest,
        "mediaManifestDigest": "sha256:"
        + hashlib.sha256(media_path.read_bytes()).hexdigest(),
        "importRunId": "import-001",
        "verifyRunId": verify_run_id,
        "guestActorHash": guest_actor_hash,
        "guestLogin": guest_login,
        "counts": {
            "entities": 1,
            "posts": 3,
            "creators": 4,
            "avatarAssets": 4,
            "imageAssets": 1,
            "tags": 2,
            "mediaAssets": 3,
            "discoveryPosts": 3,
            "premiumPlayableVideos": 1,
        },
        "entityRefs": ["entities/west-lake"],
        "postIds": ["post-article", "post-image", "post-video"],
        "creatorIds": ["creator-1", "creator-2", "creator-3", "creator-4"],
        "tagRefs": ["tag/hangzhou", "tag/west-lake"],
        "mediaAssetIds": ["article-cover", "image-asset", "video-asset"],
        "feedQueries": feed_query_evidence,
        **refs,
        "mediaManifestRef": media_path.relative_to(output_root).as_posix(),
        "appUatEnvelope": app_uat_envelope,
        "appUatEnvelopeDigest": stackctl._canonical_document_checksum(
            app_uat_envelope
        ),
        "verifiedAt": "2026-07-28T00:00:00Z",
        "passed": True,
    }
    import_ref = refs["contentImportReportRef"]
    receipt["activationEnvelope"] = {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "readinessPhase": "commercial",
        "importRunId": "import-001",
        "verifyRunId": verify_run_id,
        "importReportRef": import_ref,
        "importReportDigest": "sha256:"
        + hashlib.sha256((output_root / import_ref).read_bytes()).hexdigest(),
        "appUatEnvelopeDigest": receipt["appUatEnvelopeDigest"],
    }
    receipt["activationEnvelopeDigest"] = (
        stackctl._canonical_document_checksum(receipt["activationEnvelope"])
    )
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(receipt)
    receipt_path = evidence_root / "release-readiness.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt_path, manifest_digest


def _convert_data_readiness_fixture_to_research(
    *,
    output_root: Path,
    receipt_path: Path,
) -> None:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["releaseClass"] = "research"
    receipt["productLifecycleState"] = "research"
    receipt["readinessPhase"] = "research"
    receipt["internalSubjectHash"] = "sha256:" + "7" * 64
    receipt.pop("guestActorHash", None)
    receipt.pop("guestLogin", None)
    app_uat = receipt["appUatEnvelope"]
    app_uat["releaseClass"] = "research"
    app_uat["productLifecycleState"] = "research"
    receipt["appUatEnvelopeDigest"] = stackctl._canonical_document_checksum(
        app_uat
    )
    attestation_path = (
        output_root
        / "data/releases"
        / receipt["releaseId"]
        / "attestations/release.json"
    )
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["releaseClass"] = "research"
    attestation["productLifecycleState"] = "research"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    post_path = output_root / receipt["postApiVerificationRef"]
    post = json.loads(post_path.read_text(encoding="utf-8"))
    post["internalSubjectHash"] = receipt["internalSubjectHash"]
    post.pop("guestActorHash", None)
    post.pop("guestLogin", None)
    # DEC-031：research 私有交付下 avatar 以相对 CAS key 闭合（probeCount=0），
    # 图片以匿名 401/403 拒绝探测 + expectedSha256 闭合。
    for row in post.get("creators") or []:
        if row.get("avatarMediaReady") is True:
            row["avatarProbeCount"] = 0
            row["avatarProbe"] = None
            row["avatarUrl"] = (
                "media/objects/sha256/aa/aa/" + "a" * 64 + ".jpg"
            )
    for post_row in post.get("posts") or []:
        for probe in post_row.get("mediaProbes") or []:
            if probe.get("kind") == "image":
                probe["deliveryRef"] = (
                    "media/objects/sha256/88/88/" + "8" * 64 + ".jpg"
                )
                probe["anonymousStatus"] = 403
    post_path.write_text(json.dumps(post), encoding="utf-8")
    isolation_ref = (
        Path("env")
        / receipt["environment"]
        / "runs/data-release"
        / receipt["releaseId"]
        / receipt["verifyRunId"]
        / "research-isolation-verification.json"
    ).as_posix()
    isolation_path = output_root / isolation_ref
    isolation = {
        "policyRef": (
            f"quwoquan_ops/environments/{receipt['environment']}/runtime.yaml"
        ),
        "policySha256": "sha256:" + "8" * 64,
        "subjectHash": receipt["internalSubjectHash"],
    }
    isolation_path.write_text(json.dumps(isolation), encoding="utf-8")
    isolation_digest = "sha256:" + hashlib.sha256(
        isolation_path.read_bytes()
    ).hexdigest()
    receipt["researchIsolationVerificationRef"] = isolation_ref
    receipt["researchIsolationVerificationDigest"] = isolation_digest
    activation = receipt["activationEnvelope"]
    activation.update(
        {
            "releaseClass": "research",
            "productLifecycleState": "research",
            "readinessPhase": "research",
            "appUatEnvelopeDigest": receipt["appUatEnvelopeDigest"],
            "researchIsolationPolicy": {
                "policyRef": isolation["policyRef"],
                "policyDigest": isolation["policySha256"],
                "verificationRef": isolation_ref,
                "verificationDigest": isolation_digest,
                "subjectHash": receipt["internalSubjectHash"],
            },
        }
    )
    receipt["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(
        activation
    )
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(
        unsigned
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def test_data_release_readiness__binds_digest_exact_queries_and_evidence__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)

    receipt, loaded_path = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert loaded_path == receipt_path
    assert receipt["counts"]["premiumPlayableVideos"] == 1
    assert receipt["sourceOwner"] == "qwq_data"


def test_data_release_readiness__accepts_typed_source_identity_set__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    identities = [
        {
            "sourceRevision": "sha256:" + "6" * 64,
            "sourceDigest": "sha256:" + "7" * 64,
            "entityCatalogDigest": "sha256:" + "8" * 64,
            "executionIds": ["execution-001"],
        }
    ]
    identity_set_digest = "sha256:" + "9" * 64
    for key in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        receipt.pop(key)
        receipt["activationEnvelope"].pop(key)
    receipt["sourceIdentities"] = identities
    receipt["sourceIdentitySetDigest"] = identity_set_digest
    receipt["activationEnvelope"]["sourceIdentities"] = identities
    receipt["activationEnvelope"]["sourceIdentitySetDigest"] = identity_set_digest
    receipt["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(
        receipt["activationEnvelope"]
    )
    attestation_path = (
        tmp_path
        / "data/releases/pilot-002/attestations/release.json"
    )
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    for key in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        attestation.pop(key)
    attestation["sourceIdentities"] = identities
    attestation["sourceIdentitySetDigest"] = identity_set_digest
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(
        unsigned
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    loaded, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert loaded["sourceIdentities"] == identities
    assert loaded["sourceIdentitySetDigest"] == identity_set_digest


def test_data_release_readiness__accepts_explicit_platform_default_avatar__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    post_path = tmp_path / receipt["postApiVerificationRef"]
    post = json.loads(post_path.read_text(encoding="utf-8"))
    post["creators"][-1].update(
        {
            "avatarAssetId": None,
            "avatarUrl": "",
            "avatarMediaReady": False,
            "avatarProbeCount": 0,
            "avatarProbe": None,
            "usesPlatformDefaultAvatar": True,
        }
    )
    post_path.write_text(json.dumps(post), encoding="utf-8")
    receipt["counts"]["avatarAssets"] = 3
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(
        unsigned
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    loaded, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert loaded["counts"]["avatarAssets"] == 3


def test_data_release_readiness__research_binds_activation_isolation_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    _convert_data_readiness_fixture_to_research(
        output_root=tmp_path,
        receipt_path=receipt_path,
    )

    receipt, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.RESEARCH,
    )

    isolation = receipt["activationEnvelope"]["researchIsolationPolicy"]
    assert isolation["policyRef"] == "quwoquan_ops/environments/gamma/runtime.yaml"
    assert isolation["verificationRef"] == receipt[
        "researchIsolationVerificationRef"
    ]


def test_data_release_readiness__rejects_tampered_receipt__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["feedQueries"][-1]["matchedPostIds"] = ["post-article"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        stackctl._load_data_release_readiness(
            environment="gamma",
            release_id="pilot-002",
            verify_run_id="verify-001",
            manifest_digest=manifest_digest,
            readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
        )
    except ValueError as exc:
        assert "verificationChecksum" in str(exc)
        assert "playable video" in str(exc)
    else:
        raise AssertionError("tampered readiness receipt must be rejected")


def test_data_release_readiness__rejects_resigned_activation_identity_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["activationEnvelope"]["sourceDigest"] = "sha256:" + "9" * 64
    receipt["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(
        receipt["activationEnvelope"]
    )
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(
        unsigned
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        stackctl._load_data_release_readiness(
            environment="gamma",
            release_id="pilot-002",
            verify_run_id="verify-001",
            manifest_digest=manifest_digest,
            readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
        )
    except ValueError as exc:
        assert "activationEnvelope drifts" in str(exc)
    else:
        raise AssertionError("resigned activation identity drift must be rejected")


def test_data_release_readiness__projects_live_exact_query_expectations__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)
    receipt, _loaded_path = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert stackctl._release_feed_post_expectations(
        receipt,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    ) == {
        "content_feed": {"post-article", "post-image", "post-video"},
        "video_book_feed": {"post-video"},
        "premium_feed": {"post-video"},
    }


def _reseal_consumer_receipt(
    receipt_path: Path,
    *,
    output_root: Path,
    drop_premium_supply: bool,
) -> None:
    """Rewrite the fixture as a consumer-phase receipt and re-sign every digest."""
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["readinessPhase"] = "consumer"
    receipt["activationEnvelope"]["readinessPhase"] = "consumer"
    if drop_premium_supply:
        receipt["feedQueries"] = [
            row for row in receipt["feedQueries"] if row["name"] != "premium_stream"
        ]
        receipt["counts"]["premiumPlayableVideos"] = 0
    receipt["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(
        receipt["activationEnvelope"]
    )
    post_path = output_root / receipt["postApiVerificationRef"]
    post = json.loads(post_path.read_text(encoding="utf-8"))
    post["feedQueries"] = list(receipt["feedQueries"])
    post_path.write_text(json.dumps(post), encoding="utf-8")
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(unsigned)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def test_data_release_readiness__consumer_accepts_release_bound_premium_supply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    _reseal_consumer_receipt(
        receipt_path,
        output_root=tmp_path,
        drop_premium_supply=False,
    )

    loaded, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.CONSUMER,
    )

    assert loaded["readinessPhase"] == "consumer"
    # consumer 起 premium_stream 就要有 release-bound 读回期望，实时探测与 receipt
    # 校验器同源；少了 premium_feed 就说明实时探测又退回了自己那一套分档。
    assert stackctl._release_feed_post_expectations(
        loaded,
        readiness_phase=stackctl.ReadinessPhase.CONSUMER,
    ) == {
        "content_feed": {"post-article", "post-image", "post-video"},
        "video_book_feed": {"post-video"},
        "premium_feed": {"post-video"},
    }


def test_data_release_readiness__consumer_requires_premium_supply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # environment-topology-and-packaging REQ-002：四环境内容 consumer/commercial
    # readiness 都必须校验 premium_stream 的 release-bound 非空读回，任一 exact
    # query 为空不得产生通过回执。视频书唯一消费该池，typed_video 绿不代表其绿。
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    _reseal_consumer_receipt(
        receipt_path,
        output_root=tmp_path,
        drop_premium_supply=True,
    )

    try:
        stackctl._load_data_release_readiness(
            environment="gamma",
            release_id="pilot-002",
            verify_run_id="verify-001",
            manifest_digest=manifest_digest,
            readiness_phase=stackctl.ReadinessPhase.CONSUMER,
        )
    except ValueError as exc:
        assert "premium_stream has no release-bound playable video" in str(exc)
    else:
        raise AssertionError(
            "consumer readiness without premium supply must be rejected"
        )


def _write_lifecycle_exit_fixture(
    *,
    output_root: Path,
    readiness: dict,
) -> str:
    environment = readiness["environment"]
    release_id = readiness["releaseId"]
    rollback_release_id = "empty-baseline-001"
    rollback_digest = "sha256:" + "4" * 64
    rollback_attestation = (
        output_root
        / "data/releases"
        / rollback_release_id
        / "attestations/release.json"
    )
    rollback_attestation.parent.mkdir(parents=True)
    rollback_attestation.write_text(
        json.dumps(
            {
                "releaseId": rollback_release_id,
                "sourceOwner": "qwq_data",
                "payloadSha256": rollback_digest,
            }
        ),
        encoding="utf-8",
    )
    run_bindings = (
        (release_id, readiness["importRunId"]),
        (release_id, readiness["verifyRunId"]),
        (rollback_release_id, "rollback-001"),
        (rollback_release_id, "rollback-verify-001"),
        (release_id, "replay-001"),
        (release_id, "replay-verify-001"),
    )
    for bound_release_id, run_id in run_bindings:
        result = (
            output_root
            / "env"
            / environment
            / "runs/data-release"
            / bound_release_id
            / run_id
            / "result.json"
        )
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("{}\n", encoding="utf-8")

    def result_ref(bound_release_id: str, run_id: str) -> str:
        return (
            Path("env")
            / environment
            / "runs/data-release"
            / bound_release_id
            / run_id
            / "result.json"
        ).as_posix()

    exit_run_id = "exit-001"
    receipt = {
        "schema": "quwoquan_data.environment_release_lifecycle_exit",
        "environment": environment,
        "sourceOwner": "qwq_data",
        "exitRunId": exit_run_id,
        "originalReleaseId": release_id,
        "originalManifestDigest": readiness["manifestDigest"],
        "originalImportRunId": readiness["importRunId"],
        "originalVerifyRunId": readiness["verifyRunId"],
        "originalImportResultRef": result_ref(
            release_id,
            readiness["importRunId"],
        ),
        "originalVerifyResultRef": result_ref(
            release_id,
            readiness["verifyRunId"],
        ),
        "rollbackToReleaseId": rollback_release_id,
        "rollbackToManifestDigest": rollback_digest,
        "rollbackRunId": "rollback-001",
        "rollbackVerifyRunId": "rollback-verify-001",
        "rollbackResultRef": result_ref(rollback_release_id, "rollback-001"),
        "rollbackVerifyResultRef": result_ref(
            rollback_release_id,
            "rollback-verify-001",
        ),
        "replayImportRunId": "replay-001",
        "replayVerifyRunId": "replay-verify-001",
        "replayManifestDigest": readiness["manifestDigest"],
        "replayImportResultRef": result_ref(release_id, "replay-001"),
        "replayVerifyResultRef": result_ref(release_id, "replay-verify-001"),
        "recordedAt": "2026-07-28T00:05:00Z",
        "passed": True,
    }
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(receipt)
    ref = (
        Path("env")
        / environment
        / "runs/release-lifecycle-exit"
        / release_id
        / exit_run_id
        / "lifecycle-exit.json"
    ).as_posix()
    path = output_root / ref
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return ref


def test_data_lifecycle_exit__binds_original_readiness_and_same_digest_replay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )

    receipt, path = stackctl._load_data_release_lifecycle_exit(
        environment="gamma",
        release_id="pilot-002",
        manifest_digest=manifest_digest,
        readiness=readiness,
        lifecycle_exit_ref=ref,
    )

    assert path == tmp_path / ref
    assert receipt["originalImportRunId"] == readiness["importRunId"]
    assert receipt["replayManifestDigest"] == manifest_digest



def test_data_lifecycle_exit__allows_commercial_readiness_on_replay_import(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Commercial verify after lifecycle binds via replayImportRunId."""
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )
    # Simulate post-lifecycle commercial verify on the replayed import.
    readiness = dict(readiness)
    readiness["importRunId"] = "replay-001"
    readiness["verifyRunId"] = "commercial-verify-001"
    commercial_result = (
        tmp_path
        / "env/gamma/runs/data-release/pilot-002/commercial-verify-001/result.json"
    )
    commercial_result.parent.mkdir(parents=True, exist_ok=True)
    commercial_result.write_text("{}\n", encoding="utf-8")

    receipt, path = stackctl._load_data_release_lifecycle_exit(
        environment="gamma",
        release_id="pilot-002",
        manifest_digest=manifest_digest,
        readiness=readiness,
        lifecycle_exit_ref=ref,
    )

    assert path == tmp_path / ref
    assert receipt["replayImportRunId"] == readiness["importRunId"]
    assert receipt["originalImportRunId"] != readiness["importRunId"]


def test_data_lifecycle_exit__rejects_replay_digest_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )
    path = tmp_path / ref
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["replayManifestDigest"] = "sha256:" + "9" * 64
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(unsigned)
    path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        stackctl._load_data_release_lifecycle_exit(
            environment="gamma",
            release_id="pilot-002",
            manifest_digest=manifest_digest,
            readiness=readiness,
            lifecycle_exit_ref=ref,
        )
    except ValueError as exc:
        assert "replayManifestDigest" in str(exc)
    else:
        raise AssertionError("same-digest replay drift must be rejected")
