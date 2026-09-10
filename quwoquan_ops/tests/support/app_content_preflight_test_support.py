"""App content preflight imports 与现役 Data 无类别 闭包 fixture。"""
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as patrol_smoke


def write_release_readiness(output_root: Path, *, environment: str = "gamma", release_id: str = "pilot-002", verify_run_id: str = "verify-001", import_run_id: str = "activate-001", prepared_run_id: str = "apply-001", manifest_digest: str = "sha256:" + "2" * 64, source_identity: dict | None = None, unverified: bool = False) -> tuple[Path, str]:
    """构造 schema 有效的本地证据；不声称真实 runtime/UAT 已执行。"""
    from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema

    def checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def write(ref, value):
        path = output_root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return path

    source = source_identity
    if source is None:
        identities = [{"sourceRevision": "sha256:" + "a" * 64, "sourceDigest": "sha256:" + "b" * 64, "entityCatalogDigest": "sha256:" + "c" * 64, "executionIds": ["execution-001"]}]
        source = {"sourceIdentities": identities, "sourceIdentitySetDigest": checksum({"schema": "quwoquan_data.source_identity_set", "sourceIdentities": identities})}
    identity = {"environment": environment, "releaseId": release_id, "manifestDigest": manifest_digest}
    rights = {"containsUnverifiedAssets": unverified, "authorizationRequiredAssetIds": ["image-asset"] if unverified else [], "rightsStatusCounts": {"verified": 2 if unverified else 3, "unverified": int(unverified), "restricted": 0, "unknown": 0}, "acceptedCount": 3}
    prefix = f"env/{environment}/runs/data-release/{release_id}"
    payload = f"data/releases/{release_id}/payload"
    posts = ["post-article", "post-image", "post-video"]
    media = {"schema": "quwoquan_data.release_media_manifest", "releaseId": release_id, "sourceOwner": "qwq_data", "assets": [{"assetId": item} for item in ("article-cover", "image-asset", "video-asset")]}
    media_path = write(f"{payload}/media_manifest.json", media)
    import_ref = f"{prefix}/{prepared_run_id}/import.json"
    import_path = write(import_ref, {"schema": "quwoquan.content_import_report", **identity, "status": "staged", "activationMode": "stage-only", "counts": {"postsLoaded": 3, "postsUpserted": 3, "outboxEventsReady": 3, "outboxEventsAppended": 3}, "postBindings": [{"contentId": f"content-{carrier}", "postRef": f"{carrier}/item", "contentType": carrier, "postId": f"post-{carrier}", "authorId": "author-1"} for carrier in ("article", "image", "video")]})
    write(f"{prefix}/{prepared_run_id}/result.json", {"schema": "quwoquan_data.environment_release_result", **identity, "runId": prepared_run_id, "status": "prepared", "contentImportReportRef": import_ref})
    write(f"{prefix}/{import_run_id}/result.json", {"schema": "quwoquan_data.environment_release_result", **identity, "runId": import_run_id, "status": "completed", "importRunId": prepared_run_id})
    queries = [("discovery_work", "identity=work&limit=20", posts), ("typed_article", "identity=work&type=article&limit=20", [posts[0]]), ("typed_image", "identity=work&type=image&limit=20", [posts[1]]), ("typed_video", "identity=work&type=video&limit=20", [posts[2]]), ("homepage_recommend", "sort=recommend&channelId=recommend&limit=20", [posts[2]]), ("premium_stream", "sort=recommend&channelId=premium_stream&limit=20", [posts[2]])]

    def operation(path, page, suffix):
        return {"path": path, "pageId": page, "status": 200, "requestId": f"DATA.{suffix}", "traceId": f"TRACE.{suffix}", "startedAt": "2026-09-09T00:00:00.000Z", "endedAt": "2026-09-09T00:00:00.001Z", "durationMs": 1}

    feed = [{"name": name, "path": "/content/feed", "query": query, "status": 200, "releaseBound": True, "matchedPostIds": ids, "requests": [operation("/content/feed", "content.feed.list", name)]} for name, query, ids in queries]
    guest = {"guestActorHash": "sha256:" + "3" * 64, "guestLogin": operation("/auth/login/anonymous", "user.login.anonymous", "guest")}
    avatar_url = f"https://cdn.{environment}.quwoquan.com/media/avatar/s/asset/creator-avatar-1/v1/source.jpg"
    avatar_probe = {"publicUrl": avatar_url, "status": 200, "mimeType": "image/jpeg", "bytes": 12, "sha256": "sha256:" + "4" * 64, "hashVerified": True}
    creator = {"creatorRef": "creator-1", "personaId": "persona-1", "profileStatus": 200, "avatarAssetId": "creator-avatar-1", "avatarMediaReady": True, "usesPlatformDefaultAvatar": False, "avatarProbeCount": 1, "avatarUrl": avatar_url, "avatarProbe": avatar_probe}
    image_probe = {"assetId": "image-asset", "kind": "image", "status": 200, "mimeType": "image/jpeg", "bytes": 12, "expectedBytes": 12, "sha256": "sha256:" + "5" * 64, "expectedSha256": "sha256:" + "5" * 64, "hashVerified": True}
    post_ref = f"{prefix}/{verify_run_id}/post-api-verification.json"
    write(post_ref, {"schema": "quwoquan_data.post_api_verification", **identity, "passed": True, **guest, "feedQueries": feed, "creators": [creator], "posts": [{"postId": item, "mediaProbeCount": int(item == "post-image"), "mediaProbes": [image_probe] if item == "post-image" else []} for item in posts], "searchQueries": [{"targetId": item, "targetType": "post"} for item in posts] + [{"targetId": "persona-1", "targetType": "author"}]})
    homepage_ref = f"{prefix}/{verify_run_id}/homepage-api-verification.json"
    write(homepage_ref, {"schema": "quwoquan_data.homepage_api_verification", **identity, "runId": verify_run_id, "passed": True, "issues": [], "entities": [{"entityRef": "entities/west-lake", "homepageId": "homepage-west-lake", "detailStatus": 200, "introductionStatus": 200}]})
    creator_ref = f"{prefix}/{prepared_run_id}/creator-import.json"
    tag_ref = f"{prefix}/{verify_run_id}/tag-attribution.json"
    write(creator_ref, {**identity, "status": "active", "verifiedCreatorIds": ["creator-1"]})
    write(tag_ref, {})
    attestation = {"schema": "quwoquan_data.release_attestation", "releaseId": release_id, "sourceOwner": "qwq_data", "releaseKind": "content", **source, **rights, "payloadSha256": manifest_digest, "executionIds": ["execution-001"], "carrierCounts": {"homepage": 1, "article": 1, "image": 1, "video": 1, "total": 4}, "entityCount": 1, "postCount": 3, "creatorCount": 1, "tagCount": 1, "canonicalMerkle": "sha256:" + "6" * 64, "sourceDigests": [{"algorithm": "sha256", "digest": "sha256:" + "a" * 64, "inputs": ["quwoquan_data"]}], "recordedAt": "2026-09-09T00:00:00Z"}
    _validate_data_schema(attestation, "release_attestation")
    write(f"data/releases/{release_id}/attestations/release.json", attestation)
    receipt = {"schema": "quwoquan_data.environment_release_readiness", **identity, "releaseKind": "content", "sourceOwner": "qwq_data", **source, **rights, "mediaManifestDigest": "sha256:" + hashlib.sha256(media_path.read_bytes()).hexdigest(), "importRunId": import_run_id, "verifyRunId": verify_run_id, **guest, "counts": {"entities": 1, "posts": 3, "creators": 1, "avatarAssets": 1, "imageAssets": 1, "tags": 1, "mediaAssets": 3, "discoveryPosts": 3, "premiumPlayableVideos": 1}, "entityRefs": ["entities/west-lake"], "postIds": posts, "creatorIds": ["creator-1"], "tagRefs": ["tag/west-lake"], "mediaAssetIds": ["article-cover", "image-asset", "video-asset"], "feedQueries": feed, "contentImportReportRef": import_ref, "creatorAttributionRef": creator_ref, "tagAttributionRef": tag_ref, "homepageApiVerificationRef": homepage_ref, "postApiVerificationRef": post_ref, "mediaManifestRef": f"{payload}/media_manifest.json", "verifiedAt": "2026-09-09T00:00:00Z", "passed": True}
    receipt["activationEnvelope"] = {"schema": "quwoquan_data.environment_activation_envelope", **identity, **source, "importRunId": import_run_id, "verifyRunId": verify_run_id, "importReportRef": import_ref, "importReportDigest": "sha256:" + hashlib.sha256(import_path.read_bytes()).hexdigest()}
    receipt["activationEnvelopeDigest"] = checksum(receipt["activationEnvelope"])
    receipt["verificationChecksum"] = checksum(receipt)
    _validate_data_schema(receipt, "environment_release_readiness")
    return write(f"{prefix}/{verify_run_id}/release-readiness.json", receipt), manifest_digest
