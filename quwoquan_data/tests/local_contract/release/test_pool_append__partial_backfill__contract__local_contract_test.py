from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical import (  # noqa: E402
    creator_projection,
    pool_attribution_repair,
    pool_backfill_canonical,
)
from content.release.canonical.content_pool_record import (  # noqa: E402
    POOL_RECORD_SCHEMA,
    append_pool_record,
    is_pool_record_admitted,
    iter_pool_records,
    latest_pool_record,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.pool_append import (  # noqa: E402
    BATCH_SCHEMA,
    append_pool_batch,
    plan_pool_backfill,
)
from content.release.canonical.pool_attribution_repair import (  # noqa: E402
    repair_pool_attribution,
)
from core.io import write_json  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDigest,
    content_source_revision,
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _attestation(root: Path) -> Path:
    path = root / "attestation.json"
    write_json(
        path,
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    return path


def _source_identity(execution_id: str = "execution-a") -> dict[str, str]:
    source_digest = "sha256:" + "2" * 64
    entity_catalog_digest = "sha256:" + "3" * 64
    identity = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    return {**identity, "identityDigest": source_identity_digest(identity)}


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "Source Author",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset",
        "attributionText": "Source Author / source-platform",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _creator_fixture(
    tmp_path: Path, monkeypatch
) -> tuple[Path, Path, Path, Path]:
    creator_pool = tmp_path / "creator_pool"
    evidence = creator_pool / "evidence" / "author.json"
    write_json(evidence, {"processResult": "completed", "qualityResult": "passed"})
    profile_path = creator_pool / "profiles/system_builtin/author.creator.yaml"
    profile_path.parent.mkdir(parents=True)
    profile = {
        "creatorProfileId": "creator-a",
        "authorId": "author-a",
        "personaId": "author-a",
        "version": 1,
        "status": "active",
        "displayName": "作者甲",
        "publicProfileTagRefs": [],
        "disclosure": {"type": "platform_virtual_creator", "visible": True},
        "admission": {
            "processResult": "completed",
            "qualityResult": "passed",
            "evidenceRef": "evidence/author.json",
            "evidenceDigest": _digest(evidence),
        },
    }
    profile_path.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    publish = tmp_path / "publish"
    monkeypatch.setattr(
        creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", creator_pool
    )
    monkeypatch.setattr(creator_projection, "PUBLISH_ROOT", publish)
    return creator_pool, publish, profile_path, evidence


def _content_item(root: Path, index: int, *, passed: bool) -> dict[str, object]:
    object_root = root / "posts" / "article" / f"work-{index}" / "1"
    write_json(
        object_root / "manifest.json",
        {
            "contentId": f"content-{index}",
            "version": 1,
            "executionId": "execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceIdentity": _source_identity(),
            "sourceAttribution": _source_attribution(),
            "contentType": "article",
            "authorId": "author-a",
            "reviewDecision": "approved",
        },
    )
    evidence = _attestation(object_root)
    object_ref = object_root.relative_to(root / "posts").as_posix()
    return {
        "itemId": f"content-{index}",
        "sourceRef": f"posts/{object_ref}",
        "record": {
            "schema": POOL_RECORD_SCHEMA,
            "objectType": "content",
            "objectId": f"content-{index}",
            "objectRef": object_ref,
            "recordSequence": 1,
            "contentVersion": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed" if passed else "pending",
            "usageScope": "research" if passed else None,
            "evidenceRef": "attestation.json",
            "evidenceDigest": _digest(evidence),
            "payloadDigest": pool_payload_digest(object_root),
            "canonicalObjectDigest": pool_payload_digest(object_root),
            "sourceIdentity": _source_identity(),
            "sourceAttribution": _source_attribution(),
        },
    }


def test_pool_append_rejects_mixed_admission_batch_without_mutation(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    items = [_content_item(publish, index, passed=index < 7) for index in range(10)]
    batch = tmp_path / "batch.json"
    write_json(
        batch,
        {"schema": BATCH_SCHEMA, "appendSetId": "partial", "items": items},
    )

    report = append_pool_batch(input_path=batch, publish_root=publish, apply=True)

    assert report["result"] == "blocked"
    assert report["counts"] == {
        "total": 10,
        "ready": 0,
        "eligibilityPending": 3,
        "failed": 7,
    }
    for index in range(10):
        record = latest_pool_record(
            publish / "posts" / "article" / f"work-{index}" / "1", "content"
        )
        assert record is None


def test_same_version_same_record_replays_and_different_record_only_rejects_item(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    item = _content_item(publish, 1, passed=True)
    batch = tmp_path / "batch.json"
    write_json(
        batch,
        {"schema": BATCH_SCHEMA, "appendSetId": "first", "items": [item]},
    )
    assert append_pool_batch(
        input_path=batch, publish_root=publish, apply=True
    )["result"] == "ready"
    replay = append_pool_batch(input_path=batch, publish_root=publish, apply=True)
    assert replay["items"][0]["status"] == "replayed"

    item["record"]["usageScope"] = "commercial"
    conflict = tmp_path / "conflict.json"
    write_json(
        conflict,
        {"schema": BATCH_SCHEMA, "appendSetId": "conflict", "items": [item]},
    )
    report = append_pool_batch(
        input_path=conflict, publish_root=publish, apply=True
    )
    assert report["result"] == "blocked"
    assert report["counts"]["failed"] == 1
    assert report["reasons"][0]["code"] == "DATA.POOL.VERSION_CONFLICT"


def test_author_append_is_independent_and_avatar_is_optional(
    tmp_path: Path, monkeypatch
) -> None:
    creator_pool = tmp_path / "creator_pool"
    evidence = creator_pool / "evidence" / "author.json"
    write_json(evidence, {"processResult": "completed", "qualityResult": "passed"})
    profile_path = creator_pool / "profiles/system_builtin/author.creator.yaml"
    profile_path.parent.mkdir(parents=True)
    profile = {
        "creatorProfileId": "creator-a",
        "authorId": "author-a",
        "personaId": "author-a",
        "version": 1,
        "status": "active",
        "displayName": "作者甲",
        "publicProfileTagRefs": [],
        "disclosure": {"type": "platform_virtual_creator", "visible": True},
        "admission": {
            "processResult": "completed",
            "qualityResult": "passed",
            "evidenceRef": "evidence/author.json",
            "evidenceDigest": _digest(evidence),
        },
    }
    profile_path.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    publish = tmp_path / "publish"
    monkeypatch.setattr(
        creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", creator_pool
    )
    monkeypatch.setattr(creator_projection, "PUBLISH_ROOT", publish)

    plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=creator_pool
    )
    batch = tmp_path / "author-batch.json"
    write_json(batch, plan["batch"])
    report = append_pool_batch(
        input_path=batch,
        publish_root=publish,
        creator_pool_root=creator_pool,
        apply=True,
    )

    assert report["result"] == "ready"
    assert report["counts"]["ready"] == 1
    projected = publish / "creators/creator-a"
    assert (projected / "profile.json").is_file()
    assert "avatarAsset" not in json.loads(
        (projected / "profile.json").read_text(encoding="utf-8")
    )
    assert latest_pool_record(projected, "author")["objectId"] == "author-a"


def test_author_backfill_excludes_pre_sequence_sidecar_without_rewrite(
    tmp_path: Path, monkeypatch
) -> None:
    creator_pool, publish, profile_path, evidence = _creator_fixture(
        tmp_path, monkeypatch
    )
    projected = publish / "creators/creator-a"
    stale_path = projected / "_pool/versions/1.json"
    stale_record = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "author",
        "objectId": "author-a",
        "objectRef": "creator-a",
        "version": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": None,
        "evidenceRef": "evidence/author.json",
        "evidenceDigest": _digest(evidence),
        "payloadDigest": _digest(profile_path),
    }
    write_json(stale_path, stale_record)
    stale_bytes = stale_path.read_bytes()

    plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=creator_pool
    )

    assert plan["batch"]["items"] == []
    assert "DATA.POOL.AUTHOR_IDENTITY_INVALID" in plan["reasons"]
    assert stale_path.read_bytes() == stale_bytes

    replay_plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=creator_pool
    )
    assert replay_plan["batch"]["items"] == []
    assert "DATA.POOL.AUTHOR_IDENTITY_INVALID" in replay_plan["reasons"]
    assert stale_path.read_bytes() == stale_bytes


