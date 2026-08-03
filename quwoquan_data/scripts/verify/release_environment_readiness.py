"""Semantic verification for one bound Data environment readiness receipt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.app_uat_envelope import (
    AppUatEnvelopeError,
    build_app_uat_envelope,
)
from core.io import read_json
from core.release_layout import payload_file


def _read_object(path: Path, *, label: str, issues: list[str]) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"{path}: invalid {label}: {exc}")
        return {}
    if not isinstance(value, Mapping):
        issues.append(f"{path}: {label} must be an object")
        return {}
    return dict(value)


def environment_release_readiness_issues(
    readiness: Mapping[str, Any],
    *,
    homepage_verification: Mapping[str, Any],
    post_verification: Mapping[str, Any],
    release: Path,
    output_root: Path,
    import_run: Path,
    verify_run: Path,
    attestation: Mapping[str, Any],
    desired_refs: Mapping[str, list[str]],
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
) -> list[str]:
    """Recompute receipt identity, digests, IDs and non-empty feed counts."""

    issues: list[str] = []
    path = verify_run / "release-readiness.json"
    if readiness.get("environment") != environment:
        issues.append(f"{path}: environment does not match run")
    if readiness.get("releaseId") != release_id:
        issues.append(f"{path}: releaseId does not match run")
    if readiness.get("sourceOwner") != "qwq_data":
        issues.append(f"{path}: sourceOwner must be qwq_data")
    if readiness.get("importRunId") != import_run_id:
        issues.append(f"{path}: importRunId drift")
    if readiness.get("verifyRunId") != verify_run_id:
        issues.append(f"{path}: verifyRunId drift")
    if readiness.get("manifestDigest") != attestation.get("payloadSha256"):
        issues.append(f"{path}: manifestDigest drift from immutable payload")
    if readiness.get("guestActorHash") != post_verification.get("guestActorHash"):
        issues.append(f"{path}: guestActorHash drift from post verification")
    if readiness.get("guestLogin") != post_verification.get("guestLogin"):
        issues.append(f"{path}: guestLogin drift from post verification")
    if readiness.get("feedQueries") != post_verification.get("feedQueries"):
        issues.append(f"{path}: feedQueries drift from post verification")

    media_manifest_path = payload_file(release, "media_manifest.json")
    try:
        media_bytes = media_manifest_path.read_bytes()
        media_manifest_digest = "sha256:" + hashlib.sha256(media_bytes).hexdigest()
        media_manifest_ref = media_manifest_path.relative_to(output_root).as_posix()
    except (OSError, ValueError) as exc:
        issues.append(f"{media_manifest_path}: cannot bind release media manifest: {exc}")
    else:
        if readiness.get("mediaManifestDigest") != media_manifest_digest:
            issues.append(f"{path}: mediaManifestDigest drift")
        if readiness.get("mediaManifestRef") != media_manifest_ref:
            issues.append(f"{path}: mediaManifestRef drift")

    content_import = _read_object(
        import_run / "import.json",
        label="content import report",
        issues=issues,
    )
    if content_import.get("manifestDigest") != attestation.get("payloadSha256"):
        issues.append(f"{import_run / 'import.json'}: manifestDigest drift from immutable payload")
    bindings = [
        row
        for row in content_import.get("postBindings") or []
        if isinstance(row, Mapping)
    ]
    expected_ids = sorted(str(row.get("postId") or "") for row in bindings)
    if readiness.get("postIds") != expected_ids:
        issues.append(f"{path}: postIds drift from import receipt")
    for field, kind in (
        ("entityRefs", "entities"),
        ("creatorIds", "creators"),
        ("tagRefs", "tags"),
    ):
        if readiness.get(field) != desired_refs[kind]:
            issues.append(f"{path}: {field} drift from desired state")

    media_manifest = _read_object(
        media_manifest_path,
        label="release media manifest",
        issues=issues,
    )
    media_asset_ids = sorted(
        str(row.get("assetId") or "")
        for row in media_manifest.get("assets") or []
        if isinstance(row, Mapping)
    )
    if readiness.get("mediaAssetIds") != media_asset_ids:
        issues.append(f"{path}: mediaAssetIds drift")
    feed_queries = {
        str(row.get("name") or ""): row
        for row in readiness.get("feedQueries") or []
        if isinstance(row, Mapping)
    }
    release_post_ids = set(expected_ids)
    discovery_ids = set(
        feed_queries.get("discovery_work", {}).get("matchedPostIds") or []
    ) & release_post_ids
    premium_ids = set(
        feed_queries.get("premium_stream", {}).get("matchedPostIds") or []
    ) & release_post_ids
    video_ids = {
        str(row.get("postId") or "")
        for row in bindings
        if row.get("contentType") == "video"
    }
    verified_playable_video_ids = {
        str(row.get("postId") or "")
        for row in post_verification.get("posts") or []
        if isinstance(row, Mapping)
        and row.get("contentType") == "video"
        and row.get("detailStatus") == 200
        and row.get("mediaReady") is True
        and int(row.get("mediaProbeCount") or 0) >= 2
    }
    verified_avatar_asset_ids = {
        str(row.get("avatarAssetId") or "")
        for row in post_verification.get("creators") or []
        if isinstance(row, Mapping)
        and row.get("creatorRef") in desired_refs["creators"]
        and row.get("profileStatus") == 200
        and row.get("avatarMediaReady") is True
        and row.get("avatarProbeCount") == 1
    }
    verified_image_asset_ids = {
        str(probe.get("assetId") or "")
        for row in post_verification.get("posts") or []
        if isinstance(row, Mapping)
        for probe in row.get("mediaProbes") or []
        if isinstance(probe, Mapping)
        and probe.get("kind") == "image"
        and probe.get("status") == 200
        and str(probe.get("mimeType") or "").startswith("image/")
        and probe.get("hashVerified") is True
        and probe.get("sha256") == probe.get("expectedSha256")
        and probe.get("bytes") == probe.get("expectedBytes")
    }
    expected_counts = {
        "entities": len(desired_refs["entities"]),
        "posts": len(expected_ids),
        "creators": len(desired_refs["creators"]),
        "avatarAssets": len(verified_avatar_asset_ids),
        "imageAssets": len(verified_image_asset_ids),
        "tags": len(desired_refs["tags"]),
        "mediaAssets": len(media_asset_ids),
        "discoveryPosts": len(discovery_ids),
        "premiumPlayableVideos": len(
            premium_ids & video_ids & verified_playable_video_ids
        ),
    }
    if readiness.get("counts") != expected_counts:
        issues.append(f"{path}: counts drift from bound evidence")

    if readiness.get("readinessPhase") == "commercial":
        try:
            expected_app_uat_envelope = build_app_uat_envelope(
                release_root=release,
                release_id=release_id,
                entity_refs=desired_refs["entities"],
                post_refs=desired_refs["posts"],
                creator_ids=desired_refs["creators"],
                tag_refs=desired_refs["tags"],
                bindings=list(bindings),
                homepage_report=homepage_verification,
                queries_by_name=feed_queries,
                verified_playable_video_ids=verified_playable_video_ids,
            )
        except AppUatEnvelopeError as exc:
            issues.append(f"{path}: cannot project appUatEnvelope: {exc}")
        else:
            if readiness.get("appUatEnvelope") != expected_app_uat_envelope:
                issues.append(
                    f"{path}: appUatEnvelope drifts from immutable release closure"
                )

    unsigned = dict(readiness)
    declared_checksum = str(unsigned.pop("verificationChecksum", ""))
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_checksum = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    if declared_checksum != actual_checksum:
        issues.append(f"{path}: verificationChecksum drift")
    return issues


__all__ = ["environment_release_readiness_issues"]