def test_pool_append_preflights_entire_batch_before_any_mutation(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    first = _content_item(publish, 1, passed=True)
    conflicting = _content_item(publish, 2, passed=True)
    conflict_path = (
        publish
        / "posts/article/work-2/1/_pool/versions/1.json"
    )
    different = dict(conflicting["record"])
    different["usageScope"] = "commercial"
    write_json(conflict_path, different)
    conflict_bytes = conflict_path.read_bytes()
    batch = tmp_path / "atomic-conflict.json"
    write_json(
        batch,
        {
            "schema": BATCH_SCHEMA,
            "appendSetId": "atomic-conflict",
            "items": [first, conflicting],
        },
    )

    report = append_pool_batch(input_path=batch, publish_root=publish, apply=True)

    assert report["result"] == "blocked"
    assert report["counts"]["ready"] == 0
    assert report["counts"]["failed"] == 2
    assert any(
        row["code"] == "DATA.POOL.VERSION_CONFLICT"
        for row in report["reasons"]
    )
    assert not (
        publish / "posts/article/work-1/1/_pool/versions/1.json"
    ).exists()
    assert conflict_path.read_bytes() == conflict_bytes


def test_modern_video_record_is_not_replanned_and_ready_matches_admitted(
    tmp_path: Path, monkeypatch
) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/video/体验/已准入视频/1"
    video = post / "assets/video.mp4"
    poster = post / "assets/poster.webp"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    poster.write_bytes(b"poster")
    write_json(
        post / "manifest.json",
        {
            "contentId": "content-admitted-video",
            "version": 1,
            "contentType": "video",
            "authorId": "author-a",
            "executionId": "execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceIdentity": _source_identity(),
            "sourceAttribution": _source_attribution(),
            "assets": [
                {
                    "kind": "video",
                    "fileName": "assets/video.mp4",
                    "sha256": _digest(video),
                    "posterFileName": "assets/poster.webp",
                    "posterSha256": _digest(poster),
                }
            ],
        },
    )
    _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "verified",
                    "authorizationProof": "research-proof",
                    "licenseUrl": "https://source.example/terms",
                }
            ]
        },
    )
    write_json(
        post / "provenance.json",
        {"sources": [{"drmDetected": False, "accessControlBypassed": False}]},
    )
    monkeypatch.setattr(
        pool_backfill_canonical,
        "probe_professional_video",
        lambda _path: {
            "playable": True,
            "motionVideo": True,
            "staticImageSequence": False,
        },
    )
    first_plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=tmp_path / "empty-creators"
    )
    [first_item] = first_plan["batch"]["items"]
    append_pool_record(object_root=post, record=first_item["record"])
    assert is_pool_record_admitted(latest_pool_record(post, "content"))

    replay_plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=tmp_path / "empty-creators"
    )

    assert replay_plan["batch"]["items"] == []
    assert replay_plan["counts"]["ready"] == 1
    assert replay_plan["counts"]["alreadyAdmitted"] == 1


def test_identity_invalid_video_is_typed_excluded(
    tmp_path: Path, monkeypatch
) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/video/体验/身份无效视频/1"
    video = post / "assets/video.mp4"
    poster = post / "assets/poster.webp"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    poster.write_bytes(b"poster")
    write_json(
        post / "manifest.json",
        {
            "contentId": "content-invalid-video",
            "version": 1,
            "contentType": "video",
            "authorId": "author-a",
            "sourceAttribution": _source_attribution(),
            "assets": [
                {
                    "kind": "video",
                    "fileName": "assets/video.mp4",
                    "sha256": _digest(video),
                    "posterFileName": "assets/poster.webp",
                    "posterSha256": _digest(poster),
                }
            ],
        },
    )
    _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "verified",
                    "authorizationProof": "research-proof",
                    "licenseUrl": "https://source.example/terms",
                }
            ]
        },
    )
    write_json(
        post / "provenance.json",
        {"sources": [{"drmDetected": False, "accessControlBypassed": False}]},
    )
    monkeypatch.setattr(
        pool_backfill_canonical,
        "probe_professional_video",
        lambda _path: {
            "playable": True,
            "motionVideo": True,
            "staticImageSequence": False,
        },
    )

    plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=tmp_path / "empty-creators"
    )

    assert plan["batch"]["items"] == []
    assert plan["counts"]["ready"] == 0
    assert plan["counts"]["failed"] == 1
    assert plan["reasons"] == ["DATA.POOL.SOURCE_IDENTITY_INVALID"]


def test_backfill_keeps_unverified_redistribution_pending(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/video/体验/待核实视频/1"
    write_json(
        post / "manifest.json",
        {
            "contentId": "content-unverified-video",
            "version": 1,
            "contentType": "video",
            "authorId": "author-a",
            "reviewDecision": "approved",
            "sourceAttribution": {
                **_source_attribution(),
            },
            "executionId": "execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceIdentity": _source_identity(),
        },
    )
    _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "unverified",
                    "authorizationProof": "",
                    "licenseUrl": "https://example.test/terms",
                }
            ]
        },
    )

    report = plan_pool_backfill(
        publish_root=publish, creator_pool_root=tmp_path / "empty-creators"
    )

    assert report["result"] == "blocked"
    assert report["counts"]["contents"] == 1
    assert report["counts"]["eligibilityPending"] == 1
    assert report["batch"]["items"][0]["record"]["usageScope"] is None


def test_backfill_excludes_legacy_identity_instead_of_inferring_from_path(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    for version in (1, 2, 3):
        post = publish / "posts/article/攻略/同一作品" / str(version)
        write_json(
            post / "manifest.json",
            {
                "contentType": "article",
                "authorId": "author-a",
                "reviewDecision": "approved",
            },
        )
        _attestation(post)
        write_json(
            post / "rights.json",
            {
                "assets": [
                    {
                        "rightsAuditStatus": "verified",
                        "authorizationProof": "internal-research-evidence",
                        "licenseUrl": "https://example.test/terms",
                    }
                ]
            },
        )

    plan = plan_pool_backfill(
        publish_root=publish, creator_pool_root=tmp_path / "empty-creators"
    )

    assert plan["batch"]["items"] == []
    assert plan["counts"]["contents"] == 3
    assert plan["counts"]["failed"] == 3
    assert plan["reasons"] == ["DATA.POOL.IDENTITY_INVALID"]


def test_pre_sequence_record_shape_blocks_backfill(tmp_path: Path) -> None:
    """A sidecar without recordSequence is rejected instead of being upgraded."""

    publish = tmp_path / "publish"
    post = publish / "posts/article/攻略/旧对象/1"
    write_json(
        post / "manifest.json",
        {
            "contentType": "article",
            "authorId": "author-a",
            "reviewDecision": "approved",
            "executionId": "pre-contract-execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceAttribution": _source_attribution(),
        },
    )
    evidence = _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "verified",
                    "authorizationProof": "internal-research-evidence",
                    "licenseUrl": "https://example.test/terms",
                }
            ]
        },
    )
    object_ref = post.relative_to(publish / "posts").as_posix()
    pre_sequence_record = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": "content",
        "objectId": "content-pre-contract-explicit",
        "objectRef": object_ref,
        "version": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": "research",
        "evidenceRef": "attestation.json",
        "evidenceDigest": _digest(evidence),
        "payloadDigest": pool_payload_digest(post),
    }
    write_json(post / "_pool/versions/1.json", pre_sequence_record)

    with pytest.raises(Exception, match="RECORD_SEQUENCE_MISSING"):
        plan_pool_backfill(
            publish_root=publish,
            creator_pool_root=tmp_path / "empty-creators",
        )


def test_backfill_emits_typed_attribution_repair_requirement(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/image/画报/旧图片/1"
    write_json(
        post / "manifest.json",
        {
            "contentId": "content-old-image",
            "version": 1,
            "contentType": "image",
            "authorId": "author-a",
            "executionId": "execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceIdentity": _source_identity(),
            "sourceAttribution": {"isOriginal": False},
        },
    )
    _attestation(post)
    write_json(post / "rights.json", {"assets": []})

    plan = plan_pool_backfill(
        publish_root=publish,
        creator_pool_root=tmp_path / "empty-creators",
    )

    assert plan["batch"]["items"] == []
    [requirement] = plan["repairRequirements"]
    assert requirement["objectRef"] == "image/画报/旧图片/1"
    assert requirement["repairEvidencePolicy"] == (
        "canonical_bytes_plus_fresh_source_evidence"
    )
    assert requirement["oldTaskReceiptReuseAllowed"] is False
    assert "originalCreatorName" in requirement["requiredSourceAttributionFields"]
    assert {row["ref"] for row in requirement["evidenceSources"]} == {
        "manifest.json",
        "rights.json",
        "attestation.json",
    }


def test_video_migration_reprobes_motion_and_access_safety(
    tmp_path: Path, monkeypatch
) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/video/体验/旧视频/1"
    video = post / "assets/video.mp4"
    poster = post / "assets/poster.webp"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"real-video-bytes")
    poster.write_bytes(b"poster-bytes")
    write_json(
        post / "manifest.json",
        {
            "contentId": "content-old-video",
            "version": 1,
            "contentType": "video",
            "authorId": "author-a",
            "executionId": "execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
            "sourceIdentity": _source_identity(),
            "sourceAttribution": _source_attribution(),
            "assets": [
                {
                    "kind": "video",
                    "fileName": "assets/video.mp4",
                    "sha256": _digest(video),
                    "posterFileName": "assets/poster.webp",
                    "posterSha256": _digest(poster),
                }
            ],
        },
    )
    _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "verified",
                    "authorizationProof": "research-proof",
                    "licenseUrl": "https://source.example/terms",
                }
            ]
        },
    )
    write_json(
        post / "provenance.json",
        {
            "sources": [
                {"drmDetected": False, "accessControlBypassed": False}
            ]
        },
    )
    monkeypatch.setattr(
        pool_backfill_canonical,
        "probe_professional_video",
        lambda _path: {
            "playable": True,
            "motionVideo": False,
            "staticImageSequence": True,
        },
    )
    blocked = plan_pool_backfill(
        publish_root=publish,
        creator_pool_root=tmp_path / "empty-creators",
    )
    assert blocked["reasons"] == ["DATA.POOL.VIDEO_STATIC_IMAGE_SEQUENCE"]

    monkeypatch.setattr(
        pool_backfill_canonical,
        "probe_professional_video",
        lambda _path: {
            "playable": True,
            "motionVideo": True,
            "staticImageSequence": False,
        },
    )
    ready = plan_pool_backfill(
        publish_root=publish,
        creator_pool_root=tmp_path / "empty-creators",
    )
    assert ready["counts"]["ready"] == 1


def test_repair_producer_rejects_pre_sequence_sidecar_without_rewrite(
    tmp_path: Path, monkeypatch
) -> None:
    publish = tmp_path / "publish"
    post = publish / "posts/image/画报/旧图/1"
    write_json(
        post / "manifest.json",
        {
            "contentType": "image",
            "authorId": "author-a",
            "executionId": "legacy-execution-a",
            "sourceDigest": SourceDigest("sha256:" + "2" * 64).to_document(),
        },
    )
    evidence = _attestation(post)
    write_json(
        post / "rights.json",
        {
            "assets": [
                {
                    "rightsAuditStatus": "verified",
                    "authorizationProof": "research-proof",
                    "licenseUrl": "https://source.example/terms",
                }
            ]
        },
    )
    object_ref = "image/画报/旧图/1"
    write_json(
        post / "_pool/versions/1.json",
        {
            "schema": POOL_RECORD_SCHEMA,
            "objectType": "content",
            "objectId": "content-old-image",
            "objectRef": object_ref,
            "version": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "research",
            "evidenceRef": "attestation.json",
            "evidenceDigest": _digest(evidence),
            "payloadDigest": pool_payload_digest(post),
        },
    )
    candidate = {
        "candidateId": "image-repair-1",
        "carrier": "image",
        "objectRef": f"posts/{object_ref}",
        "sourceAttribution": _source_attribution(),
    }
    monkeypatch.setattr(
        pool_attribution_repair,
        "_pool_candidates",
        lambda **_kwargs: (
            {"image-repair-1": candidate},
            {
                "sourcePoolRef": "data/source-pool.json",
                "sourcePoolFileSha256": "sha256:" + "4" * 64,
                "sourcePoolDigest": "sha256:" + "5" * 64,
                "sourcePoolEvidenceRootRef": "data/evidence",
                "evidenceBindingCount": "1",
            },
        ),
    )
    binding_document = {
        "schema": "quwoquan_data.pool_attribution_repair_bindings",
        "repairId": "repair-old-image",
        "items": [
            {
                "objectType": "content",
                "objectRef": object_ref,
                "canonicalObjectDigest": pool_payload_digest(post),
                "candidateId": "image-repair-1",
            }
        ],
    }
    encoded = json.dumps(
        binding_document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    binding_document["bindingsDigest"] = (
        "sha256:" + hashlib.sha256(encoded).hexdigest()
    )
    bindings = tmp_path / "repair-bindings.json"
    write_json(bindings, binding_document)

    sidecar_bytes = (post / "_pool/versions/1.json").read_bytes()
    with pytest.raises(Exception, match="RECORD_SEQUENCE_MISSING"):
        repair_pool_attribution(
            publish_root=publish,
            output_root=tmp_path / "output",
            bindings_path=bindings,
            source_pool_ref="data/source-pool.json",
            evidence_root_ref="data/evidence",
            apply=True,
        )
    assert (post / "_pool/versions/1.json").read_bytes() == sidecar_bytes
